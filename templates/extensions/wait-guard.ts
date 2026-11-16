/**
 * Wait guard: no `bg_wait` in an interactive session.
 *
 * A sub-agent run started from an interactive session wakes it when it ends: each
 * child's notice and the run's final one arrive as messages and start a turn. So
 * pi-subagents' own launch result says "Detached. Return control now: native
 * completion wakes you, so do not sleep, poll, or call bg_wait for it", and
 * AGENTS.md says to end the turn. The model waited anyway: in test4 four
 * 10-minute `bg_wait` windows held the user's session until they pressed
 * Escape; in test5 (2026-11-12), after both rules were in place, one held it
 * for 6.5 minutes. So the harness answers the call instead of the prompt.
 *
 * Its message once opened "Not in an interactive session", which is false every
 * time it fires; in test6 the parent called bg_wait three more times, then read
 * and edited a running child's page. It now says what the call is not for.
 *
 * Refused once, the model found other ways to wait: in test9 (2026-11-12) it called
 * a `pi_subagents_notice` tool that does not exist (pi-subagents wraps its notices
 * in a tag of that name) twice, asked `subagent` for the run's status twice, ran
 * `sleep 5` and `sleep 10`, and read the run's log under async-subagent-runs. So
 * for the rest of that turn those are refused too, with the same answer: a bash
 * command that only sleeps (and echoes), a `subagent` status check, and a command
 * that reads a run's files under async-subagent-runs. The next turn starts clean.
 *
 * Only with a UI. `pi -p` has nobody to wake it and needs the result in the same
 * reply, where pi-subagents' own advice is `bg_wait`; a sub-agent has no UI
 * either, and waits on its own descendants if it has any.
 *
 * Refused, it was still called: four `bg_wait`s and a status check in one turn of a
 * driven session (auto01, 2026-11-13). So the launcher no longer offers `bg_wait` to
 * an interactive session at all, and this guard is what is left: the launch result's
 * one status check is allowed, and after it a second check, a sleep or a read of the run's files
 * in the same turn is the refused wait. A successful async launch arms sleep detection too:
 * checking the wrong status tool must not be a way around the instruction to end the turn.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const REASON =
	"bg_wait is not used in an interactive session like this one: the run wakes this session when it ends, and each " +
	"child's notice arrives as a message. End your turn now with one line saying what is running - no status " +
	"checks, no reading or changing its files meanwhile - and read the results when the notices come. A child's " +
	"files are its own until its notice arrives; the run's last is \"Background task completed\".";

export const AGAIN =
	"Still waiting is still not needed: nothing to call, check or sleep on - the notices arrive by themselves and " +
	"start your next turn. End your turn now with one line saying what is running.";

/**
 * Waits refused in one turn before a refused wait is made to take time. From here each one is held,
 * in the handler, until a sub-agent's notice is waiting or HOLD_MS has passed: the wait the model was
 * asking for, without a model request to pay for it.
 *
 * This replaces ending the turn with ctx.abort(), which did stop the polling (auto11, 2026-11-13: eight
 * refused waits in 45 s, each a turn of ~50k tokens) and also stopped the session for good: pi-subagents
 * takes any abort for the user pressing Esc, holds its wake-ups from then on, and words the completion
 * notice "The user stopped the parent turn ... do not resume". In three driven sessions of three where
 * the abort fired (highland-cows-6 in batch 1; deer-10 and salmon-8 in batch 3, 2026-11-14) the children
 * finished, the notices were appended, and no turn ever started: ten pages with ten footers, never
 * looked at.
 */
export const ENOUGH = 3;
/** The same bash command this many times running is a wait. */
export const SAME_AGAIN = 3;
export const HOLD_MS = 120_000;
const HOLD_STEP_MS = 500;
export const HELD_NOTICE =
	"A sub-agent's notice has arrived: it is in this turn's next messages. Read it; do not check status or wait again.";
export const HELD_QUIET =
	"Two minutes on and no notice yet: the run is still working, and nothing was lost by waiting here. End your " +
	"turn now with one line saying what is running - its notices start your next turn.";

let holdMs = HOLD_MS;
/** For tests: a shorter hold. */
export function setHoldMs(ms: number): void {
	holdMs = ms;
}

/** Resolves true as soon as `arrived()` is, false after `ms`. */
export async function hold(arrived: () => boolean, ms = HOLD_MS, step = HOLD_STEP_MS, signal?: AbortSignal): Promise<boolean> {
	const end = Date.now() + ms;
	while (Date.now() < end) {
		if (arrived()) return true;
		if (signal?.aborted) return false;
		await new Promise<void>((resolve) => setTimeout(resolve, Math.min(step, Math.max(0, end - Date.now()))));
	}
	return arrived();
}

