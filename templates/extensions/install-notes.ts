/**
 * install-notes: when the agent installs software, the user is told what, where
 * it lives and how to remove it, and agent/installs.log keeps the record.
 *
 * Why: the prompt and the installing-software skill both ask for it, and it was
 * not done. Measured: asked to look at an EPS file on a machine without
 * Ghostscript, Qwen found conda-forge's with `pixi exec`, converted the file and
 * described the figure correctly - and its report never said that anything had
 * been downloaded, or where. What an assistant leaves on a researcher's machine
 * should not depend on it remembering to mention it.
 *
 * So after a successful `bash` command that installs - pip/uv pip, uv add, pixi
 * exec, pixi global install, pixi add, docker/podman pull, brew install - its
 * result gets a note saying what went where and how to undo it, with the
 * instruction to pass it on, and the same line is appended to agent/installs.log.
 * Commands are recognised by name, within chains and subshells (`cd x && pip
 * install y`, `(cd x && pip install y)`); an install hidden inside a script is
 * not seen.
 */

import { accessSync, appendFileSync, constants } from "node:fs";
import { homedir } from "node:os";
import { delimiter, dirname, join, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export interface Install {
	what: string;
	where: string;
	undo: string;
}

const agentDir = () => process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent");

function onPath(tool: string): string | undefined {
	for (const dir of (process.env.PATH ?? "").split(delimiter)) {
		if (!dir) continue;
		try {
			accessSync(join(dir, tool), constants.X_OK);
			return join(dir, tool);
		} catch {
			// not in this one
		}
	}
	return undefined;
}

/** Shell-ish words of one command: quotes removed, no expansion, redirections dropped. */
function words(segment: string): string[] {
	const all = [...segment.matchAll(/"([^"]*)"|'([^']*)'|(\S+)/g)].map((m) => ({ word: m[1] ?? m[2] ?? m[3], bare: m[3] !== undefined }));
	const out: string[] = [];
	for (let i = 0; i < all.length; i++) {
		const { word, bare } = all[i];
		// 2>&1, >log, 2>/dev/null, &>out - and a lone > or 2> takes the next word with it.
		const redirect = bare ? /^(\d*|&)(>>?|<)(&?\S*)$/.exec(word) : null;
		if (redirect) {
			if (redirect[3] === "") i++;
			continue;
		}
		out.push(word);
	}
	return out;
}

/**
 * The commands of a command line, split at && || ; | & and newlines outside quotes,
 * with a subshell's parentheses as entries of their own: `(cd x && pip install y)`.
 */
function commands(line: string): string[] {
	const out: string[] = [];
	let current = "";
	let quote = "";
	const cut = (mark?: string) => {
		out.push(current.trim());
		if (mark) out.push(mark);
		current = "";
	};
	for (let i = 0; i < line.length; i++) {
		const c = line[i];
		if (c === "\\" && quote !== "'") {
			// an escaped character, or a line continuation, which joins the lines
			const next = line[++i] ?? "";
			if (next !== "\n") current += c + next;
		} else if (quote) {
			if (c === quote) quote = "";
			current += c;
		} else if (c === "'" || c === '"') {
			quote = c;
			current += c;
		} else if (c === "(" || c === ")") {
			cut(c);
		} else if (c === ";" || c === "\n" || c === "|") {
			if (c === "|" && line[i + 1] === "|") i++;
			cut();
		} else if (c === "&" && line[i + 1] === "&") {
			i++;
			cut();
		} else if (c === "&" && !/[<>]/.test(line[i - 1] ?? "") && line[i + 1] !== ">") {
			// a command sent to the background; 2>&1 and &>log are redirections
			cut();
		} else {
			current += c;
		}
	}
	cut();
	return out.filter((part) => part !== "");
}

/** The index of the first operand (or of `--`): where a subcommand, or the command an option-taking wrapper runs, is. */
function firstOperand(args: string[], valued: string[]): number {
	for (let i = 0; i < args.length; i++) {
		if (args[i] === "--" || !args[i].startsWith("-")) return i;
		if (valued.includes(args[i])) i++;
	}
	return args.length;
}

/** The operands after a subcommand: not options, and not the values of the options that take one. */
function operands(args: string[], valued: string[]): string[] {
	const out: string[] = [];
	for (let i = 0; i < args.length; i++) {
		const a = args[i];
		if (valued.includes(a)) i++;
		else if (!a.startsWith("-")) out.push(a);
	}
	return out;
}

/** The values given to these options, as `--opt value`, `--opt=value`, `-o value` or `-ovalue`. */
function optionValues(args: string[], flags: string[]): string[] {
	const out: string[] = [];
	for (let i = 0; i < args.length; i++) {
		const a = args[i];
		const eq = a.startsWith("--") ? a.indexOf("=") : -1;
		const attached = eq > 0 || /^-[^-]./.test(a);
		const flag = eq > 0 ? a.slice(0, eq) : attached ? a.slice(0, 2) : a;
		if (!flags.includes(flag)) continue;
		const value = eq > 0 ? a.slice(eq + 1) : attached ? a.slice(2) : args[++i];
		if (value !== undefined) out.push(value);
	}
	return out;
}

/** A help or dry run installs nothing, though it exits 0. */
const installsNothing = (args: string[]) => args.some((a) => a === "--help" || a === "-h" || a === "--dry-run");

/** Where `cd` with these arguments goes from `here`; `here` again when that cannot be told (`cd -`, `cd $DIR`). */
function cdTo(args: string[], here: string): string {
	const target = args[firstOperand(args, [])];
	if (target === undefined || target === "--") return homedir();
	if (target === "-" || /[$`]/.test(target)) return here;
	if (target === "~" || target.startsWith("~/")) return join(homedir(), target.slice(1));
	return resolve(here, target);
}

/** The commands that run the next one, with the options of each that take a value: `sudo -u ci pip install x`. */
const WRAPPERS = new Map<string, string[]>([
	["sudo", ["-u", "--user", "-g", "--group", "-C", "--close-from", "-D", "--chdir", "-h", "--host", "-p", "--prompt",
		"-r", "--role", "-t", "--type", "-T", "--command-timeout", "-U", "--other-user"]],
	["env", ["-u", "--unset", "-C", "--chdir", "-P"]],
	["time", ["-f", "--format", "-o", "--output"]],
]);

/** Every option of `pip install` that takes a value (pip 25.1's --help), so no value is taken for a package. */
const PIP_VALUED = [
	"-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-t", "--target", "--platform",
	"--python-version", "--implementation", "--abi", "--root", "--prefix", "--src", "--upgrade-strategy",
	"-C", "--config-settings", "--global-option", "--no-binary", "--only-binary", "--progress-bar",
	"--root-user-action", "--report", "--group", "-i", "--index-url", "--extra-index-url", "-f", "--find-links",
	"--python", "--log", "--keyring-provider", "--proxy", "--retries", "--timeout", "--exists-action",
	"--trusted-host", "--cert", "--client-cert", "--cache-dir", "--use-feature", "--use-deprecated", "--resume-retries",
];
/** Those `uv pip install` adds to pip's. */
const UV_PIP_VALUED = [
	"-p", "--requirements", "--constraints", "--overrides", "-b", "--build-constraints", "--extra", "-P",
	"--upgrade-package", "--reinstall-package", "--refresh-package", "--index", "--default-index", "--index-strategy",
	"--resolution", "--prerelease", "--exclude-newer", "--no-build-isolation-package", "--config-setting",
	"--link-mode", "--python-platform", "--torch-backend", "--color", "--allow-insecure-host", "--config-file",
	"--directory", "--project",
];
/** The options of `uv add` that take a value. */
const UV_ADD_VALUED = [
	"-r", "--requirements", "-c", "--constraints", "-m", "--marker", "--optional", "--group", "--rev", "--tag",
	"--branch", "--extra", "--package", "--script", "--bounds", "--index", "--default-index", "-i", "--index-url",
	"--extra-index-url", "-f", "--find-links", "--index-strategy", "--keyring-provider", "--resolution",
	"--prerelease", "--exclude-newer", "--no-build-isolation-package", "-C", "--config-setting", "--link-mode",
	"-P", "--upgrade-package", "--reinstall-package", "--refresh-package", "-p", "--python", "--cache-dir",
	"--color", "--allow-insecure-host", "--config-file", "--directory", "--project",
];

/** pip's general options that take a value, which may come before `install` (pip 25.1's --help). */
const PIP_GENERAL_VALUED = [
	"--python", "--log", "--keyring-provider", "--proxy", "--retries", "--timeout", "--exists-action",
	"--trusted-host", "--cert", "--client-cert", "--cache-dir", "--use-feature", "--use-deprecated", "--resume-retries",
];
/** The options of `pixi add` that take a value. */
const PIXI_ADD_VALUED = [
	"-c", "--channel", "-f", "--feature", "-p", "--platform", "--manifest-path", "-g", "--git", "--branch", "--tag",
	"--rev", "-s", "--subdir", "--auth-file", "--concurrent-solves", "--concurrent-downloads",
];
/** The options of `pixi exec` that take a value; the first operand is the command it runs. */
const PIXI_EXEC_VALUED = [
	"-s", "--spec", "-w", "--with", "-c", "--channel", "-p", "--platform", "--auth-file", "--concurrent-solves",
	"--concurrent-downloads",
];
/** The options of `docker pull` and `podman pull` that take a value. */
const PULL_VALUED = [
	"--platform", "--arch", "--os", "--variant", "--authfile", "--cert-dir", "--creds", "--decryption-key", "--policy",
	"--retry", "--retry-delay",
];

/** What one shell command installs, or nothing. */
export function describe(command: string, cwd: string): Install[] {
	const found: Install[] = [];
	// A `cd` moves the project folder of the commands after it, until its subshell ends.
	let here = cwd;
	const outer: string[] = [];
	for (const part of commands(command)) {
		if (part === "(") {
			outer.push(here);
			continue;
		}
		if (part === ")") {
			here = outer.pop() ?? here;
			continue;
		}
		let w = words(part);
		// VAR=x cmd, sudo -H cmd, env VAR=x cmd, time cmd - in any order.
		for (;;) {
			const valued = WRAPPERS.get(w[0]);
			if (/^[A-Za-z_][A-Za-z0-9_]*=/.test(w[0] ?? "")) w = w.slice(1);
			else if (valued) w = w.slice(1 + firstOperand(w.slice(1), valued)).filter((x, i) => i > 0 || x !== "--");
			else break;
		}
		if (!w.length) continue;
		const tool = w[0].split("/").pop() ?? w[0];
		if (tool === "cd") {
			here = cdTo(w.slice(1), here);
			continue;
		}
		const pixiHome = process.env.PIXI_HOME || join(agentDir(), "pixi");
		const pixiCache = process.env.PIXI_CACHE_DIR || join(pixiHome, "cache");

		// pip, pip3, pip3.11; python3 -m pip; uv pip - each with options before the subcommand allowed.
		const pipAt = /^pip(\d+(\.\d+)?)?$/.test(tool) ? 1
			: /^python(\d+(\.\d+)?)?$/.test(tool) && w[1] === "-m" && w[2] === "pip" ? 3
			: tool === "uv" && w[1] === "pip" ? 2
			: -1;
		const pipSub = pipAt < 0 ? -1 : pipAt + firstOperand(w.slice(pipAt), PIP_GENERAL_VALUED);

		if (tool === "pixi" && w[1] === "exec") {
			// Only pixi's own options: those after the command it runs are that command's (rg -s).
			const own = w.slice(2, 2 + firstOperand(w.slice(2), PIXI_EXEC_VALUED));
			if (installsNothing(own)) continue;
			const specs = optionValues(own, ["-s", "--spec", "-w", "--with"]);
			found.push({
				what: `${specs.join(", ") || "a package"} from conda-forge, run with pixi exec (nothing installed)`,
				where: `downloaded packages cached in ${pixiCache}`,
				undo: "pixi clean cache",
			});
		} else if (tool === "pixi" && w[1] === "global" && w[2] === "install") {
			if (installsNothing(w.slice(3))) continue;
			const pkgs = operands(w.slice(3), ["-c", "--channel", "-e", "--environment", "--expose", "-p", "--platform"]);
			found.push({
				what: `${pkgs.join(", ")} from conda-forge (pixi global install)`,
				where: `${join(pixiHome, "envs")}, with its commands in ${join(pixiHome, "bin")} on PATH`,
				undo: `pixi global uninstall ${pkgs.join(" ")}`,
			});
		} else if (tool === "pixi" && w[1] === "add") {
			const args = w.slice(2);
			if (installsNothing(args)) continue;
			const pkgs = operands(args, PIXI_ADD_VALUED);
			// --manifest-path names the manifest itself or the folder that holds it.
			const given = optionValues(args, ["--manifest-path"])[0];
			const manifest = given ? resolve(here, given.endsWith(".toml") ? given : join(given, "pixi.toml")) : join(here, "pixi.toml");
			found.push({
				what: `${pkgs.join(", ")} added to this project's pixi environment`,
				where: `${manifest} and ${join(dirname(manifest), ".pixi")}`,
				undo: `pixi remove ${pkgs.join(" ")}`,
			});
		} else if (tool === "uv" && w[1] === "add") {
			const args = w.slice(2);
			if (installsNothing(args)) continue;
			const pkgs = operands(args, UV_ADD_VALUED);
			const req = optionValues(args, ["-r", "--requirements"]).map((file) => `the packages in ${file}`);
			const project = resolve(here, optionValues(args, ["--project", "--directory"])[0] ?? ".");
			found.push({
				what: `${[...pkgs, ...req].join(", ")} from PyPI, added to this project's environment (uv add)`,
				where: `${join(project, "pyproject.toml")} and ${join(project, ".venv")}`,
				undo: `uv remove ${pkgs.join(" ") || "<package>"}`,
			});
		} else if (pipSub >= 0 && w[pipSub] === "install") {
			// The general options before `install` count with its own: `pip --python x install y`.
			const args = [...w.slice(pipAt, pipSub), ...w.slice(pipSub + 1)];
			if (installsNothing(args)) continue;
			const pkgs = operands(args, tool === "uv" ? [...PIP_VALUED, ...UV_PIP_VALUED] : PIP_VALUED);
			const req = optionValues(args, ["-r", "--requirement", "--requirements"]).map((file) => `the packages in ${file}`);
			const target = optionValues(args, ["-t", "--target"])[0];
			// --prefix and --root install under another tree than the environment's,
			// and --user into the account's own site-packages.
			const prefix = optionValues(args, ["--prefix"])[0];
			const root = optionValues(args, ["--root"])[0];
			const user = args.includes("--user");
			// A pip or python named by path is that one; a bare name is the first on PATH.
			const python =
				optionValues(args, ["--python", "-p"])[0] ??
				(tool !== "uv" ? (w[0].includes("/") ? w[0] : (onPath(tool) ?? tool))
				: process.env.VIRTUAL_ENV ? join(process.env.VIRTUAL_ENV, "bin/python")
				: undefined);
			const names = pkgs.join(" ") || "<package>";
			found.push({
				what: `${[...pkgs, ...req].join(", ") || "Python packages"} from PyPI`,
				where: target ? `the folder ${target}/ (--target), not a Python environment`
					: prefix ? `the prefix ${prefix}/ (--prefix), outside the Python environment`
					: root ? `under ${root}/ (--root), outside the Python environment`
					: user ? `your user site-packages (\`python3 -m site --user-site\`)`
					: python ? `the Python environment of ${python}`
					: "the environment uv chose",
				undo: target ? `delete ${names} from ${target}/ (pip uninstall does not look there)`
					: prefix ? `delete ${names} from ${prefix}/ (pip uninstall does not look there)`
					: root ? `delete ${names} from ${root}/ (pip uninstall does not look there)`
					: `pip uninstall ${names}`,
			});
		} else if ((tool === "docker" || tool === "podman") && (w[1] === "pull" || (w[1] === "image" && w[2] === "pull"))) {
			const args = w.slice(w[1] === "image" ? 3 : 2);
			if (installsNothing(args)) continue;
			const image = operands(args, PULL_VALUED)[0] ?? "an image";
			found.push({ what: `the container image ${image}`, where: `${tool}'s image store`, undo: `${tool} rmi ${image}` });
		} else if (tool === "brew" && (w[1] === "install" || w[1] === "reinstall")) {
			if (installsNothing(w.slice(2))) continue;
			const pkgs = operands(w.slice(2), []);
			found.push({
				what: `${pkgs.join(", ")} (Homebrew)`,
				where: "Homebrew's prefix (`brew --prefix`), shared with everything else on this machine that uses Homebrew",
				undo: `brew uninstall ${pkgs.join(" ")}`,
			});
		}
	}
	return found;
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_result", async (event, ctx) => {
		if (event.toolName !== "bash" || event.isError) return;
		const command = typeof event.input.command === "string" ? event.input.command : "";
		const cwd = ctx?.cwd ?? process.cwd();
		const installs = describe(command, cwd);
		if (installs.length === 0) return;

		const stamp = new Date().toISOString().replace(/\.\d+Z$/, "Z");
		try {
			appendFileSync(
				join(agentDir(), "installs.log"),
				installs.map((i) => `${stamp}\t${cwd}\t${i.what}\t${i.where}\tremove: ${i.undo}\n`).join(""),
			);
		} catch {
			// the note below still reaches the user
		}
		const lines = installs.map((i) => `- ${i.what}\n  where: ${i.where}\n  remove: ${i.undo}`);
		const note =
			"[install-notes] This command installed software. Tell the user in your report - what, where it lives, " +
			`and how to remove it (also logged in ${join(agentDir(), "installs.log")}):\n${lines.join("\n")}`;
		return { content: [...event.content, { type: "text", text: note }] };
	});
}
