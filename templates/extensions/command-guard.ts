/**
 * command-guard: a bash command the permission gate denies is refused however
 * it is spelled.
 *
 * pi-permission-system matches each command of a bash program against its
 * `bash` rules as written: wildcards over the text, the last matching rule
 * wins. That sees through chains and substitutions, but `ssh *` does not match
 * `'ssh' host`, `\ssh host`, `/usr/bin/ssh host`, `command ssh host`, a tab
 * after `ssh` or two spaces in `docker  run`; and in front of `sudo`, `env` or
 * `xargs` the wrapper's own rule or its ask decides, not the command it runs.
 * The shell runs the denied command all the same.
 *
 * So this reads each command the way the shell will run it - quotes and
 * escapes removed, braces expanded, words split on any whitespace, the command
 * name also by its last path segment, then again past each wrapper (`sudo`,
 * `env`, `xargs`, `command`, `exec`, `builtin`, `timeout`, ...) and into a
 * `bash -c`, `eval`, `env -S` or `flock -c` payload, a function's body and
 * every substitution, arithmetic and `${...}` ones included - and refuses the
 * call when the gate's own rules (extensions/pi-permission-system/config.json,
 * in the file's order) deny one of those spellings, with that rule's reason. It
 * only ever adds a denial; everything else is the gate's to decide, asks
 * included. A command too deeply nested, or a brace expansion too large, to
 * read here is refused. A name the shell computes (`$x host`) is not known
 * until it runs, so it is not caught here either.
 *
 * Containers get two checks the gate's text matching cannot make: a run or
 * create gets no network only when its own options say `--network none`
 * (matched as text, `docker run alpine echo --network=none` passes the rules),
 * and an engine pointed at another machine (DOCKER_HOST and friends, set in
 * the command or in pi's environment) is refused, since every container then
 * runs off this machine.
 */

import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

type Rule = string | { action?: string; reason?: string };

/** A spelling the gate's rules deny: the rule, its reason, and the command as the shell runs it. */
export interface Denial {
	pattern: string;
	reason?: string;
	spelling: string;
}

/** Substitutions inside substitutions and wrappers inside wrappers stop here: deeper is refused. */
const MAX_DEPTH = 16;
/** The most words one brace expansion may make; more is refused. */
const MAX_WORDS = 1024;

/** A command the guard cannot read with confidence. It is refused: the shell would run it all the same. */
class Unreadable extends Error {
	readonly spelling: string;
	constructor(spelling: string, reason: string) {
		super(reason);
		this.spelling = spelling;
	}
}
const TOO_DEEP = "It nests commands, substitutions or wrappers too deeply for the command guard to read. Write it more plainly.";
const TOO_WIDE = `It brace-expands to more than ${MAX_WORDS} words, too many for the command guard to read. Use seq or a loop.`;

const BLANKS = new Set([" ", "\t", "\r"]);
const SEPARATORS = new Set([";", "&", "|", "(", ")"]);
const REDIRECT = /&>>|&>|>>|>&|>\||<&|<>|>|</y;

/** Words that open or close shell syntax in front of the command they precede. */
const RESERVED = new Set(["!", "{", "}", "if", "then", "elif", "else", "fi", "while", "until", "do", "done", "esac", "coproc"]);
/** A loop or case header names no command. */
const HEADERS = new Set(["for", "select", "case"]);
/** What can follow `coproc NAME`: then NAME is the coprocess's name, not a command. */
const COMPOUND = new Set(["{", "if", "while", "until", "for", "select", "case", "[["]);
const ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=/;
/** A word that makes the `(` right after it an array's words, not a subshell: `a=(...)`, `a+=(...)`. */
const ARRAY = /^[A-Za-z_][A-Za-z0-9_]*\+?=$/;
/** Words after which the next word is a command again. */
const KEEPS_COMMAND = new Set(["!", "{", "}", "if", "then", "elif", "else", "while", "until", "do", "time", "coproc"]);

const ENGINES = new Set(["docker", "podman"]);
/** Variables that send docker or podman to an engine elsewhere. */
const REMOTE_ENGINE = /^(?:DOCKER_HOST|CONTAINER_HOST|DOCKER_CONTEXT|CONTAINER_CONNECTION)=/;
/**
 * Options of `run`/`create` that take a value, so the image is the first word
 * after the options. An option not listed here is taken as a flag; if it
 * really takes a value, the scan stops early and the run is refused - the safe
 * side.
 */