/** A bash command that does nothing but wait: `sleep 10`, `sleep 5 && echo "Checking..."`. */
export const ONLY_SLEEP = /^\s*(?:(?:sleep\s+[\d.]+[smh]?|echo(?:\s+(?:"[^"]*"|'[^']*'|[^;&|]*))?|true|:)\s*(?:&&|;|$)\s*)+$/;
/** A command that starts by sleeping five seconds or more: a poll (auto03: `sleep 30 && ls site/*.html`). */
export const LONG_SLEEP_FIRST = /^\s*sleep\s+(?:[5-9]|\d{2,})(?:\.\d+)?s?\b/;
/** A command that reads a running sub-agent run's own files. */
export const RUN_FILES = /async-subagent-runs\//;

/** Whether a call is one more way of waiting for a run. */
export function waiting(toolName: string, input: Record<string, unknown>): boolean {
	if (toolName === "bg_wait") return true;
	if (toolName === "subagent") return input.action === "status";
	if (toolName === "bash" && typeof input.command === "string")
		return (
			(ONLY_SLEEP.test(input.command) && /\bsleep\b/.test(input.command)) ||
			LONG_SLEEP_FIRST.test(input.command) ||
			RUN_FILES.test(input.command)
		);
	return false;
}

/** Tools that only mean something inside a sub-agent. */
export const CHILD_ONLY = ["contact_supervisor"];

export default function (pi: ExtensionAPI) {
	// contact_supervisor is a sub-agent's line to the session that launched it. pi-subagents offers it to
	// the top session too, which has no supervisor: in two of four driven sessions (batch 1, 2026-11-14)
	// the model called it to "report progress" and got an error back. Taken out before the first
	// request, so the tool list the gateway caches does not change mid-session.
	let trimmed = false;
	pi.on("before_agent_start", async () => {
		if (trimmed || process.env.PI_SUBAGENT_CHILD === "1") return undefined;
		trimmed = true;
		const active = pi.getActiveTools?.() ?? [];
		if (active.some((name) => CHILD_ONLY.includes(name))) pi.setActiveTools(active.filter((name) => !CHILD_ONLY.includes(name)));
		return undefined;
	});

	let lastCall = ""; // the previous tool call of this session, whatever it was
	let same = 0; // how many times in a row it has been made
	let told = false; // this turn, a wait has been refused once already
	let checked = false; // this turn, the one status check has been made
	let detached = false; // this turn, an async subagent launch succeeded
	let refused = 0; // waits refused this turn
	pi.on("agent_start", () => {
		told = false;
		checked = false;
		detached = false;
		refused = 0;
	});
	pi.on("tool_result", (event, ctx) => {
		if (!ctx.hasUI || event.toolName !== "subagent" || event.isError) return;
		// python-before parallel.1 (2026-11-15) used the wrong status tools, then polled and changed
		// running children's files. A successful async launch itself is enough to make sleeping a wait.
		if (event.content.some((part) => part.type === "text" && /^Async\b[^\n[]*\[[0-9a-f-]{36}\]/im.test(part.text))) detached = true;
	});
	pi.on("tool_call", async (event, ctx) => {
		if (!ctx.hasUI) return undefined;
		const input = (event.input ?? {}) as Record<string, unknown>;
		const refuse = async () => {
			const again = told;
			told = true;
			// Told twice, a third wait is held (see ENOUGH): never ctx.abort().
			if (++refused >= ENOUGH) {
				const arrived = await hold(() => ctx.hasPendingMessages?.() === true, holdMs, HOLD_STEP_MS, (ctx as { signal?: AbortSignal }).signal);
				return { block: true, reason: arrived ? HELD_NOTICE : HELD_QUIET };
			}
			return { block: true, reason: again ? AGAIN : REASON };
		};
		// The same shell command, call after call with nothing else between: polling by another name. batch 4,
		// gannets-manual (2026-11-14) ran `ls -lh .../*.html` 91 times while its children wrote the pages, up to
		// 28 in a row - 195 turns and 8M tokens in the parent, and in manual mode an ask for each. Counted over
		// the session, not the turn: a child's notice or a retry starts a new run and the listing goes on.
		const signature = `${event.toolName} ${JSON.stringify(input)}`.replace(/\s+/g, " ");
		same = signature === lastCall ? same + 1 : 1;
		lastCall = signature;
		if (event.toolName === "bash" && same >= SAME_AGAIN) return refuse();
		if (event.toolName === "bg_wait") return refuse();
		if (event.toolName === "subagent" && input.action === "status") {
			if (told || checked) return refuse();
			checked = true;
			return undefined;
		}
		// A running run's own files are never this session's to read: auto02 (2026-11-13, manual) read its
		// child's output-0.log again and again, and each read asked the user to allow it.
		if (event.toolName === "bash" && typeof input.command === "string" && RUN_FILES.test(input.command)) return refuse();
		// After the one check, any other wait is the refused one: auto02 (2026-11-13, manual) followed its
		// status check with `sleep 10 && cat .../async-subagent-runs/<id>/output-0.log`, which the user was
		// then asked to allow.
		if ((told || checked || detached) && waiting(event.toolName, input)) return refuse();
		return undefined;
	});
}
