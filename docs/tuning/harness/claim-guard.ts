/**
 * Experiment: catch a reply that claims work the run never did.
 *
 * Mistral, asked to add a function and "reply with one line saying what you did",
 * replied that it had added it - with no tool call at all - in every run, with or
 * without written guidance. This looks at the run before pi settles it: no tool
 * call in the whole run, and a final reply that says something was added, changed
 * or run, gets one note back and one more turn. Once per run, so it cannot loop.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const CLAIM = /\b(added|adds|created|creates|wrote|written|fixed|updated|changed|renamed|implemented|edited|modified|saved|removed|deleted|moved|ran|installed|refactored|replaced|inserted)\b/i;
const NOTE =
	"Your reply says you changed or ran something, but this run made no tool call, so nothing was changed or run. " +
	"Do the work now with tool calls, check the result, then reply. If you were only describing earlier work, say that in one line.";

export default function (pi: ExtensionAPI) {
	let calls = 0;
	let nudged = false;
	pi.on("agent_start", async () => {
		calls = 0;
		nudged = false;
	});
	pi.on("tool_call", async () => {
		calls += 1;
		return undefined;
	});
	pi.on("agent_before_settle", async (event) => {
		// Not event.context.canContinue: that describes the run before this note is
		// added, and a run that ends in a reply can never continue as it stands.
		if (nudged || calls > 0) return undefined;
		const last = [...event.context.contextMessages].reverse().find((m) => m.role === "assistant");
		const text = last && Array.isArray(last.content)
			? last.content.map((part) => (part.type === "text" ? part.text : "")).join("\n")
			: "";
		if (!CLAIM.test(text)) return undefined;
		nudged = true;
		return { entries: [{ type: "custom_message", customType: "claim-guard", content: NOTE, display: true }], continue: true };
	});
}
