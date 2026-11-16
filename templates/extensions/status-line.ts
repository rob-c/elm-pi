/**
 * status-line: what this session is actually on, in the footer.
 *
 * Why: `pi --remote` changes what a whole session can do, and a non-default model changes what it is
 * good at, and after launch neither shows anywhere (the plan's items 5 and 20, one item). A session
 * that cannot say "this one can reach the web" is how a 403 gets explained away as a broken gateway.
 *
 * How: on session start and on each turn, one footer line - the model when it is not the install's
 * default, and whether the web is open - and nothing at all when the session is the ordinary case,
 * so the footer stays empty for most sessions. It reads the default from `agent/settings.json` and
 * the web from the tools actually offered (`web_search` present is what `--remote` buys), not from an
 * environment variable that may be set by a wrapper.
 */
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function agentDir(): string {
	return process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent");
}

/** The install's own default model id, or "" when the file cannot be read. */
export function defaultModel(dir = agentDir()): string {
	try {
		const settings = JSON.parse(readFileSync(join(dir, "settings.json"), "utf8")) as { defaultModel?: string };
		return settings.defaultModel ?? "";
	} catch {
		return "";
	}
}

/**
 * The footer line, or "" when there is nothing worth saying. `name` is the model's display name when
 * the harness has one, so a reader sees "Qwen 3.5 397B" rather than a repository path.
 */
export function label(model: string, name: string, def: string, web: boolean): string {
	const parts: string[] = [];
	if (model !== "" && model !== def) parts.push(name || model);
	if (web) parts.push("web");
	return parts.join(" · ");
}

export default function (pi: ExtensionAPI) {
	const paint = (ctx: { model?: { id?: string; name?: string }; ui: { setStatus: (key: string, text: string) => void } }) => {
		const tools = (pi.getActiveTools?.() ?? []) as string[];
		const web = tools.includes("web_search");
		const text = label(ctx.model?.id ?? "", ctx.model?.name ?? "", defaultModel(), web);
		ctx.ui.setStatus("elm-pi", text);
	};
	pi.on("session_start", async (_event, ctx) => paint(ctx));
	pi.on("agent_start", async (_event, ctx) => paint(ctx));
	// A /model selection changes the session before its next turn (2026-11-15 UI replay).
	pi.on("model_select", async (_event, ctx) => paint(ctx));
}
