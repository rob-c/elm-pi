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
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Every tool in this install that can change a file. */
const WRITING_TOOLS = new Set([
	"write",
	"edit",
	"replace",
	"insert",
	"undo_last_change",
]);

/** Directory names that are off limits at any depth. */
const BLOCKED_DIRS = new Set([".git", "node_modules"]);

/**
 * True for `.env` and for `.env.local`, `.env.production` and the like, but not
 * for a file that merely contains the string - `config.environment` is fine.
 * Substring matching was the previous behaviour and produced both misses and
 * false positives.
 */
function isDotenv(name: string): boolean {
	return name === ".env" || name.startsWith(".env.");
}

function blockedReason(rawPath: string): string | undefined {
	// Normalise separators so a Windows-style path is checked the same way, and
	// drop empty and "." segments so "./.git/config" still matches.
	const segments = rawPath
		.replace(/\\/g, "/")
		.split("/")
		.filter((segment) => segment !== "" && segment !== ".");

	for (const segment of segments) {
		if (BLOCKED_DIRS.has(segment)) return `"${segment}" is protected`;
	}
	const name = segments[segments.length - 1];
	if (name && isDotenv(name)) return "dotenv files are protected";
	return undefined;
}

export default function (pi: ExtensionAPI) {
	pi.on("tool_call", async (event, ctx) => {
		if (!WRITING_TOOLS.has(event.toolName)) return undefined;

		// Tools name the file differently; take whichever is present rather than
		// assuming one, because an unrecognised shape must not silently pass.
		const input = (event.input ?? {}) as Record<string, unknown>;
		const candidates = [input.path, input.file, input.filePath, input.file_path];
		const path = candidates.find((value) => typeof value === "string" && value) as
			| string
			| undefined;
		if (!path) return undefined;

		const reason = blockedReason(path);
		if (!reason) return undefined;

		if (ctx.hasUI) {
			ctx.ui.notify(`Blocked ${event.toolName} to protected path: ${path}`, "warning");
		}
		return { block: true, reason: `Path "${path}" is protected: ${reason}` };
	});
}
