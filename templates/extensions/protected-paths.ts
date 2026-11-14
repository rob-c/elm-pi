/**
 * Protected Paths Extension
 *
 * Blocks write operations to paths that should never be edited by the agent:
 * the git metadata directory, installed dependencies, and dotenv files.
 *
 * It must name every writing tool, not just the builtin ones. This install
 * disables the builtin `edit` and does all editing through
 * pi-hashline-edit-pro's anchor tools, so an earlier version of this file -
 * which guarded only `write` and `edit` - protected a tool that does not exist
 * here and missed the ones that do. Verified at the time: the agent changed
 * `bare = false` to `bare = true` in a repository's `.git/config` through
 * `replace`, with this extension loaded.
 *
 * The elm-pi install this session runs on is protected as a whole: its guards
 * (agent/extensions), its launcher and its configuration are what hold the
 * session to ELM and to its permission mode, so a session must not edit them -
 * a change would apply from the next session on, unreviewed. elm-pi is developed
 * in a separate clone (its AGENTS.md and scripts/dev-setup.sh), and an install
 * changes through `pi update`. Left open: `.pi` folders, where pi keeps a session's
 * own files when one is started inside the install, and agent/tmp, the TMPDIR the
 * launcher gives every session (mktemp's folders, a command's temporary files).
 *
 * Names are compared case-insensitively. macOS's default filesystem is
 * case-insensitive, so a write to `.GIT/config` lands in `.git/config`; on a
 * case-sensitive filesystem the cost is only refusing an oddly named file.
 */

import { existsSync, realpathSync } from "node:fs";
import { dirname, isAbsolute, relative, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Every tool in this install that can change a file. copy and move are
 * switched off in agent/hashline/config.json, and named here anyway so that
 * turning them back on does not open a gap. */
const WRITING_TOOLS = new Set([
	"write",
	"edit",
	"replace",
	"replace_match",
	"insert",
	"copy",
	"move",
	"undo_last_change",
]);

/** Directory names that are off limits at any depth. */
const BLOCKED_DIRS = new Set([".git", "node_modules"]);

/**
 * Dotenv templates hold variable names, not values, and the permission config
 * (pi-permission-system/config.json) allows `*.env.example`; refusing it here
 * would undo that rule for every writing tool.
 */
const DOTENV_TEMPLATES = new Set([".env.example"]);

/**
 * True for `.env` and for `.env.local`, `.env.production` and the like, but not
 * for a file that merely contains the string - `config.environment` is fine.
 * Substring matching was the previous behaviour and produced both misses and
 * false positives.
 */
function isDotenv(name: string): boolean {
	if (DOTENV_TEMPLATES.has(name)) return false;
	return name === ".env" || name.startsWith(".env.");
}

function blockedReason(rawPath: string): string | undefined {
	// Normalise separators so a Windows-style path is checked the same way, and
	// drop empty and "." segments so "./.git/config" still matches.
	const segments = rawPath
		.replace(/\\/g, "/")
		.split("/")
		.filter((segment) => segment !== "" && segment !== ".");

	// Lower-cased, the segment is also the canonical name the reason gives.
	const names = segments.map((segment) => segment.toLowerCase());
	for (const segment of names) {
		if (BLOCKED_DIRS.has(segment)) return `"${segment}" is protected`;
	}
	const name = names[names.length - 1];
	if (name && isDotenv(name)) return "dotenv files are protected";
	return undefined;
}

/** The elm-pi install this session runs on: the folder above its agent dir, when it has the launcher. */
export function installDir(env: NodeJS.ProcessEnv = process.env): string | undefined {
	const agent = env.PI_CODING_AGENT_DIR;
	if (!agent) return undefined;
	const root = dirname(resolve(agent));
	if (!existsSync(resolve(root, "pi")) || !existsSync(resolve(root, "bootstrap.sh"))) return undefined;
	try {
		return realpathSync(root);
	} catch {
		return root;
	}
}

/** Why a path inside the running install may not be written, or undefined. */
export function installReason(path: string, cwd: string, install: string | undefined): string | undefined {
	if (!install) return undefined;
	let target = isAbsolute(path) ? path : resolve(cwd, path.replace(/^~(?=\/)/, process.env.HOME ?? "~"));
	// The nearest existing folder decides: a new file has no real path of its own yet.
	let probe = target;
	while (!existsSync(probe) && dirname(probe) !== probe) probe = dirname(probe);
	try {
		target = resolve(realpathSync(probe), relative(probe, target));
	} catch {
		// keep it as resolved
	}
	const rel = relative(install, target);
	if (rel === "" || rel.startsWith("..") || isAbsolute(rel)) return undefined;
	if (rel.split(/[\\/]/).some((segment) => segment.toLowerCase() === ".pi")) return undefined;
	// agent/tmp is the launcher's TMPDIR: what mktemp and every temporary file of the session's commands use.
	if (/^agent[\\/]tmp(?:[\\/]|$)/i.test(rel)) return undefined;
	return (
		`it is part of the elm-pi install this session runs on (${install}) - its guards, launcher and configuration. ` +
		"Develop elm-pi in a separate clone instead (git clone it, then scripts/dev-setup.sh there; its AGENTS.md says how); " +
		"this install changes only through `pi update`."
	);
}

export default function (pi: ExtensionAPI) {
	const install = installDir();
	pi.on("tool_call", async (event, ctx) => {
		if (!WRITING_TOOLS.has(event.toolName)) return undefined;

		// Tools name the file differently; take whichever is present rather than
		// assuming one, because an unrecognised shape must not silently pass.
		const input = (event.input ?? {}) as Record<string, unknown>;
		const candidates = [input.path, input.file, input.filePath, input.file_path];
		const path = candidates.find((value) => typeof value === "string" && value) as
			| string
			| undefined;
		if (!path) {
			// pi-hashline-edit-pro resolves the file from the anchor when no path
			// is given, so a path-free edit is invisible to this check. This install
			// sets its requirePath option; refuse rather than wave one through if
			// that setting is ever lost.
			if (event.toolName === "write" || event.toolName === "edit") return undefined;
			return {
				block: true,
				reason: `${event.toolName} must name the file it changes ("path"), so protected paths can be checked`,
			};
		}

		const reason = blockedReason(path) ?? installReason(path, ctx.cwd, install);
		if (!reason) return undefined;

		if (ctx.hasUI) {
			ctx.ui.notify(`Blocked ${event.toolName} to protected path: ${path}`, "warning");
		}
		return { block: true, reason: `Path "${path}" is protected: ${reason}` };
	});
}
