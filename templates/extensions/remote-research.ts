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
	"",
	"Local evidence still comes first: the user's files, and the output of commands",
	"you run on them, outrank anything on the web about their setup.",
].join("\n");

export default function (pi: ExtensionAPI) {
	if (process.env.PI_ELM_REMOTE !== "1") return;
	pi.on("before_agent_start", (event) => {
		event.systemPromptOptions.sections.remote_research = RESEARCH;
	});
}
