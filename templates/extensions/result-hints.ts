/**
 * result-hints: two results a session misreads as failures are said plainly.
 *
 * Why: the penalty scan of 2026-11-17 (six arms, 50 tasks, three rounds) counted tool errors per arm, and the arm at
 * repetition_penalty 1.1 had the most. Read one by one, the difference was not failures:
 *
 *   - `grep` that matched nothing. grep exits 1 when no line matches, pi reports any non-zero exit as a failed
 *     command, and the session is handed "(no output) / Command exited with code 1" marked as an error - 22 times in
 *     that arm, 10 and 11 in the two controls. "Is this function used anywhere?" answered "no" is the answer.
 *   - a scratch file written to /tmp. The permission gate asks about a path outside the project, and where there is
 *     nobody to ask (`pi -p`, a sub-agent) the result is "requires approval, but no interactive UI is available" -
 *     five times in that arm - which names no place the file could go. AGENTS.md says `.pi/tmp/`; the refusal did not.
 *
 * So: a search whose last command is grep, rg, ag or `git grep`, which printed nothing and exited 1, is returned as
 * a result that says so, not as an error. Exit 2 and above (a bad pattern, a missing file) stays an error, and so
 * does any output. A third, from the cluster treadmill of 2026-11-17: `docker network create NAME` answered "already
 * exists" and the session went on to use that network - three clusters in five runs joined the one a different
 * cluster was on. The result now says whose it is not. And a fourth: an image build stopped at its ten-minute limit
 * (suites2-xrd) because `apt-get install` inside it was asking for a time zone; the session ran the same build again. And where there is nobody to ask, a command that writes a file under /tmp, /private/tmp or
 * /var/tmp is refused here, before the gate, with the same answer and where scratch goes. (The first version added
 * that line to the gate's own refusal; a live trial showed a call the gate blocks never reaches `tool_result`.)
 * With a person at the keyboard the gate still asks them. Nothing is allowed that was refused.
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** What pi's bash tool returns for a command that printed nothing and exited 1. */
const QUIET_EXIT_1 = /^\s*\(no output\)\s*Command exited with code 1\s*$/;

/** Commands that exit 1 to say "nothing matched". */
const SEARCHERS = new Set(["grep", "egrep", "fgrep", "rg", "ag", "zgrep"]);

export const NO_MATCHES =
	"No matches: the search ran and found nothing (grep exits 1 for that - it is not a failure). " +
	"If that is surprising, check the pattern and the paths before concluding the thing is absent.";

/** `docker network create` (or podman's) saying the name is taken: the network is somebody's. */
const NETWORK_EXISTS = /network with name (\S+) already exists|network (\S+) already exists|network name (\S+) (?:is )?already (?:used|in use)/i;
export const NOT_YOUR_NETWORK = (name: string) =>
	`[The network ${name} was not made in this run: other containers may be on it, with host names that clash with yours ` +
	`(\`docker network inspect ${name}\` lists them). Unless the user asked you to add to what is on it, make a new internal network under another name and use that.]`;

/** pi's words for a command stopped at its time limit. */
const TIMED_OUT = /Command timed out after \d+ seconds/;
export const SILENT_BUILD =
	"[A build that runs to its time limit is usually not slow but waiting: a package install inside it has asked a question " +
	"(apt asking for a time zone is the usual one) and a build has no terminal to answer on. Before running it again, see where " +
	"it stopped (`docker build --progress=plain ... 2>&1 | tail -20`) and make the install ask nothing - for apt, " +
	"`DEBIAN_FRONTEND=noninteractive` on that `RUN` line.]";

export const SCRATCH =
	"Scratch files go in `.pi/tmp/` under the project (`mkdir -p .pi/tmp`), which needs no approval: write there, not under /tmp.";

