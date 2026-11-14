/**
 * Report guard: no report file nobody asked for.
 *
 * Asked for a website, test6's agent (2026-11-12) also wrote README.md calling it "100%
 * self-consistent"; asked to check its links, it wrote LINK_VERIFICATION.md. In test7 a
 * sub-agent wrote README.md and the parent then replaced it with its own - after AGENTS.md
 * had been given "a report goes in your reply, not a new file". So creating a new report-like
 * Markdown file - README, SUMMARY, REPORT, NOTES, OVERVIEW, FINDINGS, *_VERIFICATION and the
 * like - is refused unless the request asks for one: a user message (for a sub-agent, its
 * task) that names the file, or says readme, report, summary, notes, document(ation), docs,
 * write-up or markdown.
 *
 * Never refused: changing a file that already exists, anything under .pi/ (scratch), and any
 * other name. Checked: `write`, and in `bash` a redirect or `tee` into such a file (test6's
 * LINK_VERIFICATION.md was a heredoc).
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, isAbsolute, join, resolve, sep } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const REPORT_NAME =
	/^(?:[\w.-]*[_.-])?(?:readme|summary|report|notes|overview|verification|checklist|findings|audit|results)(?:[_.-][\w.-]*)?\.(?:md|markdown|rst)$/i;
/**
 * Words in a request that ask for a written document. "Report" alone is not one of them: "Report:
 * the files you wrote", "report back" and "report what you did" ask for a reply - test11's
 * workflow agents were told "Report: summary of verification results" - so a report counts as
 * asked for with an article or a verb of making in front of it ("a report", "write a summary"),
 * as a file ("report file"), or as readme, documentation, docs, a write-up or Markdown.
 */
const ASKED =
	/\b(?:readme|documentation|docs|write-?up|markdown|summari[sz]e)\b|\.md\b|\b(?:a|an|the|your|this|that)\s+(?:\w+\s+){0,2}?(?:reports?|summary|summaries|notes|document)\b|\b(?:reports?|summary|notes)\s+(?:file|document|page)\b|\b(?:write|create|make|produce|keep|save|prepare|draft)\s+(?:\w+\s+){0,3}?(?:reports?|summary|summaries|notes|docs?|document)\b|\bdocument\s+(?:it|this|them|the)\b/i;
