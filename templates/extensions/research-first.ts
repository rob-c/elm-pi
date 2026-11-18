/**
 * research-first: when a service or a cluster is being set up, the documentation is read before anything is
 * built, and an error is looked up before it is guessed at twice.
 *
 * Why: the SLURM-in-Docker treadmill of 2026-11-17. With no recipe, sessions wrote a Dockerfile and a slurm.conf
 * from memory and then debugged what memory had got wrong - 110 to 210 tool calls and 15 to 34 minutes a run. One
 * concluded "SLURM cannot run jobs in a container on this machine" from a cgroup error and gave up; another, asked
 * for Rocky Linux 9, decided it was impossible and built Ubuntu instead. Both claims were false, and each was a
 * search away from the setting that fixes it (I found and tested both that evening). None of those sessions had
 * searched for the message in front of it. The `package-admin` skill says to research each step; this is what
 * holds a session to the two moments where it matters.
 *
 *   - Before the first build: in a run whose request is to set up a service or a cluster, the first `docker
 *     build`, long-running `docker run`, `compose up`, package install, or the first Dockerfile/compose/.conf
 *     written, is refused if no web search has been made yet - with what to look for - and refused again until
 *     INSTALL-LOG.md holds the plan with at least one source. The first three research-driven runs searched
 *     once, for tutorials, wrote no notes, and one of the three got a job to run: a search that leaves nothing
 *     written down was not read.
 *   - After the second failure in a row: a failing command following another, with no search between them, gets
 *     one line added to its result - search this exact message before changing anything else.
 *
 *   - Before the report: the containers the request names are looked for (`docker ps`). One that is not running is
 *     said so, once, before the session settles: finish it, or open the reply with what is missing. Grid Engine was
 *     asked for twice as a qmaster container and an execution-host container; both runs ended with one container
 *     and a reply that began "Perfect! Everything is working" and "Excellent! Everything is working".
 *
 * Narrow on purpose: only such requests (the same words that route the skill); the refusal once per request and
 * twice per session; at most eight error notes a session; not in a sub-agent, whose brief is its parent's. It
 * cannot make a session read well - only make it look.
 */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { basename, join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** A request to set up a service or a cluster: both kinds of word, anywhere in it. Kept in step with skill-router's package-admin route. */
export const SETS_UP =
	/^(?=[\s\S]*\b(set(ting)?( \w+){0,3}? ?up(?! to\b)|stand(ing)?( \w+){0,3}? up(?! to\b)|bring(ing)?( \w+){0,3}? up(?! to\b)|spin(ning)?( \w+){0,3}? up(?! to\b)|deploy(s|ed|ing|ment)?|provision(s|ed|ing)?|install(s|ed|ing)?|configur(e|es|ed|ing))\b)(?=[\s\S]*\b(clusters?|schedulers?|daemons?|(batch|queu(e|ing)|storage|grid) systems?|grid engine|sge|xrootd|redirectors?|(compute|computing) elements?|(central manager|head|compute|worker|execute|data|login|submit) nodes?|condor pools?|(database|web|mail|message|ldap|dns|nfs|file|license) servers?|message (queue|broker)s?|slurm|kubernetes|k8s|htcondor|nordugrid|arc ce|opensearch|elasticsearch|postgres(ql)?|mariadb|mysql|redis|rabbitmq|kafka|nginx|apache|ceph|lustre|openldap|kerberos)\b)/i;

/** The tools that look something up. */
export const SEARCHES = new Set(["web_search", "get_search_content", "fetch_content", "websearch", "websearch_search"]);

/** Commands that start building: an image, a long-running container, a compose project, a package install. */
const BUILDS = /\b(?:docker|podman)\s+(?:image\s+)?build\b|\b(?:docker|podman)(?:-compose|\s+compose)\b[^\n;|&]*\bup\b|\b(?:docker|podman)\s+(?:container\s+)?run\b(?![^\n;|&]*--rm\b)[^\n;|&]*\s-d\b|\b(?:apt(?:-get)?|dnf|yum|zypper|apk)\s+(?:-\S+\s+)*(?:install|add)\b/;
/** Files that are the build: written from memory, they are where the wrong option names go. */
const BUILD_FILES = /^(?:Dockerfile(?:\..+)?|.+\.dockerfile|(?:docker-)?compose\.ya?ml|.+\.conf|.+\.service)$/i;
const WRITERS = new Set(["write", "edit", "replace", "replace_match", "insert"]);

export const MAX_REFUSALS = 4;
// Not "notes": report-guard refuses a new *notes*.md nobody asked for, and refused this file in three sessions of
// three (res2 r4-r6, 2026-11-17) while this guard was asking for it.
export const NOTES = "INSTALL-LOG.md";
export const MAX_NOTES = 8;

export const RESEARCH_FIRST =
	"Not yet: nothing has been looked up in this run, and a setup written from memory fails on the details that changed " +
	"between versions. Search first (`web_search`, then `get_search_content` on what answers): the software's own " +
	"installation and configuration guide for this operating system and version - its packages, its daemons and what " +
	"each needs running first, its required configuration options - and how it is run in a container, without systemd. " +
	"Write the plan and its sources in INSTALL-LOG.md, then build. See the package-admin skill.";

export const NOTES_FIRST =
	`Not yet: ${NOTES} does not hold the plan and its sources. Before building, write there what the documentation you read ` +
	"says - the version you will install and where it comes from (the distribution's own packages unless they cannot do the job), " +
	"each daemon and the machine it runs on, the configuration every machine must share, the order things start in and the " +
	"command that shows each is up - with the URL each point came from. If you have only read search snippets, open the " +
	"software's own guide with `fetch_content` first.";

export const SEARCH_THE_ERROR =
	"[That is the second failure in a row with no search between them. Before changing anything else: `web_search` for the " +
	"exact message above, in quotes, with the software's name and version, and read what it means. If it seems to say the " +
	"thing cannot be done here, search for how it is run in a container before concluding that. Note the cause and its " +
	"source in INSTALL-LOG.md.]";

/**
 * Words a failing daemon, build or client prints. A session rarely sees a failure as a failed command: it reads logs
 * (`docker logs x | tail`) and pipes builds through `tail`, and the pipe's status is the last command's. suites2-xrd
 * (2026-11-18) spent an hour on 84 commands and 37 rewritten files after one search at the start, and was never told
 * to look anything up, because not one of those results was marked as an error.
 */
const SAYS_FAILED = /(?:^|[\s:\[(])(?:error|fatal|failed|failure|unable to|cannot|can't|could not|refused|denied|not found|no such|traceback|exited with code [1-9]|timed out)\b/i;

/** Whether a command's result reports a failure: marked as one, or saying so. */
export function reportsFailure(isError: boolean, text: string): boolean {
	return isError || SAYS_FAILED.test(text);
}

/**
 * The containers a request names: a hyphenated or numbered name led into by "container(s)" - "a container named
 * ht-cm", "containers os-node1 and os-node2", "(container v2-head)". Only names of that shape, so "a container for
 * the database" names nothing.
 */
export function namedContainers(request: string): string[] {
	const names: string[] = [];
	// Each mention is read with what follows it, up to the end of its sentence: one mention's tail may hold the next.
	for (const m of request.matchAll(/\bcontainers?\b(?=([^.;!?]{0,90}))/gi)) {
		for (const n of m[1].matchAll(/(?:^|named|called|name|,|\band|\bor|\()\s*`?([a-z][a-z0-9]*(?:[-_][a-z0-9]+)+)`?/gi)) {
			const name = n[1].toLowerCase();
			if (!names.includes(name)) names.push(name);
		}
	}
	return names;
}

/** The names of the containers running now, or undefined when the engine does not answer. */
export type RunningProbe = () => string[] | undefined;
const askRunning: RunningProbe = () => {
	for (const engine of ["docker", "podman"]) {
		try {
			return execFileSync(engine, ["ps", "--format", "{{.Names}}"], { encoding: "utf8", timeout: 5000, stdio: ["ignore", "pipe", "ignore"] }).split("\n").map((l) => l.trim()).filter(Boolean);
		} catch {
			// try the other engine
		}
	}
	return undefined;
};
let running: RunningProbe = askRunning;
/** For tests: what the engine would list. */
export function setRunningProbe(probe?: RunningProbe): void {
	running = probe ?? askRunning;
}

export function missingNote(missing: string[], asked: string[]): string {
	const list = missing.map((name) => `\`${name}\``).join(" and ");
	const verb = missing.length === 1 ? "is" : "are";
	return (
		`Before you report: the request asks for the containers ${asked.map((name) => `\`${name}\``).join(", ")}, and ${list} ${verb} not running ` +
		"(`docker ps`). If the work is not finished, finish it. If it cannot be, or the user asked for it to be taken down, the first line of " +
		"your reply says what is missing and why - before anything that does work."
	);
}

/** Whether the notes hold a plan someone could check: there is a file, with something in it, and a source. */
export function hasPlan(cwd: string): boolean {
	const path = join(cwd, NOTES);
	if (!existsSync(path)) return false;
	try {
		const text = readFileSync(path, "utf8");
		return text.trim().length >= 200 && /https?:\/\/\S+/.test(text);
	} catch {
		return false;
	}
}

/** Whether this call starts the build: a command that builds or installs, or a build file being written. */
export function startsBuild(tool: string, input: { command?: unknown; path?: unknown }): boolean {
	if (tool === "bash") return typeof input.command === "string" && BUILDS.test(input.command);
	return WRITERS.has(tool) && typeof input.path === "string" && BUILD_FILES.test(basename(input.path));
}

export default function (pi: ExtensionAPI) {
	const child = Boolean(process.env.PI_SUBAGENT_CHILD);
	let settingUp = false;
	let request = "";
	let checkedContainers = false;
	let searches = 0;
	let refused = false;
	let askedForNotes = false;
	let planned = false;
	let refusals = 0;
	let failures = 0;
	let notes = 0;

	pi.on("input", async (event: any) => {
		if (typeof event?.text === "string" && event.source !== "extension") {
			settingUp = SETS_UP.test(event.text);
			request = event.text;
			checkedContainers = false;
			searches = 0;
			refused = false;
			askedForNotes = false;
			planned = false;
			failures = 0;
		}
		return undefined;
	});

	pi.on("tool_call", async (event: any, ctx: any) => {
		const tool = event?.toolName ?? "";
		if (SEARCHES.has(tool)) {
			searches += 1;
			failures = 0;
			return undefined;
		}
		if (child || !settingUp || planned || refusals >= MAX_REFUSALS) return undefined;
		if (!startsBuild(tool, event.input ?? {})) return undefined;
		if (searches === 0) {
			if (refused) return undefined;
			refused = true;
			refusals += 1;
			return { block: true, reason: RESEARCH_FIRST };
		}
		if (hasPlan(ctx?.cwd ?? process.cwd()) || askedForNotes) {
			planned = true;
			return undefined;
		}
		askedForNotes = true;
		refusals += 1;
		return { block: true, reason: NOTES_FIRST };
	});

	pi.on("agent_before_settle", async () => {
		if (child || !settingUp || checkedContainers) return undefined;
		const asked = namedContainers(request);
		if (asked.length === 0) return undefined;
		const up = running();
		if (up === undefined) return undefined;
		const missing = asked.filter((name) => !up.includes(name));
		checkedContainers = true;
		if (missing.length === 0) return undefined;
		return { entries: [{ type: "custom_message", customType: "research-first", content: missingNote(missing, asked), display: true }], continue: true };
	});

	pi.on("tool_result", async (event: any) => {
		if (child || !settingUp || event?.toolName !== "bash" || !Array.isArray(event.content)) return undefined;
		const text = event.content.map((part: { type?: string; text?: string }) => (part.type === "text" ? part.text ?? "" : "")).join("\n");
		if (!reportsFailure(Boolean(event.isError), text)) {
			failures = 0;
			return undefined;
		}
		failures += 1;
		if (failures < 2 || notes >= MAX_NOTES) return undefined;
		failures = 0;
		notes += 1;
		return { content: [...event.content, { type: "text" as const, text: SEARCH_THE_ERROR }] };
	});
}
