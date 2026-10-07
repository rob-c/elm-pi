/**
 * Skill router: makes the skills in agent/skills get used.
 *
 * pi lists each skill's name and description and leaves loading to the model,
 * and its own documentation warns that a model might not load a relevant
 * skill. Measured on this install: asked for a half-life, the model never read
 * `data-fitting` and fitted ln(N) unweighted - the method that skill forbids;
 * asked for a sub-agent workflow, it made two malformed calls before reading
 * `elm-subagent-workflows`. So the routing is not left to the model:
 *
 * 1. Each request is matched against the keyword table below. The two best
 *    matches are put into the system prompt for that request in full, and any
 *    further matches are named with their paths. Naming alone was not enough:
 *    told to read `data-fitting` first, the model still did not, and repeated
 *    the mistakes the skill exists to prevent. A skill is ~1k tokens, paid
 *    only by a request that matches it.
 * 2. The first `subagent` or `workflow` call of a session is refused until the
 *    orchestration skill it needs has been read, with the path to read. One
 *    `read` per session; after that the call goes through unchanged.
 */

import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Skill -> what a request that needs it tends to say. Order is priority. */
const ROUTES: Array<[string, RegExp]> = [
	["data-fitting", /\b(fit|fits|fitting|fitted|regression|half[- ]?li(fe|ves)|decay constant|calibrat\w*|chi2|chi-?squared|χ²|least[- ]squares|curve_fit|iminuit|resistance|slope)\b/i],
	["statistics-and-significance", /\b(significance|p-?values?|\d\s*σ|sigma|confidence (level|interval)|upper limits?|CLs|exclusion|discovery|efficienc\w*|hypothesis|look[- ]elsewhere)\b/i],
	["uncertainty-propagation", /\b(uncertaint\w*|error bars?|propagat\w*|systematics?|significant figures|weighted average)\b/i],
	["histogram-analysis", /\b(histograms?|binning|bins|cut ?flow|event selection|uproot|TTree|TH1\w*|ROOT file)\b/i],
	["derivation-checks", /\b(deriv(e|ation)|prove|show that|closed[- ]form|analytic(al(ly)?)?|dimensional analysis|limiting case)\b/i],
	["numerical-methods", /\b(simulat\w*|integrat\w*|ODEs?|differential equations?|numerically|monte ?carlo|convergen\w*|stiff|eigen\w*|root[- ]finding)\b/i],
	["physical-constants", /\b(constants?|masses|mass of|lifetimes?|branching (ratio|fraction)s?|PDG|CODATA|coupling)\b/i],
	["physics-documents", /\b(slides?|lectures?|beamer|latex|paper|report|lecture notes|problem sheets?|deck)\b/i],
	["scientific-cpp", /(\bC\+\+|\bcpp\b|\bcmake\b|\bEigen\b|\bGSL\b|\bg\+\+|\bclang\b)/i],
	["scientific-python", /\b(python|numpy|scipy|matplotlib|pandas|plot(s|ting)?|\.py\b|csv)\b/i],
];
const MAX_ROUTED = 4;
/** How many of the matches are inlined in full rather than named. */
const MAX_INLINED = 2;

/** A skill's instructions without its frontmatter. */
function skillBody(name: string): string {
	return readFileSync(skillPath(name), "utf8").replace(/^---\n[\s\S]*?\n---\n/, "").trim();
}

/** Tool -> the skill that must have been read before its first call. */
function requiredSkill(toolName: string, input: Record<string, unknown>): string | undefined {
	if (toolName === "workflow") return "elm-dynamic-workflows";
	if (toolName !== "subagent") return undefined;
	if (input.workflow !== undefined) return "elm-subagent-workflows";
	if (input.agent !== undefined || input.task !== undefined) return "elm-delegation";
	return undefined; // status, list, children.list and the like need nothing
}

function skillsDir(): string {
	return join(process.env.PI_CODING_AGENT_DIR || join(homedir(), ".pi", "agent"), "skills");
}

function skillPath(name: string): string {
	return join(skillsDir(), name, "SKILL.md");
}

export default function (pi: ExtensionAPI) {
	const read = new Set<string>();

	pi.on("before_agent_start", (event) => {
		const matched = ROUTES.filter(([name, pattern]) => pattern.test(event.prompt) && existsSync(skillPath(name)))
			.slice(0, MAX_ROUTED)
			.filter(([name]) => !read.has(name));
		if (matched.length === 0) {
			delete event.systemPromptOptions.sections.skill_routing;
			return;
		}
		const inlined = matched.slice(0, MAX_INLINED).map(([name]) => name);
		const named = matched.slice(MAX_INLINED).map(([name]) => name);
		event.systemPromptOptions.sections.skill_routing = [
			"# Skills for this request",
			"",
			`This request matches the skills below. Follow them: ${inlined.join(" and ")} ${inlined.length > 1 ? "are" : "is"} included here in full.`,
			...(named.length
				? ["", "Also relevant - read these with `read` before the parts of the work they cover:",
					...named.map((name) => `- ${name}: ${skillPath(name)}`)]
				: []),
			...inlined.flatMap((name) => ["", `## Skill: ${name}`, "", skillBody(name)]),
		].join("\n");
	});

	pi.on("tool_call", async (event) => {
		const input = (event.input ?? {}) as Record<string, unknown>;
		if (event.toolName === "read" && typeof input.path === "string") {
			const match = /([^/\\]+)[/\\]SKILL\.md$/.exec(input.path);
			if (match) read.add(match[1]);
			return undefined;
		}
		const skill = requiredSkill(event.toolName, input);
		if (!skill || read.has(skill) || !existsSync(skillPath(skill))) return undefined;
		return {
			block: true,
			reason:
				`Read the ${skill} skill before the first ${event.toolName} call of this session: ` +
				`read ${skillPath(skill)}, then make this call again following it.`,
		};
	});
}
