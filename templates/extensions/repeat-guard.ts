/**
 * Repeat guard: the same tool call failing the same way, turn after turn.
 *
 * test4 (2026-11-12): two qwen sub-agents finished the file they were given and
 * then took the parent's workflow launch, in the conversation they had inherited,
 * for their own. They called `subagent({ action: "status", id })` - a tool
 * children do not have - 394 and 705 times, every one answered "Tool subagent
 * not found", until pi-subagents' 30-minute timeout. That was about 75 million
 * input tokens, most of the session's use, and it set off the 429s the parent
 * hit too. pi-subagents already tells every child to treat the inherited
 * conversation as reference only, and the model did it anyway; so the harness
 * catches it:
 *
 *   a turn whose tool calls all failed, with the same calls and the same errors
 *   as the turn before, counts one more. At WARN_AT in a row the model is told,
 *   once; at STOP_AT the run is stopped, so a sub-agent ends and its parent gets
 *   its report instead of a timeout.
 *
 * A turn with any success, or a different call or error, starts the count again:
 * a test that keeps failing while the code changes between runs is not a repeat,
 * since the edits in between succeed. Calls to a tool the session does not have
 * are counted apart, by the tool's name, for the whole run: in test5 a child
 * alternated `subagent({ action: "status" })` with `subagent({ action:
 * "children.list" })`, which reset the count of identical turns, and was warned
 * only at its eighth call. No call to a missing tool can ever succeed. A turn that ended on a gateway error (a
 * 429 the retries could not clear) made no call and changes nothing: the loop
 * above had 69 of them mixed in.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const WARN_AT = 3;
export const STOP_AT = 8;

/**
 * A sub-agent's turns, over its whole session. A child is one bounded piece of work: in two batches of
 * driven sessions (2026-11-14) the children that wrote a page took 3 to 32 turns. Two did not stop -
 * one asked for a stylesheet went on to edit all eight pages, one was given "fix ALL pages" - and took
 * 140 and 98 turns of small edits, each resending a context of about 90k tokens: 12.8M and 8.5M input
 * tokens, 21M of the session's 26M (batch 2, salmon-8). Nothing failed, so nothing above caught it.
 * Told once at TURNS_WARN to finish and report what is left; stopped at TURNS_STOP, so the parent gets
 * a report it can split into smaller tasks. The top session is the user's and has no such limit.
 */
export const TURNS_WARN = 30;
export const TURNS_STOP = 60;

export function turnsWarning(turns: number): string {
	return (
		`This sub-agent has taken ${turns} turns, more than a task of its size needs, and each one resends the whole ` +
		`conversation. Finish the step in hand now and give your final report: what is done, and under LEFT what is ` +
		`not - the session that launched you can hand the rest out as smaller tasks. At ${TURNS_STOP} turns the run is stopped.`
	);
}

export function turnsStop(turns: number): string {
	return (
		`elm-pi stopped this sub-agent after ${turns} turns. What it changed is on disk and nothing was undone; ` +
		"what its task still needed is not done. Check the files, and hand what is left out as smaller tasks."
	);
}

type Part = { type?: string; text?: string; name?: string; arguments?: unknown };
type Message = { role?: string; content?: unknown; toolName?: string; isError?: boolean; stopReason?: string };

function parts(message: Message | undefined): Part[] {
	return message && Array.isArray(message.content) ? (message.content as Part[]) : [];
}

function text(message: Message): string {
	return parts(message)
		.map((part) => (part.type === "text" ? part.text ?? "" : ""))
		.join("\n")
		.trim();
}

export interface FailedTurn {
	/** The calls and their errors: equal keys are the same failing turn. */
	key: string;
	tool: string;
	error: string;
}