/** The last simple command of `command`, as words: what the shell's exit status is the status of. */
export function lastCommand(command: string): string[] {
	let plain = "";
	for (let i = 0, quote = ""; i < command.length; i++) {
		const c = command[i];
		if (c === "\\") { plain += "xx"; i += 1; continue; }
		if (quote) { if (c === quote) quote = ""; plain += c === "\n" ? " " : "x"; continue; }
		if (c === "'" || c === '"') { quote = c; plain += "x"; continue; }
		plain += c;
	}
	const cut = Math.max(plain.lastIndexOf("|"), plain.lastIndexOf(";"), plain.lastIndexOf("\n"), plain.lastIndexOf("&"));
	const words = command.slice(cut + 1).trim().split(/\s+/).filter(Boolean);
	// VAR=value prefixes and the wrappers that pass the status through.
	while (words.length && (/^[A-Za-z_][A-Za-z0-9_]*=/.test(words[0]) || ["command", "env", "time", "nice", "stdbuf"].includes(words[0]))) words.shift();
	return words;
}

/** Whether the command's status is a searcher's: `grep`, `/usr/bin/grep`, `git grep`, `git -C x grep`. */
export function isSearch(command: string): boolean {
	const words = lastCommand(command);
	if (words.length === 0) return false;
	const name = words[0].split("/").pop() ?? "";
	if (SEARCHERS.has(name)) return true;
	if (name !== "git") return false;
	for (let i = 1; i < words.length; i++) {
		if (words[i] === "-C" || words[i] === "-c") { i += 1; continue; }
		if (words[i].startsWith("-")) continue;
		return words[i] === "grep";
	}
	return false;
}

/**
 * The first file under a shared temporary folder that `command` writes by redirection, `tee`, `touch` or `mkdir`,
 * or undefined. The folders pi's own sub-agents use there are the gate's to allow.
 */
export function scratchWrite(command: string): string | undefined {
	const path = String.raw`((?:\/private)?(?:\/var)?\/tmp\/[^\s;|&<>()'"]*)`;
	const found =
		new RegExp(String.raw`(?:^|[^<])>>?\s*["']?` + path).exec(command) ??
		new RegExp(String.raw`(?:^|[\s;|&(])(?:tee|touch|mkdir)\s+(?:-[A-Za-z-]+\s+)*["']?` + path).exec(command);
	if (!found || /\/tmp\/pi-subagents-uid-/.test(found[1])) return undefined;
	return found[1];
}

export function scratchRefusal(path: string): string {
	return `This command writes ${path}, which is outside the project: that needs the user's approval, and this session has nobody to ask. ${SCRATCH}`;
}

type Part = { type: string; text?: string };

export default function (pi: ExtensionAPI) {
	// Where a person can be asked, a path outside the project is theirs to allow: the gate's dialog. Where nobody can
	// (`pi -p`, a sub-agent), the gate's answer is already no, and this says the same with somewhere to go.
	pi.on("tool_call", async (event: any, ctx: any) => {
		if (event?.toolName !== "bash" || ctx?.hasUI) return undefined;
		const command = event.input?.command;
		const path = typeof command === "string" ? scratchWrite(command) : undefined;
		return path ? { block: true, reason: scratchRefusal(path) } : undefined;
	});
	pi.on("tool_result", async (event: any) => {
		if (event?.toolName !== "bash" || !Array.isArray(event.content)) return undefined;
		const first = (event.content as Part[]).findIndex((part) => part.type === "text");
		if (first === -1) return undefined;
		const text = (event.content[first] as Part).text ?? "";
		const command = typeof event.input?.command === "string" ? event.input.command : "";
		const taken = /\b(?:docker|podman)\s+network\s+create\b/.test(command) ? NETWORK_EXISTS.exec(text) : null;
		if (taken) {
			const name = (taken[1] ?? taken[2] ?? taken[3] ?? "").replace(/[^A-Za-z0-9_.-]/g, "");
			if (name && !text.includes("was not made in this run")) return { content: [...event.content, { type: "text" as const, text: NOT_YOUR_NETWORK(name) }] };
		}
		if (TIMED_OUT.test(text) && /\b(?:docker|podman)\s+(?:image\s+|buildx\s+)?build\b/.test(command) && !text.includes("usually not slow but waiting")) {
			return { content: [...event.content, { type: "text" as const, text: SILENT_BUILD }] };
		}
		if (event.isError && QUIET_EXIT_1.test(text) && isSearch(command)) {
			return { content: [{ type: "text" as const, text: NO_MATCHES }], isError: false };
		}
		return undefined;
	});
}
