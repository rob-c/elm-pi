/**
 * verify-guard: a turn that wrote code and ran nothing.
 *
 * Why: the 200-problem batch of 2026-11-14 (ten sessions of twenty stock coding problems each, one
 * file per problem, prompts rotated) - two of the ten sessions wrote all twenty files and executed
 * none of them, replying "Done." after each; the other eight ran one `python3 -c` check per file.
 * Nothing failed, which is why it is worth fixing: the code was right and the hidden check passed
 * either way (c20.6: 20 writes and 0 commands in 41 requests; c20.7: 20 writes and 0 commands in 40,
 * against the other sessions' 60-63). The install tells a session to run the cheapest convincing
 * check before it reports (`AGENTS.md`, "Checking and finishing"), and claim-guard does not catch
 * this: its condition is a run with no tool call at all, and these runs wrote files.
 *
 * So the harness asks, once: a run that wrote a code file and executed nothing gets one note back
 * and one more turn. The same habit on a task the model is less sure of is work reported and never
 * run, and there is no other moment at which that is visible.
 *
 * Narrow on purpose. Only files that could be executed count, by extension: writing a README, a
 * config or a .csv is not this. Any executing call in the run - `bash`, a python tool, a notebook
 * run, a sub-agent or workflow launch whose child may run it - suppresses the note whether it
 * succeeded or failed, since a failed command is a run that tried and the reply then has something
 * true to report. A write that failed or was refused does not count as written. Twice per session at
 * most, so it cannot loop; and the note says what to do when there was nothing to run.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Files whose contents can be executed, by extension. `write` of anything else is not this guard's. */
export const CODE = /\.(?:py|pyi|ts|tsx|js|jsx|mjs|cjs|sh|bash|c|h|cc|cpp|cxx|hpp|rs|go|r|jl|f|f90|f95|java|kt|rb|pl|php|lua)$/i;

/** The tools that write one of them: this install's anchor editor is replace/replace_match/insert. */
export const WRITERS = new Set(["write", "edit", "replace", "replace_match", "insert"]);

/** Tools that run something the turn wrote - or launch a child that may. */
export function executes(tool: string): boolean {
	return /^(?:bash|powershell|python)$/i.test(tool) || /(?:^|_)run(?:_|$)/i.test(tool) || tool === "subagent" || tool === "workflow";
}

/** The most notes one session is sent, whatever its runs do. */
export const MAX_NOTES = 2;

export function note(files: number): string {
	const noun = files === 1 ? "file" : "files";
	return (
		`This turn wrote ${files} code ${noun} and ran nothing, so nothing here is known to work. ` +
		"Run the cheapest convincing check now - the examples in the request, a test, the script itself - and report " +
		"what it printed, or say in one line that there was nothing you could run."
	);
}

type Call = { toolName?: string; input?: { path?: string } };
type Result = { toolName?: string; isError?: boolean };

export default function (pi: ExtensionAPI) {
	// Per run: reset at agent_start. `wrote` counts code writes attempted now, `written` those that
	// succeeded, `ran` anything executed or launched.
	let wrote = 0;
	let written = 0;
	let ran = false;
	let noted = false;
	let notes = 0;

	pi.on("agent_start", async () => {
		wrote = 0;
		written = 0;
		ran = false;
		noted = false;
	});
	pi.on("tool_call", async (event) => {
		const call = event as Call;
		const tool = call.toolName ?? "";
		if (executes(tool)) ran = true;
		const path = call.input?.path;
		if (typeof path === "string" && WRITERS.has(tool) && CODE.test(path)) wrote += 1;
		return undefined;
	});
	pi.on("tool_result", async (event) => {
		const result = event as Result;
		const tool = result.toolName ?? "";
		if (executes(tool)) ran = true;
		if (!result.isError && WRITERS.has(tool)) written += 1;
		return undefined;
	});
	pi.on("agent_before_settle", async () => {
		if (noted || notes >= MAX_NOTES) return undefined;
		if (ran || wrote === 0 || written === 0) return undefined;
		noted = true;
		notes += 1;
		return {
			entries: [{ type: "custom_message", customType: "verify-guard", content: note(wrote), display: true }],
			continue: true,
		};
	});
}
