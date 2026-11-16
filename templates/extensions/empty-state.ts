/**
 * empty-state: on a new session, three lines saying what exists.
 *
 * Why: a first session showed a prompt and nothing else. `/help` and the prompt templates were there
 * and nothing on screen said so; the plan's item 2 (deepseek_suggestions.md) is this screen. It names
 * only what this install really has - the templates are read from `agent/prompts`, so a template this
 * repo drops stops being named.
 *
 * How: at session_start, only with a screen (a `pi -p` run has none) and only on a session that is
 * starting rather than being resumed, forked or reloaded, where the user has already been here.
 */
import { readdirSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function agentDir(): string {
	return process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent");
}

/** The prompt templates this install has, by name, from the directory pi reads them from. */
export function templates(dir = agentDir()): string[] {
	try {
		return readdirSync(join(dir, "prompts"))
			.filter((name) => name.endsWith(".md"))
			.map((name) => name.slice(0, -3))
			.sort();
	} catch {
		return [];
	}
}

export function firstSession(dir = agentDir()): string {
	const names = templates(dir);
	const install = dirname(dir);
	const commands = names.length ? `; ${names.map((name) => `\`/${name}\``).join(", ")} are prompt templates` : "";
	return [
		`pi here. \`/help\` lists this session's commands and tools${commands}.`,
		"A question is a request to do the work: ask for what you want, in your own words.",
		`Every part and setting is in ${join(install, "INSTALL.md")}; ${join(dir, "reference")} has how to ask, report and plot.`,
	].join("\n");
}

/** A session that is starting: not resumed, not forked, not reloaded in place. */
export function isNew(reason: string | null | undefined): boolean {
	return reason === undefined || reason === null || reason === "" || reason === "new" || reason === "startup";
}

export default function (pi: ExtensionAPI) {
	pi.on("session_start", async (event, ctx) => {
		if (!ctx.hasUI) return;
		if (!isNew((event as { reason?: string }).reason)) return;
		// CLI --continue/--resume emit "startup" too (2026-11-15 UI replay); their branch is not empty.
		if (ctx.sessionManager.getBranch().some((entry) => entry.type === "message")) return;
		ctx.ui.notify(firstSession(), "info");
	});
}
