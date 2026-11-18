/**
 * standing-rules: rules the user set for the work that follows are put beside each later request.
 *
 * Why: the long-session scenarios of 2026-11-17. One opens with six house rules for a file built up over seven
 * messages ("every port is even", "names are lowercase with hyphens", "the list is kept sorted by name") and then
 * asks for one small change at a time. Three sessions of six left the file breaking a rule by the end: a rename
 * that left the list unsorted, a name the user typed with an underscore kept as typed, a file that was no longer
 * JSON. Each request was done as asked; the rules from message 1 were not what the session was looking at by
 * message 5. `pin_instruction` (pinned-instructions.ts) exists for this and none of the six sessions called it.
 *
 * So this does not wait to be called. A user message that says it is setting rules for what follows - "house
 * rules", "from now on", "which apply to everything", "for the rest of this session" - is kept, word for word, and
 * every later request in the session gets it back in a short note: these still apply, check the result against
 * each. The user's words, not a summary of them: a paraphrase is where a rule gets lost.
 *
 * Narrow on purpose: the phrases are ones that announce a rule for later, not "always" or "never" wherever they
 * fall; the two most recent such messages, 1,500 characters each at most; not in the turn that set them; not in
 * a sub-agent, whose brief is its parent's to write. A later rule-setting message is added, not swapped in: the
 * user amending one rule has not withdrawn the rest.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const MESSAGE_TYPE = "standing-rules";
export const MAX_KEPT = 2;
export const MAX_CHARS = 1500;

/** Words that announce rules for the work that follows. */
export const SETS_RULES =
	/\b(?:house rules?|ground rules?|standing (?:rules?|instructions?)|from now on|from here on|for the rest of (?:this|the|our) (?:session|conversation|project|work)|(?:which|that|these|they) appl(?:y|ies) to everything|appl(?:y|ies) to everything (?:we|you|i)|in everything (?:we|you) (?:add|do|write|make)|unless I (?:say|tell you) otherwise|rules? (?:for|that hold for) (?:everything|the whole|all of))\b/i;

export function setsRules(text: string): boolean {
	return SETS_RULES.test(text);
}

export function note(kept: string[]): string {
	const quoted = kept.map((text) => `"""\n${text.length > MAX_CHARS ? `${text.slice(0, MAX_CHARS)} [...]` : text}\n"""`).join("\n\n");
	const lead = kept.length === 1 ? "Earlier in this session the user set rules for the work that follows:" : "Earlier in this session the user set rules for the work that follows, in these messages:";
	return (
		`${lead}\n\n${quoted}\n\n` +
		"They still apply to this request. Before you report, check what you changed - and what else the change moved - " +
		"against each rule. Where this request seems to ask for something a rule forbids, follow the rule and say so in one line."
	);
}

export default function (pi: ExtensionAPI) {
	const child = Boolean(process.env.PI_SUBAGENT_CHILD);
	let kept: string[] = [];

	pi.on("before_agent_start", (event: any) => {
		if (child || event?.messageType !== "user" || typeof event.prompt !== "string") return undefined;
		const earlier = kept;
		if (setsRules(event.prompt)) kept = [...kept.filter((text) => text !== event.prompt), event.prompt].slice(-MAX_KEPT);
		if (earlier.length === 0) return undefined;
		return { message: { customType: MESSAGE_TYPE, content: note(earlier), display: true } };
	});
}
