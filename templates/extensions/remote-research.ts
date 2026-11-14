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
 * Items 5 and 6 are from test9 (2026-11-12): asked under --remote for a website about alpacas,
 * "download images to populate the website", six agents wrote every page from memory and
 * fetched seven "alpaca" photos from picsum.photos - which serves random ones. In test10
 * (2026-11-13) qwen children, which have no web tools, were told by item 5 to look things up and
 * tried; guessed upload.wikimedia.org thumbnail sizes came back 400 and hash paths 404 in two
 * runs, while Special:FilePath worked; the gallery credited none of its CC BY-SA photos, and
 * one page said 22,000 annelid species where another said 20,000. In test13 a guessed name for
 * Special:FilePath came back 404 and the run fell back to placeholders; Commons' own search API
 * gives the exact names.
 *
 * The paragraph on refusals is from test12 (2026-11-13): this section in its prompt, a --remote
 * session read Wikimedia's own 403 (Python's default User-Agent) and 400 (a thumbnail size it
 * does not serve) as the egress proxy, after AGENTS.md and reference/egress.md - written for a
 * gated session - had said a 403 is this install, and told the user it had no --remote.
 *
 * The launcher exports PI_ELM_REMOTE=1 for --remote, and sub-agents inherit it
 * along with the open proxy, so they get the same section. The text is fixed for
 * the whole session, so it costs the gateway's prefix cache nothing.
 *
 * Item 0 of the Safari section is from a live run (2026-11-12): asked to "check the visual
 * renderings between each subpage", the parent opened its three pages in Safari, read the
 * accessibility outline, never saw them, and called them consistent; `view` was not used.
 *
 * A Commons file name nothing in the session has shown is refused before the download: item 6
 * says to take names from the search, and in auto01 (2026-11-13, a driven session) the child
 * fetching the pictures guessed eleven - "Giant_Otter_(Pteronura_brasiliensis).jpg" and the
 * like, each a 404 - before it searched; test13 and test14 guessed too.
 *
 * When the session also has computer use (PI_ELM_COMPUTER_USE=1, and not a sub-agent
 * child: the top-level --remote session only), a second section says how to drive Safari: typing a
 * URL does not open it until Return is pressed, and when the agent is done it
 * minimises the window and brings the user's terminal back, rather than
 * leaving them looking at a browser while it reports.
 */

import { execFile } from "node:child_process";
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
	"5. What you write for the user is made of facts too: a web page, report or",
	"   document about a subject needs its numbers, names and dates looked up like",
	"   any answer. A `qwen` sub-agent has no web tools, so look them up before",
	"   you hand out the writing - yourself, or with the `researcher` agent - and",
	"   put them in its task; a number on two pages must be the same number.",
	"6. Pictures of a real thing are real pictures, from Wikimedia Commons' freely",
	"   licensed photos. Take exact file names from its search - `curl -s --get",
	"   https://commons.wikimedia.org/w/api.php -d action=query -d list=search -d srnamespace=6 -d format=json",
	"   --data-urlencode 'srsearch=African elephant'` lists `File:` titles - never guess one, then download each file with",
	"   `curl -fL -o x.jpg 'https://commons.wikimedia.org/wiki/Special:FilePath/<name>?width=960'`.",
	"   Look at each one, and credit each on the page with its author and licence",
	"   (CC BY and CC BY-SA require it). Fetch them all in one place - yourself or",
	"   one agent - before the agents that write pages start: Commons answers a",
	"   burst from several at once with 429 Too Many Requests. picsum.photos and",
	"   other placeholder services give an arbitrary photo, never the subject.",
	"7. Asked about a particular paper, report or page, check that what you found",
	"   is that one - its title and abstract against the request - before using",
	"   it: a search for one paper finds its companions. One session summarised",
	"   the LIGO detector paper as the GW150914 discovery paper.",
	"",
	"The egress proxy refuses nothing in this session: a 403, 400 or error page is",
	"the site's own answer, so read it and do what it says. Wikimedia refuses a",
	"script's default User-Agent (send one naming the program) and thumbnail sizes",
	"it does not serve (use Special:FilePath above).",
	"",
	"Local evidence still comes first: the user's files, and the output of commands",
	"you run on them, outrank anything on the web about their setup.",
].join("\n");