const RUN_VALUED = new Set([
	"-a", "--attach", "-c", "--cpu-shares", "-e", "--env", "-h", "--hostname", "-l", "--label", "-m", "--memory",
	"-p", "--publish", "-u", "--user", "-v", "--volume", "-w", "--workdir", "--add-host", "--annotation",
	"--blkio-weight", "--cap-add", "--cap-drop", "--cgroup-parent", "--cgroupns", "--cidfile", "--cpu-period",
	"--cpu-quota", "--cpu-rt-period", "--cpu-rt-runtime", "--cpus", "--cpuset-cpus", "--cpuset-mems", "--device",
	"--device-cgroup-rule", "--device-read-bps", "--device-read-iops", "--device-write-bps", "--device-write-iops",
	"--dns", "--dns-option", "--dns-search", "--domainname", "--entrypoint", "--env-file", "--expose", "--gpus",
	"--group-add", "--health-cmd", "--health-interval", "--health-retries", "--health-start-period",
	"--health-timeout", "--ip", "--ip6", "--ipc", "--isolation", "--label-file", "--link", "--link-local-ip",
	"--log-driver", "--log-opt", "--mac-address", "--memory-reservation", "--memory-swap", "--memory-swappiness",
	"--mount", "--name", "--network", "--net", "--network-alias", "--net-alias", "--oom-score-adj", "--pid",
	"--pids-limit", "--platform", "--pull", "--restart", "--runtime", "--security-opt", "--shm-size",
	"--stop-signal", "--stop-timeout", "--storage-opt", "--sysctl", "--tmpfs", "--ulimit", "--userns", "--uts",
	"--volume-driver", "--volumes-from", "--arch", "--os", "--pod", "--secret",
]);
const NETWORK_OPTIONS = new Set(["--network", "--net"]);
const SHELLS = new Set(["sh", "bash", "dash", "zsh", "ksh", "fish"]);

/**
 * Commands that run the command after their own options. `valued` options
 * take the next word, `operands` words come before the command (a duration, a
 * lock file), and `runsNothing` options make the wrapper describe or edit
 * rather than run: `command -v ssh` only prints where ssh is. A wrapper with
 * `subcommands` runs a command only after one of them: `pixi exec` fetches
 * and runs any conda-forge package (openssh among them), `pixi add` does not.
 */
interface Wrapper {
	subcommands?: string[];
	valued?: string[];
	operands?: number;
	runsNothing?: string[];
}

const WRAPPERS = new Map<string, Wrapper>([
	["sudo", {
		valued: ["-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "--close-from", "-D", "--chdir",
			"-r", "--role", "-t", "--type", "-U", "--other-user", "-T", "--command-timeout", "-R", "--chroot"],
		runsNothing: ["-l", "--list", "-e", "--edit", "-v", "--validate", "-K", "--remove-timestamp", "-V", "--version"],
	}],
	["doas", { valued: ["-u", "-C"] }],
	["env", { valued: ["-u", "--unset", "-C", "--chdir", "-P", "-S", "--split-string", "-a", "--argv0"] }],
	["xargs", {
		valued: ["-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a", "-J", "-R", "-S", "--max-args", "--max-procs",
			"--max-lines", "--delimiter", "--eof", "--max-chars", "--arg-file", "--process-slot-var"],
	}],
	["nohup", {}],
	["time", { valued: ["-o", "--output", "-f", "--format"] }],
	["timeout", { valued: ["-s", "--signal", "-k", "--kill-after"], operands: 1 }],
	["nice", { valued: ["-n", "--adjustment"] }],
	["setsid", {}],
	["stdbuf", { valued: ["-i", "--input", "-o", "--output", "-e", "--error"] }],
	["flock", { valued: ["-w", "--timeout", "--wait", "-E", "--conflict-exit-code"], operands: 1 }],
	["caffeinate", { valued: ["-t", "-w"] }],
	["watch", { valued: ["-n", "--interval"] }],
	["command", { runsNothing: ["-v", "-V"] }],
	["exec", { valued: ["-a"] }],
	["builtin", {}],
	["pixi", {
		subcommands: ["run", "exec", "x"],
		valued: ["-s", "--spec", "-c", "--channel", "-e", "--environment", "--manifest-path", "-p", "--platform",
			"--with", "--executable"],
	}],
	["uv", {
		subcommands: ["run"],
		valued: ["--with", "-w", "--with-requirements", "--python", "-p", "--project", "--directory", "--package",
			"--env-file", "--extra", "--group", "--index", "--index-url", "-i", "--from"],
	}],
	["uvx", { valued: ["--from", "--with", "-w", "--python", "-p", "--index", "--index-url", "-i"] }],
	["pipx", { subcommands: ["run"], valued: ["--spec", "--python", "--pip-args", "--index-url", "-i"] }],
	["parallel", {
		valued: ["-j", "--jobs", "-S", "--sshlogin", "--sshloginfile", "-a", "--arg-file", "--delay", "--timeout",
			"--joblog", "--results", "-N", "-n", "--max-args", "-L", "--colsep", "-C", "-I", "--tagstring",
			"--workdir", "--wd"],
	}],
]);

const ESCAPES: Record<string, string> = {
	a: "\x07", b: "\b", e: "\x1b", E: "\x1b", f: "\f", n: "\n", r: "\r", t: "\t", v: "\v",
	"\\": "\\", "'": "'", '"': '"', "?": "?",
};

function basename(name: string): string {
	return name.slice(name.lastIndexOf("/") + 1);
}

/** The word at `i` when one starts there (after a blank or an operator), for spotting keywords. */
const WORD = /[^\s;&|()<>]+/y;
function wordAt(source: string, i: number, first: number): string | undefined {
	if (i > first && !/[\s;&|()<>]/.test(source[i - 1])) return undefined;
	WORD.lastIndex = i;
	return WORD.exec(source)?.[0];
}

