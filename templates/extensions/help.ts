/**
 * /help: what this session can do, without a model turn.
 *
 * Why: `/help` is the reflex first command, and elm-pi shipped without one - a new session had to
 * read INSTALL.md to learn that `/mode`, `/todos` and five prompt templates exist, or guess.
 *
 * How: pi.getCommands() gives every slash command the session really has (extension commands, prompt
 * templates and `skill:` commands), with each one's own description, so the list cannot drift from
 * what is installed. The tools come from pi.getActiveTools(), with descriptions from getAllTools().
 * Nothing here is a static list of features: a template removed from agent/prompts
 * disappears from /help on the next session, and a tool an extension stops registering disappears too.
 *
 * Long by nature, so it is grouped and capped: commands with their one-line descriptions, the skill
 * commands as names only (they load themselves when a request needs them), the tool names on one line,
 * then where to read more. `/help <word>` filters on name and description.
 *
 * The K-Dense library (agent/skills/kdense, 167 skills since 2026-11-17) is a count and the path of
 * its index, not 167 names: named, it was most of the screen. A filter still finds one by name.
 */
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

interface Command {
	name: string;
	description?: string;
	source?: string;
	/** For a skill: where its SKILL.md is, which is how the library's are told from the rest. */
	sourceInfo?: { path?: string };
}

const inLibrary = (command: Command) => /[/\\]skills[/\\]kdense[/\\]/.test(command.sourceInfo?.path ?? "");

/** How many lines a command list may take before the rest are counted instead of named. */
const MAX_LINES = 24;

export function render(commands: Command[], tools: Command[], filter = ""): string {
	const needle = filter.trim().toLowerCase();
	const matches = (c: Command) =>
		needle === "" || c.name.toLowerCase().includes(needle) || (c.description ?? "").toLowerCase().includes(needle);
	const named = commands.filter(matches);
	const offered = tools.filter(matches);
	if (needle !== "" && named.length === 0 && offered.length === 0) return `Nothing here matches "${filter.trim()}".`;
	const group = (source: string) => named.filter((c) => c.source === source);
	const out: string[] = [];

	const typed = [...group("extension"), ...group("prompt")];
	if (typed.length) {
		out.push("Commands");
		for (const command of typed.slice(0, MAX_LINES)) {
			out.push(`  /${command.name}${command.description ? ` - ${command.description}` : ""}`);
		}
		if (typed.length > MAX_LINES) out.push(`  ... and ${typed.length - MAX_LINES} more`);
	}

	const bare = (c: Command) => c.name.replace(/^skill:/, "");
	const skills = group("skill").filter((c) => !inLibrary(c)).map(bare);
	const library = group("skill").filter(inLibrary);
	if (skills.length || library.length) {
		out.push("", "Skills (loaded automatically when a request needs them)");
		if (skills.length) out.push(`  ${skills.join(", ")}`);
		if (library.length && needle !== "") out.push(`  K-Dense library: ${library.map(bare).join(", ")}`);
		if (library.length && needle === "") {
			const index = join(dirname(library[0].sourceInfo?.path ?? ""), "..", "INDEX.md");
			out.push(`  K-Dense library: ${library.length} more, named when a request mentions one or loaded with /skill:<name> - ${index}`);
		}
	}

	const known = named.filter((c) => c.source !== "extension" && c.source !== "prompt" && c.source !== "skill");
	if (known.length) {
		out.push("", "Also");
		for (const command of known.slice(0, MAX_LINES)) out.push(`  /${command.name}`);
	}

	if (offered.length) out.push("", `Tools offered now: ${offered.map((tool) => tool.name).join(", ")}`);
	if (needle === "") {
		const install = process.env.PI_CODING_AGENT_DIR ? dirname(process.env.PI_CODING_AGENT_DIR) : homedir();
		out.push("", `Read more: ${join(install, "INSTALL.md")} (every part and setting), ${join(install, "README.md")}`);
	}
	return out.join("\n");
}

export default function (pi: ExtensionAPI) {
	pi.registerCommand("help", {
		description: "list this session's commands, skills and tools",
		handler: async (args, ctx) => {
			const commands = (pi.getCommands?.() ?? []) as Command[];
			// The 2026-11-15 UI replay advertised disabled web tools and could not find bash by name.
			const known = new Map((pi.getAllTools?.() ?? []).map((tool) => [tool.name, tool]));
			const tools = (pi.getActiveTools?.() ?? []).map((name) => known.get(name) ?? { name });
			ctx.ui.notify(render(commands, tools, args ?? ""), "info");
		},
	});
}
