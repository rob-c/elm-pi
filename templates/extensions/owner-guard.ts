/**
 * Owner guard: a file named in a running child's task is that child's.
 *
 * test6 (2026-11-12), "use 5 agents make me a website about frogs": the parent
 * started five qwen children at once, one page each. A qwen child is forked from
 * the parent's conversation, so each one saw the user's whole request and all
 * five tasks, and two of them took on the whole site. Task 1 wrote the
 * stylesheet and rewrote the other four pages "to match"; task 4 wrote "since
 * the sub-agents haven't completed, I'll create all remaining pages myself" and
 * overwrote four pages and the stylesheet. The three children that did only
 * their own page had their work thrown away; qwen.md's "Write only the files
 * your task names" did not stop it. The parent, told to change none of the
 * children's files until the run's final notice, edited lifecycle.html while
 * task 4 - which it had just steered to keep writing that file - still ran.
 *
 * So, in a child (pi-subagents sets PI_SUBAGENT_CHILD=1 in every child):
 * - its first turn is told which files its siblings' tasks name, and that they
 *   are not its own;
 * - a change to a file that only a sibling's task names is refused;
 * - `write` over an existing file that changed after the child started - not
 *   through the child's own tools - and that it has not read since, is refused
 *   (the stylesheet nobody's task named, which task 4 replaced).
 * In the parent: while a run it started is going, a change to a file named in a
 * child's task is refused until that child's completion notice, or the run's,
 * arrives (or `subagent` status says the run has ended, or 35 minutes pass:
 * pi-subagents gives up on a run after 30).
 *
 * A task's files are its *outputs*: the paths it says to create, write, save,
 * edit or fix ("Create gallery.html", "Save to /site/species.html"), relative to
 * the task's cwd. A path it only mentions - "links to: index.html, about.html",
 * "Use the shared styles.css", "from data.csv" - is not. test7 (2026-11-12) is
 * why: every task listed all five pages for the navigation bar, the first
 * version of this guard took every mentioned file as the child's own, every
 * child owned every page, and task 4 rewrote task 2's finished page unrefused.
 * A task in which no output can be told apart falls back to every path it names.
 * A file the child's own task outputs is always its own. The tasks of a workflow
 * *script* are inside the script and are not read; neither is bash (a redirect
 * or `sed -i` passes).
 *
 * The parent is told who wrote what. Each forked child records what it wrote,
 * and what it was refused, in a ledger per run (under the temp folder); when the
 * run's final notice is in, the parent's next turn starts with that list (under
 * `pi -p`, where the parent waits inside its turn, `bg_wait`'s result ends with it) - in
 * test7 the parent told the user five agents had each built a page, when one had
 * rewritten another's and said so in its own report.
 */
import { appendFileSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { basename, dirname, isAbsolute, join, relative, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Every tool in this install that can change a file (protected-paths.ts keeps the same list). */
export const WRITING_TOOLS = new Set(["write", "edit", "replace", "replace_match", "insert", "copy", "move", "undo_last_change"]);
/** Tools after which the child has seen a file's current content. */
const SEEING_TOOLS = new Set(["read", "view", ...WRITING_TOOLS]);
export const RUN_EXPIRY_MS = 35 * 60 * 1000;
/** Slack around a tool call, for filesystems that round modification times. */
const SLACK_MS = 1500;
export const NOTE_TYPE = "owner-guard";
export const LEDGER_TYPE = "owner-guard-ledger";
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;
/** A path written in prose: something with an extension, standing on its own. */
const PATH_IN_TEXT =
	/(?:^|[\s"'`(<[,;=])((?:~\/|\.{1,2}\/|\/)?[\w@%+~.\-/]*[\w-]\.[A-Za-z][A-Za-z0-9]{0,7})(?=$|[\s"'`)\]>,;:!?]|\.(?:\s|$))/g;
/** Words that make a path a task's output, when they lead to it within its sentence. */
const OUTPUT_VERB =
	/\b(?:create|write|save|build|generate|produce|make|edit|update|fix|modify|implement|add|rewrite|replace|refactor|render|draw|plot|put|store|output|emit|export|overwrite|append|change|patch|fill|complete|finish|redo|convert)\b/gi;
/** Words that, between that verb and the path, make it an input or a reference instead. */
const NOT_OUTPUT =
	/\b(?:from|using|use|uses|with|like|per|based|see|link|links|linking|linked|read|reads|reading|match|matches|matching|same|import|imports|importing|load|loads|loading|reference|references|referencing|include|includes|including|against|already|existing|consistent|identical|other|shared)\b/i;
/** pi-subagents' preamble on a forked child's task (DEFAULT_FORK_PREAMBLE), then the task. */
const FORK_TASK = /You are a delegated subagent[\s\S]*?\n\s*Task:\s*\n([\s\S]*)$/;

type Part = { type?: string; text?: string; name?: string; id?: string; arguments?: Record<string, unknown> };
export type Entry = {
	type?: string;
	customType?: string;
	content?: unknown;
	timestamp?: string;
	message?: { role?: string; content?: unknown; toolCallId?: string; toolName?: string; isError?: boolean };
};
export interface Task {
	key: string;
	text: string;
	cwd: string;
}
interface Owner {
	key: string;
	path: string;
	runId?: string;
}

function textOf(content: unknown): string {
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	return (content as Part[]).map((p) => (p?.type === "text" ? String(p.text ?? "") : "")).join("\n");
}

/** A path as compared: absolute, and case-folded where the filesystem folds case. */
function same(path: string): string {
	return process.platform === "darwin" || process.platform === "win32" ? path.toLowerCase() : path;
}

function resolveIn(written: string, cwd: string, home: string): string {
	if (written.startsWith("~/")) return join(home, written.slice(2));
	return isAbsolute(written) ? resolve(written) : resolve(cwd, written);
}

/** The files a task's text names, as absolute paths. */
export function namedPaths(text: string, cwd: string, home: string = homedir()): string[] {
	const out = new Set<string>();
	for (const m of text.matchAll(PATH_IN_TEXT)) {
		if (m[1].startsWith("//")) continue; // the tail of a URL
		out.add(resolveIn(m[1], cwd, home));
	}
	return [...out];
}

/**
 * The files a task says to produce: a path is an output when a verb such as create, write, save
 * or fix leads to it within its sentence, with no "from", "use", "links to" and the like between.
 */
export function outputPaths(text: string, cwd: string, home: string = homedir()): string[] {
	const out = new Set<string>();
	for (const m of text.matchAll(PATH_IN_TEXT)) {
		if (m[1].startsWith("//")) continue;
		const at = (m.index ?? 0) + m[0].indexOf(m[1]);
		const before = text.slice(0, at);
		const sentence = before.slice(Math.max(before.lastIndexOf("\n"), ...[". ", "! ", "? ", "; "].map((b) => before.lastIndexOf(b))) + 1);
		const verbs = [...sentence.matchAll(OUTPUT_VERB)];
		const verb = verbs[verbs.length - 1];
		if (!verb) continue;
		const between = sentence.slice((verb.index ?? 0) + verb[0].length);
		if (between.length <= 100 && !NOT_OUTPUT.test(between)) out.add(resolveIn(m[1], cwd, home));
	}
	return [...out];
}

/** A task's own files: its outputs, or every path it names when none can be told apart. */
export function ownedPaths(task: Task, home: string = homedir()): string[] {
	const outputs = outputPaths(task.text, task.cwd, home);
	return outputs.length ? outputs : namedPaths(task.text, task.cwd, home);
}

/** The tasks a `subagent` call starts, keyed as pi-subagents keys them (task-N, step-N, step-N-M). */
export function tasksOf(input: Record<string, unknown>, cwd: string): Task[] {
	const at = (r: Record<string, unknown>) => (typeof r.cwd === "string" ? resolve(cwd, r.cwd) : cwd);
	const one = (item: unknown, key: string): Task[] => {
		if (!item || typeof item !== "object") return [];
		const r = item as Record<string, unknown>;
		if (Array.isArray(r.parallel)) return r.parallel.flatMap((p, j) => one(p, `${key}-${j + 1}`));
		return typeof r.task === "string" ? [{ key, text: r.task, cwd: at(r) }] : [];
	};
	const args = (input.args ?? {}) as Record<string, unknown>;
	if (input.workflow === "parallel" && Array.isArray(args.tasks)) return args.tasks.flatMap((t, i) => one(t, `task-${i + 1}`));
	if (input.workflow !== undefined) return []; // a script: its tasks are code
	if (Array.isArray(input.tasks)) return input.tasks.flatMap((t, i) => one(t, `task-${i + 1}`));
	if (Array.isArray(input.chain)) return input.chain.flatMap((s, i) => one(s, `step-${i + 1}`));
	if (typeof input.task === "string") return [{ key: "", text: input.task, cwd: at(input) }];
	return [];
}

function subagentCalls(entry: Entry): Part[] {
	const m = entry.message;
	if (entry.type !== "message" || m?.role !== "assistant" || !Array.isArray(m.content)) return [];
	return (m.content as Part[]).filter((p) => p?.type === "toolCall" && p.name === "subagent");
}

export interface Run {
	runId: string;
	at: number;
	tasks: Task[];
}

/** This session's async runs, which have ended, and which of their children have finished. */
export function runsIn(entries: Entry[], cwd: string, now: number): { runs: Run[]; ended: Set<string>; finished: Set<string> } {
	const pending = new Map<string, Task[]>();
	const runs: Run[] = [];
	const ended = new Set<string>();
	const finished = new Set<string>(); // `${runId} ${key}`
	for (const e of entries) {
		for (const call of subagentCalls(e)) if (call.id) pending.set(call.id, tasksOf(call.arguments ?? {}, cwd));
		const m = e.message;
		if (e.type === "message" && m?.role === "toolResult" && m.toolName === "subagent" && !m.isError) {
			const text = textOf(m.content);
			const tasks = m.toolCallId ? pending.get(m.toolCallId) : undefined;
			const runId = /\bAsync\b[^\n[]*\[([0-9a-f-]{36})\]/i.exec(text)?.[1];
			if (runId && tasks?.length) runs.push({ runId: runId.toLowerCase(), at: Date.parse(e.timestamp ?? "") || now, tasks });
			// a status the model asked for, of a run that is no longer going
			const status = /^Run: ([0-9a-f-]{36})$/m.exec(text)?.[1];
			const state = /^State: (\w+)/m.exec(text)?.[1];
			if (status && state && !/^(running|queued|pending|starting)$/i.test(state)) ended.add(status.toLowerCase());
		}
		if (e.type === "custom_message" && String(e.customType ?? "").startsWith("subagent")) {
			const text = textOf(e.content);
			const child = /child completed: \*\*([^*\n]+)\*\*[\s\S]*?Workflow run: ([0-9a-f-]{36})/i.exec(text);
			if (child) finished.add(`${child[2].toLowerCase()} ${child[1]}`);
			else if (e.customType === "subagent-notify" || /^Background task\b/.test(text))
				for (const id of text.match(UUID) ?? []) ended.add(id.toLowerCase());
		}
	}
	return { runs, ended, finished };
}

/**
 * Files held by children of this session's runs that are still going: absolute path
 * (as compared) to the child that owns it.
 */
export function heldFiles(entries: Entry[], cwd: string, now: number, home: string = homedir()): Map<string, Owner> {
	const { runs, ended, finished } = runsIn(entries, cwd, now);
	const held = new Map<string, Owner>();
	for (const run of runs) {
		if (ended.has(run.runId) || now - run.at > RUN_EXPIRY_MS) continue;
		for (const task of run.tasks) {
			if (finished.has(`${run.runId} ${task.key}`)) continue;
			for (const path of ownedPaths(task, home)) held.set(same(path), { key: task.key, path, runId: run.runId });
		}
	}
	return held;
}

export interface ChildScope {
	/** This child's key in the parent's call, when its task was found there. */
	key?: string;
	/** The run that started it, when its launch is in the branch (a forked child). */
	runId?: string;
	/** Files this child's own task outputs. */
	own: Set<string>;
	/** Files only a sibling's task names, to the sibling. */
	siblings: Map<string, Owner>;
	/** How many tasks the parent's call started. */
	total: number;
	/** This child's task, as written. */
	task: string;
}

/**
 * What a child owns: its own task's files, and the files only its siblings' tasks name - found in the
 * call that started it, which a forked child has in its own branch and a fresh one (qwen's default
 * since 2026-11-13) finds in `parent`, the parent's session.
 */
export function childScope(entries: Entry[], cwd: string, home: string = homedir(), parent?: Entry[]): ChildScope {
	// This session's task: the last forked-task message, else (a fresh child) the first user message.
	let taskAt = -1;
	let taskText = "";
	entries.forEach((e, i) => {
		if (e.type !== "message" || e.message?.role !== "user") return;
		const text = textOf(e.message.content);
		const fork = FORK_TASK.exec(text);
		if (fork) [taskAt, taskText] = [i, fork[1]];
		else if (taskAt < 0 && !taskText) taskText = text;
	});
	const own = new Set(ownedPaths({ key: "", text: taskText, cwd }, home).map(same));
	const scope: ChildScope = { own, siblings: new Map(), total: 0, task: taskText };
	const forked = taskAt >= 0;
	if (!forked && !(parent?.length && taskText.trim())) return scope;
	// The call that started it: the last subagent call before its task with more than one task (in a
	// fresh child's parent, the last one with this task among them), and the run id its result gave.
	let tasks: Task[] = [];
	let callId: string | undefined;
	for (const e of forked ? entries.slice(0, taskAt) : (parent ?? [])) {
		for (const call of subagentCalls(e)) {
			const found = tasksOf(call.arguments ?? {}, cwd);
			const ours = forked || found.some((t) => t.text.trim() && taskText.includes(t.text.trim()));
			if (found.length > 1 && ours) [tasks, callId, scope.runId] = [found, call.id, undefined];
		}
		const m = e.message;
		if (e.type === "message" && m?.role === "toolResult" && m.toolName === "subagent" && callId && m.toolCallId === callId)
			scope.runId = /\bAsync\b[^\n[]*\[([0-9a-f-]{36})\]/i.exec(textOf(m.content))?.[1]?.toLowerCase();
	}
	const mine = tasks.filter((t) => t.text.trim() && taskText.includes(t.text.trim()));
	if (mine.length === 0) return scope;
	scope.key = mine[0].key;
	scope.total = tasks.length;
	for (const t of mine) for (const p of ownedPaths(t, home)) own.add(same(p));
	for (const t of tasks) {
		if (mine.includes(t)) continue;
		for (const path of ownedPaths(t, home)) {
			if (!own.has(same(path))) scope.siblings.set(same(path), { key: t.key, path });
		}
	}
	return scope;
}

/** The files a writing tool's input changes. */
export function targets(input: Record<string, unknown>): string[] {
	return [input.path, input.file, input.filePath, input.file_path, input.to, input.destination, input.dest]
		.filter((v): v is string => typeof v === "string" && v.length > 0);
}

function shown(path: string, cwd: string): string {
	const rel = relative(cwd, path);
	return rel && !rel.startsWith("..") && !isAbsolute(rel) ? rel : path;
}

export function siblingReason(path: string, owner: Owner, cwd: string): string {
	const name = shown(path, cwd);
	return `${name} is ${owner.key}'s file: a sibling child of the same run is writing it from its own task, now. ` +
		"Write only the files your task names - not to fix theirs, not to make them match yours, and not because " +
		`one looks missing (it may not be written yet). If ${name} has to change for your work to fit, say so in ` +
		"your report; the parent reconciles the pieces when every child has finished.";
}

export function changedReason(path: string, cwd: string): string {
	const name = shown(path, cwd);
	return `${name} changed after you started, and not through your tools: another agent or the user is working ` +
		`on it. Read it before you replace it. If it is not part of your task, leave it, and say in your report ` +
		"what it should contain.";
}

export function heldReason(path: string, owner: Owner, cwd: string): string {
	const name = shown(path, cwd);
	const who = owner.key ? `${owner.key} of run ${owner.runId?.slice(0, 8)}` : `run ${owner.runId?.slice(0, 8)}`;
	const notice = owner.key ? `"Workflow child completed: **${owner.key}**"` : "the run's \"Background task\"";
	return `${name} is named in the task of ${who}, which is still running and may write it again. Change it after ` +
		`${notice} or the run's final notice arrives; to change course now, steer that child (subagent action ` +
		'"steer"). If nothing else needs doing meanwhile, end your turn: the notice wakes you.';
}

export function scopeNote(scope: ChildScope, cwd: string): string | undefined {
	if (scope.siblings.size === 0) return undefined;
	const byKey = new Map<string, string[]>();
	for (const owner of scope.siblings.values()) byKey.set(owner.key, [...(byKey.get(owner.key) ?? []), shown(owner.path, cwd)]);
	const list = [...byKey].slice(0, 16).map(([key, files]) => `${key}: ${files.slice(0, 6).join(", ")}`).join("; ");
	return [
		"# Your part of a shared job",
		"",
		`The request at the top of this conversation went to the parent, which split it into ${scope.total} tasks ` +
			`that run at the same time as yours. Yours is ${scope.key}, the task above; the rest of the request is ` +
			"theirs. These files are the other children's - do not create, change or replace them: " +
			`${list}. A file of theirs that does not exist yet is being written, not missing: do not wait for it, ` +
			"poll for it or write it, and build yours from your task alone. Do not wait for, check on or steer the " +
			"parent's run either: it is not yours. Where your work " +
			"has to agree with theirs and your task does not say how, decide, and say what you decided in your " +
			"report; the parent puts the pieces together.",
	].join("\n");
}

/** One thing a child did to a file: wrote it, or was refused it (and whose it was). */
export interface LedgerLine {
	key: string;
	path: string;
	tool: string;
	refused?: string;
}

/** Where a run's children record what they wrote: one file per run, in this user's temp folder. */
export function ledgerPath(runId: string): string {
	const uid = typeof process.getuid === "function" ? process.getuid() : "user";
	return join(process.env.ELM_PI_LEDGER_DIR || join(tmpdir(), `elm-pi-runs-${uid}`), `${runId}.jsonl`);
}

function readLedger(runId: string): LedgerLine[] {
	try {
		return readFileSync(ledgerPath(runId), "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l) as LedgerLine);
	} catch {
		return [];
	}
}

/** The parent's account of a finished run: each child's files, from the children's own records. */
export function ledgerNote(run: Run, lines: LedgerLine[], cwd: string, home: string = homedir()): string | undefined {
	if (lines.length === 0) return undefined;
	const rows = run.tasks.map((task) => {
		const mine = lines.filter((l) => l.key === task.key);
		const owned = new Set(ownedPaths(task, home).map(same));
		const wrote = [...new Set(mine.filter((l) => !l.refused).map((l) => l.path))];
		const inside = wrote.filter((p) => owned.has(same(p))).map((p) => shown(p, cwd));
		const outside = wrote.filter((p) => !owned.has(same(p))).map((p) => shown(p, cwd));
		const refused = [...new Set(mine.filter((l) => l.refused).map((l) => `${shown(l.path, cwd)} (${l.refused})`))];
		const parts = [inside.length ? inside.join(", ") : "none of its own files"];
		if (outside.length) parts.push(`also ${outside.join(", ")}, which its task does not name`);
		if (refused.length) parts.push(`refused: ${refused.join(", ")}`);
		return `- ${task.key || "the child"}: ${parts.join("; ")}`;
	});
	return [
		`# What the children of run ${run.runId.slice(0, 8)} wrote`,
		"",
		"From each child's own record of its writes, not from its report:",
		...rows,
		"",
		"Tell the user who did what as this shows it, not as the reports claim.",
	].join("\n");
}

/** The folders directly in `dir`, hidden ones left out. */
function subfolders(dir: string): string[] {
	try {
		return readdirSync(dir, { withFileTypes: true })
			.filter((e) => e.isDirectory() && !e.name.startsWith("."))
			.slice(0, 50)
			.map((e) => join(dir, e.name));
	} catch {
		return [];
	}
}

/** A page or document: what a child told to make one should be making. */
const PAGE_OUTPUT = /\.(?:html?|php|md|markdown|tex|rst)$/i;

/**
 * Whether a child may create `path`, a file that does not exist yet. A child that is one of
 * several, told to make a page or document, makes that: in test10 (2026-11-13) three children
 * each building one page of a site took on the user's "download images from the internet"
 * themselves, failed, and wrote placeholder drawings - two of them over each other's - into an
 * images/ folder none of their tasks named, while the parent fetched the real photos. So such a
 * child may create the files its task names, files in a folder its task names ("images/",
 * "the images folder"), and scratch - under a hidden folder or the temp folder - and nothing
 * else. Changing an existing file is left to the checks before this one.
 */
export function mayCreate(scope: ChildScope, path: string, cwd: string, home: string = homedir()): boolean {
	if (scope.total < 2 || ![...scope.own].some((p) => PAGE_OUTPUT.test(p))) return true;
	if (scope.own.has(same(path))) return true;
	if (namedPaths(scope.task, cwd, home).some((p) => same(p) === same(path))) return true;
	// Scratch: under a hidden folder, or in the temp folder outside the project (which may itself be in it).
	const inProject = same(path).startsWith(`${same(cwd)}/`) || [...scope.own].some((p) => same(path).startsWith(`${dirname(p)}/`));
	if (path.split("/").some((part) => part.startsWith(".") && part.length > 1)) return true;
	if (!inProject && [tmpdir(), "/tmp", "/private/tmp"].some((t) => path.startsWith(`${t}/`))) return true;
	const task = scope.task.toLowerCase();
	// scope.own holds paths as compared (case-folded on macOS), so both sides are compared that way.
	const bases = [same(cwd), ...[...scope.own].map(dirname)];
	return bases.some((base) => {
		const folder = relative(base, same(dirname(path)));
		if (!folder || folder.startsWith("..")) return false;
		const last = folder.split("/").pop() ?? folder;
		return task.includes(`${folder}/`) || new RegExp(`\\b${last.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s+(?:folder|directory)\\b`).test(task);
	});
}

export function notInTaskReason(path: string, scope: ChildScope, cwd: string): string {
	const mine = [...scope.own].map((p) => shown(p, same(cwd))).join(", "); // scope.own is case-folded on macOS
	return (
		`${shown(path, cwd)} is not in your task, which is ${mine || "your own file"}. The rest of the user's request went to ` +
		"the parent and your siblings: do not take it on. If your page needs a picture or diagram, draw it inside your own " +
		"file (an inline <svg>), or say in your report what is missing, for the parent. Scratch files go in /tmp."
	);
}

/** Files a page links to rather than builds on: a sibling page need not exist for a link to it. */
const PAGE_FILE = /\.(?:html?|php|md|markdown|txt|rst|pdf)$/i;
/**
 * A task that is to start once the others are done. Tasks started side by side start together: test12
 * (2026-11-13) launched "COORDINATOR TASK: After the other 4 agents complete their pages: ... update
 * all HTML files" beside those four, and it ran at once - refused one page, wrote a stylesheet
 * nobody linked, and reported one line - while the pages came back unstyled.
 */
const AFTER_OTHERS =
	/\b(?:after|once|when)\s+(?:all\s+)?(?:of\s+)?(?:the\s+)?(?:other|remaining)\s+(?:\w+\s+){0,2}?(?:agents?|tasks?|children|sub-?agents?|workers?|pages?)\b|\bwait\s+(?:for|until)\s+(?:all\s+)?(?:the\s+)?(?:other|remaining)\b/i;

/** A task told to share something with its siblings without being given the file it is in. */
const SHARED_THING =
	/\b(?:shared|consistent|same|common|matching|identical|uniform)\s+(?:[\w-]+\s+){0,2}?(?:css|stylesheets?|style\s?sheets?|styles?|styling|navigation|nav(?:bar)?|menus?|headers?|footers?|templates?)\b/i;
/** The same said the other way round: "footer consistent with other pages", "navigation menu (same as index)". */
const SHARED_AFTER =
	/\b(?:css|stylesheets?|styles?|styling|navigation|nav(?:bar)?|menus?|headers?|footers?|templates?)\s+(?:[\w-]+\s+)?\(?(?:consistent|same|identical|matching|uniform)\s+(?:with|as|across)\b/i;
const SHARED_NOUN = /\b(?:css|stylesheets?|styles?|styling|classes|navigation|nav(?:bar)?|menus?|headers?|footers?|templates?|layout|design)\b/i;
const COPY_WORD = /\b(?:match(?:es|ing)?|copy|same|consistent|identical|exact(?:ly)?|follow|mirror|reuse|like)\b/i;
const COPY_FROM = /\b(?:from|as(?:\s+(?:in|on))?|with|like|matching|match|copy(?:ing)?|mirror(?:ing)?)\s+(?:the\s+)?(?:one\s+(?:in|on)\s+|that\s+of\s+|those\s+(?:in|of|on)\s+)?$/i;

/**
 * The page files a task takes its shared parts from, among the pages its siblings are writing. auto01
 * (2026-11-13): four of five page tasks said "Match the exact CSS classes, navigation structure, and
 * footer from index.html" while task-1 wrote index.html - a file none of them could see yet.
 */
function fromSiblingPages(task: Task, tasks: Task[], home: string): string[] {
	const theirs = new Map<string, string>();
	for (const t of tasks)
		if (t !== task) for (const p of outputPaths(t.text, t.cwd, home)) if (PAGE_FILE.test(p)) theirs.set(basename(p).toLowerCase(), t.key);
	const own = new Set(outputPaths(task.text, task.cwd, home).map((p) => basename(p).toLowerCase()));
	const found = new Set<string>();
	for (const sentence of task.text.split(/(?<=[.!?])\s+|\n+/)) {
		if (!SHARED_NOUN.test(sentence) || !COPY_WORD.test(sentence)) continue;
		for (const m of sentence.matchAll(PATH_IN_TEXT)) {
			const name = basename(m[1]).toLowerCase();
			// what is copied from, not a page the menu links to: "as index.html", "from index.html"
			const before = sentence.slice(Math.max(0, (m.index ?? 0) - 40), (m.index ?? 0) + m[0].indexOf(m[1]));
			if (!COPY_FROM.test(before)) continue;
			if (theirs.has(name) && !own.has(name)) found.add(basename(m[1]));
		}
	}
	return [...found];
}

/**
 * Why a fan-out cannot start yet, or undefined. Children started side by side cannot see each
 * other's files, so a file two of them build on - the stylesheet, a shared script, a module -
 * has to exist before they start; so does whatever they are told to share (a header, the
 * navigation, a footer, "the shared CSS") when no task names an existing file it is in.
 * elm-delegation's rule 3 says so, and test8 and test9 (2026-11-12) launched anyway: in test8
 * six children were told to "link to shared CSS" the parent wrote while they ran - one guessed
 * styles.css, the pages came back with four different footers; in test9 the stylesheet was one
 * child's task and the other four styled their pages against a file they could not see. A
 * relative path counts as there when it is under the cwd or beside one of the task's outputs.
 */
export function sharedGaps(
	input: Record<string, unknown>,
	cwd: string,
	exists: (path: string) => boolean,
	home: string = homedir(),
	folders: (dir: string) => string[] = subfolders,
): string | undefined {
	const parallel = input.workflow === "parallel" || (input.workflow === undefined && Array.isArray(input.tasks));
	const tasks = parallel ? tasksOf(input, cwd) : [];
	if (tasks.length < 2) return undefined;
	const there = (task: Task, written: string) => {
		const outputs = outputPaths(task.text, task.cwd, home);
		// Folders the task names, too: "... for the red squirrel website at /Users/.../red-squirrel-website/"
		// with "images/red-squirrel-portrait.jpg" beside it. auto15 (2026-11-13) was refused three times over
		// pictures it had already downloaded there, and wrote all five pages itself.
		const named = [...task.text.matchAll(DIR_IN_TEXT)].map((m) => resolveIn(m[1], task.cwd, home)).filter((d) => exists(d));
		const bases = [task.cwd, ...outputs.map(dirname), ...named];
		const rel = isAbsolute(written) || written.startsWith("~/") ? undefined : written;
		if (!rel) return exists(resolveIn(written, task.cwd, home));
		if (bases.some((b) => exists(resolve(b, rel)))) return true;
		// A bare name may be in a folder the task names apart from it - "images/ (contains
		// red-squirrel-1.jpg and red-squirrel-2.jpg)", in a live run that was refused for it.
		return !rel.includes("/") && bases.some((b) => folders(b).some((d) => exists(join(d, rel))));
	};
	// file as written (relative ones compared as written) -> the tasks naming it, and the one making it
	const deps = new Map<string, { keys: string[]; makers: string[]; missing: boolean; spelling: string }>();
	const existingNamed = new Set<string>(); // keys of tasks that name an existing file other than their own outputs
	for (const task of tasks) {
		const own = new Set(outputPaths(task.text, task.cwd, home).map(same));
		const seen = new Set<string>();
		for (const m of task.text.matchAll(PATH_IN_TEXT)) {
			const written = m[1];
			if (written.startsWith("//")) continue;
			const abs = resolveIn(written, task.cwd, home);
			const exists = there(task, written);
			if (exists && !own.has(same(abs))) existingNamed.add(task.key);
			if (PAGE_FILE.test(written)) continue;
			const id = isAbsolute(written) || written.startsWith("~/") ? same(abs) : written.replace(/^\.\//, "").toLowerCase();
			if (seen.has(id)) continue;
			seen.add(id);
			// Shown as written, made relative: the id is lower-cased on a case-insensitive disk (auto03, 2026-11-13,
			// showed "~/sandbox/..." as "../../../../users/...").
			const dep = deps.get(id) ?? { keys: [], makers: [], missing: true, spelling: isAbsolute(written) || written.startsWith("~/") ? abs : written };
			dep.keys.push(task.key);
			const rel = id.startsWith("/") ? undefined : `/${same(id)}`;
			if (own.has(same(abs)) || (rel && [...own].some((o) => o.endsWith(rel)))) dep.makers.push(task.key);
			if (exists) dep.missing = false;
			deps.set(id, dep);
		}
	}
	const keyList = (keys: string[]) => (keys.length > 2 ? `${keys.slice(0, -1).join(", ")} and ${keys[keys.length - 1]}` : keys.join(" and "));
	const lines: string[] = [];
	for (const [id, dep] of deps) {
		if (dep.keys.length < 2 || !dep.missing) continue;
		const name = isAbsolute(dep.spelling) ? (/^\.\.(\/|$)/.test(relative(cwd, dep.spelling)) ? dep.spelling : relative(cwd, dep.spelling)) || dep.spelling : dep.spelling;
		// test14: "Link to ../css/style.css" from pages in the launch folder, where the parent had just
		// written css/style.css - the tasks pointed one folder up.
		const up = /^(?:\.\.\/)+/.exec(name)?.[0];
		// Beside the launch folder, or beside the pages the tasks write (auto07: "../css/style.css" from
		// pages in hedgehog-site/, whose css/style.css the parent had written).
		const stripped = up ? name.slice(up.length) : "";
		const bases = [cwd, ...tasks.filter((t) => dep.keys.includes(t.key)).flatMap((t) => outputPaths(t.text, t.cwd, home).map(dirname))];
		const near = up && !dep.makers.length && bases.some((b) => exists(resolve(b, stripped))) ? stripped : undefined;
		lines.push(
			`- ${name}: named by ${keyList(dep.keys)}, and not there yet` +
				(dep.makers.length
					? ` (${keyList(dep.makers)} ${dep.makers.length > 1 ? "are" : "is"} to write it, while the others build on it).`
					: near
						? ` - ${near} is: "${up}" climbs out of the folder the tasks run in. Name it ${near}.`
						: "."),
		);
	}
	// Only for pages and documents: "the same plotting style" for figures can be said in the task itself.
	const madePages = (t: Task) => outputPaths(t.text, t.cwd, home).some((p) => /\.(?:html?|php|md|markdown|tex|rst)$/i.test(p));
	for (const task of tasks)
		if (AFTER_OTHERS.test(task.text))
			lines.push(
				`- ${task.key} is to start after the others finish, but tasks run side by side start together: run it after ` +
					"them - a chain, or yourself once this run ends.",
			);
	const copying = new Map<string, string[]>(); // a sibling's page -> the tasks told to take their shared parts from it
	for (const task of tasks)
		for (const page of fromSiblingPages(task, tasks, home)) {
			if (there(task, page)) continue;
			copying.set(page, [...(copying.get(page) ?? []), task.key]);
		}
	for (const [page, keys] of copying)
		lines.push(
			`- ${keyList(keys)} ${keys.length > 1 ? "are" : "is"} told to take ${keys.length > 1 ? "their" : "its"} styling, ` +
				`navigation or footer from ${page}, which a sibling is writing at the same time: none of them can see it before it is done.`,
		);
	const shares = (t: Task) => SHARED_THING.test(t.text) || SHARED_AFTER.test(t.text);
	const vague = tasks.filter((t) => shares(t) && !existingNamed.has(t.key) && madePages(t));
	if (vague.length >= 2 && copying.size === 0) {
		const all = [new RegExp(SHARED_THING.source, "gi"), new RegExp(SHARED_AFTER.source, "gi")];
		const what = [...new Set(vague.flatMap((t) => all.flatMap((re) => [...t.text.matchAll(re)].map((m) => m[0].toLowerCase()))))]
			.map((w) => w.replace(/\(/g, "").replace(/\s+/g, " ").trim())
			.slice(0, 3)
			.map((w) => `"${w}"`);
		lines.push(`- ${keyList(vague.map((t) => t.key))} are told to share ${what.join(", ")}, but name no existing file to take it from.`);
	}
	if (lines.length === 0) return undefined;
	const waits = lines.some((l) => l.includes("is to start after the others finish"));
	const misnamed = lines.some((l) => l.includes(" climbs out of the folder"));
	const shared = lines.some((l) => !l.includes("is to start after the others finish") && !l.includes(" climbs out of the folder"));
	return [
		shared
			? "Not launched: children started side by side cannot see each other's files, so what they share has to exist before they start."
			: misnamed
				? "Not launched: the tasks name a file they share where it is not."
				: "Not launched: children started side by side start together and cannot wait for each other.",
		...lines,
		shared
			? "Write those first - the stylesheet, and one finished page or a template with the header, navigation and footer every page " +
				"repeats - then launch again, naming those files in every task with the exact class names, and telling each child to copy " +
				"the shared parts exactly and to write only its own file."
			: [
					misnamed ? "Correct the name in every task and launch again." : "",
					waits ? "Launch the others now and that one after them, or do its part yourself once they are done." : "",
				]
					.filter(Boolean)
					.join(" "),
	].join("\n");
}

/** A folder a task names: an absolute or home path ending in "/". */
const DIR_IN_TEXT = /(?:^|[\s"'`(])((?:~\/|\/)[\w@%+~.\-/]*\/)(?=$|[\s"'`).,;:])/g;

/** Telling a child to fetch something from the web (in a session that cannot: PI_ELM_WEB unset). */
const DOWNLOAD_ASK =
	/\b(?:download\w*|fetch\w*|curl|wget)\b[\s\S]{0,120}\b(?:internet|web|online|wikimedia|wikipedia|unsplash|pexels|flickr|https?:\/\/)/i;
/** Telling a child to use a web tool. */
const WEB_ASK = /\b(?:web_search|fetch_content|get_search_content|source_check)\b|\bsearch(?:ing)?\s+(?:the\s+)?(?:web|internet)\b|\bweb\s+search(?:es)?\b/i;

/**
 * A launch that tells a child to use web tools it does not have. Only pi-subagents' `researcher` has
 * them (and only under `pi --remote`); a qwen child is given none. auto02 (2026-11-13) told one to
 * "Use web_search to verify facts": "Tool web_search not found", then 32 turns and 1.8M tokens of
 * working from memory, ending in writes to three pages that were other children's.
 */
export function webWithoutTools(input: Record<string, unknown>, web: boolean = process.env.PI_ELM_WEB === "1"): string | undefined {
	const args = (input.args ?? {}) as Record<string, unknown>;
	const list = (input.tasks ?? args.tasks ?? input.chain ?? (input.task ? [input] : [])) as unknown[];
	const flat: { agent: string; task: string }[] = [];
	const walk = (items: unknown[]) => {
		for (const item of items ?? []) {
			const t = item as Record<string, unknown>;
			if (Array.isArray(t.parallel)) walk(t.parallel);
			else if (typeof t.task === "string") flat.push({ agent: String(t.agent ?? input.agent ?? ""), task: t.task });
		}
	};
	walk(Array.isArray(list) ? list : []);
	const keyed = flat.map((t, i) => ({ ...t, key: flat.length > 1 ? `task-${i + 1}` : "the task" }));
	// auto04 (2026-11-13, no --remote): children told to download bee photos from Wikimedia and Unsplash were
	// refused by the proxy 19 times, and one drew labelled placeholders instead.
	// With the web: two or more children fetching pictures at once. test14 and auto11 (2026-11-13) gave every
	// page child its own pictures to find: guessed names, then Wikimedia's 429s and searches that came back as
	// error pages, for all of them at once.
	if (web) {
		const several = keyed.filter((t) => DOWNLOAD_ASK.test(t.task));
		if (several.length >= 2)
			return (
				`Not launched: ${several.map((t) => t.key).join(", ")} are each told to download from the web. Children fetching ` +
				"at the same time get rate-limited (Wikimedia answers a burst with 429s and error pages) and each search the " +
				"same thing. Fetch every picture in one place first - yourself, or one agent - then launch the pages with the " +
				"files they use named in their tasks."
			);
	}
	const fetching = web ? [] : keyed.filter((t) => DOWNLOAD_ASK.test(t.task));
	if (fetching.length)
		return (
			`Not launched: ${fetching.map((t) => t.key).join(", ")} ${fetching.length > 1 ? "are" : "is"} told to download from the web, ` +
			"and this session cannot reach it (it was started without `pi --remote`; the proxy refuses every site but ELM " +
			"and the package indexes). Tell the user, and launch the rest without it."
		);
	const keys = keyed.filter((t) => t.agent !== "researcher" && WEB_ASK.test(t.task));
	if (keys.length === 0) return undefined;
	const who = keys.map((t) => `${t.key} (${t.agent || "the default agent"})`).join(", ");
	return (
		`Not launched: ${who} ${keys.length > 1 ? "are" : "is"} told to search the web, and that child has no web tools - ` +
		"only the `researcher` agent has them. " +
		(web
			? "Look the facts up yourself first and put them in its task, or give the research to `researcher` and the writing to the others once it reports."
			: "This session has no web access at all (that needs `pi --remote`): write from what you know and say so, or ask the user.")
	);
}

export default function (pi: ExtensionAPI) {
	const started = Date.now();
	const running = new Map<string, number>(); // toolCallId -> start
	/** This session's own tool calls: when, and what they named (a command's text, a tool's paths). */
	const spans: { from: number; to: number; named: string }[] = [];
	const seen = new Map<string, number>(); // path -> when the child last read or wrote it
	const isChild = () => process.env.PI_SUBAGENT_CHILD === "1";
	/** A workflow agent's session: pi-dynamic-workflows gives each one its run's store tools, and no other session has them. */
	const workflowAgent = () => {
		const tools = pi.getActiveTools?.() ?? [];
		return tools.includes("store_put") && tools.includes("store_get");
	};

	/** The first of `paths` that changed after this session started, not through its own tools, and that it has not read since. */
	const changedUnseen = (paths: string[], own: Set<string>): string | undefined => {
		for (const path of paths) {
			if (own.has(same(path))) continue;
			let mtime: number;
			try {
				const info = statSync(path);
				if (!info.isFile()) continue;
				mtime = info.mtimeMs;
			} catch {
				continue; // a new file
			}
			const since = Math.max(started, seen.get(same(path)) ?? 0) + SLACK_MS;
			// Changed during one of this session's own calls that named it. Only one that named it: a
			// live probe (2026-11-13) had a workflow agent's `sleep 8` "make" the file another agent
			// wrote meanwhile, and the sleeping one then replaced it unread. A command that writes a
			// file without naming it is refused once and reads it first - one read, against a lost file.
			const file = basename(path);
			const mine = spans.some((s) => mtime >= s.from - SLACK_MS && mtime <= s.to + SLACK_MS && s.named.includes(file));
			if (mtime > since && !mine) return path;
		}
		return undefined;
	};

	/** A fresh child's parent session, which holds the call that started it (cached by size). */
	let parentCache: { file: string; size: number; entries: Entry[] } | undefined;
	const parentEntries = (cwd: string): Entry[] | undefined => {
		const id = process.env.PI_SUBAGENT_PARENT_SESSION;
		if (!isChild() || !id) return undefined;
		try {
			const dir = join(cwd, ".pi/sessions");
			const name = readdirSync(dir).find((n) => n.endsWith(".jsonl") && n.includes(id));
			if (!name) return undefined;
			const file = join(dir, name);
			const size = statSync(file).size;
			if (parentCache?.file !== file || parentCache.size !== size) {
				const entries = readFileSync(file, "utf8")
					.split("\n")
					.filter(Boolean)
					.flatMap((l) => {
						try {
							return [JSON.parse(l) as Entry];
						} catch {
							return [];
						}
					});
				parentCache = { file, size, entries };
			}
			return parentCache.entries;
		} catch {
			return undefined;
		}
	};
	const scopeOf = (entries: Entry[], cwd: string) => childScope(entries, cwd, homedir(), parentEntries(cwd));

	const record = (scope: ChildScope, line: Omit<LedgerLine, "key">) => {
		if (!scope.runId || !scope.key) return;
		try {
			const file = ledgerPath(scope.runId);
			mkdirSync(dirname(file), { recursive: true, mode: 0o700 });
			appendFileSync(file, `${JSON.stringify({ key: scope.key, ...line })}\n`);
		} catch {
			// a missing record costs the parent's summary, never the write
		}
	};

	/** The who-wrote-what notes for these ended runs that this session has not been given yet. */
	const untold = (entries: Entry[], ended: (runId: string) => boolean, cwd: string): string[] => {
		const said = entries.map((e) => textOf(e.message?.content ?? e.content)).join("\n");
		return runsIn(entries, cwd, Date.now())
			.runs.filter((run) => ended(run.runId) && !said.includes(`# What the children of run ${run.runId.slice(0, 8)} wrote`))
			.map((run) => ledgerNote(run, readLedger(run.runId), cwd))
			.filter((note): note is string => Boolean(note));
	};

	pi.on("before_agent_start", (event, ctx) => {
		const entries = ctx.sessionManager.getBranch() as Entry[];
		if (!isChild()) {
			// Interactive: the turn a run's final notice starts begins with what its children wrote.
			// pi adds that notice to the branch after this event (test8 and test9, 2026-11-12: the
			// note never arrived), so it is read from the event as well.
			const all: Entry[] =
				event.messageType === "custom"
					? [...entries, { type: "custom_message", customType: event.message.customType, content: event.message.content }]
					: entries;
			const { ended } = runsIn(all, ctx.cwd, Date.now());
			const notes = untold(all, (id) => ended.has(id), ctx.cwd);
			return notes.length ? { message: { customType: LEDGER_TYPE, content: notes.join("\n\n"), display: false } } : undefined;
		}
		if (event.messageType !== "user") return undefined;
		if (entries.some((e) => e.type === "custom_message" && e.customType === NOTE_TYPE)) return undefined;
		// pi adds the prompt to the branch after this event: the child's task is still only here.
		const withTask = [...entries, { type: "message", message: { role: "user", content: event.prompt } }];
		const note = scopeNote(scopeOf(withTask, ctx.cwd), ctx.cwd);
		return note ? { message: { customType: NOTE_TYPE, content: note, display: false } } : undefined;
	});

	pi.on("tool_call", async (event, ctx) => {
		running.set(event.toolCallId, Date.now());
		if (event.toolName === "subagent") {
			const input = (event.input ?? {}) as Record<string, unknown>;
			const reason = webWithoutTools(input) ?? sharedGaps(input, ctx.cwd, existsSync);
			return reason ? { block: true, reason } : undefined;
		}
		if (!WRITING_TOOLS.has(event.toolName)) return undefined;
		const input = (event.input ?? {}) as Record<string, unknown>;
		const paths = targets(input).map((p) => resolveIn(p, ctx.cwd, homedir()));
		if (paths.length === 0) return undefined;
		const entries = ctx.sessionManager.getBranch() as Entry[];
		// Whole-file replacements: what the unseen-change rule below looks at.
		const replaced = event.toolName === "write" ? paths : event.toolName === "copy" || event.toolName === "move" ? paths.slice(-1) : [];
		if (!isChild()) {
			const held = heldFiles(entries, ctx.cwd, Date.now());
			for (const path of paths) {
				const owner = held.get(same(path));
				if (owner) return { block: true, reason: heldReason(path, owner, ctx.cwd) };
			}
			// A workflow agent (pi --workflows) runs in this process, beside the others of its run, with
			// no task this guard can read: the one rule that needs none - do not replace, unread, a file
			// someone else changed since you started - is what keeps two of them off each other's work.
			if (workflowAgent()) {
				const path = changedUnseen(replaced, new Set());
				if (path) return { block: true, reason: changedReason(path, ctx.cwd) };
			}
			return undefined;
		}
		const scope = scopeOf(entries, ctx.cwd);
		for (const path of paths) {
			const owner = scope.siblings.get(same(path));
			if (owner) {
				record(scope, { path, tool: event.toolName, refused: `${owner.key}'s` });
				return { block: true, reason: siblingReason(path, owner, ctx.cwd) };
			}
		}
		for (const path of paths) {
			if (existsSync(path) || mayCreate(scope, path, ctx.cwd)) continue;
			record(scope, { path, tool: event.toolName, refused: "not in its task" });
			return { block: true, reason: notInTaskReason(path, scope, ctx.cwd) };
		}
		// Replacing a whole file someone else changed meanwhile, unseen.
		const path = changedUnseen(replaced, scope.own);
		if (path) {
			record(scope, { path, tool: event.toolName, refused: "changed by another, unread" });
			return { block: true, reason: changedReason(path, ctx.cwd) };
		}
		return undefined;
	});

	pi.on("tool_result", async (event, ctx) => {
		const from = running.get(event.toolCallId) ?? Date.now();
		running.delete(event.toolCallId);
		const given = (event.input ?? {}) as Record<string, unknown>;
		const cells = Array.isArray(given.cells) ? given.cells.map((c: { code?: unknown }) => String(c?.code ?? "")).join("\n") : "";
		spans.push({ from, to: Date.now(), named: [String(given.command ?? ""), cells, ...targets(given)].join("\n") });
		if (!isChild() && event.toolName === "bg_wait" && !event.isError) {
			// `pi -p`: the parent waits inside its turn, and bg_wait's result names each run it saw end.
			const text = textOf(event.content);
			const done = new Set([...text.matchAll(/(?:Workflow receipt|Result) \[([0-9a-f-]{36})\]/gi)].map((m) => m[1].toLowerCase()));
			const notes = untold(ctx.sessionManager.getBranch() as Entry[], (id) => done.has(id), ctx.cwd);
			return notes.length ? { content: [...event.content, { type: "text" as const, text: notes.join("\n\n") }] } : undefined;
		}
		if (event.isError || !SEEING_TOOLS.has(event.toolName)) return undefined;
		const paths = targets((event.input ?? {}) as Record<string, unknown>).map((p) => resolveIn(p, ctx.cwd, homedir()));
		for (const path of paths) seen.set(same(path), Date.now());
		if (isChild() && WRITING_TOOLS.has(event.toolName)) {
			const scope = scopeOf(ctx.sessionManager.getBranch() as Entry[], ctx.cwd);
			for (const path of paths) record(scope, { path, tool: event.toolName });
		}
		return undefined;
	});
}