/**
 * Index of the bracket that closes the one at `open`, skipping quoted text,
 * substitutions and comments; the end when there is none. Inside `( )`, the
 * `)` that ends a case pattern closes nothing: `$(case x in x) ssh;; esac)`.
 */
function closing(source: string, open: number): number {
	const paren = source[open] === "(";
	const close = paren ? ")" : "}";
	let depth = 0;
	// Each case open in here: "head" until its `in`, then "pattern" up to each pattern's `)`, then "body".
	const cases: ("head" | "pattern" | "body")[] = [];
	let commandStart = true;
	for (let i = open; i < source.length; i++) {
		const c = source[i];
		const word = paren && i > open ? wordAt(source, i, open + 1) : undefined;
		if (word !== undefined) {
			const state = cases.at(-1);
			if (word.startsWith("#")) {
				i = lineEnd(source, i) - 1;
				continue;
			}
			if (commandStart && word === "case") cases.push("head");
			else if (state === "head" && word === "in") cases[cases.length - 1] = "pattern";
			else if (word === "esac" && (state === "pattern" || (state === "body" && commandStart))) cases.pop();
			commandStart = KEEPS_COMMAND.has(word);
		}
		if (c === "\\") i++;
		else if (c === "'") i = endOf(source, "'", i + 1);
		else if (c === '"') i = endOf(source, '"', i + 1);
		else if (c === "`") i = endOf(source, "`", i + 1);
		else if (c === "$" && (source[i + 1] === "{" || (!paren && source[i + 1] === "("))) i = closing(source, i + 1);
		else if (paren && cases.at(-1) === "pattern" && (c === "(" || c === ")")) {
			// A pattern's optional `(` opens nothing; its `)` starts the arm's commands.
			if (c === ")") cases[cases.length - 1] = "body";
			commandStart = true;
		} else if (c === source[open]) {
			depth++;
			commandStart = true;
		} else if (c === close && --depth === 0) {
			return i;
		} else if (paren && (c === ";" || c === "&" || c === "|" || c === "\n")) {
			// `;;`, `;&` and `;;&` end a case arm.
			if (c === ";" && (source[i + 1] === ";" || source[i + 1] === "&") && cases.at(-1) === "body") {
				cases[cases.length - 1] = "pattern";
				i++;
			}
			commandStart = true;
		}
	}
	return source.length;
}

/** Index of the newline that ends the line `start` is on; the end when there is none. */
function lineEnd(source: string, start: number): number {
	const end = source.indexOf("\n", start);
	return end === -1 ? source.length : end;
}

/** Index of the next unescaped `quote` from `start`; the end when there is none. */
function endOf(source: string, quote: string, start: number): number {
	for (let i = start; i < source.length; i++) {
		if (source[i] === "\\" && quote !== "'") i++;
		else if (source[i] === quote) return i;
	}
	return source.length;
}

/**
 * The value of a `$'...'` string from `start`, and the index after it. As in
 * bash: `\cX` is control-X, `\U` takes up to eight hex digits, and a NUL ends
 * the value.
 */
function ansiC(source: string, start: number): [string, number] {
	let end = start;
	while (end < source.length && source[end] !== "'") end += source[end] === "\\" ? 2 : 1;
	const body = source.slice(start, end);
	let text = "";
	for (let i = 0; i < body.length;) {
		if (body[i] !== "\\") {
			text += body[i++];
			continue;
		}
		const code = /^(x[0-9a-fA-F]{1,2}|u[0-9a-fA-F]{1,4}|U[0-9a-fA-F]{1,8}|[0-7]{1,3})/.exec(body.slice(i + 1))?.[1];
		let char: string;
		if (code) {
			const point = /^[xuU]/.test(code) ? parseInt(code.slice(1), 16) : parseInt(code, 8);
			char = point <= 0x10ffff ? String.fromCodePoint(point) : "\ufffd";
			i += 1 + code.length;
		} else if (body[i + 1] === "c" && i + 2 < body.length) {
			// A backslash after \c is control-backslash, taking the one that escapes it along.
			const x = body[i + 2];
			i += x === "\\" && body[i + 3] === "\\" ? 4 : 3;
			char = x === "?" ? "\x7f" : String.fromCharCode(x.toUpperCase().charCodeAt(0) & 0x1f);
		} else {
			char = ESCAPES[body[i + 1]] ?? body.slice(i, i + 2);
			i += 2;
		}
		if (char === "\0") break;
		text += char;
	}
	return [text, end + 1];
}

/**
 * A `$(...)`, `$((...))` or backtick substitution at `i`: the commands it runs
 * go to `nested`, and the index after it comes back; undefined when there is
 * none at `i`. The substitution's output is not known, so the word keeps its
 * source text.
 */
