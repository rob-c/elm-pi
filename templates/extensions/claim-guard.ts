/**
 * Claim guard: a reply that says work was done, from a run that did none.
 *
 * Mistral Small 4, asked to "add a function to src/stats.py ... reply with one
 * line saying what you did", replied that it had added it - with no tool call at
 * all - in 12 runs out of 12, and a written rule against exactly that ("never say
 * you changed something unless a tool call did it") changed nothing. Llama did the
 * same in other tasks; Qwen never did in 51 runs. Others report it on Mistral's
 * own API ("Task completed" and nothing done), and that asking again unsticks it.
 * So it is asked again, by the harness rather than the prompt:
 *
 *   a run with no tool call at all, whose final reply says something was added,
 *   changed, fixed or run, gets one note back and one more turn.
 *
 * With it, that task passed 2 runs out of 2 (INSTALL.md, "Mistral Small 4").
 *
 * Narrow on purpose. Only the models that were seen doing it: Mistral and Llama
 * anywhere, and Qwen as a sub-agent. Qwen never did it in 51 top-level runs, but
 * in test5 (2026-11-12) a qwen child given "Create the main index.html page"
 * made no tool call and reported "CHANGED - index.html: Created new file". A
 * sub-agent is a session without the `subagent` tool (pi-subagents takes it
 * away; PI_ELM_CHILD cannot tell, the launcher exports it for every pi), and
 * there a claim with no call is never a summary of earlier work: a child starts
 * from its task. Only a run with no tool call: a run that edited something
 * and then overstated it is the reviewer's to catch, not a regex's. Once per
 * run, so it cannot loop, and the note says what to do if the reply was only
 * describing earlier work - the one way a claim without a tool call is honest.
 *
 * The note goes in at agent_before_settle, the last point before pi settles the
 * run; a custom message there reaches the model as a user message and lets pi
 * make one more request. That event's own `canContinue` is not consulted: it
 * describes the run before the note is added, when the last message is the
 * reply, and is false for every run that ends in one.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** The models this applies to, rendered in by scripts/elm_config.py. */
const GUARDED = new Set(
	[process.env.ELM_MISTRAL_MODEL_ID ?? "@MISTRAL_MODEL@", process.env.ELM_LLAMA_MODEL_ID ?? "@LLAMA_MODEL@"]
		.map((id) => id.trim().toLowerCase())
		.filter((id) => id !== "" && !id.startsWith("@")),
);

/** Words of a reply that says work was done. "Completed" is the reported form
 * ("Task completed" and nothing done); "done" is not here, being as common in an
 * honest answer ("this can be done with grep") as in a false one. */
export const CLAIM =
	/\b(added|adds|created|creates|wrote|written|fixed|updated|changed|renamed|implemented|edited|modified|saved|removed|deleted|moved|ran|installed|refactored|replaced|inserted|annotated|completed?)\b/i;

export const NOTE =
	"Your reply reports something changed, run or returned, but this run made no tool call, so nothing was changed or run and no tool returned anything. " +
	"Do the work now with tool calls, check the result, then reply. If you were only describing earlier work, say that in one line.";

/** Qwen, guarded only where it is a sub-agent. */
const CHILD_GUARDED = new Set(
	[process.env.ELM_QWEN_MODEL_ID ?? "@QWEN_MODEL@"].map((id) => id.trim().toLowerCase()).filter((id) => id !== "" && !id.startsWith("@")),
);

/**
 * A task that tells the agent to use a tool or run a command. A workflow agent told "Use the bash
 * tool to run: python3 -m http.server ... & sleep 1; echo started. Reply with exactly what the tool
 * returned" replied "started" with no tool call; another, given six such steps, wrote six results
 * ("File written: .env") for calls it never made - twice (live probes, 2026-11-13). Neither reply
 * has a claim word in it: the made-up result is the claim.
 */
export const TOOL_ASKED =
	/\b(?:use|call|with)\s+(?:the\s+)?(?:`?[\w-]+`?\s+)?tool\b|\b(?:bash|run|execute)\s*:|\b(?:run|execute)\s+(?:the\s+)?(?:command|script)\b/i;

/**
 * Whether this run, from a guarded model, ends with a reply no tool call backs: one that claims
 * work, or - in a sub-agent - any reply to a task that said to use a tool or run a command.
 */
export function needsNote(modelId: string | undefined, toolCalls: number, finalText: string, child = false, task = ""): boolean {
	if (toolCalls > 0 || !modelId) return false;
	const id = modelId.trim().toLowerCase();
	if (!GUARDED.has(id) && !(child && CHILD_GUARDED.has(id))) return false;
	return CLAIM.test(finalText) || (child && TOOL_ASKED.test(task));
}

function userText(message: { role: string; content?: unknown } | undefined): string {
	if (!message) return "";
	if (typeof message.content === "string") return message.content;
	if (!Array.isArray(message.content)) return "";
	return message.content.map((part: { type?: string; text?: string }) => (part.type === "text" ? part.text ?? "" : "")).join("\n");
}

function replyText(message: { role: string; content?: unknown } | undefined): string {
	if (!message || message.role !== "assistant" || !Array.isArray(message.content)) return "";
	return message.content.map((part: { type?: string; text?: string }) => (part.type === "text" ? part.text ?? "" : "")).join("\n");
}

export default function (pi: ExtensionAPI) {
	// Calls that worked. A refused or failed call changes nothing: test13 (2026-11-13), a workflow agent
	// in a manual session had every write refused and still reported "The stylesheet file has been
	// created". So a run counts as having made no call when none of its calls succeeded.
	let calls = 0;
	let noted = false;

	pi.on("agent_start", async () => {
		calls = 0;
		noted = false;
	});
	pi.on("tool_result", async (event) => {
		if (!event.isError) calls += 1;
		return undefined;
	});
	pi.on("agent_before_settle", async (event, ctx) => {
		if (noted) return undefined;
		const messages = [...event.context.contextMessages].reverse();
		const last = messages.find((m) => m.role === "assistant");
		const task = messages.find((m) => m.role === "user") as { role: string; content?: unknown } | undefined;
		const child = !(pi.getActiveTools?.() ?? []).includes("subagent");
		if (!needsNote(ctx.model?.id, calls, replyText(last), child, userText(task))) return undefined;
		noted = true;
		return { entries: [{ type: "custom_message", customType: "claim-guard", content: NOTE, display: true }], continue: true };
	});
}
