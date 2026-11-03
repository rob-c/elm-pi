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
 * escapes removed, words split on any whitespace, the command name also by its
 * last path segment, then again past each wrapper (`sudo`, `env`, `xargs`,
 * `command`, `exec`, `timeout`, ...) and into a `bash -c` or `eval` payload -
 * and refuses the call when the gate's own rules
 * (extensions/pi-permission-system/config.json) deny one of those spellings,
 * with that rule's reason. It only ever adds a denial; everything else is the
 * gate's to decide, asks included. A name the shell computes (`$x host`) is not
 * known until it runs, so it is not caught here either.
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

/** Substitutions inside substitutions and wrappers inside wrappers stop here. */
const MAX_DEPTH = 8;

const BLANKS = new Set([" ", "\t", "\r"]);
const SEPARATORS = new Set([";", "&", "|", "(", ")"]);
const REDIRECT = /&>>|&>|>>|>&|>\||<&|<>|>|</y;

/** Words that open or close shell syntax in front of the command they precede. */
const RESERVED = new Set(["!", "{", "}", "if", "then", "elif", "else", "fi", "while", "until", "do", "done", "esac", "coproc"]);
/** A loop, case or function header names no command. */
const HEADERS = new Set(["for", "select", "case", "function"]);
const ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*(\[[^\]]*\])?\+?=/;

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
	["env", { valued: ["-u", "--unset", "-C", "--chdir", "-P"] }],
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
	["flock", { valued: ["-w", "--timeout", "-E", "--conflict-exit-code"], operands: 1 }],
	["caffeinate", { valued: ["-t", "-w"] }],
	["watch", { valued: ["-n", "--interval"] }],
	["command", { runsNothing: ["-v", "-V"] }],
	["exec", { valued: ["-a"] }],
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

