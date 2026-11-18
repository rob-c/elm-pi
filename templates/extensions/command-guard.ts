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
 * Containers get the checks the gate's text matching cannot make: a run or
 * create gets no network only when its own options say `--network none`
 * (matched as text, `docker run alpine echo --network=none` passes the rules);
 * a network it names must be one the engine says is internal; a published
 * port must be bound to loopback;
 * and an engine pointed at another machine (DOCKER_HOST and friends, set in
 * the command or in pi's environment) is refused, since every container then
 * runs off this machine.
 */

import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
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
	const container = containerDenial(command, runs) ?? systemPythonDenial(command);
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
const NO_NETWORK =
	"Containers run here with no network (`--network=none`) or, when they must reach each other, on an internal one: " +
	"`docker network create --internal NAME`, then `--network NAME` among the run's own options, before the image. See the containers skill.";
const NOT_INTERNAL = (name: string) =>
	`The network \`${name}\` is not an internal one (or does not exist), so a container on it would have a route out past the egress proxy. ` +
	"Make one with `docker network create --internal NAME` and run the container with `--network NAME`.";
const OPEN_PORT =
	"A published port is bound to this machine's loopback only: `-p 127.0.0.1:HOST:CONTAINER`. As written it would listen on every " +
	"network interface. (On an internal network a published port does not reach the Mac at all: use `docker exec` to reach a service.)";

/**
 * Whether `name` is a network of `engine` with no route out: asked of the engine, since a name says nothing. A
 * network that is missing, an engine that does not answer in five seconds, anything but a plain "true": no.
 * The user's decision of 2026-11-17: containers that must talk to each other (a head node and a compute node)
 * may, on a network made with `--internal`; measured that day on Docker Desktop 29.9 - two containers on one
 * reached each other by name, and neither reached 1.1.1.1.
 */
export type NetworkProbe = (engine: string, name: string) => boolean;
const askEngine: NetworkProbe = (engine, name) => {
	if (!/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(name)) return false;
	try {
		return execFileSync(engine, ["network", "inspect", name, "--format", "{{.Internal}}"], { encoding: "utf8", timeout: 5000, stdio: ["ignore", "pipe", "ignore"] }).trim() === "true";
	} catch {
		return false;
	}
};
let isInternal: NetworkProbe = askEngine;

/**
 * An image from a publisher nobody here has checked is pulled only with the user's say (the gate asks about
 * `pull PUBLISHER/NAME`). `run` pulls what is missing without a word, so a run of such an image that is not on
 * this machine yet is refused, with the pull to make first: suites1-ht (2026-11-17) ran `htcondor/mini:latest`
 * that way. An image already here - pulled with approval, or built here under any name - runs.
 */
const VETTED_IMAGE = /^(?:docker\.io\/)?(?:library\/[^/]+|texlive\/texlive|pandoc\/[^/]+)(?::|@|$)|^registry\.access\.redhat\.com\/ubi|^quay\.io\/(?:rockylinux|almalinuxorg|centos)\//;
export type ImageProbe = (engine: string, image: string) => boolean;
const askImage: ImageProbe = (engine, image) => {
	try {
		execFileSync(engine, ["image", "inspect", image], { timeout: 5000, stdio: "ignore" });
		return true;
	} catch {
		return false;
	}
};
let imageIsHere: ImageProbe = askImage;
/** For tests: whether the engine has the image. */
export function setImageProbe(probe?: ImageProbe): void {
	imageIsHere = probe ?? askImage;
}
const UNVETTED_IMAGE = (engine: string, image: string) =>
	`The image \`${image}\` is from a publisher nobody here has checked and is not on this machine, so this run would pull it unasked. ` +
	`Use an official image and build what you need on it, or pull it first - \`${engine} pull ${image}\`, which asks the user.`;
/** For tests: what the engine would answer. */
export function setNetworkProbe(probe?: NetworkProbe): void {
	isInternal = probe ?? askEngine;
}

/**
 * pip's and uv's switches for installing into the system's Python, set as variables. The gate matches a
 * command past its leading assignments, so `PIP_BREAK_SYSTEM_PACKAGES=1 pip install x` reads as
 * `pip install x` there; the flags themselves are its rules (`*break-system-packages*`). auto21
 * (2026-11-14) put 92 packages into Homebrew's Python with the flag.
 */
const SYSTEM_PYTHON = /^(?:PIP_BREAK_SYSTEM_PACKAGES|UV_BREAK_SYSTEM_PACKAGES|UV_SYSTEM_PYTHON)=/;
const INTO_SYSTEM_PYTHON =
	"Installing into the system's Python changes software everything else on this machine uses, and it is not " +
	"undone with the project. Install into the project's environment or this install's (`pi setup --python`); " +
	"see the scientific-python skill.";

function systemPythonDenial(command: string): Denial | undefined {
	for (const words of commandsOf(command)) {
		const setting = words.find((word) => SYSTEM_PYTHON.test(word));
		if (setting) return { pattern: setting.split("=")[0], reason: INTO_SYSTEM_PYTHON, spelling: words.join(" ") };
	}
	return undefined;
}

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
		const { network, ports, all, image } = runOptions(words.slice(k + 1));
		const pattern = `${basename(words[0])} ${words.slice(1, k + 1).join(" ")}`;
		if (network === undefined) return { pattern, reason: NO_NETWORK, spelling: words.join(" ") };
		if (network !== "none" && !isInternal(basename(words[0]), network)) return { pattern, reason: NOT_INTERNAL(network), spelling: words.join(" ") };
		if (all || ports.some((port) => !/^(?:127\.0\.0\.1|localhost|\[::1\]):/.test(port))) return { pattern, reason: OPEN_PORT, spelling: words.join(" ") };
		if (image && image.includes("/") && !VETTED_IMAGE.test(image) && /^[A-Za-z0-9][A-Za-z0-9_.:\/@-]*$/.test(image) && !imageIsHere(basename(words[0]), image)) {
			return { pattern, reason: UNVETTED_IMAGE(basename(words[0]), image), spelling: words.join(" ") };
		}
	}
	return undefined;
}

