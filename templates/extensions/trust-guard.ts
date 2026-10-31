/**
 * trust-guard: project trust is never granted to home, the filesystem root, or
 * a folder that holds credentials, and never inherited from one.
 *
 * Project trust decides whether a folder's own .pi/ - its settings, extensions,
 * skills and system-prompt files - loads, and an extension in there runs with
 * this install's access. A saved decision covers every folder below the one it
 * names, and pi's trust prompt offers "Trust parent folder": accepted once in
 * ~/notes, that trusts ~ itself, and with it every repository cloned anywhere
 * in the home folder, including ones not opened yet. defaultProjectTrust
 * "never" (templates/settings.json) stops a new folder being trusted silently;
 * it does not stop that.
 *
 * So for a folder on the list this answers "no" before pi consults its saved
 * decisions, and a saved "yes" on a listed folder is not passed down to the
 * folders under it. A project trusted by its own name is unaffected. The list
 * is untrustedFolders in config/elm-pi.json (ELM_UNTRUSTED_EXACT and
 * ELM_UNTRUSTED_TREE through runtime.env) plus every ancestor of home - the
 * same list the launcher uses to refuse a session started in one of them.
 *
 * Only agent-dir and command-line extensions see project_trust, which is why
 * this is a local extension and on the launcher's POLICY_EXTENSIONS. A
 * command-line --approve still overrides it: pi applies that first.
 */
import { readFileSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const HOME = process.env.HOME || homedir();

/** Absolute and symlink-resolved, as pi keys trust.json. */
function canonical(path: string): string {
	const expanded = path === "~" ? HOME : path.startsWith("~/") ? join(HOME, path.slice(2)) : path;
	const absolute = resolve(expanded);
	try {
		return realpathSync(absolute);
	} catch {
		return absolute; // a folder that does not exist on this machine
	}
}

const listed = (name: string) =>
	(process.env[name] ?? "")
		.split("\n")
		.map((entry) => entry.trim())
		.filter(Boolean)
		.map(canonical);

function withAncestors(path: string): string[] {
	const out = [path];
	for (let up = dirname(path); up !== out[out.length - 1]; up = dirname(up)) out.push(up);
	return out;
}

const EXACT = new Set([...listed("ELM_UNTRUSTED_EXACT"), ...withAncestors(canonical(HOME))]);
const TREES = listed("ELM_UNTRUSTED_TREE");

export function untrusted(dir: string): boolean {
	return EXACT.has(dir) || TREES.some((tree) => dir === tree || dir.startsWith(`${tree}/`));
}

/** The saved decision pi would apply: the nearest folder at or above dir in trust.json. */
function nearestSaved(dir: string): { path: string; trusted: boolean } | undefined {
	let saved: Record<string, unknown>;
	try {
		const agentDir = process.env.PI_CODING_AGENT_DIR;
		if (!agentDir) return undefined;
		saved = JSON.parse(readFileSync(join(agentDir, "trust.json"), "utf8"));
	} catch {
		return undefined; // no file yet, or one pi itself will complain about
	}
	for (const path of withAncestors(dir)) {
		const value = saved[path];
		if (value === true || value === false) return { path, trusted: value };
	}
	return undefined;
}

export default function (pi: ExtensionAPI) {
	pi.on("project_trust", async (event, ctx) => {
		const dir = canonical(event.cwd);
		const tell = (message: string) => {
			if (ctx.hasUI) ctx.ui.notify(message, "warning");
		};

		if (untrusted(dir)) {
			tell(
				`elm-pi: ${dir} is never trusted as a project, so its .pi/ settings and extensions are not loaded. ` +
					"Work in a project folder instead. See LOCKDOWN.md.",
			);
			return { trusted: "no" };
		}

		const saved = nearestSaved(dir);
		if (saved?.trusted && saved.path !== dir && untrusted(saved.path)) {
			tell(
				`elm-pi: the trust saved for ${saved.path} would cover every folder under it, so it is ignored here. ` +
					"To trust this project, run /trust in it and choose Trust (not the parent folder).",
			);
			return { trusted: "no" };
		}

		return { trusted: "undecided" };
	});
}
