/**
 * command-output: draws a finished `bash` result for a person to read - an exit
 * line, the start and the end of the output, and colour by what each line is.
 *
 * Why: pi strips every colour code when it captures a command (the tools run
 * without a terminal anyway) and shows the last five lines in one grey. The
 * first error of a build and the file it names are usually above those five,
 * and a passing run looks the same as a failing one until you expand it.
 *
 * Display only. The model's copy of the result is never touched, so nothing
 * here costs tokens or moves the prompt cache; keeping the tools' own colours
 * would have meant escape codes in Qwen's context. So colour is re-applied by
 * recognising lines: errors, warnings, passes, diffs, `file:line` locations.
 * A result that is still streaming keeps pi's own live view and timer.
 */

import type { ExtensionAPI, Theme, ThemeColor } from "@earendil-works/pi-coding-agent";
import { keyHint } from "@earendil-works/pi-coding-agent";
import { Container, getCapabilities, Text } from "@earendil-works/pi-tui";

// Collapsed view: the first lines say what ran, the last ones how it ended.
const HEAD_LINES = 4;
const TAIL_LINES = 12;

export type Kind = "error" | "warning" | "success" | "added" | "removed" | "hunk" | "meta" | "plain";

const COLOUR: Record<Kind, ThemeColor> = {
	error: "error",
	warning: "warning",
	success: "success",
	added: "toolDiffAdded",
	removed: "toolDiffRemoved",
	hunk: "accent",
	meta: "muted",
	plain: "toolOutput",
};

// "0 errors", "no failures": a count of nothing is not a problem.
const NOTHING = /\b(?:0|no|zero)\s+(?:errors?|failures?|failed|warnings?)\b/gi;
const ERROR_WORDS =
	/\b(?:error|errors|failed|failure|failures|fatal|exception|traceback|panic(?:ked)?|segmentation fault|core dumped|permission denied|connection refused|could not|no such file|not found|undefined reference|aborted)\b/i;
// Case matters for these: ValueError, pytest's `E   assert`, Go's FAIL, npm ERR!.
const ERROR_MARKS = /[a-z](?:Error|Exception)\b|^E\s|^FAIL\b|\bERR!|[✗✘]/;
const WARNING = /\b(?:warn|warning|warnings|deprecated|deprecation)\b|⚠/i;
const WARNING_MARKS = /[a-z]Warning\b/;   // DeprecationWarning, RuntimeWarning
// A linter's finding: `fit.py:3:8: F401 ...` (ruff, flake8), `SC2086` (shellcheck).
const LINT = /:\d+(?::\d+)?:? [A-Z]{1,3}\d{2,4}\b/;
const SUCCESS = /\b(?:passed|succeeded|successfully|success)\b|^(?:OK|ok)\b|[✓✔]|\bAll checks passed\b/;
// src/fit.py:42:7, ./run.sh:3, and Python's `File "fit.py", line 42`.
const LOCATION = /(?:(?<![\w/.~-])(?:[A-Za-z]:)?[\w.~/@+-]*[\w-]\.[A-Za-z]\w*:\d+(?::\d+)?)|File "[^"]+", line \d+/g;

/** True when the output is a unified diff, so `+`/`-` lines are changes, not list items. */
export function isDiff(lines: string[]): boolean {
	return lines.some((line) => /^@@ -\d/.test(line) || line.startsWith("diff --git "));
}

export function classify(line: string, diff: boolean): Kind {
	if (diff) {
		if (/^(?:diff --git |index |\+\+\+ |--- )/.test(line)) return "meta";
		if (line.startsWith("@@")) return "hunk";
		if (line.startsWith("+")) return "added";
		if (line.startsWith("-")) return "removed";
		return "plain";
	}
	const text = line.replace(NOTHING, "");
	if (ERROR_WORDS.test(text) || ERROR_MARKS.test(text)) return "error";
	if (WARNING.test(text) || WARNING_MARKS.test(text) || LINT.test(text)) return "warning";
	if (SUCCESS.test(text)) return "success";
	return "plain";
}

/** One line in its kind's colour, with any file:line location in the accent colour. */
export function paintLine(line: string, kind: Kind, theme: Pick<Theme, "fg">): string {
	const colour = COLOUR[kind];
	if (kind === "added" || kind === "removed" || kind === "hunk" || kind === "meta") return theme.fg(colour, line);
	// Painted as separate runs: a nested colour would end with a reset and
	// leave the rest of the line uncoloured.
	let out = "";
	let at = 0;
	for (const match of line.matchAll(LOCATION)) {
		const start = match.index ?? 0;
		if (start > at) out += theme.fg(colour, line.slice(at, start));
		out += theme.fg("accent", match[0]);
		at = start + match[0].length;
	}
	if (at < line.length) out += theme.fg(colour, line.slice(at));
	return out;
}

export interface Outcome {
	/** The command's own output, without pi's status and truncation footers. */
	lines: string[];
	/** Lines the model was sent: more when pi truncated the output. */
	totalLines: number;
	status: string;
	failed: boolean;
	fullOutputPath?: string;
	/** Text other extensions appended (install notes, attached figures). */
	notes: string[];
	images: number;
}

const strip = (text: string) =>
	text
		.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g, "")
		.replace(/\r/g, "")
		.replace(/\t/g, "   ");

