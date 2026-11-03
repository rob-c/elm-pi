/**
 * command-output: draws a finished `bash` result for a person to read - an exit
 * line, the start and the end of the output, and colour - and gives the model
 * the same output without escape codes.
 *
 * Why: pi passes a command's output to the model as printed, colour codes and
 * progress-bar redraws (`\r`) included, and only its display strips them: it
 * shows the last five lines in one grey. So Qwen paid tokens to read
 * `\x1b[31m`, while the first error of a build and the file it names were
 * usually above those five lines, and a passing run looked like a failing one.
 *
 * When the output has escape codes, the model's copy becomes plain text (what
 * a terminal would have left on screen) and the colour version goes into the
 * result's `details`, which only the display reads - the provider sends
 * `content` alone, and pi's saved copy of a long output is made plain too.
 * The plain copy is the text the same command gives without colour: tabs and
 * control bytes are left for the display to draw, and a long output is cut
 * where pi would have cut it plain, not sooner for its colour codes' bytes.
 * Output without escape codes reaches the model unchanged.
 * When colour reached the display, the model's copy says so in one line:
 * without it Qwen cannot tell a rainbow from no colour, and claimed one.
 * The display shows a command's own colour (agent/shell/colour.sh turns it on)
 * as it printed it, on the terminal's own background, and colours everything
 * else by recognising lines:
 * errors, warnings, passes, diffs, `file:line` locations. A result that is
 * still streaming keeps pi's own live view and timer.
 */

import { readFileSync, statSync, writeFileSync } from "node:fs";
import type { ExtensionAPI, Theme, ThemeColor, TruncationResult } from "@earendil-works/pi-coding-agent";
import { DEFAULT_MAX_BYTES, formatSize, keyHint, truncateTail } from "@earendil-works/pi-coding-agent";
import type { Component } from "@earendil-works/pi-tui";
import { Container, getCapabilities, Text, visibleWidth, wrapTextWithAnsi } from "@earendil-works/pi-tui";

// Added to the model's copy, never drawn: the display shows the colour itself.
export const COLOUR_NOTE = "[The user saw this output in colour; the colour codes were taken out of your copy.]";

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
// Nor is a label for a count: valgrind's `ERROR SUMMARY: 0 errors`, and
// unittest's `OK (expected failures=1)`, failures the tests were meant to have.
const LABELS = /\bERROR SUMMARY:|\bexpected failures?\b/gi;
// A word followed by an extension is a file name (src/errors.rs), not a report.
const ERROR_WORDS =
	/\b(?:error|errors|failed|failure|failures|fatal|exception|traceback|panic(?:ked)?|segmentation fault|core dumped|permission denied|connection refused|could not|no such file|not found|undefined reference|aborted)\b(?!\.[A-Za-z])/i;
// Case matters for these: ValueError and OSError, pytest's `E   assert`, Go's
// FAIL and `--- FAIL: TestSlope`, npm ERR!, TeX's `! Undefined control sequence.`.
const ERROR_MARKS = /[A-Za-z](?:Error|Exception)\b|^E\s|^\s*(?:--- )?FAIL\b|\bERR!|^! |[✗✘]/;
const WARNING = /\b(?:warn|warning|warnings|deprecated|deprecation)\b|⚠/i;
const WARNING_MARKS = /[a-z]Warning\b/;   // DeprecationWarning, RuntimeWarning
// A linter's finding: `fit.py:3:8: F401 ...` (ruff, flake8), `SC2086` (shellcheck).
const LINT = /:\d+(?::\d+)?:? [A-Z]{1,3}\d{2,4}\b|\bSC\d{4}\b/;
// pytest -v's PASSED, pip's `Successfully installed`, unittest's OK, Go's ok.
const SUCCESS = /\b(?:passed|succeeded|successfully|success)\b|^ok\b|[✓✔]|\bAll checks passed\b/i;
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
	const text = line.replace(NOTHING, "").replace(LABELS, "");
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
	/** The same output with the command's own colour codes, when it printed any. */
	colour?: string[];
	/** Text other extensions appended (install notes, attached figures). */
	notes: string[];
	images: number;
}

