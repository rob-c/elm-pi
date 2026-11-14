/**
 * Ultracode note: `/ultracode` in a session that has no `workflow` tool.
 *
 * pi-dynamic-workflows' `/ultracode` and `/effort` append about 1,600 characters
 * to every message of 16 characters or more typed after them - "[workflows mode
 * armed ... handle it by calling the `workflow` tool: write a script that fans
 * the task out ... via agent()/parallel()/pipeline()" and "Effort: ULTRA ..." -
 * without checking that the tool is there. This install offers the tool unless
 * the session was started with `pi --no-workflows` (or PI_ELM_WORKFLOWS=0); before
 * 2026-11-13 only with `pi --workflows`. Without it the note
 * named a tool the model did not have, and twice (test3, test4, 2026-11-12) Qwen
 * spent 11 to 14 turns switching between the two script dialects for it.
 *
 * So, while `workflow` is not among the active tools, what the model is sent has
 * the block replaced by one line: the tool is not loaded, fan out with
 * `subagent`. The session file keeps what was typed and what the package added;
 * only the request changes, and the same way every time, so the gateway's
 * prefix cache still matches. Sub-agents inherit the block in their copy of the
 * conversation and get the same line.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Where the package's block starts in the user's message (dist/workflow-editor.js). */
export const ARMED = "\n\n---\n[workflows mode armed";

export const NOTE =
	"[/ultracode is on, but this session has no `workflow` tool: it was started with `pi --no-workflows` " +
	'(or PI_ELM_WORKFLOWS=0). Independent parts go in one `subagent({ workflow: "parallel", args: { tasks } })` call - ' +
	"no script, no `export const meta`, no `workflow-check`. A question or a small task gets a direct answer. " +
	"Say once that /ultracode needs a session started without that.]";

/** The text with the package's block, which runs to the end of the message, replaced by NOTE. */
export function withoutArmedBlock(text: string): string {
	const at = text.indexOf(ARMED);
	return at < 0 ? text : `${text.slice(0, at)}\n\n${NOTE}`;
}

type Part = { type?: string; text?: string };
type Message = { role?: string; content?: unknown };

/** The messages with every user message's block replaced, or undefined when none had one. */
export function rewrite(messages: readonly Message[]): Message[] | undefined {
	let changed = false;
	const out = messages.map((message) => {
		if (message.role !== "user") return message;
		if (typeof message.content === "string") {
			const content = withoutArmedBlock(message.content);
			if (content === message.content) return message;
			changed = true;
			return { ...message, content };
		}
		if (!Array.isArray(message.content)) return message;
		let touched = false;
		const content = (message.content as Part[]).map((part) => {
			if (part.type !== "text" || typeof part.text !== "string") return part;
			const text = withoutArmedBlock(part.text);
			if (text === part.text) return part;
			touched = true;
			return { ...part, text };
		});
		if (!touched) return message;
		changed = true;
		return { ...message, content };
	});
	return changed ? out : undefined;
}

export default function (pi: ExtensionAPI) {
	pi.on("context", (event) => {
		if (pi.getActiveTools().includes("workflow")) return undefined;
		const messages = rewrite(event.messages as unknown as Message[]);
		return messages ? { messages: messages as unknown as typeof event.messages } : undefined;
	});
}