function seconds(ms: number): string {
	return ms < 1000 ? `${ms}ms` : ms < 60_000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.floor(ms / 60_000)}m${Math.round((ms % 60_000) / 1000)}s`;
}

interface ResultLike {
	content: Array<{ type: string; text?: string }>;
	details?: { truncation?: { truncated?: boolean; totalLines?: number }; fullOutputPath?: string };
	structuredContent?: unknown;
}

/** What a bash result says, read the way pi's bash tool writes it. */
export function readResult(result: ResultLike, isError: boolean, durationMs?: number): Outcome {
	const texts = result.content.filter((part) => part.type === "text").map((part) => strip(part.text ?? ""));
	let output = texts[0] ?? "";
	const notes = texts.slice(1).map((note) => note.trim()).filter(Boolean);
	const images = result.content.filter((part) => part.type === "image").length;

	// pi appends the status after a blank line: "Command exited with code 2",
	// "Command timed out after 30 seconds", "Command aborted".
	let status = "";
	const tail = /(?:^|\n\n)(Command (?:exited with code \d+|timed out after \d+ seconds|aborted|terminated without an exit code))$/.exec(output);
	if (tail) {
		status = tail[1];
		output = output.slice(0, tail.index);
	}
	const fullOutputPath = result.details?.fullOutputPath;
	if (fullOutputPath) {
		const footer = output.lastIndexOf("\n\n[");
		if (footer !== -1 && output.slice(footer).includes(fullOutputPath)) output = output.slice(0, footer);
	}
	output = output.replace(/\s+$/, "");
	const lines = output ? output.split("\n") : [];

	const code = (result.structuredContent as { exit_code?: unknown } | undefined)?.exit_code;
	const exitCode = typeof code === "number" ? code : status.startsWith("Command exited") ? Number(status.split(" ").pop()) : isError ? undefined : 0;
	const failed = isError || (exitCode !== undefined && exitCode !== 0);
	const what =
		exitCode !== undefined
			? `exit ${exitCode}`
			: status.replace(/^Command /, "").replace(/ seconds$/, "s") || "failed";
	const totalLines = result.details?.truncation?.truncated ? (result.details.truncation.totalLines ?? lines.length) : lines.length;
	const parts = [`${failed ? "✗" : "✓"} ${what}`];
	if (durationMs !== undefined) parts.push(seconds(durationMs));
	parts.push(`${totalLines} line${totalLines === 1 ? "" : "s"}`);
	return { lines, totalLines, status: parts.join(" · "), failed, fullOutputPath, notes, images };
}

/** The lines to show, already painted: everything, or head + a hint + tail. */
export function bodyLines(lines: string[], expanded: boolean, theme: Pick<Theme, "fg">, hint: () => string): string[] {
	const diff = isDiff(lines);
	const kinds = lines.map((line) => classify(line, diff));
	const paint = (i: number) => paintLine(lines[i], kinds[i], theme);
	if (expanded || lines.length <= HEAD_LINES + TAIL_LINES + 1) return lines.map((_, i) => paint(i));
	const hiddenFrom = HEAD_LINES;
	const hiddenTo = lines.length - TAIL_LINES;
	const hiddenKinds = kinds.slice(hiddenFrom, hiddenTo);
	const errors = hiddenKinds.filter((kind) => kind === "error").length;
	const warnings = hiddenKinds.filter((kind) => kind === "warning").length;
	const flagged = [errors && `${errors} error`, warnings && `${warnings} warning`].filter(Boolean);
	let gap = theme.fg("muted", `… ${hiddenTo - hiddenFrom} lines hidden`);
	if (flagged.length) gap += theme.fg(errors ? "error" : "warning", `, ${flagged.join(" and ")} line${errors + warnings === 1 ? "" : "s"} among them`);
	gap += theme.fg("muted", " (") + hint() + theme.fg("muted", ")");
	return [
		...lines.slice(0, hiddenFrom).map((_, i) => paint(i)),
		gap,
		...lines.slice(hiddenTo).map((_, i) => paint(hiddenTo + i)),
	];
}

export default function commandOutput(pi: ExtensionAPI) {
	pi.registerToolRenderer((toolName, next) => {
		const base = next();
		if (toolName !== "bash" || !base) return base;
		return {
			...base,
			renderResult(result, options, theme, context) {
				if (options.isPartial && base.renderResult) return base.renderResult(result, options, theme, context);
				const component = context.lastComponent instanceof Container ? context.lastComponent : new Container();
				component.clear();
				const outcome = readResult(result as ResultLike, context.isError, context.durationMs);
				const rows = [theme.fg(outcome.failed ? "error" : "success", theme.bold(outcome.status))];
				rows.push(...bodyLines(outcome.lines, options.expanded, theme, () => keyHint("app.tools.expand", "to expand")));
				if (outcome.fullOutputPath) rows.push(theme.fg("muted", `full output (${outcome.totalLines} lines): ${outcome.fullOutputPath}`));
				for (const note of outcome.notes) rows.push(theme.fg("muted", note));
				if (outcome.images && !(getCapabilities().images && context.showImages)) {
					rows.push(theme.fg("muted", `[${outcome.images} image${outcome.images === 1 ? "" : "s"} attached, not shown in this terminal]`));
				}
				component.addChild(new Text(`\n${rows.join("\n")}`, 0, 0));
				component.invalidate();
				return component;
			},
		};
	});
}