function substitution(source: string, i: number, nested: (inner: string) => void): number | undefined {
	if (source[i] === "`") {
		const end = endOf(source, "`", i + 1);
		nested(source.slice(i + 1, end).replace(/\\([`$\\])/g, "$1"));
		return end + 1;
	}
	if (source[i] === "$" && source[i + 1] === "(") {
		if (source[i + 2] === "(") {
			// Arithmetic when the inner bracket closes just before the outer one, as bash decides:
			// `$((ssh host) )` is a subshell in a substitution. Substitutions inside arithmetic still run.
			const inner = closing(source, i + 2);
			if (source[inner + 1] === ")") {
				expansionsIn(source.slice(i + 3, inner), nested);
				return inner + 2;
			}
		}
		const end = closing(source, i + 1);
		nested(source.slice(i + 2, end));
		return end + 1;
	}
	return undefined;
}

/**
 * The substitutions in `text` - a `${...}` body, an arithmetic expression, an
 * array's words - go to `nested`. Single quotes quote only outside double ones.
 */
function expansionsIn(text: string, nested: (inner: string) => void): void {
	let quoted = false;
	for (let i = 0; i < text.length;) {
		const after = substitution(text, i, nested);
		if (after !== undefined) {
			i = after;
		} else if (text[i] === "\\") {
			i += 2;
		} else if (text[i] === '"') {
			quoted = !quoted;
			i++;
		} else if (!quoted && text[i] === "'") {
			i = endOf(text, "'", i + 1) + 1;
		} else if (!quoted && text[i] === "$" && text[i + 1] === "'") {
			i = ansiC(text, i + 2)[1];
		} else if (!quoted && (text[i] === "<" || text[i] === ">") && text[i + 1] === "(") {
			const end = closing(text, i + 1);
			nested(text.slice(i + 2, end));
			i = end + 1;
		} else {
			i++;
		}
	}
}

/**
 * A word's text in pieces, for brace expansion: a literal string, an unquoted
 * `{`, `,` or `}`, or the point where quoted text began (a word with any is
 * kept even when it comes out empty).
 */
type Piece = string | { brace: string } | { quoted: true };

function piecesText(pieces: Piece[]): string {
	return pieces.map((p) => (typeof p === "string" ? p : "brace" in p ? p.brace : "")).join("");
}

/** The words bash makes of `pieces` by brace expansion: `ss{h,} host` runs `ssh ss host`. */
function braceExpand(pieces: Piece[]): string[] {
	return expandPieces(pieces).flatMap((word) => {
		const text = piecesText(word);
		return text !== "" || word.some((p) => typeof p !== "string" && "quoted" in p) ? [text] : [];
	});
}

function isBrace(piece: Piece | undefined, brace: string): boolean {
	return typeof piece === "object" && "brace" in piece && piece.brace === brace;
}

function expandPieces(pieces: Piece[]): Piece[][] {
	for (let s = 0; s < pieces.length; s++) {
		if (!isBrace(pieces[s], "{")) continue;
		let depth = 0;
		let end = -1;
		const commas: number[] = [];
		for (let j = s; j < pieces.length && end === -1; j++) {
			if (isBrace(pieces[j], "{")) depth++;
			else if (isBrace(pieces[j], "}") && --depth === 0) end = j;
			else if (isBrace(pieces[j], ",") && depth === 1) commas.push(j);
		}
		if (end === -1) continue;
		let alternatives: Piece[][];
		if (commas.length > 0) {
			const bounds = [s, ...commas, end];
			alternatives = bounds.slice(1).map((bound, k) => pieces.slice(bounds[k] + 1, bound));
		} else {
			const body = pieces.slice(s + 1, end);
			const words = body.every((p) => typeof p === "string") ? sequence(body.join("")) : undefined;
			if (!words) continue; // `{a}` is itself; a later brace may still expand
			alternatives = words.map((word) => [word]);
		}
		const tails = expandPieces(pieces.slice(end + 1));
		const out: Piece[][] = [];
		for (const alternative of alternatives) {
			for (const middle of expandPieces(alternative)) {
				for (const tail of tails) {
					if (out.length >= MAX_WORDS) throw new Unreadable(piecesText(pieces), TOO_WIDE);
					out.push([...pieces.slice(0, s), ...middle, ...tail]);
				}
			}
		}
		return out;
	}
	return [pieces];
}

/** The words of a sequence expression `{x..y}` or `{x..y..step}`, of integers or of letters; undefined when it is not one. */
function sequence(body: string): string[] | undefined {
	const numbers = /^(-?\d+)\.\.(-?\d+)(?:\.\.(-?\d+))?$/.exec(body);
	const letters = /^([A-Za-z])\.\.([A-Za-z])(?:\.\.(-?\d+))?$/.exec(body);
	const match = numbers ?? letters;
	if (!match) return undefined;
	const [from, to] = numbers ? [Number(match[1]), Number(match[2])] : [match[1].charCodeAt(0), match[2].charCodeAt(0)];
	const step = Math.abs(Number(match[3] ?? 1)) || 1;
	if (Math.abs(to - from) / step >= MAX_WORDS) throw new Unreadable(`{${body}}`, TOO_WIDE);
	// A leading zero pads every number to the longer end's width, sign included.
	const width = numbers && (/^-?0\d/.test(match[1]) || /^-?0\d/.test(match[2])) ? Math.max(match[1].length, match[2].length) : 0;
	const words: string[] = [];
	for (let n = from; from <= to ? n <= to : n >= to; n += from <= to ? step : -step) {
		if (!numbers) words.push(String.fromCharCode(n));
		else words.push(n < 0 ? `-${String(-n).padStart(width - 1, "0")}` : String(n).padStart(width, "0"));
	}
	return words;
}

/** A heredoc delimiter's word from `start`, quotes removed, and the index after it. */
function delimiterWord(source: string, start: number): [string, number] {
	let text = "";
	let i = start;
	while (i < source.length && !BLANKS.has(source[i]) && source[i] !== "\n" && !SEPARATORS.has(source[i])) {
		if (source[i] === "'" || source[i] === '"') {
			const end = endOf(source, source[i], i + 1);
			text += source.slice(i + 1, end);
			i = end + 1;
		} else if (source[i] === "\\") {
			text += source[i + 1] ?? "";
			i += 2;
		} else {
			text += source[i++];
		}
	}
	return [text, i];
}

/** The index after the heredoc bodies that start at `start`: they are data, not commands. */
function skipHeredocs(source: string, start: number, heredocs: { delimiter: string; tabs: boolean }[]): number {
	let i = start;
	for (const { delimiter, tabs } of heredocs) {
		while (i < source.length) {
			const end = lineEnd(source, i);
			const line = source.slice(i, end);
			i = end + 1;
			if ((tabs ? line.replace(/^\t+/, "") : line) === delimiter) break;
		}
	}
	return Math.min(i, source.length);
}

/**
 * The simple commands of a bash program, each as the words the shell passes
 * it: quotes and escapes removed, split on any whitespace, redirections and
 * comments dropped. Commands in substitutions are listed as well. Shell
 * keywords are left in place; {@link collectRuns} reads past them.
 */
export function commandsOf(source: string, out: string[][] = [], depth = 0): string[][] {
	let words: string[] = [];
	let word: Piece[] | undefined;
	let redirectTarget = false;
	let heredocs: { delimiter: string; tabs: boolean }[] = [];
	const nested = (inner: string) => {
		if (depth >= MAX_DEPTH) throw new Unreadable(inner, TOO_DEEP);
		commandsOf(inner, out, depth + 1);
	};
	const add = (text: string, quoted = false) => {
		word ??= [];
		if (quoted) word.push({ quoted: true });
		if (text !== "") word.push(text);
	};
	const text = () => (word ?? []).filter((p) => typeof p === "string").join("");
	const endWord = () => {
		if (word === undefined) return;
		if (redirectTarget) redirectTarget = false;
		else words.push(...braceExpand(word));
		word = undefined;
	};
	const endCommand = () => {
		endWord();
		if (words.length > 0) out.push(words);
		words = [];
		redirectTarget = false;
	};

	let i = 0;
	while (i < source.length) {
		const c = source[i];
		const after = substitution(source, i, nested);
		if (after !== undefined) {
			add(source.slice(i, after));
			i = after;
		} else if (c === "#" && word === undefined) {
			i = lineEnd(source, i);
		} else if (BLANKS.has(c)) {
			endWord();
			i++;
		} else if (c === "\n") {
			endCommand();
			i = skipHeredocs(source, i + 1, heredocs);
			heredocs = [];
		} else if (c === "\\") {
			if (source[i + 1] !== "\n") add(source[i + 1] ?? "", true);
			i += 2;
		} else if (c === "'") {
			const end = endOf(source, "'", i + 1);
			add(source.slice(i + 1, end), true);
			i = end + 1;
		} else if (c === '"' || (c === "$" && source[i + 1] === '"')) {
			i = source.indexOf('"', i) + 1;
			let inside = "";
			while (i < source.length && source[i] !== '"') {
				const inner = substitution(source, i, nested);
				if (inner !== undefined) {
					inside += source.slice(i, inner);
					i = inner;
				} else if (source[i] === "\\" && '$`"\\\n'.includes(source[i + 1] ?? "")) {
					if (source[i + 1] !== "\n") inside += source[i + 1];
					i += 2;
				} else {
					inside += source[i++];
				}
			}
			add(inside, true);
			i++;
		} else if (c === "$" && source[i + 1] === "'") {
			const [value, end] = ansiC(source, i + 2);
			add(value, true);
			i = end;
		} else if (c === "$" && source[i + 1] === "{") {
			// Its value is not known, but substitutions in it run: `${x:-$(ssh host)}`.
			const end = closing(source, i + 1);
			expansionsIn(source.slice(i + 2, end), nested);
			add(source.slice(i, end + 1));
			i = end + 1;
		} else if ((c === "<" || c === ">") && source[i + 1] === "(") {
			// Process substitution: its commands run, and it stands as a word (a file name).
			const end = closing(source, i + 1);
			nested(source.slice(i + 2, end));
			add(source.slice(i, end + 1));
			i = end + 1;
		} else if (c === "(" && word !== undefined && ARRAY.test(text())) {
			// An array assignment's words are data; only substitutions among them run.
			const end = closing(source, i);
			expansionsIn(source.slice(i + 1, end), nested);
			add(source.slice(i, end + 1));
			i = end + 1;
		} else if (c === "<" || c === ">" || (c === "&" && source[i + 1] === ">")) {
			if (word !== undefined && /^\d+$/.test(text())) word = undefined; // the descriptor in 2>
			endWord();
			if (source.startsWith("<<<", i)) {
				i += 3;
			} else if (source.startsWith("<<", i)) {
				i += 2;
				const tabs = source[i] === "-";
				if (tabs) i++;
				while (BLANKS.has(source[i])) i++;
				const [delimiter, end] = delimiterWord(source, i);
				heredocs.push({ delimiter, tabs });
				i = end;
				continue;
			} else {
				REDIRECT.lastIndex = i;
				REDIRECT.test(source);
				i = REDIRECT.lastIndex;
			}
			redirectTarget = true;
		} else if (SEPARATORS.has(c)) {
			endCommand();
			i++;
		} else if (c === "{" || c === "," || c === "}") {
			word ??= [];
			word.push({ brace: c });
			i++;
		} else {
			add(c);
			i++;
		}
	}
	endCommand();
	return out;
}

/**
 * The program a shell's `-c` runs, when the command is a shell given one: the
 * first word after the shell's options, `-c` among them (`-lc`, `+c`, `-c --`).
 */
function shellPayload(command: string[]): string | undefined {
	let c = false;
	for (let k = 1; k < command.length; k++) {
		const word = command[k];
		if (word === "--" || word === "-") return c ? command[k + 1] : undefined;
		if (word === "--command") return command[k + 1]; // fish
		if (word.startsWith("--command=")) return word.slice("--command=".length);
		if (word === "--rcfile" || word === "--init-file") k++;
		else if (/^[-+][A-Za-z]+$/.test(word)) {
			if (word.includes("c")) c = true;
			if (/[oO]/.test(word)) k++; // -o and -O take an option's name
		} else if (!/^[-+]/.test(word)) return c ? word : undefined; // without -c, a script file
	}
	return undefined;
}

/** The words `env -S` makes of its string: split at blanks, with env's own quotes and escapes. */
function splitString(text: string): string[] {
	const words: string[] = [];
	let word: string | undefined;
	let quote = "";
	for (let i = 0; i < text.length; i++) {
		const c = text[i];
		if (quote === "'" && c === "'") {
			quote = "";
		} else if (quote === "'" && !(c === "\\" && "\\'".includes(text[i + 1] ?? "."))) {
			word = (word ?? "") + c;
		} else if (c === "\\") {
			const next = text[++i] ?? "";
			if (next === "c") break; // \c ends the string
			if (next === "_" && !quote) {
				if (word !== undefined) words.push(word);
				word = undefined;
			} else {
				word = (word ?? "") + (next === "_" ? " " : ESCAPES[next] ?? next);
			}
		} else if (quote === '"') {
			if (c === '"') quote = "";
			else word = (word ?? "") + c;
		} else if (/\s/.test(c)) {
			if (word !== undefined) words.push(word);
			word = undefined;
		} else if (c === "#" && word === undefined) {
			break;
		} else if (c === "'" || c === '"') {
			quote = c;
			word ??= "";
		} else {
			word = (word ?? "") + c;
		}
	}
	if (word !== undefined) words.push(word);
	return words;
}

/**
 * The command a wrapper runs, past its options and operands; undefined when it
 * runs none. Short options may share a word (`sudo -iu root`): the first that
 * takes a value takes the rest of the word, or the next word.
 */
function wrapped(name: string, command: string[]): string[] | undefined {
	const wrapper = WRAPPERS.get(name);
	if (!wrapper) return undefined;
	if (wrapper.subcommands && !wrapper.subcommands.includes(command[1])) return undefined;
	let words = command;
	let k = wrapper.subcommands ? 2 : 1;
	for (; k < words.length; k++) {
		const word = words[k];
		if (word === "--") {
			k++;
			break;
		}
		if (name === "env" && ASSIGNMENT.test(word)) continue;
		if (!word.startsWith("-")) break;
		let option = word;
		let value: string | undefined;
		if (word.startsWith("--")) {
			const equals = word.indexOf("=");
			if (equals !== -1) [option, value] = [word.slice(0, equals), word.slice(equals + 1)];
			if (wrapper.runsNothing?.includes(option)) return undefined;
			if (value === undefined && wrapper.valued?.includes(option)) value = words[++k];
		} else {
			for (let j = 1; j < word.length; j++) {
				option = `-${word[j]}`;
				if (wrapper.runsNothing?.includes(option)) return undefined;
				if (wrapper.valued?.includes(option)) {
					value = j + 1 < word.length ? word.slice(j + 1) : words[++k];
					break;
				}
			}
		}
		// env -S splits its string into more of env's own arguments: `env -S'ssh host'`.
		if (name === "env" && (option === "-S" || option === "--split-string") && value !== undefined) {
			words = [...words.slice(0, k + 1), ...splitString(value), ...words.slice(k + 1)];
		}
	}
	k += wrapper.operands ?? 0;
	return k < words.length ? words.slice(k) : undefined;
}

/**
 * Every command a simple command runs: itself, past keywords and assignments,
 * then what each wrapper, shell, eval or function header runs.
 */
function collectRuns(words: string[], out: string[][], depth: number): void {
	if (depth > MAX_DEPTH) throw new Unreadable(words.join(" "), TOO_DEEP);
	let start = 0;
	while (start < words.length && (RESERVED.has(words[start]) || ASSIGNMENT.test(words[start]))) start++;
	const command = words.slice(start);
	// `function f { ...; }`: what follows the name is the body, which runs when f is called.
	if (command[0] === "function") return collectRuns(command.slice(2), out, depth + 1);
	if (command.length === 0 || HEADERS.has(command[0])) return;
	// `coproc NAME { ...; }` names the coprocess; read past NAME as well.
	if (words.slice(0, start).includes("coproc") && COMPOUND.has(command[1])) collectRuns(command.slice(1), out, depth + 1);
	out.push(command);
	const name = basename(command[0]);
	let payload = name === "eval" ? command.slice(1).join(" ") : SHELLS.has(name) ? shellPayload(command) : undefined;
	const inner = payload === undefined ? wrapped(name, command) : undefined;
	// flock FILE -c COMMAND runs COMMAND in a shell; so do watch (but for -x) and parallel, its words joined.
	if (name === "flock" && (inner?.[0] === "-c" || inner?.[0] === "--command")) payload = inner[1] ?? "";
	const options = inner ? command.slice(1, command.length - inner.length) : [];
	if (inner && name === "watch" && !options.some((w) => w === "--exec" || /^-[A-Za-z]*x/.test(w))) payload = inner.join(" ");
	if (inner && name === "parallel") payload = inner.join(" ");
	if (payload !== undefined) {
		for (const run of commandsOf(payload)) collectRuns(run, out, depth + 1);
		return;
	}
	if (inner) collectRuns(inner, out, depth + 1);
}

/**
 * The gate's wildcard: `*` any text, `?` one character, and a trailing ` *`
 * that may also match nothing. One character is one code point here (the `u`
 * flag); the gate's `?` is one UTF-16 unit, which scripts/check_config.py
 * keeps out of the shipped rules wherever the two could differ.
 */
function wildcard(pattern: string): RegExp {
	let source = pattern
		.split("*")
		.map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replaceAll("\\?", "."))
		.join(".*");
	if (source.endsWith(" .*")) source = `${source.slice(0, -3)}( .*)?`;
	return new RegExp(`^${source}$`, "su");
}

