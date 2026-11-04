/**
 * Remote research: in a session started with `pi --remote`, tell the model to
 * look things up rather than answer from memory.
 *
 * Why: the web tools are the one thing --remote adds, and a model that can
 * search still answers from memory when nothing tells it the search is worth
 * the call - versions, flags, API names, citations and numbers come back
 * plausible and wrong. APPEND_SYSTEM.md already puts the web second in its
 * order for resolving unknowns, but it is written for every session, most of
 * which cannot reach the web, so it cannot insist. This section can: it is only
 * there when the network is open.
 *
 * The launcher exports PI_ELM_REMOTE=1 for --remote, and sub-agents inherit it
 * along with the open proxy, so they get the same section. The text is fixed for
 * the whole session, so it costs the gateway's prefix cache nothing.
 *
 * When the session also has computer use (PI_ELM_COMPUTER_USE=1: the top-level
 * --remote session only), a second section says how to drive Safari: typing a
 * URL does not open it until Return is pressed, and when the agent is done it
 * minimises the window and brings the user's terminal back, rather than
 * leaving them looking at a browser while it reports.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const RESEARCH = [
	"# Research, do not guess",
	"",
	"This session was started with `pi --remote`: `web_search` and `fetch_content`",
	"reach the internet. ALWAYS research to find an answer rather than answering",
	"from memory:",
	"",
	"1. Before you state a fact you have not checked in this session - a version,",
	"   a command-line option, an API or function name, a configuration key, a",
	"   paper, a number, a date, how a tool behaves, anything recent - look it up,",
	"   and cite the source you used.",
	"2. Never invent a URL, citation, version, option, quotation or result. A",
	"   source you did not open is not a source.",
	"3. If the search finds nothing reliable, say so plainly and name what you",
	"   could not confirm, instead of filling the gap with a guess.",
	"4. Asked about yourself, ELM or the University of Edinburgh's model hosting,",
	"   read the University's public pages (information-services.ed.ac.uk, starting",
	"   at /computing/comms-and-collab/elm, and elm.edina.ac.uk) and answer from",
	"   what they say, with links.",
	"",
	"Local evidence still comes first: the user's files, and the output of commands",
	"you run on them, outrank anything on the web about their setup.",
].join("\n");

export const COMPUTER_USE = [
	"# Driving Safari and other apps",
	"",
	"1. To open a URL in Safari, focus the address field, `setText` the whole URL,",
	"   check the field shows exactly that URL (autocomplete can change it), then",
	"   send `keypress` with `keys: [\"return\"]` as its own step. Typing alone opens",
	"   nothing: confirm from the successor state or `wait_for` that the page loaded",
	"   before reading it.",
	"2. When you have finished with Safari, or any app you brought forward,",
	"   minimise its window - with it focused, `keypress` `keys: [\"cmd\", \"m\"]` -",
	"   then bring the terminal running this session back to the front: `find_roots`",
	"   for it (`echo $TERM_PROGRAM` in `bash` names it: `Apple_Terminal` is",
	"   Terminal, `iTerm.app` is iTerm2) and click its window. Do both before your",
	"   final report, so the user is looking at it.",
].join("\n");

export default function (pi: ExtensionAPI) {
	if (process.env.PI_ELM_REMOTE !== "1") return;
	const computerUse = process.env.PI_ELM_COMPUTER_USE === "1";
	pi.on("before_agent_start", (event) => {
		event.systemPromptOptions.sections.remote_research = RESEARCH;
		if (computerUse) event.systemPromptOptions.sections.computer_use = COMPUTER_USE;
	});
}
