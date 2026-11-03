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

/** The values given to these options, as `--opt value` or `--opt=value`. */
function optionValues(args: string[], flags: string[]): string[] {
	const out: string[] = [];
	for (let i = 0; i < args.length; i++) {
		const eq = args[i].startsWith("--") ? args[i].indexOf("=") : -1;
		if (!flags.includes(eq > 0 ? args[i].slice(0, eq) : args[i])) continue;
		const value = eq > 0 ? args[i].slice(eq + 1) : args[++i];
		if (value !== undefined) out.push(value);
	}
	return out;
}

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

/** What one shell command installs, or nothing. */
export function describe(command: string, cwd: string): Install[] {
	const found: Install[] = [];
	// A subshell's parentheses separate commands like && does: `(cd x && pip install y)`.
	for (const raw of command.split(/&&|\|\||;|\||\n|\(|\)/)) {
		let w = words(raw.trim());
		// VAR=x cmd, sudo cmd, env VAR=x cmd, time cmd - in any order.
		while (w.length && (/^[A-Za-z_][A-Za-z0-9_]*=/.test(w[0]) || w[0] === "sudo" || w[0] === "env" || w[0] === "time")) {
			w = w.slice(1);
		}
		if (!w.length) continue;
		const tool = w[0].split("/").pop() ?? w[0];
		const pixiHome = process.env.PIXI_HOME || join(agentDir(), "pixi");
		const pixiCache = process.env.PIXI_CACHE_DIR || join(pixiHome, "cache");

		if (tool === "pixi" && w[1] === "exec") {
			const specs: string[] = [];
			for (let i = 2; i < w.length; i++) if (w[i] === "--spec" || w[i] === "-s") specs.push(w[++i]);
			found.push({
				what: `${specs.join(", ") || "a package"} from conda-forge, run with pixi exec (nothing installed)`,
				where: `downloaded packages cached in ${pixiCache}`,
				undo: "pixi clean cache",
			});
		} else if (tool === "pixi" && w[1] === "global" && w[2] === "install") {
			const pkgs = operands(w.slice(3), ["-c", "--channel", "-e", "--environment", "--expose", "-p", "--platform"]);
			found.push({
				what: `${pkgs.join(", ")} from conda-forge (pixi global install)`,
				where: `${join(pixiHome, "envs")}, with its commands in ${join(pixiHome, "bin")} on PATH`,
				undo: `pixi global uninstall ${pkgs.join(" ")}`,
			});
		} else if (tool === "pixi" && w[1] === "add") {
			const args = w.slice(2);
			const pkgs = operands(args, ["-c", "--channel", "-f", "--feature", "-p", "--platform", "--manifest-path"]);
			// --manifest-path names the manifest itself or the folder that holds it.
			const given = optionValues(args, ["--manifest-path"])[0];
			const manifest = given ? resolve(cwd, given.endsWith(".toml") ? given : join(given, "pixi.toml")) : join(cwd, "pixi.toml");
			found.push({
				what: `${pkgs.join(", ")} added to this project's pixi environment`,
				where: `${manifest} and ${join(dirname(manifest), ".pixi")}`,
				undo: `pixi remove ${pkgs.join(" ")}`,
			});
		} else if (tool === "uv" && w[1] === "add") {
			const args = w.slice(2);
			const pkgs = operands(args, UV_ADD_VALUED);
			const req = optionValues(args, ["-r", "--requirements"]).map((file) => `the packages in ${file}`);
			const project = resolve(cwd, optionValues(args, ["--project", "--directory"])[0] ?? ".");
			found.push({
				what: `${[...pkgs, ...req].join(", ")} from PyPI, added to this project's environment (uv add)`,
				where: `${join(project, "pyproject.toml")} and ${join(project, ".venv")}`,
				undo: `uv remove ${pkgs.join(" ") || "<package>"}`,
			});
		} else if (
			((tool === "pip" || tool === "pip3") && w[1] === "install") ||
			(/^python3?(\.\d+)?$/.test(tool) && w[1] === "-m" && w[2] === "pip" && w[3] === "install") ||
			(tool === "uv" && w[1] === "pip" && w[2] === "install")
		) {
			const start = tool === "uv" ? 3 : tool.startsWith("python") ? 4 : 2;
			const args = w.slice(start);
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
			const image = operands(w.slice(w[1] === "image" ? 3 : 2), ["--platform"])[0] ?? "an image";
			found.push({ what: `the container image ${image}`, where: `${tool}'s image store`, undo: `${tool} rmi ${image}` });
		} else if (tool === "brew" && (w[1] === "install" || w[1] === "reinstall")) {
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