/**
 * The first spelling of `command` the bash `rules` deny, as the gate would
 * decide that spelling; or a refusal when the command cannot be read. The rules
 * come in the file's order ({@link bashRulesOf}); an object's integer-like keys
 * would come first.
 */
export function deniedSpelling(command: string, rules: Record<string, Rule> | [string, Rule][]): Denial | undefined {
	try {
		return decideSpelling(command, Array.isArray(rules) ? rules : Object.entries(rules));
	} catch (error) {
		if (error instanceof Unreadable) return { pattern: "command-guard", reason: error.message, spelling: error.spelling };
		throw error;
	}
}

function decideSpelling(command: string, rules: [string, Rule][]): Denial | undefined {
	const compiled = rules.map(([pattern, rule]) => ({ pattern, rule, regex: wildcard(pattern) }));
	const decide = (text: string) => compiled.filter(({ regex }) => regex.test(text)).at(-1);
	const action = (rule: Rule) => (typeof rule === "string" ? rule : rule.action);
	const runs: string[][] = [];
	for (const words of commandsOf(command)) collectRuns(words, runs, 0);
	let hiddenAsk: Denial | undefined;
	for (const words of runs) {
		const spellings = new Set([words.join(" "), [basename(words[0]), ...words.slice(1)].join(" ")]);
		for (const spelling of spellings) {
			const match = decide(spelling);
			if (match === undefined) continue;
			const { pattern, rule } = match;
			if (action(rule) === "deny") {
				return { pattern, reason: typeof rule === "string" ? undefined : rule.reason, spelling };
			}
			if (action(rule) === "ask") hiddenAsk ??= { pattern, spelling, reason: askReason(spelling) };
		}
	}
	const container = containerDenial(command, runs);
	if (container) return container;
	// An ask matches the command as written, so `git  push` or `'git' push`
	// would run unasked. When nothing in the text as written is asked about
	// or denied, refuse it and say how to write it so the gate can ask.
	if (hiddenAsk && !rawSegments(command).some((segment) => {
		const match = decide(segment);
		return match !== undefined && action(match.rule) !== "allow";
	})) {
		return hiddenAsk;
	}
	return undefined;
}

