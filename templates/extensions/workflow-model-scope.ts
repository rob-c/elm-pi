/**
 * ELM-only model scope for @quintinshaw/pi-dynamic-workflows.
 *
 * pi-subagents enforces this declaratively - `modelScope: { enforce: true,
 * strict: true, allow: ["elm/*", "elm-shim/*", "inherit"] }` in settings.json -
 * so no child of a pi-subagents fan-out can be routed off the university's GPUs.
 * Dynamic Workflows has no config equivalent: its tiers live in a JSON file whose
 * own documented examples are `openai-codex/gpt-5.4-mini` and `openai-codex/
 * gpt-5.5`. What it does expose is one process-wide policy hook that runs after
 * it resolves model/tier/phase intent and before the session is created, and
 * which may reject the spawn outright. This is that policy.
 *
 * Registration writes the documented globalThis slot directly rather than
 * importing `setPreSpawnModelResolver`. Two reasons: the package lives in
 * agent/npm/node_modules, which is not on this file's module resolution path, and
 * writing the slot works whether or not the package is installed - with it
 * absent, nothing ever reads the slot and this extension is inert.
 *
 * Known limit, and it matters. The package documents the precedence as per-run
 * `AgentRunOptions.preSpawnModel` > instance `WorkflowAgentOptions.preSpawnModel`
 * > this process resolver. A workflow script that sets its own per-run resolver
 * therefore outranks this one. pi-subagents' `strict` scope has no such hole, so
 * this is a weaker guarantee than the one it stands in for, not an equal one.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** The slot the package reads its process-wide policy from. */
const RESOLVER_SLOT = Symbol.for("@quintinshaw/pi-dynamic-workflows.preSpawnModelResolver");

/** Providers this install is allowed to reach: ELM direct, and the tool-call shim. */
const ALLOWED_PREFIXES = ["elm/", "elm-shim/"];

type ModelSource = "explicit" | "tier" | "phase" | "default" | "session";

interface PreSpawnModelContext {
	requestedModel?: string;
	tier?: string;
	resolvedModel?: string;
	modelSource: ModelSource;
	label?: string;
}

type Decision =
	| { action: "unchanged" }
	| { action: "use"; model: string }
	| { action: "reject"; reason: string };

function isElmModel(model: string): boolean {
	return ALLOWED_PREFIXES.some((prefix) => model.startsWith(prefix));
}

export function decide(ctx: PreSpawnModelContext): Decision {
	// The concrete model, if the package has settled on one. resolvedModel is
	// what it would actually spawn; requestedModel is what was asked for.
	const model = (ctx.resolvedModel ?? ctx.requestedModel ?? "").trim();

	if (!model) {
		// "session" (and "default" with nothing resolved) means the session's own
		// model is used. That model is necessarily ELM: agent/models.json declares
		// only ELM entries and elm-only.ts strips everything else from the
		// registry, so there is nothing else for it to be.
		return { action: "unchanged" };
	}

	if (isElmModel(model)) return { action: "unchanged" };

	// Anything else is refused rather than quietly rewritten. Rewriting would
	// silently run the work on a model the author did not choose; refusing says
	// what happened and where to fix it.
	const where =
		ctx.modelSource === "tier"
			? `the "${ctx.tier ?? "?"}" tier in ~/.pi/workflows/model-tiers.json`
			: ctx.modelSource === "phase"
				? "a workflow phase or meta model"
				: ctx.modelSource === "explicit"
					? "an explicit model on the script or agent type"
					: `implicit routing (${ctx.modelSource})`;

	return {
		action: "reject",
		reason:
			`This install is restricted to university-hosted models. ` +
			`"${model}" came from ${where}${ctx.label ? ` for agent "${ctx.label}"` : ""}. ` +
			`Use a model under elm/ or elm-shim/ - see /workflows-models.`,
	};
}

export default function (pi: ExtensionAPI) {
	(globalThis as Record<symbol, unknown>)[RESOLVER_SLOT] = (ctx: PreSpawnModelContext) =>
		decide(ctx);

	// Say so once, so a session that has this policy in force is distinguishable
	// from one where the slot was overwritten by something loaded later.
	pi.on("session_start", async (_event, ctx: any) => {
		ctx.ui?.notify?.("workflow model scope: elm/ and elm-shim/ only", "info");
	});
}