// What the panel draws: a tab as three spaces, nothing for other control bytes.
// Only the display does this - the model reads tabs and NULs as printed.
const onScreen = (text: string) => text.replace(/\t/g, "   ").replace(/[\x00-\x08\x0b-\x1a\x1c-\x1f\x7f]/g, "");

const strip = (text: string) =>
	onScreen(text.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g, "").replace(/\r/g, ""));

const COLOUR_CODE = /\x1b\[[0-9;:]*m/;
const COLOUR_CODES = /\x1b\[[0-9;:]*m/g;

/**
 * The output as a terminal would leave it: colour codes kept, every other
 * escape and `\r` redraw gone. Its text is what the same output printed without
 * colour turns into, so tabs and other control bytes stay.
 */
export function colourText(raw: string): string {
	const lines = raw.split("\n").map((line) => {
		// A line ending: git colours a CRLF line's \r and resets after it.
		line = line.replace(/(?:\r|\x1b\[[0-9;:]*m)+$/, (end) => end.replace(/\r/g, ""));
		// A progress bar redraws its line with \r: keep what it ended as.
		line = line.slice(line.lastIndexOf("\r") + 1);
		return line
			.replace(/\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g, "")
			.replace(/\x1b\[[0-9;:?]*[ -/]*[@-~]/g, (seq) => (/^\x1b\[[0-9;:]*m$/.test(seq) ? seq : ""))
			// Any other escape ends at its first byte in 0-~: `tput sgr0`'s
			// charset reset ESC ( B, save-cursor ESC 7, reset ESC c.
			.replace(/\x1b(?!\[[0-9;:]*m)[ -/]*[0-~]?/g, "");
	});
	return lines.join("\n");
}

/** Output as the model should read it, and - when the command printed colour - as the display should show it. */
export function separate(text: string): { plain: string; colour?: string } {
	if (!/[\x1b\r]/.test(text)) return { plain: text };
	const colour = colourText(text);
	return { plain: colour.replace(COLOUR_CODES, ""), colour: COLOUR_CODE.test(colour) ? colour : undefined };
}

/**
 * Each line made to stand alone: it starts in the colour the previous line left
 * open and ends with a reset, so a colour never bleeds into pi's own rows.
 */
export function carryColour(lines: string[]): string[] {
	let open: string[] = [];
	return lines.map((line) => {
		const out = open.join("") + line;
		for (const match of line.matchAll(/\x1b\[([0-9;:]*)m/g)) {
			const params = match[1];
			if (params === "" || params === "0") open = [];
			else if (params.startsWith("0;")) open = [match[0]];
			// lolcat sets a colour per character and never resets: only the last few matter.
			else open = [...open, match[0]].slice(-8);
		}
		return COLOUR_CODE.test(out) ? `${out}\x1b[0m` : out;
	});
}

function seconds(ms: number): string {
	if (ms < 1000) return `${ms}ms`;
	// Rounded before the unit is chosen or the minutes split off, so 59960ms
	// reads 1m0s, not 60.0s, and 119999ms reads 2m0s, not 1m60s.
	if (Math.round(ms / 100) < 600) return `${(Math.round(ms / 100) / 10).toFixed(1)}s`;
	const s = Math.round(ms / 1000);
	return `${Math.floor(s / 60)}m${s % 60}s`;
}

interface ResultLike {
	content: Array<{ type: string; text?: string }>;
	details?: { truncation?: { truncated?: boolean; totalLines?: number }; fullOutputPath?: string; colour?: string };
	structuredContent?: unknown;
}

/** What a bash result says, read the way pi's bash tool writes it. */
export function readResult(result: ResultLike, isError: boolean, durationMs?: number): Outcome {
	const texts = result.content.filter((part) => part.type === "text").map((part) => strip(part.text ?? ""));
	let output = texts[0] ?? "";
	const notes = texts.slice(1).map((note) => note.trim()).filter((note) => note && note !== COLOUR_NOTE);
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
	// Line for line the same text as the model's copy, so the output's lines are its first lines.
	const colour = typeof result.details?.colour === "string" ? result.details.colour.split("\n").slice(0, lines.length).map(onScreen) : undefined;
	return { lines, totalLines, status: parts.join(" · "), failed, fullOutputPath, colour, notes, images };
}

/**
 * The lines to show, already painted: everything, or head + a hint + tail. With
 * the command's own colour, its lines are shown as it coloured them - and a line
 * it left plain stays plain - while the hidden-line counts still come from
 * reading the text.
 */
export function bodyLines(lines: string[], expanded: boolean, theme: Pick<Theme, "fg">, hint: () => string, colour?: string[]): string[] {
	if (colour) lines = colour.map((line) => line.replace(COLOUR_CODES, ""));
	const diff = isDiff(lines);
	const kinds = lines.map((line) => classify(line, diff));
	const own = colour && carryColour(colour);
	const paint = (i: number) => (own ? (COLOUR_CODE.test(own[i]) ? own[i] : theme.fg("toolOutput", own[i])) : paintLine(lines[i], kinds[i], theme));
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

// Rewrites a saved output as plain text, and returns it as it was printed. pi
// has closed the file by the time the result reaches extensions; one too large
// to hold is left as it is.
export function plainFile(path: string): string | undefined {
	try {
		if (statSync(path).size > 64 * 1024 * 1024) return undefined;
		const text = readFileSync(path, "utf8");
		const { plain } = separate(text);
		if (plain !== text) writeFileSync(path, plain);
		return text;
	} catch {
		// Gone or unreadable: nothing to clean.
		return undefined;
	}
}

// What colour adds to an output: its codes, and the erase-to-end grep sends
// after each one.
const COLOURING = /(\x1b\[[0-9;:]*m|\x1b\[K)/g;

// The end of a coloured line holding the last `chars` characters of its text,
// opened with the code in force where it is cut.
function colourTail(line: string, chars: number): string {
	const parts = line.split(COLOURING);
	let out = "";
	for (let i = parts.length - 1; i >= 0; i -= 2) {
		if (parts[i].length >= chars) {
			const open = i > 0 ? parts[i - 1] : "";
			return open + parts[i].slice(parts[i].length - chars) + out;
		}
		chars -= parts[i].length;
		out = (i > 0 ? parts[i - 1] : "") + parts[i] + out;
	}
	return out;
}

/**
 * pi keeps the last 2000 lines or 50KB of an output, counting its colour codes
 * as bytes, so a coloured output gave the model fewer lines than the same output
 * plain. This makes the cut again from the saved output as printed, on its text
 * without colour codes, and gives pi's result text for it - still coloured, for
 * separate() - with pi's own footer and the status after it, and the truncation
 * for details (undefined when the plain output fits whole).
 */
export function recut(
	text: string,
	printed: string,
	path: string,
	limits: { maxLines?: number; maxBytes?: number } = {},
): { text: string; truncation?: TruncationResult } | undefined {
	const marker = `Full output: ${path}]`;
	const end = text.lastIndexOf(marker);
	if (end === -1 || text.lastIndexOf("\n\n[", end) === -1) return undefined;
	const status = text.slice(end + marker.length);
	const plain = printed.replace(COLOURING, "");
	const cut = truncateTail(plain, { maxLines: limits.maxLines, maxBytes: limits.maxBytes });
	if (!cut.truncated) return { text: `${printed || "(no output)"}${status}` };
	// Colour holds no newline, so the printed lines are the plain ones.
	const lines = printed.split("\n");
	if (printed.endsWith("\n")) lines.pop();
	let body: string;
	let footer: string;
	if (cut.lastLinePartial) {
		body = colourTail(lines[lines.length - 1], cut.content.length);
		const lastLine = formatSize(Buffer.byteLength(plain.slice(plain.lastIndexOf("\n") + 1), "utf8"));
		footer = `[Showing last ${formatSize(cut.outputBytes)} of line ${cut.totalLines} (line is ${lastLine}). ${marker}`;
	} else {
		body = lines.slice(lines.length - cut.outputLines).join("\n");
		const shown = `lines ${cut.totalLines - cut.outputLines + 1}-${cut.totalLines} of ${cut.totalLines}`;
		footer = cut.truncatedBy === "lines" ? `[Showing ${shown}. ${marker}` : `[Showing ${shown} (${formatSize(DEFAULT_MAX_BYTES)} limit). ${marker}`;
	}
	return { text: `${body || "(no output)"}\n\n${footer}${status}`, truncation: cut };
}

// The output sits on the terminal's own background, inside a margin of the
// tool box's colour: a command's colours were made for that background, and
// its reset (`\x1b[0m`) clears pi's tint anyway, so a rainbow came out in patches.
export class TerminalPanel implements Component {
	private rows: string[];
	private boxBg: string;
	private cache?: { width: number; lines: string[] };

	constructor(rows: string[], boxBg: string) {
		this.rows = rows;
		this.boxBg = boxBg;
	}

	invalidate(): void {
		this.cache = undefined;
	}

	render(width: number): string[] {
		if (this.cache?.width === width) return this.cache.lines;
		const inner = Math.max(1, width - 2);
		const lines = this.rows
			.flatMap((row) => (row ? wrapTextWithAnsi(row, inner) : [""]))
			.map((line) => `\x1b[49m ${line}${" ".repeat(Math.max(0, inner - visibleWidth(line)))} ${this.boxBg}`);
		this.cache = { width, lines };
		return lines;
	}
}

export default function commandOutput(pi: ExtensionAPI) {
	pi.on("tool_result", (event) => {
		if (event.toolName !== "bash") return;
		// pi saves a long output whole, as printed, for the model to `read` later;
		// its colour may sit in lines the result's own text leaves out.
		const saved = event.details as { fullOutputPath?: unknown; truncation?: TruncationResult } | undefined;
		const fullOutputPath = saved?.fullOutputPath;
		const printed = typeof fullOutputPath === "string" ? plainFile(fullOutputPath) : undefined;
		const first = event.content.findIndex((part) => part.type === "text");
		if (first === -1) return;
		const original = (event.content[first] as { text: string }).text;
		let text = original;
		let details = event.details;
		if (typeof fullOutputPath === "string" && printed !== undefined && saved?.truncation?.truncated && COLOUR_CODE.test(printed)) {
			const again = recut(text, printed, fullOutputPath, saved.truncation);
			if (again) {
				text = again.text;
				// Fitting whole once plain, it is a result pi would not have cut, and names no saved file.
				const { truncation: _cut, fullOutputPath: _path, ...rest } = saved;
				details = again.truncation ? { ...saved, truncation: again.truncation } : Object.keys(rest).length ? rest : undefined;
			}
		}
		const { plain, colour } = separate(text);
		if (plain === original && details === event.details) return;
		const content = event.content.map((part, i) => (i === first ? { ...part, text: plain } : part));
		if (colour) content.splice(first + 1, 0, { type: "text", text: COLOUR_NOTE });
		// structuredContent carries the output too (for codemode scripts), and
		// pi drops it when content is replaced without it.
		const structured = event.structuredContent as { output?: unknown } | undefined;
		const structuredContent =
			structured && typeof structured.output === "string" ? { ...structured, output: separate(structured.output).plain } : event.structuredContent;
		return { content, structuredContent, details: colour ? { ...details, colour } : details };
	});

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
				component.addChild(new Text(`\n${theme.fg(outcome.failed ? "error" : "success", theme.bold(outcome.status))}`, 0, 0));
				// pi 1.5 passes keyHint in the context: the imported one can be this
				// extension's own copy, which does not see the user's keybindings.
				const hint = (context as { keyHint?: typeof keyHint }).keyHint ?? keyHint;
				const body = bodyLines(outcome.lines, options.expanded, theme, () => hint("app.tools.expand", "to expand"), outcome.colour);
				// The same tint pi gives the box (tool-execution.js), restored after each line.
				if (body.length) component.addChild(new TerminalPanel(body, theme.getBgAnsi(context.isError ? "toolErrorBg" : "toolSuccessBg")));
				const rows: string[] = [];
				if (outcome.fullOutputPath) {
					const count = `${outcome.totalLines} line${outcome.totalLines === 1 ? "" : "s"}`;
					rows.push(theme.fg("muted", `full output (${count}): ${outcome.fullOutputPath}`));
				}
				for (const note of outcome.notes) rows.push(theme.fg("muted", note));
				if (outcome.images && !(getCapabilities().images && context.showImages)) {
					rows.push(theme.fg("muted", `[${outcome.images} image${outcome.images === 1 ? "" : "s"} attached, not shown in this terminal]`));
				}
				if (rows.length) component.addChild(new Text(rows.join("\n"), 0, 0));
				component.invalidate();
				return component;
			},
		};
	});
}
