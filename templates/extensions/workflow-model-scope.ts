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
const ALLOWED_PREFIXES = (
	process.env.PI_ELM_ALLOWED_PROVIDERS ?? process.env.ELM_ALLOWED_PROVIDERS ?? "elm,elm-shim"
)
	.split(/[\s,]+/)
	.map((provider) => `${provider.trim().toLowerCase()}/`)
	.filter((provider) => provider !== "/");

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

/**
 * The two model ids this gateway actually serves, rendered in by
 * scripts/elm_config.py and overridable by the same environment variables
 * elm-shim.ts reads.
 *
 * The prefix check alone was not enough, and a real run proved it: a workflow
 * script asked five agents for `elm/qwen-3.5-397b`, an invented id that passed
 * because the provider was `elm`. pi forwarded it and the gateway answered
 * `404 model_not_found`, which reads as an elm-pi fault and is nothing of the
 * kind. A plausible-looking model id is exactly what a model writing a workflow
 * script produces, so the id is checked too.
 */
const ELM_MODEL_IDS = new Set(
	[
		process.env.ELM_QWEN_MODEL_ID ?? "@QWEN_MODEL@",
		process.env.ELM_LLAMA_MODEL_ID ?? "@LLAMA_MODEL@",
	].map((id) => id.trim().toLowerCase()),
);

/** Providers whose model ids this install can check. A widened allowlist (the
 * documented PI_ELM_UNLOCK escape hatch) names providers whose catalogues this
 * extension knows nothing about, so those are judged on the prefix alone. */
const CHECKED_PROVIDERS = new Set(["elm/", "elm-shim/"]);

function providerPrefix(model: string): string | undefined {
	const normalised = model.toLowerCase();
	return ALLOWED_PREFIXES.find((prefix) => normalised.startsWith(prefix));
}

/** Strip the provider and any `:thinking` suffix, leaving the gateway's own id.
 * Only the FIRST segment is the provider: ELM ids contain slashes of their own,
 * as in elm/Qwen/Qwen3.5-397B-A17B-FP8. */
function modelId(model: string, prefix: string): string {
	return model.slice(prefix.length).split(":")[0].trim().toLowerCase();
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

	const prefix = providerPrefix(model);
	if (prefix) {
		// Right provider. Now the id, for the providers whose catalogue is known.
		if (!CHECKED_PROVIDERS.has(prefix)) return { action: "unchanged" };
		if (ELM_MODEL_IDS.has(modelId(model, prefix))) return { action: "unchanged" };
		const served = [...ELM_MODEL_IDS].join(", ");
		return {
			action: "reject",
			reason:
				`"${model}" is not a model this gateway serves${ctx.label ? ` (agent "${ctx.label}")` : ""}. ` +
				`The provider is right and the model id is not; forwarding it returns ` +
				`404 model_not_found from ELM. Served ids: ${served}. ` +
				`Best practice on this install is to omit "model" entirely - ` +
				`inheritMainModel is on, so an agent without one runs on the session model.`,
		};
	}

	// A provider outside the allowlist is refused rather than quietly rewritten.
	// Rewriting would silently run the work on a model the author did not choose;
	// refusing says what happened and where to fix it.
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

export default function (_pi: ExtensionAPI) {
	(globalThis as Record<symbol, unknown>)[RESOLVER_SLOT] = (ctx: PreSpawnModelContext) =>
		decide(ctx);
}