/** What a turn did, when it made tool calls and every one of them failed; otherwise undefined. */
export function failedTurn(assistant: Message | undefined, results: readonly Message[]): FailedTurn | undefined {
	const calls = parts(assistant).filter((part) => part.type === "toolCall");
	if (calls.length === 0 || results.length === 0 || !results.every((result) => result.isError)) return undefined;
	const errors = results.map((result) => text(result).slice(0, 300));
	return {
		key: JSON.stringify([calls.map((call) => [call.name, call.arguments ?? null]), errors]),
		tool: String(calls[0].name ?? results[0].toolName ?? "a tool"),
		error: errors[0].split("\n")[0].slice(0, 200),
	};
}

const MISSING = /^Tool (\S+) not found$/;

/** The tool a turn called that the session does not have, if any. */
export function absentTool(results: readonly Message[]): string | undefined {
	for (const result of results) {
		const match = result.isError ? MISSING.exec(text(result)) : null;
		if (match) return match[1];
	}
	return undefined;
}

/** For a tool the session does not have, what the call usually is: something inherited. */
function missingTool(error: string): string {
	return MISSING.test(error)
		? " That tool is not in this session. A run id, launch, wait or status call earlier in the conversation" +
				" belongs to whoever made it, not to you."
		: "";
}

export function warning(turn: FailedTurn, count: number): string {
	return (
		`The same \`${turn.tool}\` call has now failed ${count} times in a row, with the same result: ${turn.error}.` +
		`${missingTool(turn.error)} Repeating it will not change that. Do something different, or, if your task is` +
		" done, stop and give your final report now."
	);
}

export function stopNote(turn: FailedTurn, count: number): string {
	return (
		`elm-pi stopped this run: the same \`${turn.tool}\` call failed ${count} times in a row (${turn.error}).` +
		" Nothing else was undone; a new message continues the session."
	);
}

function warnOrStop(turn: FailedTurn, count: number, ctx: { abort(): void; hasUI?: boolean }) {
	if (count >= STOP_AT) {
		const note = stopNote(turn, count);
		// Without a UI (pi -p, and every sub-agent) the entry is never drawn, and all that
		// shows is pi's "This operation was aborted": say why where it will be read.
		if (!ctx.hasUI) process.stderr.write(`${note}\n`);
		ctx.abort();
		return { entries: [{ type: "custom_message" as const, customType: "repeat-guard", content: note, display: true }] };
	}
	if (count === WARN_AT) {
		return { entries: [{ type: "custom_message" as const, customType: "repeat-guard", content: warning(turn, count), display: true }] };
	}
	return undefined;
}

export default function (pi: ExtensionAPI) {
	let last = "";
	let count = 0;
	/** Calls this run to each tool the session does not have. */
	let missing = new Map<string, number>();

	pi.on("agent_start", async () => {
		last = "";
		count = 0;
		missing = new Map();
	});

	// Never reset: a retry or a note starts a new run, and the budget is the session's.
	let turns = 0;
	const child = process.env.PI_SUBAGENT_CHILD === "1";

	pi.on("turn_end", async (event, ctx) => {
		const assistant = event.message as Message;
		if (assistant?.stopReason === "error") return undefined;
		const results = event.toolResults as unknown as Message[];
		if (child && results.length > 0) {
			turns += 1;
			if (turns >= TURNS_STOP) {
				const note = turnsStop(turns);
				if (!ctx.hasUI) process.stderr.write(`${note}\n`);
				ctx.abort();
				return { entries: [{ type: "custom_message" as const, customType: "repeat-guard", content: note, display: true }] };
			}
			if (turns === TURNS_WARN) {
				return { entries: [{ type: "custom_message" as const, customType: "repeat-guard", content: turnsWarning(turns), display: true }] };
			}
		}
		const absent = absentTool(results);
		if (absent) {
			const calls = (missing.get(absent) ?? 0) + 1;
			missing.set(absent, calls);
			last = "";
			count = 0;
			return warnOrStop({ key: `missing:${absent}`, tool: absent, error: `Tool ${absent} not found` }, calls, ctx);
		}
		const turn = failedTurn(assistant, results);
		if (!turn) {
			last = "";
			count = 0;
			return undefined;
		}
		count = turn.key === last ? count + 1 : 1;
		last = turn.key;
		return warnOrStop(turn, count, ctx);
	});
}