export const COMPUTER_USE = [
	"# Driving Safari and other apps",
	"",
	"0. Safari is for the web. To look at a file on this machine - a page or site",
	"   you built, a figure, a PDF - use `view`: it draws the page as a browser",
	"   would, shows several together (`paths`), and says what differs between the",
	"   pages of a site. An app's outline is not a look at the page.",
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

/** A Commons file name as the search lists it and as a URL spells it, made comparable. */
export function commonsName(name: string): string {
	let text = name;
	try {
		text = decodeURIComponent(text);
	} catch {
		// keep it as written
	}
	return text.replace(/^File:/i, "").replace(/_/g, " ").replace(/\s+/g, " ").trim().toLowerCase();
}

/** The Commons files a command downloads by name: Special:FilePath/<name>, and upload.wikimedia.org paths. */
export function commonsFiles(command: string): string[] {
	const names: string[] = [];
	for (const m of command.matchAll(/Special:FilePath\/([^?"'\s&#]+)/gi)) names.push(m[1]);
	for (const m of command.matchAll(/upload\.wikimedia\.org\/wikipedia\/commons\/(?:thumb\/)?[0-9a-f]\/[0-9a-f]{2}\/([^/?"'\s]+)/gi))
		names.push(m[1]);
	return [...new Set(names.filter((n) => !n.includes("$")).map(commonsName))];
}

/** Spaces in a Special:FilePath name inside quotes, as %20 - what curl needs and the shell left alone. */
export function encodeFilePathSpaces(command: string): string {
	return command.replace(/(["'])((?:(?!\1).)*?Special:FilePath\/)((?:(?!\1)[^?\n])*)/g, (_m, quote, before, name) =>
		`${quote}${before}${name.replace(/ /g, "%20")}`,
	);
}

/** Text the session has been shown, made comparable with commonsName: tool results and messages. */
export function seenText(text: string): string {
	return text.replace(/%[0-9A-Fa-f]{2}(?:%[0-9A-Fa-f]{2})*/g, (s) => {
		try {
			return decodeURIComponent(s);
		} catch {
			return s;
		}
	})
		// raw JSON from the search API spells "Á" as \u00c1
		.replace(/\\u([0-9a-fA-F]{4})/g, (_s, hex) => String.fromCharCode(Number.parseInt(hex, 16)))
		.replace(/_/g, " ")
		.replace(/\s+/g, " ")
		.toLowerCase();
}

export function unseenReason(names: string[]): string {
	const list = names.map((n) => `"${n}"`).join(", ");
	return (
		`Not run: ${list} ${names.length > 1 ? "are" : "is"} in no search result of this session, and Commons names are exact - ` +
		"a guessed one comes back 404 (eleven did in one run here). Search, then copy a title from what it lists: " +
		"curl -s --get https://commons.wikimedia.org/w/api.php -d action=query -d list=search -d srnamespace=6 " +
		"-d format=json --data-urlencode 'srsearch=<words, spaces and all>' (--data-urlencode, or the spaces break the URL)"
	);
}

/** What a guessed file name was after: its words, without the extension, dates and numbering. */
export function searchWords(name: string): string {
	return name
		.replace(/\.[a-z0-9]{2,5}$/i, "")
		.replace(/[()[\],_\-.]+/g, " ")
		.replace(/\b(?:19|20)\d\d\b|\b\d+\b/g, " ")
		.replace(/\b(?:january|february|march|april|may|june|july|august|september|october|november|december|jpe?g|png|edit)\b/gi, " ")
		.split(/\s+/)
		.filter(Boolean)
		.slice(0, 4)
		.join(" ");
}

/** File titles Commons' own search gives for these words (through the session's proxy), or none. */
export function commonsSearch(words: string, timeoutMs = 8000): Promise<string[]> {
	return new Promise((resolveTitles) => {
		if (!words) return resolveTitles([]);
		execFile(
			"curl",
			["-s", "--max-time", String(Math.ceil(timeoutMs / 1000)), "--get", "https://commons.wikimedia.org/w/api.php",
				"-A", "elm-pi/1.0 (University of Edinburgh)", "-d", "action=query", "-d", "list=search", "-d", "srnamespace=6",
				"-d", "srlimit=6", "-d", "format=json", "--data-urlencode", `srsearch=${words}`],
			{ timeout: timeoutMs + 1000 },
			(error, stdout) => {
				if (error) return resolveTitles([]);
				try {
					const found = JSON.parse(stdout)?.query?.search ?? [];
					resolveTitles(found.map((r: { title?: string }) => String(r.title ?? "")).filter((t: string) => /^File:/.test(t)));
				} catch {
					resolveTitles([]);
				}
			},
		);
	});
}

/** The search the refusal runs; tests give a stand-in, so they never reach the network. */
let search: (words: string) => Promise<string[]> = commonsSearch;
export function setCommonsSearch(fn: (words: string) => Promise<string[]>): void {
	search = fn;
}

function textOf(content: unknown): string {
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	return content.map((c: any) => (c?.type === "text" ? String(c.text ?? "") : "")).join("\n");
}

/**
 * A request for something from the web, in a session that cannot reach it. auto04 (2026-11-13, no
 * --remote) was asked to "download images from the internet": five children were refused by the
 * proxy, one built a .venv in the project to draw 21 labelled yellow boxes, and the final reply said
 * "Downloaded/generated all required images locally". The user hears the limit at once instead.
 */
export const WANTS_WEB =
	/\b(?:download\w*|fetch\w*|grab\w*|pull)\b[\s\S]{0,80}\b(?:from (?:the )?(?:internet|web|online)|online|wikimedia|wikipedia|unsplash|pexels|flickr)\b|\b(?:from|off) the (?:internet|web)\b|\breal (?:photos|pictures|images)\b/i;
export const NO_WEB_TYPE = "no-web-note";
export const NO_WEB_NOTE =
	"This session cannot reach the web: it was started without `pi --remote`, and its egress proxy lets only ELM and " +
	"package indexes through. So nothing asked for here can be downloaded from the internet - not by you, not by a " +
	"sub-agent. Say so to the user in your first reply, with the way to get it (quit and start `pi --remote`), and " +
	"do the rest of the request. A drawn or labelled stand-in is not what was asked for: make one only if the user " +
	"agrees, and call it a stand-in in your final reply.";

export default function (pi: ExtensionAPI) {
	if (process.env.PI_ELM_WEB !== "1" && process.env.PI_ELM_REMOTE !== "1") {
		pi.on("before_agent_start", async (event: any, ctx: any) => {
			if (process.env.PI_SUBAGENT_CHILD === "1") return undefined;
			if (!WANTS_WEB.test(String(event.prompt ?? ""))) return undefined;
			const entries = ctx.sessionManager?.getBranch?.() ?? [];
			if (entries.some((e: any) => e?.type === "custom_message" && e.customType === NO_WEB_TYPE)) return undefined;
			return { message: { customType: NO_WEB_TYPE, content: NO_WEB_NOTE, display: false } };
		});
		return;
	}
	if (process.env.PI_ELM_REMOTE !== "1") return;
	// What this session has been shown, for the Commons names it may download.
	let seen = "";
	const remember = (text: string) => {
		if (!text) return;
		seen = (seen + "\n" + seenText(text)).slice(-4_000_000);
	};
	pi.on("session_start", async (_event, ctx: any) => {
		// A forked child starts with its parent's conversation: what the parent found counts.
		for (const e of ctx.sessionManager?.getBranch?.() ?? []) {
			const m = e?.message;
			if (e?.type === "message" && (m?.role === "toolResult" || m?.role === "user")) remember(textOf(m.content));
			if (e?.type === "custom_message") remember(textOf(e.content));
		}
	});
	pi.on("tool_result", async (event: any) => {
		remember(textOf(event.content));
		return undefined;
	});
	pi.on("tool_call", async (event: any) => {
		if (event.toolName !== "bash" || typeof event.input?.command !== "string") return undefined;
		// A file name with spaces in a quoted URL: curl refuses it ("URL rejected: Malformed input"), as it did
		// for auto09 and auto17 (2026-11-13). Spelled with %20, it is the same file.
		event.input.command = encodeFilePathSpaces(event.input.command);
		const unseen = commonsFiles(event.input.command).filter((name) => !seen.includes(name));
		if (!unseen.length) return undefined;
		// The search, run for it: auto10 (2026-11-13) was refused five times in a row, guessing a new name
		// after each refusal. The titles Commons gives for what each guess was after go in the refusal, and
		// count as seen, so the next call can use one.
		const found: string[] = [];
		for (const name of unseen.slice(0, 3)) {
			const words = searchWords(name);
			const titles = await search(words);
			if (titles.length) {
				remember(titles.join("\n"));
				found.push(`for "${words}": ${titles.map((t) => `"${t.replace(/^File:/, "")}"`).join(", ")}`);
			}
		}
		const listed = found.length
			? `\nCommons' search, run for you - use one of these exact names (in the URL, spaces as %20): ${found.join("; ")}.`
			: "";
		return { block: true, reason: unseenReason(unseen) + listed };
	});
	// pi-subagents starts a child with the parent's environment and not through the launcher, whose
	// unset of PI_ELM_COMPUTER_USE for children never runs, so a child, which has no computer use,
	// was given the Safari section; and a child's prompt starts from its parent's sections, so the
	// section is taken out, not just left unset. This holds for a child started fresh (a llama
	// child). A forked child (qwen's default) is sent its parent's system prompt unchanged - pi-
	// subagents does that to reuse the parent's prompt cache - so it still reads the section, with
	// no computer-use tools to act on it (seen in a dump of the requests, 2026-11-13).
	const computerUse = process.env.PI_ELM_COMPUTER_USE === "1" && process.env.PI_SUBAGENT_CHILD !== "1";
	pi.on("before_agent_start", (event) => {
		remember(String((event as { prompt?: unknown }).prompt ?? ""));
		event.systemPromptOptions.sections.remote_research = RESEARCH;
		// A forked child starts from its parent's sections, so one it must not have is taken out.
		if (computerUse) event.systemPromptOptions.sections.computer_use = COMPUTER_USE;
		else delete event.systemPromptOptions.sections.computer_use;
	});
}