/** The run's own options, up to the image: the last network named, every published port, and `-P`. */
function runOptions(args: string[]): { network?: string; ports: string[]; all: boolean; image?: string } {
	let network: string | undefined;
	const ports: string[] = [];
	let all = false;
	let image: string | undefined;
	for (let i = 0; i < args.length; i++) {
		const word = args[i];
		if (word === "--") { image = args[i + 1]; break; }
		if (!word.startsWith("-")) { image = word; break; }
		const [name, inline] = word.startsWith("--") && word.includes("=") ? [word.slice(0, word.indexOf("=")), word.slice(word.indexOf("=") + 1)] : [word, undefined];
		if (NETWORK_OPTIONS.has(name)) network = inline ?? args[++i];
		else if (name === "-p" || name === "--publish") ports.push(inline ?? args[++i] ?? "");
		else if (name === "-P" || name === "--publish-all") all = true;
		else if (/^-p./.test(word) && !word.startsWith("--")) ports.push(word.slice(2));
		else if (inline === undefined && RUN_VALUED.has(name)) i++;
	}
	return { network, ports, all, image };
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

/**
 * `compose up` (and `run`, `create`, `start`, `restart`): the networks are in a file, not on the command line, and a
 * compose project's default network has a route out. The gate asks about compose, and an approval there says nothing
 * about the network - so the resolved configuration is read (`compose config --format json`, the engine's own
 * reading of the file, with its includes and variables) and the start is refused unless every network is
 * `internal: true`, no service sets a `network_mode` other than `none`, and every published port is bound to
 * loopback. Added with the internal-network rule (2026-11-17), before a session was asked for a compose file.
 */
export type ComposeProbe = (engine: string, before: string[], cwd: string) => string | undefined;
const askCompose: ComposeProbe = (engine, before, cwd) => {
	try {
		const argv = engine.endsWith("-compose") ? [...before, "config", "--format", "json"] : ["compose", ...before, "config", "--format", "json"];
		return execFileSync(engine, argv, { cwd, encoding: "utf8", timeout: 15000, stdio: ["ignore", "pipe", "ignore"], maxBuffer: 8 * 1024 * 1024 });
	} catch {
		return undefined;
	}
};
let composeConfig: ComposeProbe = askCompose;
/** For tests: what `compose config` would print. */
export function setComposeProbe(probe?: ComposeProbe): void {
	composeConfig = probe ?? askCompose;
}

const COMPOSE_STARTS = new Set(["up", "run", "create", "start", "restart"]);
const COMPOSE_VALUED = new Set(["-f", "--file", "-p", "--project-name", "--project-directory", "--env-file", "--profile", "--parallel", "--progress", "--ansi"]);
const INTERNAL_HOW =
	"In the compose file, make every network internal - for the one a project gets by default:\n" +
	"networks:\n  default:\n    internal: true\n" +
	"Containers then reach each other by service name and nothing else; reach a service inside with `docker compose exec`.";

/** Why this compose project may not be started, or undefined. */
export function composeProblem(json: string | undefined): string | undefined {
	if (json === undefined) return "The compose file could not be read (`docker compose config` failed): fix it before starting anything.";
	let config: any;
	try {
		config = JSON.parse(json);
	} catch {
		return "The compose file could not be read (`docker compose config` gave no JSON).";
	}
	const networks = config?.networks ?? {};
	const services = config?.services ?? {};
	for (const [name, service] of Object.entries<any>(services)) {
		const mode = service?.network_mode;
		if (mode !== undefined && mode !== "none") return `Service \`${name}\` sets network_mode: ${mode}, which has a route out past the egress proxy. ${INTERNAL_HOW}`;
		for (const port of Array.isArray(service?.ports) ? service.ports : []) {
			const host = typeof port === "object" && port !== null ? port.host_ip : undefined;
			if (!["127.0.0.1", "::1", "localhost"].includes(host)) return `Service \`${name}\` publishes a port on every network interface: bind it to loopback (\`127.0.0.1:HOST:CONTAINER\`), or drop it and use \`docker compose exec\`.`;
		}
		const used = service?.networks === undefined || service?.networks === null ? ["default"] : Object.keys(service.networks);
		for (const net of mode === "none" ? [] : used) {
			if (networks[net]?.internal !== true) return `Service \`${name}\` is on the network \`${net}\`, which is not internal, so the container would have a route out past the egress proxy. ${INTERNAL_HOW}`;
		}
	}
	return undefined;
}

export function composeDenial(command: string, cwd: string): Denial | undefined {
	for (const words of commandsOf(command)) {
		const first = basename(words[0] ?? "");
		let i: number;
		let engine: string;
		if (first === "docker-compose" || first === "podman-compose") { engine = first; i = 1; }
		else if (ENGINES.has(first) && words[1] === "compose") { engine = first; i = 2; }
		else continue;
		const before: string[] = [];
		for (; i < words.length; i++) {
			const word = words[i];
			if (!word.startsWith("-")) break;
			before.push(word);
			if (COMPOSE_VALUED.has(word) && !word.includes("=") && i + 1 < words.length) before.push(words[++i]);
		}
		if (!COMPOSE_STARTS.has(words[i] ?? "")) continue;
		const problem = composeProblem(composeConfig(engine, before, cwd));
		if (problem) return { pattern: `${engine === first && i === 1 ? first : `${first} compose`} ${words[i]}`, reason: problem, spelling: words.join(" ") };
	}
	return undefined;
}

/**
 * A shell script the command runs is read too. Every rule here reads the command given to `bash`, and
 * `./start.sh` says nothing: suites1-ht (2026-11-17) wrote run-condor-pool.sh holding `docker run -d --name ht-cm
 * IMAGE` - no network option, an image from a publisher nobody had approved - and ran it, and the container came
 * up on Docker's default network with a route out. So the scripts a command runs (`./x.sh`, `bash x.sh`,
 * `source x.sh`, after any `cd` in the same command) are read, to three scripts deep, and their text is held to
 * the same rules. Only shell scripts: a Python program that starts a container is not seen here.
 */
const SCRIPT_RUNNERS = new Set(["bash", "sh", "zsh", "dash", "ksh", "source", "."]);
const MAX_SCRIPT_BYTES = 200_000;
const MAX_SCRIPT_DEPTH = 3;

/** The shell scripts `command` runs, as [path, text], found from `cwd`. */
export function scriptsRun(command: string, cwd: string): Array<[string, string]> {
	const found: Array<[string, string]> = [];
	let dir = cwd;
	let commands: string[][];
	try {
		commands = commandsOf(command);
	} catch {
		return found;
	}
	for (const words of commands) {
		const args = words.filter((word) => !ASSIGNMENT.test(word));
		if (args.length === 0) continue;
		if (args[0] === "cd" && args[1]) {
			dir = isAbsolute(args[1]) ? args[1] : resolve(dir, args[1]);
			continue;
		}
		let named: string | undefined;
		if (SCRIPT_RUNNERS.has(basename(args[0]))) named = args.slice(1).find((word) => !word.startsWith("-"));
		else if (args[0].includes("/") || /\.(?:sh|bash)$/.test(args[0])) named = args[0];
		if (!named) continue;
		const path = isAbsolute(named) ? named : resolve(dir, named);
		try {
			const text = readFileSync(path, "utf8");
			if (text.length > MAX_SCRIPT_BYTES) continue;
			if (!/\.(?:sh|bash)$/.test(path) && !/^#!.*\b(?:sh|bash|zsh|dash|ksh)\b/.test(text.split("\n", 1)[0]) && !SCRIPT_RUNNERS.has(basename(args[0]))) continue;
			found.push([path, text]);
		} catch {
			// not a file that can be read: nothing of it runs as shell
		}
	}
	return found;
}

export function scriptDenial(command: string, cwd: string, rules: [string, Rule][], depth = 0, seen = new Set<string>()): Denial | undefined {
	if (depth >= MAX_SCRIPT_DEPTH) return undefined;
	for (const [path, text] of scriptsRun(command, cwd)) {
		if (seen.has(path)) continue;
		seen.add(path);
		let denial: Denial | undefined;
		try {
			denial = deniedSpelling(text, rules) ?? composeDenial(text, dirname(path)) ?? scriptDenial(text, dirname(path), rules, depth + 1, seen);
		} catch {
			denial = { pattern: "command-guard", reason: "The command guard could not read it. Write it more plainly.", spelling: basename(path) };
		}
		if (denial) return { ...denial, reason: `It is in the script ${basename(path)}, which this command runs. ${denial.reason ?? `The permission rule "${denial.pattern}" denies it.`}` };
	}
	return undefined;
}

/**
 * A command put in the background inside `$(...)`. The substitution reads until every process holding its
 * output has closed it, and the background one never does: `PORT=$(python3 server.py &)` waits for a server
 * that is meant to keep running. Three treadmill sessions did exactly that (bash arm local-server.1 and
 * pi.bash arm local-server.2 on 2026-11-16, local-server.2 on 2026-11-17) and each sat in that one call until
 * the driver's limit, 600 to 900 s; a person would have had to press Esc. Refused before it runs, with the two
 * spellings that work. Left alone: a background command whose output goes somewhere else (`> log`, `&>`,
 * `>&2`), which holds nothing, and a body that ends its jobs with `wait`, which is asking for exactly this.
 */
export const HELD_SUBSTITUTION =
	"`$(...)` does not return until every process holding its output has finished, and a command put in the " +
	"background inside it keeps holding it: this call would hang until the session is stopped. Start the command " +
	"outside the substitution with its output in a file - `python3 server.py > server.log 2>&1 & echo $!` - and " +
	"read what you need (a port, a ready line) from that file; inside a substitution, give the background command " +
	"its own output (`$(cmd > cmd.log 2>&1 & echo $!)`).";

/** Whether this simple command's own output goes somewhere other than the pipe it was started on. */
function stdoutElsewhere(command: string): boolean {
	for (const m of command.matchAll(/(\d*)(&>>?|>>?)(\s*)(&?[^\s;|&<>()]*)/g)) {
		const [, fd, op, , target] = m;
		if (op.startsWith("&")) return true;
		if ((fd || "1") !== "1") continue;
		if (target === "&1" || target === "") continue;
		return true;
	}
	return false;
}

/** The bodies of every `$(...)` and backquoted substitution in `source`, the nested ones too. */
function substitutionBodies(source: string, out: string[] = [], depth = 0): string[] {
	if (depth > MAX_DEPTH) return out;
	let i = 0;
	let double = false;
	while (i < source.length) {
		const c = source[i];
		if (c === "\\") { i += 2; continue; }
		if (!double && c === "'") { const end = source.indexOf("'", i + 1); i = end < 0 ? source.length : end + 1; continue; }
		if (c === '"') { double = !double; i += 1; continue; }
		if (c === "`") {
			let j = i + 1;
			while (j < source.length && source[j] !== "`") j += source[j] === "\\" ? 2 : 1;
			const body = source.slice(i + 1, j);
			out.push(body);
			substitutionBodies(body, out, depth + 1);
			i = j + 1;
			continue;
		}
		if (c === "$" && source[i + 1] === "(" && source[i + 2] !== "(") {
			let j = i + 2;
			let open = 1;
			let quote = "";
			for (; j < source.length && open > 0; j++) {
				const d = source[j];
				if (d === "\\") { j += 1; continue; }
				if (quote) { if (d === quote) quote = ""; continue; }
				if (d === "'" || d === '"') quote = d;
				else if (d === "(") open += 1;
				else if (d === ")") open -= 1;
			}
			const body = source.slice(i + 2, open === 0 ? j - 1 : j);
			out.push(body);
			substitutionBodies(body, out, depth + 1);
			i = j;
			continue;
		}
		i += 1;
	}
	return out;
}

export function heldSubstitution(command: string): Denial | undefined {
	for (const body of substitutionBodies(command)) {
		if (/(?:^|[\s;&|({])wait(?:$|[\s;&|)}])/.test(body)) continue;
		// Quoted text and nested substitutions are not this body's commands.
		let plain = "";
		for (let i = 0, quote = ""; i < body.length; i++) {
			const c = body[i];
			if (c === "\\") { plain += "  "; i += 1; continue; }
			if (quote) { if (c === quote) quote = ""; plain += c === "\n" ? "\n" : "x"; continue; }
			if (c === "'" || c === '"') { quote = c; plain += "x"; continue; }
			if (c === "#" && (i === 0 || /\s/.test(body[i - 1]))) { while (i < body.length && body[i] !== "\n") i += 1; plain += "\n"; continue; }
			plain += c;
		}
		plain = plain.replace(/\$\([^()]*\)|`[^`]*`/g, (text) => "x".repeat(text.length));
		for (let i = 0; i < plain.length; i++) {
			if (plain[i] !== "&") continue;
			const before = plain[i - 1] ?? "";
			const after = plain[i + 1] ?? "";
			if (before === "&" || before === ">" || before === "<" || before === "|" || after === "&" || after === ">") continue;
			let start = i - 1;
			while (start >= 0 && !";\n({".includes(plain[start]) && !(plain[start] === "&" && plain[start - 1] !== ">") &&
				!(plain[start] === "|" && plain[start - 1] === "|")) start -= 1;
			const job = plain.slice(start + 1, i);
			const last = job.slice(job.lastIndexOf("|") + 1);
			if (!last.trim() || stdoutElsewhere(last)) continue;
			return { pattern: "background job in $(...)", reason: HELD_SUBSTITUTION, spelling: body.slice(start + 1, i + 1).trim() };
		}
	}
	return undefined;
}

/**
 * A web server open to the network. `python3 -m http.server` listens on every
 * interface unless told otherwise, so anyone on the network can read the folder
 * it serves - in test5 (2026-11-12) a sub-agent left one serving ~/sandbox/test5,
 * and test4's parent one serving ~/sandbox/test4, still running an hour later:
 * its `pkill -f "python3 -m http.server"` missed it, macOS's framework Python
 * runs as `Python`. Refused unless it is bound to this machine, and the reason
 * says how to stop it.
 */
export const OPEN_SERVER =
	"`http.server` listens on every network interface unless it is bound, so anyone on the network could read this " +
	"folder. Bind it to elm-pi's user-visible loopback preview: `python3 -m http.server --bind 127.0.0.1 " +
	"\"$ELM_PI_PREVIEW_PORT\" & echo $!`, then open `http://127.0.0.1:$ELM_PI_PREVIEW_PORT/`; stop it by that " +
	"PID (`kill <PID>`) when you are done - `pkill -f \"python3 -m http.server\"` misses macOS's Python, which runs as " +
	"`Python`.";

export function openServer(command: string): Denial | undefined {
	const server = /\b(python[\d.]*|py)\s+(?:-[A-Za-z]+\s+)*-m\s+http\.server\b[^;&|\n]*/.exec(command);
	if (!server) return undefined;
	if (/(?:--bind(?:\s+|=)|\s-b\s+)(?:127\.0\.0\.1|localhost|::1)\b/.test(server[0])) return undefined;
	return { pattern: "http.server", reason: OPEN_SERVER, spelling: server[0].trim() };
}

/** The elm-pi install this session runs on (the folder above its agent dir, with the launcher in it). */
export function runningInstall(env: NodeJS.ProcessEnv = process.env): string | undefined {
	const agent = env.PI_CODING_AGENT_DIR;
	if (!agent) return undefined;
	const root = dirname(resolve(agent));
	if (!existsSync(join(root, "pi")) || !existsSync(join(root, "bootstrap.sh"))) return undefined;
	try {
		return realpathSync(root);
	} catch {
		return root;
	}
}

/** Commands that change every file they name; and those that change only their last (the destination). */
const CHANGES_ALL = new Set(["rm", "rmdir", "unlink", "touch", "mkdir", "chmod", "chown", "chgrp", "truncate", "tee", "mv", "shred", "patch"]);
const CHANGES_LAST = new Set(["cp", "rsync", "ln", "install", "ditto"]);
const IN_PLACE = new Set(["sed", "gsed", "perl"]);
const GIT_CHANGES = new Set(["checkout", "reset", "apply", "am", "stash", "clean", "commit", "merge", "rebase", "pull", "restore", "rm", "mv", "switch", "cherry-pick", "revert"]);

/**
 * A bash command that would change the running install - its guards, launcher or configuration. The
 * writing tools are refused there by protected-paths.ts; this is the same rule for the shell, read from
 * the command's words: what rm, mv, touch, sed -i and the like name, the destination of cp, rsync and
 * ln (copying out of the install is fine), redirections, and git commands that change the install's tree.
 * `cd` is followed through the command; `.pi` folders stay open, as for the tools.
 */
export function installWrite(command: string, cwd: string, install: string | undefined, env: NodeJS.ProcessEnv = process.env): Denial | undefined {
	if (!install) return undefined;
	let dir = cwd;
	const expand = (word: string) =>
		word
			.replace(/^["']|["']$/g, "")
			.replace(/^~(?=\/|$)/, env.HOME ?? homedir())
			.replace(/\$\{?HOME\}?/g, env.HOME ?? homedir())
			.replace(/\$\{?PI_CODING_AGENT_DIR\}?/g, env.PI_CODING_AGENT_DIR ?? "");
	const inside = (word: string): boolean => {
		const raw = expand(word);
		if (!raw || raw.startsWith("-")) return false;
		let target = isAbsolute(raw) ? raw : resolve(dir, raw);
		let probe = target;
		while (!existsSync(probe) && dirname(probe) !== probe) probe = dirname(probe);
		try {
			target = resolve(realpathSync(probe), relative(probe, target));
		} catch {
			// as resolved
		}
		const rel = relative(install, target);
		if (rel.startsWith("..") || isAbsolute(rel)) return false;
		// agent/tmp is the launcher's TMPDIR, as in protected-paths.ts
		if (/^agent\/tmp(?:\/|$)/i.test(rel)) return false;
		return !rel.split("/").some((s) => s.toLowerCase() === ".pi");
	};
	const deny = (spelling: string): Denial => ({
		pattern: "the running install",
		reason:
			`It would change the elm-pi install this session runs on (${install}) - its guards, launcher and configuration. ` +
			"Develop elm-pi in a separate clone (git clone it, then scripts/dev-setup.sh there; its AGENTS.md says how); " +
			"this install changes only through `pi update`.",
		spelling,
	});
	for (const m of command.matchAll(/(?:^|[^<>&0-9])>{1,2}\|?\s*([^\s;&|()<>]+)/g)) if (inside(m[1])) return deny(`> ${m[1]}`);
	const runs: string[][] = [];
	for (const words of commandsOf(command)) collectRuns(words, runs, 0);
	for (const run of runs) {
		const name = basename(run[0]);
		const args = run.slice(1);
		const files = args.filter((a) => !a.startsWith("-"));
		if (name === "cd") {
			const to = files[0] ? expand(files[0]) : (env.HOME ?? homedir());
			dir = isAbsolute(to) ? to : resolve(dir, to);
			continue;
		}
		let named: string[] = [];
		if (CHANGES_ALL.has(name)) named = name === "chmod" || name === "chown" || name === "chgrp" ? files.slice(1) : files;
		else if (CHANGES_LAST.has(name)) named = files.length > 1 ? files.slice(-1) : [];
		else if (IN_PLACE.has(name) && args.some((a) => /^-[A-Za-z]*i|^--in-place/.test(a))) named = files;
		else if (name === "dd") named = args.filter((a) => a.startsWith("of=")).map((a) => a.slice(3));
		else if (name === "git") {
			const at = args.indexOf("-C");
			const where = at >= 0 ? args[at + 1] : ".";
			const sub = args.find((a, i) => !a.startsWith("-") && !(at >= 0 && i === at + 1));
			if (sub && GIT_CHANGES.has(sub) && inside(where)) return deny(run.join(" "));
		}
		const hit = named.find(inside);
		if (hit) return deny(run.join(" "));
	}
	return undefined;
}

/**
 * python-before and python-after parallel.1 (2026-11-15): both children chose .pi/tmp/venv,
 * and one deleted it while the other still used it. The second run ignored the unique-scratch
 * prompt too. Refuse this shared path for creation/cleanup, while allowing existing-env use.
 */
export function sharedScratchVenv(command: string, cwd: string, env: NodeJS.ProcessEnv = process.env): Denial | undefined {
	if (env.PI_SUBAGENT_CHILD !== "1") return undefined;
	const canonical = (path: string): string => {
		let probe = path;
		while (!existsSync(probe) && dirname(probe) !== probe) probe = dirname(probe);
		try {
			return resolve(realpathSync(probe), relative(probe, path));
		} catch {
			return path;
		}
	};
	let dir = canonical(resolve(cwd));
	const scratch = canonical(join(dir, ".pi/tmp"));
	const shared = canonical(join(scratch, "venv"));
	const pathOf = (word: string): string => canonical(resolve(dir, word.replace(/\$\{PWD\}|\$PWD\b/g, dir)));
	const runs: string[][] = [];
	for (const words of commandsOf(command)) collectRuns(words, runs, 0);
	for (const run of runs) {
		const name = basename(run[0]);
		const args = run.slice(1);
		if (name === "cd") {
			const target = args.find((arg) => !arg.startsWith("-"));
			if (target) dir = pathOf(target);
			continue;
		}
		let creation: string[] | undefined;
		if (/^(?:python[\d.]*|py)$/.test(name)) {
			for (let i = 0; i < args.length; i++) {
				const arg = args[i];
				if (arg === "--" || arg === "-" || arg.startsWith("-c") || !arg.startsWith("-")) break;
				if (["-W", "-X", "--check-hash-based-pycs"].includes(arg)) { i++; continue; }
				if (arg.startsWith("-m")) {
					const module = arg === "-m" ? args[i + 1] : arg.slice(2);
					if (/^(?:venv|virtualenv)$/.test(module ?? "")) creation = args.slice(i + (arg === "-m" ? 2 : 1));
					break;
				}
			}
		} else if (name === "virtualenv") creation = args;
		else if (name === "uv") {
			const subcommand = args.findIndex((arg) => !arg.startsWith("-"));
			if (args[subcommand] === "venv") creation = args.slice(subcommand + 1);
		}
		const cleanup = ["rm", "rmdir", "unlink", "mv"].includes(name);
		if (!creation && !cleanup) continue;
		if (creation?.some((arg) => arg === "--help" || arg === "-h")) continue;
		const candidates: string[] = [];
		const operands = creation ?? args;
		for (let i = 0; i < operands.length; i++) {
			const arg = operands[i];
			if (creation && ["--prompt", "--python", "-p", "--creator", "--seeder"].includes(arg)) { i++; continue; }
			if (!arg.startsWith("-")) candidates.push(pathOf(arg));
		}
		if (!candidates.some((path) => path === shared || (cleanup && (path === scratch || path.startsWith(`${shared}/`))))) continue;
		return {
			pattern: "shared subagent scratch environment",
			spelling: run.join(" "),
			reason: "Other children may be using .pi/tmp/venv. Do not create, replace or remove that shared environment, or remove .pi/tmp itself. " +
				"Run `mkdir -p .pi/tmp`, then `mktemp -d .pi/tmp/child.XXXXXX` once; retain the returned path, create your virtualenv inside it, " +
				"and clean up only that private directory. Using an existing shared environment to run tests is allowed.",
		};
	}
	return undefined;
}

/**
 * Read-only auto: the mode between manual and auto (asked for on 2026-11-14). The gate runs manual's
 * floor - every call asks - and this reviews each ask before it reaches the user: a shell command that
 * can only read, and only inside the project, is allowed; everything else is the user's, as in manual.
 *
 * Why it exists: manual asks about every shell command, and some of what it asks about is the agent
 * looking around - `ls`, `grep`, `cat` through bash, where the `ls`, `grep` and `find` tools, which never
 * ask, were called 0 times against 202 bash calls with the session already told to prefer them. How
 * much, measured with this reviewer over eight manual sessions: 38 of 172 dialogs in seven of them
 * (22%), and 100 of 112 in the eighth, which was polling with `ls`. (A first count of "50 of 104" took
 * the first word of each command and so counted `cd images && curl -o ...` as reading: it was wrong.)
 * In three sessions in this mode, 24 reading commands ran unasked and none was asked about.
 *
 * It is read with the guard's own parser, not matched as text, and anything not provably reading is
 * left to the user: a name with a path in it, an assignment, a variable, a substitution, a redirection
 * (2>/dev/null, >/dev/null and 2>&1 aside), a flag that writes or runs something, a path outside the
 * project or with `..` in it. A wrong "this only reads" would be a hole in the mode; a wrong "ask" costs
 * one dialog.
 */
export const READ_AUTO_LINK = "elm-read-only-auto";
const READ_ONLY = new Set([
	"ls", "cat", "head", "tail", "wc", "file", "stat", "pwd", "du", "diff", "cmp", "grep", "egrep", "fgrep", "rg", "find", "cd",
	"echo", "which", "basename", "dirname", "realpath", "sort", "uniq", "cut", "tr", "nl", "tree", "true", "test", "[",
]);
/** Flags that make one of those write a file, run a program or never return. */
const NOT_READING: Record<string, RegExp> = {
	find: /^-(?:exec|execdir|ok|okdir|delete|fprint|fprint0|fprintf|fls)$/,
	rg: /^--pre(?:=|$)/,
	tail: /^(?:-[a-zA-Z0-9]*[fF][a-zA-Z0-9]*|--follow(?:=.*)?|--retry)$/,
	file: /^(?:-[a-zA-Z]*C[a-zA-Z]*|--compile)$/,
	sort: /^(?:-[a-zA-Z]*o.*|--output.*)$/,
	tree: /^(?:-o.*|--output.*)$/,
};

/** Whether `path`, as given to a command run in `cwd`, stays inside `cwd`. */
function insideProject(path: string, cwd: string): boolean {
	if (path.startsWith("~") || path.split("/").includes("..")) return false;
	if (!isAbsolute(path)) return true;
	const rel = relative(cwd, resolve(path));
	return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel));
}

/**
 * Whether a command has no redirection, variable or substitution: none outside quotes, and no `$` or
 * backtick inside double quotes, where the shell still expands them. Read one character at a time, as
 * the shell does - a pattern over the text is fooled by `"'" > x "'"`, whose quotes are not the ones
 * it sees. `grep '<nav' a.html` is plain; that case is the commonest look at a website there is.
 *
 * A backslash is followed only where the shell's rule is simple: inside single quotes it is a
 * character; inside double quotes it and the character after it are text (`grep "nav\|footer"`, the
 * second commonest); at the end of a line it joins the next. Anywhere else outside quotes it is refused
 * rather than reasoned about.
 */
function plainOutsideQuotes(command: string): boolean {
	let quote = "";
	for (let i = 0; i < command.length; i++) {
		const ch = command[i];
		if (quote === "'") {
			if (ch === "'") quote = "";
		} else if (quote === '"') {
			if (ch === "\\") i++;
			else if (ch === '"') quote = "";
			else if (ch === "$" || ch === "`") return false;
		} else if (ch === "\\") {
			if (command[i + 1] !== "\n") return false;
			i++;
		} else if (ch === "'" || ch === '"') {
			quote = ch;
		} else if (ch === ">" || ch === "<" || ch === "$" || ch === "`") {
			return false;
		}
	}
	return quote === ""; // an unclosed quote is not something to vouch for
}

/** Whether a bash command can only read, and only inside `cwd`. Anything unclear is false. */
export function readOnlyCommand(command: string, cwd: string): boolean {
	const bare = command.replace(/(^|\s)[12]?>\s*\/dev\/null(?=$|[\s;&|)])/g, "$1").replace(/(^|\s)2>&1(?=$|[\s;&|)])/g, "$1");
	if (!plainOutsideQuotes(bare)) return false;
	let commands: string[][];
	try {
		commands = commandsOf(command);
	} catch {
		return false;
	}
	if (commands.length === 0) return false;
	for (const words of commands) {
		const name = words[0] ?? "";
		if (!READ_ONLY.has(name)) return false; // a bare name on the list: `/x/ls`, `FOO=1 ls` and `sudo ls` are not
		const args = words.slice(1);
		const operands = args.filter((arg) => !arg.startsWith("-"));
		if (NOT_READING[name] && args.some((arg) => NOT_READING[name].test(arg))) return false;
		if (name === "cd" && operands.length !== 1) return false; // `cd` alone goes home; `cd -` goes anywhere
		if (name === "cd" && args.length !== 1) return false;
		if (name === "uniq" && operands.length > 1) return false; // its second operand is a file to write
		if (!operands.every((arg) => insideProject(arg, cwd))) return false;
	}
	return true;
}

/** What the reviewer says of one ask: allow a reading command in read-only auto, else leave it to the user. */
export function readAutoVerdict(
	details: { payload?: { kind?: string; evidence?: readonly { label?: string; text?: string }[] }; command?: string; toolCallId?: string; forwarding?: unknown },
	commands: ReadonlyMap<string, string>,
	cwd: string,
	env: NodeJS.ProcessEnv = process.env,
): { kind: "allow" } | { kind: "defer" } {
	const defer = { kind: "defer" as const };
	if (env.PI_ELM_READ_AUTO !== "1" || env.PI_ELM_PERMISSION_MODE !== "manual") return defer;
	if (details.payload?.kind !== "bash" || details.forwarding) return defer; // not a sub-agent's ask, not a path ask
	// The whole command, never the one piece of a chain the ask happens to name.
	const whole =
		(details.toolCallId ? commands.get(details.toolCallId) : undefined) ??
		details.payload.evidence?.find((fact) => fact.label === "full command")?.text ??
		details.command;
	return typeof whole === "string" && readOnlyCommand(whole, cwd) ? { kind: "allow" } : defer;
}

export default function (pi: ExtensionAPI) {
	const install = runningInstall();
	// The commands of this session's bash calls, by call id, for the reviewer; and where the session works.
	const asked = new Map<string, string>();
	let projectDir = process.cwd();
	let disposeLink: (() => void) | undefined;
	(pi as any).events?.on?.("permissions:ready", (data: { sessionId?: string | null }) => {
		if (disposeLink || !data?.sessionId) return;
		// The gate publishes its service process-wide under this key (its docs/cross-extension-api.md); a
		// link decides nothing until config.json names it in authorizerChain, which this install's does.
		const services = (globalThis as Record<symbol, unknown>)[Symbol.for("@gotgenes/pi-permission-system:session-services")] as
			| Map<string, { registerAuthorizer?: (name: string, authorize: (details: any) => Promise<unknown>) => () => void }>
			| undefined;
		try {
			disposeLink = services?.get(data.sessionId)?.registerAuthorizer?.(READ_AUTO_LINK, async (details) => readAutoVerdict(details, asked, projectDir));
		} catch {
			// Registered already (a reload): the first registration stays live.
		}
	});
	pi.on("session_start", async (_event: unknown, ctx: any) => {
		if (typeof ctx?.cwd === "string") projectDir = ctx.cwd;
	});
	pi.on("session_shutdown", async () => {
		disposeLink?.();
		disposeLink = undefined;
	});
	pi.on("tool_call", async (event, ctx) => {
		if (event.toolName !== "bash") return undefined;
		const input = (event.input ?? {}) as Record<string, unknown>;
		if (typeof input.command !== "string") return undefined;
		if (typeof ctx?.cwd === "string") projectDir = ctx.cwd;
		const callId = (event as { toolCallId?: string }).toolCallId;
		if (callId) {
			asked.set(callId, input.command);
			if (asked.size > 200) asked.delete(asked.keys().next().value as string);
		}
		let denial: Denial | undefined;
		try {
			denial =
				deniedSpelling(input.command, bashRules()) ??
				remoteEngineInEnvironment(input.command) ??
				openServer(input.command) ??
				heldSubstitution(input.command) ??
				composeDenial(input.command, ctx.cwd) ??
				scriptDenial(input.command, ctx.cwd, bashRules()) ??
				sharedScratchVenv(input.command, ctx.cwd) ??
				installWrite(input.command, ctx.cwd, install);
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