const FORK_TASK = /You are a delegated subagent[\s\S]*?\n\s*Task:\s*\n([\s\S]*)$/;
/** Where a redirect or `tee` writes, in a bash command. */
const REDIRECT = /(?:>>?|\btee\s+(?:-a\s+)?)\s*(["']?)([^\s"'<>|;&()]+)\1/g;

type Entry = { type?: string; message?: { role?: string; content?: unknown } };

function textOf(content: unknown): string {
	if (typeof content === "string") return content;
	if (!Array.isArray(content)) return "";
	return content.map((p) => (p && typeof p === "object" && (p as { type?: string }).type === "text" ? String((p as { text?: unknown }).text ?? "") : "")).join("\n");
}

/** What was asked: the user's messages, or for a sub-agent, its own task. */
export function request(entries: Entry[], child: boolean): string {
	const users = entries.filter((e) => e.type === "message" && e.message?.role === "user").map((e) => textOf(e.message?.content));
	if (!child) return users.filter((t) => !FORK_TASK.test(t)).join("\n");
	const tasks = users.map((t) => FORK_TASK.exec(t)?.[1]).filter((t): t is string => Boolean(t));
	return tasks.length ? tasks[tasks.length - 1] : (users[0] ?? "");
}

/** The report-like files a call would create, as absolute paths. */
export function newReports(toolName: string, input: Record<string, unknown>, cwd: string): string[] {
	const written: string[] = [];
	if (toolName === "write" && typeof input.path === "string") written.push(input.path);
	if (toolName === "bash" && typeof input.command === "string") for (const m of input.command.matchAll(REDIRECT)) written.push(m[2]);
	return written
		.map((p) => (p.startsWith("~/") ? join(homedir(), p.slice(2)) : isAbsolute(p) ? p : resolve(cwd, p)))
		.filter((p) => REPORT_NAME.test(basename(p)) && !p.split(sep).includes(".pi") && !existsSync(p));
}

export function asked(path: string, text: string): boolean {
	return ASKED.test(text) || text.toLowerCase().includes(basename(path).toLowerCase());
}

export function reason(path: string, child: boolean): string {
	return `Nobody asked for ${basename(path)}: a report or summary goes in your reply, not in a new file. Create it ` +
		`only when ${child ? "your task names it" : "the user asks for one"}.`;
}

/**
 * A `workflow` call's script: its text, or the file it names (`script: ".pi/tmp/x.mjs"`, which
 * workflow-script.ts reads in - before or after this extension, as pi happens to load them).
 */
export function scriptText(input: Record<string, unknown>, cwd: string): string {
	const script = input.script;
	if (typeof script !== "string") return "";
	const named = script.trim().replace(/^["'`]+|["'`]+$/g, "");
	if (named.length > 1024 || /[\n;(){}=`]/.test(named) || !/\.m?js$/i.test(named)) return script;
	try {
		return readFileSync(isAbsolute(named) ? named : resolve(cwd, named), "utf8");
	} catch {
		return script;
	}
}

/** The report-like file names a `subagent` launch's tasks or a `workflow` script tell agents to write. */
export function delegatedReports(toolName: string, input: Record<string, unknown>, cwd: string = process.cwd()): string[] {
	let text = "";
	if (toolName === "workflow") text = scriptText(input, cwd);
	if (toolName === "subagent") text = JSON.stringify(input);
	const names = new Set<string>();
	for (const m of text.matchAll(/[\w./${}-]*?([\w.-]+\.(?:md|markdown|rst))\b/gi)) if (REPORT_NAME.test(m[1])) names.add(m[1]);
	return [...names];
}

/** Whether a file of this name is anywhere in the project already (a few levels down, at most). */
function inProject(cwd: string, name: string): boolean {
	const want = name.toLowerCase();
	let seen = 0;
	const walk = (dir: string, depth: number): boolean => {
		let entries: import("node:fs").Dirent[];
		try {
			entries = readdirSync(dir, { withFileTypes: true });
		} catch {
			return false;
		}
		for (const e of entries) {
			if (++seen > 5000) return false;
			if (e.isFile() && e.name.toLowerCase() === want) return true;
			if (e.isDirectory() && depth < 3 && !e.name.startsWith(".") && e.name !== "node_modules" && walk(join(dir, e.name), depth + 1))
				return true;
		}
		return false;
	};
	return walk(cwd, 0);
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event, ctx) => {
		// test11 (2026-11-13): a workflow script told its verification agent to "Create a report file at
		// .../VERIFICATION_REPORT.md", which the user had not asked for; the agent's own task then asked
		// for it, so the guard in the agent let it through. So the launch is checked against the user.
		if ((event.toolName === "workflow" || event.toolName === "subagent") && process.env.PI_SUBAGENT_CHILD !== "1") {
			const named = delegatedReports(event.toolName, (event.input ?? {}) as Record<string, unknown>, ctx.cwd);
			if (named.length === 0) return undefined;
			const text = request(ctx.sessionManager.getBranch() as Entry[], false);
			// Changing a file that is already there is never refused, so neither is asking an agent to.
			const unasked = named.find((name) => !asked(name, text) && !inProject(ctx.cwd, name));
			if (!unasked) return undefined;
			return {
				block: true,
				reason:
					`Not started: it tells an agent to write ${unasked}, which the user did not ask for. A report goes in the ` +
					"agent's reply, and from there in yours - take the file out of its task and launch again.",
			};
		}
		if (event.toolName !== "write" && event.toolName !== "bash") return undefined;
		const reports = newReports(event.toolName, (event.input ?? {}) as Record<string, unknown>, ctx.cwd);
		if (reports.length === 0) return undefined;
		const child = process.env.PI_SUBAGENT_CHILD === "1";
		const text = request(ctx.sessionManager.getBranch() as Entry[], child);
		const unasked = reports.find((p) => !asked(p, text) && !packageReadme(p, ctx.cwd));
		return unasked ? { block: true, reason: reason(unasked, child) } : undefined;
	});
}

/** Files that make a folder a software project, whose README is part of it rather than a report. */
const PROJECT_FILES = ["pyproject.toml", "setup.py", "setup.cfg", "package.json", "Cargo.toml", "go.mod", "CMakeLists.txt", "DESCRIPTION", "Project.toml", "pom.xml", "build.gradle"];

/**
 * A README beside a software project's manifest. auto13 (2026-11-13) was asked for "a proper package layout"
 * for a Python tool and had its README.md refused - a package's README is part of the package (pyproject.toml
 * points at it), not a summary of the work.
 */
export function packageReadme(path: string, cwd: string): boolean {
	if (!/^readme(?:\.[\w-]+)?$/i.test(basename(path))) return false;
	const dir = dirname(resolve(cwd, path));
	return PROJECT_FILES.some((f) => existsSync(join(dir, f)));
}