const OFF_MACHINE = "A container engine pointed at another machine runs every container there, past the egress proxy. Not available here; see LOCKDOWN.md.";
const NO_NETWORK = "Containers run here only with no network: give `--network=none` among the run's own options, before the image. See LOCKDOWN.md.";

/** A container run that would get a network, or an engine set to run elsewhere. */
function containerDenial(command: string, runs: string[][]): Denial | undefined {
	for (const words of commandsOf(command)) {
		const remote = words.find((word) => REMOTE_ENGINE.test(word));
		if (remote) return { pattern: remote.split("=")[0], reason: OFF_MACHINE, spelling: words.join(" ") };
	}
	for (const words of runs) {
		if (!ENGINES.has(basename(words[0]))) continue;
		let k = 1;
		if (words[k] === "container") k++;
		if (words[k] !== "run" && words[k] !== "create") continue;
		if (!runsWithoutNetwork(words.slice(k + 1))) {
			return { pattern: `${basename(words[0])} ${words.slice(1, k + 1).join(" ")}`, reason: NO_NETWORK, spelling: words.join(" ") };
		}
	}
	return undefined;
}

/** True when the last network option before the image is `none`. */
function runsWithoutNetwork(args: string[]): boolean {
	let network: string | undefined;
	for (let i = 0; i < args.length; i++) {
		const word = args[i];
		if (word === "--" || !word.startsWith("-")) break;
		const [name, inline] = word.startsWith("--") && word.includes("=") ? [word.slice(0, word.indexOf("=")), word.slice(word.indexOf("=") + 1)] : [word, undefined];
		if (NETWORK_OPTIONS.has(name)) network = inline ?? args[++i];
		else if (inline === undefined && RUN_VALUED.has(name)) i++;
	}
	return network === "none";
}