/** Index of the bracket that closes the one at `open`, skipping quoted text; the end when there is none. */
function closing(source: string, open: number): number {
	const close = source[open] === "{" ? "}" : ")";
	let depth = 0;
	for (let i = open; i < source.length; i++) {
		const c = source[i];
		if (c === "\\") i++;
		else if (c === "'") i = endOf(source, "'", i + 1);
		else if (c === '"') i = endOf(source, '"', i + 1);
		else if (c === source[open]) depth++;
		else if (c === close && --depth === 0) return i;
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

/** The value of a `$'...'` string from `start`, and the index after it. */
function ansiC(source: string, start: number): [string, number] {
	let text = "";
	let i = start;
	while (i < source.length && source[i] !== "'") {
		if (source[i] !== "\\") {
			text += source[i++];
			continue;
		}
		const code = /^(x[0-9a-fA-F]{1,2}|u[0-9a-fA-F]{1,4}|[0-7]{1,3})/.exec(source.slice(i + 1))?.[1];
		if (code) {
			text += String.fromCodePoint(/^[xu]/.test(code) ? parseInt(code.slice(1), 16) : parseInt(code, 8));
			i += 1 + code.length;
		} else {
			text += ESCAPES[source[i + 1]] ?? source.slice(i, i + 2);
			i += 2;
		}
	}
	return [text, i + 1];
}

/**
 * A `$(...)` or backtick substitution at `i`: its commands go to `nested`,
 * and the index after it comes back; undefined when there is none at `i`.
 * The substitution's output is not known, so the word keeps its source text.
 */
function substitution(source: string, i: number, nested: (inner: string) => void): number | undefined {
	if (source[i] === "`") {
		const end = endOf(source, "`", i + 1);
		nested(source.slice(i + 1, end).replace(/\\([`$\\])/g, "$1"));
		return end + 1;
	}
	if (source[i] === "$" && source[i + 1] === "(") {
		const end = closing(source, i + 1);
		if (source[i + 2] !== "(") nested(source.slice(i + 2, end)); // $(( )) is arithmetic
		return end + 1;
	}
	return undefined;
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
	let word: string | undefined;
	let redirectTarget = false;
	let heredocs: { delimiter: string; tabs: boolean }[] = [];
	const nested = (inner: string) => {
		if (depth < MAX_DEPTH) commandsOf(inner, out, depth + 1);
	};
	const endWord = () => {
		if (word === undefined) return;
		if (redirectTarget) redirectTarget = false;
		else words.push(word);
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
			word = (word ?? "") + source.slice(i, after);
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
			if (source[i + 1] !== "\n") word = (word ?? "") + (source[i + 1] ?? "");
			i += 2;
		} else if (c === "'") {
			const end = endOf(source, "'", i + 1);
			word = (word ?? "") + source.slice(i + 1, end);
			i = end + 1;
		} else if (c === '"' || (c === "$" && source[i + 1] === '"')) {
			i = source.indexOf('"', i) + 1;
			let text = "";
			while (i < source.length && source[i] !== '"') {
				const inner = substitution(source, i, nested);
				if (inner !== undefined) {
					text += source.slice(i, inner);
					i = inner;
				} else if (source[i] === "\\" && '$`"\\\n'.includes(source[i + 1] ?? "")) {
					if (source[i + 1] !== "\n") text += source[i + 1];
					i += 2;
				} else {
					text += source[i++];
				}
			}
			word = (word ?? "") + text;
			i++;
		} else if (c === "$" && source[i + 1] === "'") {
			const [text, end] = ansiC(source, i + 2);
			word = (word ?? "") + text;
			i = end;
		} else if (c === "$" && source[i + 1] === "{") {
			const end = closing(source, i + 1);
			word = (word ?? "") + source.slice(i, end + 1);
			i = end + 1;
		} else if ((c === "<" || c === ">") && source[i + 1] === "(") {
			// Process substitution: its commands run, and it stands as a word (a file name).
			const end = closing(source, i + 1);
			nested(source.slice(i + 2, end));
			word = (word ?? "") + source.slice(i, end + 1);
			i = end + 1;
		} else if (c === "<" || c === ">" || (c === "&" && source[i + 1] === ">")) {
			if (word !== undefined && /^\d+$/.test(word)) word = undefined; // the descriptor in 2>
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
		} else {
			word = (word ?? "") + c;
			i++;
		}
	}
	endCommand();
	return out;
}

/** The program a shell's `-c` runs, when the command is a shell given one. */
function shellPayload(command: string[]): string | undefined {
	for (let k = 1; k < command.length; k++) {
		const word = command[k];
		if (/^[-+][oO]$/.test(word)) k++;
		else if (/^-[A-Za-z]*c[A-Za-z]*$/.test(word)) return command[k + 1];
		else if (!/^[-+]/.test(word)) return undefined; // a script file, run with arguments
	}
	return undefined;
}

/** The command a wrapper runs, past its options and operands; undefined when it runs none. */
function wrapped(name: string, command: string[]): string[] | undefined {
	const wrapper = WRAPPERS.get(name);
	if (!wrapper) return undefined;
	if (wrapper.subcommands && !wrapper.subcommands.includes(command[1])) return undefined;
	let k = wrapper.subcommands ? 2 : 1;
	for (; k < command.length; k++) {
		const word = command[k];
		if (word === "--") {
			k++;
			break;
		}
		if (name === "env" && ASSIGNMENT.test(word)) continue;
		if (!word.startsWith("-")) break;
		if (wrapper.runsNothing?.includes(word)) return undefined;
		if (wrapper.valued?.includes(word)) k++;
	}
	k += wrapper.operands ?? 0;
	return k < command.length ? command.slice(k) : undefined;
}

/** Every command a simple command runs: itself, past keywords and assignments, then what each wrapper runs. */
function collectRuns(words: string[], out: string[][], depth: number): void {
	let start = 0;
	while (start < words.length && (RESERVED.has(words[start]) || ASSIGNMENT.test(words[start]))) start++;
	const command = words.slice(start);
	if (command.length === 0 || HEADERS.has(command[0]) || depth > MAX_DEPTH) return;
	out.push(command);
	const name = basename(command[0]);
	const payload = name === "eval" ? command.slice(1).join(" ") : SHELLS.has(name) ? shellPayload(command) : undefined;
	if (payload !== undefined) {
		for (const inner of commandsOf(payload)) collectRuns(inner, out, depth + 1);
		return;
	}
	const inner = wrapped(name, command);
	if (inner) collectRuns(inner, out, depth + 1);
}

/** The gate's wildcard: `*` any text, `?` one character, and a trailing ` *` that may also match nothing. */
function wildcard(pattern: string): RegExp {
	let source = pattern
		.split("*")
		.map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replaceAll("\\?", "."))
		.join(".*");
	if (source.endsWith(" .*")) source = `${source.slice(0, -3)}( .*)?`;
	return new RegExp(`^${source}$`, "s");
}

/** The first spelling of `command` the bash `rules` deny, as the gate would decide that spelling. */
export function deniedSpelling(command: string, rules: Record<string, Rule>): Denial | undefined {
	const compiled = Object.entries(rules).map(([pattern, rule]) => ({ pattern, rule, regex: wildcard(pattern) }));
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
 * The gate's bash rules, read at each call so an edit applies at once. No
 * readable config means no rules to add to: the gate reports a broken config
 * itself.
 */
function bashRules(): Record<string, Rule> {
	const agentDir = process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent");
	try {
		const config = JSON.parse(readFileSync(join(agentDir, "extensions/pi-permission-system/config.json"), "utf8"));
		return config?.permission?.bash ?? {};
	} catch {
		return {};
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
		const denial = deniedSpelling(input.command, bashRules()) ?? remoteEngineInEnvironment(input.command);
		if (!denial) return undefined;
		if (ctx.hasUI) ctx.ui.notify(`Blocked bash: it runs \`${denial.spelling}\``, "warning");
		const why = denial.reason ?? `the permission rule "${denial.pattern}" denies it.`;
		return { block: true, reason: `This command runs \`${denial.spelling}\`. ${why}` };
	});
}
