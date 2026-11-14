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
 * in the same turn is the refused wait.
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

/** Waits refused in one turn before the turn is ended for it. */
export const ENOUGH = 3;
export const ENDED =
	"elm-pi ended this turn: it kept waiting for sub-agents that report by themselves. Their notices start the next one.";

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

export default function (pi: ExtensionAPI) {
	let told = false; // this turn, a wait has been refused once already
	let checked = false; // this turn, the one status check has been made
	let refused = 0; // waits refused this turn
	pi.on("agent_start", () => {
		told = false;
		checked = false;
		refused = 0;
	});
	pi.on("tool_call", async (event, ctx) => {
		if (!ctx.hasUI) return undefined;
		const input = (event.input ?? {}) as Record<string, unknown>;
		const refuse = () => {
			const again = told;
			told = true;
			// Told twice, a third wait ends the turn: auto11 (2026-11-13) was refused eight times in 45 s - sleeps,
			// status checks, sleep-then-ls - each a turn of ~50k tokens. The runs are detached processes and keep
			// going; their notices start the next turn, as they would have.
			if (++refused >= ENOUGH) {
				ctx.ui?.notify?.(ENDED, "info");
				(ctx as { abort?: () => void }).abort?.();
			}
			return { block: true, reason: again ? AGAIN : REASON };
		};
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
		if ((told || checked) && waiting(event.toolName, input)) return refuse();
		return undefined;
	});
}