function askReason(spelling: string): string {
	return `It needs the user's approval, which is asked for only when the command is written plainly: run it as \`${spelling}\`.`;
}

/** The text of each command as written, roughly as the gate sees it: split at operators, assignments dropped. */
function rawSegments(command: string): string[] {
	return command
		.split(/&&|\|\||[;|&\n()`]|\$\(/)
		.map((segment) => segment.trim().replace(/^(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)+/, ""))
		.filter(Boolean);
}

/**
 * The bash rules of a pi-permission-system config, in the file's order. A JS
 * object lists integer-like keys ("7", "22") before every other, which would
 * change which rule matches last, so each key is parsed with a prefix that
 * keeps it a name, and the prefix is dropped after.
 */
export function bashRulesOf(text: string): [string, Rule][] {
	const keyed = text.replace(/"(?:[^"\\]|\\.)*"(\s*:)?/g, (string, colon) => (colon ? `"#${string.slice(1)}` : string));
	const unkey = (value: unknown): unknown =>
		Array.isArray(value) ? value.map(unkey)
		: value !== null && typeof value === "object" ? Object.fromEntries(Object.entries(value).map(([k, v]) => [k.slice(1), unkey(v)]))
		: value;
	const bash = JSON.parse(keyed)?.["#permission"]?.["#bash"];
	if (bash === null || typeof bash !== "object" || Array.isArray(bash)) return [];
	return Object.entries(bash).map(([pattern, rule]) => [pattern.slice(1), unkey(rule) as Rule]);
}

/**
 * The gate's bash rules, read at each call so an edit applies at once. No
 * readable config means no rules to add to: the gate reports a broken config
 * itself.
 */
function bashRules(): [string, Rule][] {
	const agentDir = process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent");
	try {
		return bashRulesOf(readFileSync(join(agentDir, "extensions/pi-permission-system/config.json"), "utf8"));
	} catch {
		return [];
	}
}

/** pi's own environment can point the engine elsewhere too; a local socket is fine. */
export function remoteEngineInEnvironment(command: string, env: NodeJS.ProcessEnv = process.env): Denial | undefined {
	const target = ["DOCKER_HOST", "CONTAINER_HOST", "DOCKER_CONTEXT", "CONTAINER_CONNECTION"].find((name) => {
		const value = env[name];
		return value !== undefined && value !== "" && !value.startsWith("unix://") && value !== "default";
	});
	if (!target) return undefined;
	const runs: string[][] = [];
	for (const words of commandsOf(command)) collectRuns(words, runs, 0);
	const engine = runs.find((words) => ENGINES.has(basename(words[0])));
	return engine ? { pattern: target, reason: OFF_MACHINE, spelling: engine.join(" ") } : undefined;
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event, ctx) => {
		if (event.toolName !== "bash") return undefined;
		const input = (event.input ?? {}) as Record<string, unknown>;
		if (typeof input.command !== "string") return undefined;
		let denial: Denial | undefined;
		try {
			denial = deniedSpelling(input.command, bashRules()) ?? remoteEngineInEnvironment(input.command);
		} catch {
			// A command that breaks the guard's reading is one it cannot vouch for.
			denial = { pattern: "command-guard", reason: "The command guard could not read it. Write it more plainly.", spelling: input.command };
		}
		if (!denial) return undefined;
		if (ctx.hasUI) ctx.ui.notify(`Blocked bash: it runs \`${denial.spelling}\``, "warning");
		const why = denial.reason ?? `the permission rule "${denial.pattern}" denies it.`;
		return { block: true, reason: `This command runs \`${denial.spelling}\`. ${why}` };
	});
}
