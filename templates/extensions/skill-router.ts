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
 * 1. Each user request is matched against the keyword table below. The two best
 *    matches are added to the conversation in full, right after the request,
 *    and any further matches are named with their paths. Naming alone was not
 *    enough: told to read `data-fitting` first, the model still did not, and
 *    repeated the mistakes the skill exists to prevent.
 * 2. The first `subagent` or `workflow` call of a session is refused until the
 *    orchestration skill it needs has been read, with the path to read. One
 *    `read` per session; after that the call goes through unchanged.
 *
 * Why a message and not the system prompt: the ELM gateway's prefix cache is
 * what makes a long session cheap, and it only helps while every request starts
 * with the same bytes. pi turns a changed system-prompt section into a system
 * message, and for openai-completions models (no mid-conversation system
 * messages) pi-ai folds the current one into the leading system prompt - so a
 * section that changed with each request ("now plot it" routes one skill, "yes,
 * go ahead" none) changed the first bytes and re-read the whole history: ~10 s
 * and ~100k prefill tokens at 100k context. The skill text is now a custom
 * message returned from before_agent_start. pi stores it in the session after
 * the user's message and sends it to the model as a user message, so it only
 * ever appends to the transcript and later requests keep their prefix.
 *
 * Each skill goes in once per session. What is already there is read back from
 * the session's context entries, not kept in memory, so a resumed, forked or
 * re-opened session does not get a second copy, and a fork (sub-agent) that
 * inherited its parent's copy does not either. A compaction that summarised an
 * injected skill away removes it from those entries, and a later request that
 * needs it gets it again: the compaction has already replaced the start of the
 * transcript, so re-adding ~1k tokens after the summary costs no cache, and a
 * summary keeps at most a paraphrase - which is what failed before.
 *
 * Only the request itself is matched. A sub-agent's task arrives wrapped in its
 * own instructions (pi-subagents' `<subagent_instructions>` block, `[Read
 * from: ...]`, an output-path footer), and the qwen agent prompt alone matches
 * several routes, so those are cut first. Sub-agents are routed like any
 * session: the qwen and llama agents set `inheritSkills: false`, so a fresh
 * child is not even told the skills exist, and this is how its task gets them.
 * (PI_ELM_CHILD does not mark a child: the launcher exports it for every pi it
 * starts, the top-level one included.) Runs not started by a user prompt -
 * auto-compaction resumes, loop drivers, sub-agent completion notices - add
 * nothing; what was injected earlier stays in the transcript.
 */

import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import type { ExtensionAPI, SessionEntry, Theme } from "@earendil-works/pi-coding-agent";

/** The custom message type the routed skills are stored under. */
const MESSAGE_TYPE = "skill-routing";
interface RoutingDetails {
	/** Skills whose full text the message carries. */
	inlined: string[];
	/** Skills it only names, with their paths. */
	named: string[];
}

/**
 * Skill -> what a request that needs it tends to say. Order is priority.
 *
 * Every word here is one that everyday software work does not use the same
 * way. Those that it does ("report", "constant", "integration", "propagate",
 * "systematic", "efficiency", "coupling", "fit", "regression", "simulate",
 * "lifetime") count only with a qualifier or with physics or data in the
 * request. A `^(?=...)(?=...)` alternative is that second kind: both words
 * anywhere in the request - "fit" with "data", "curve", "peak"..., but not
 * "fits on one line" or "overrides fit()". tests/test_skill_router.py runs this
 * table against both kinds of request.
 */
export const ROUTES: Array<[string, RegExp]> = [
	["data-fitting", /^(?=[\s\S]*\b(fit|fits|fitting|fitted|slopes?|calibrat\w*)\b(?!\s*\())(?=[\s\S]*\b(data|dataset|points|measure\w*|curves?|spectr\w*|peaks?|counts|events|histograms?|decays?|gaussian|exponential|polynomial|straight line|parameters|residuals|calibration|resonance|lineshape)\b)|\b(half[- ]?li(fe|ves)|decay (constant|curve|rate)s?|chi2|chi-?squared?|χ²|least[- ]squares|curve_fit|iminuit|lmfit|best[- ]fit|goodness[- ]of[- ]fit|fit (function|range|parameters|results?|quality)|(linear|polynomial|logistic|nonlinear|weighted) regression|pulls)\b/i],
	["statistics-and-significance", /\b(p-?values?|\d+(\.\d+)?\s*(σ|sigma)|(statistical|discovery|observed|expected|local|global) significance|statistically significant|confidence (level|interval|belt)s?|credible intervals?|upper limits?|CLs (method|limits?|values?)|exclusion (limit|contour|region)s?|(null|alternative|background[- ]only|signal[- ]plus[- ]background) hypothes[ie]s|likelihood[- ]ratio|test statistic|look[- ]elsewhere|feldman[- ]cousins|(detector|trigger|selection|reconstruction|tagging|signal|cut|event|identification) efficienc(y|ies)|efficiency (correction|map|curve)s?)\b/i],
	["uncertainty-propagation", /\b(uncertaint(y|ies)|error bars?|error propagation|(statistical|systematic|measurement) (errors?|uncertaint\w*)|systematics|significant figures|sig figs|weighted (average|mean)s?|(in|added in) quadrature|covariance matrix|correlated (errors|inputs|uncertaint\w*))\b/i],
	["histogram-analysis", /\b(histograms?|binning|(equal|variable|log|fixed|fine|coarse|\d+) bins|bin (width|edges|contents|counts?)|cut ?flow|event selection|uproot|TTree|TH1\w*|ROOT files?)\b/i],
	["derivation-checks", /\b(derive(?!\s*(\(|from\b))|deriving(?!\s*(\(|from\b))|derivations?|derivatives?|closed[- ]form|analytic(al)? (solution|result|expression|form|continuation)s?|analytically|dimensional analysis|limiting cases?|natural units|sympy)\b|^(?=[\s\S]*\b(prove|show that)\b)(?=[\s\S]*\b(equations?|formula|identity|integral|expression|theorem|lemma|operator|commutator|hamiltonian|lagrangian|potential|eigenvalues?|inequality|series)\b)/i],
	["numerical-methods", /\b(ODEs?|PDEs?|differential equations?|numerical(ly)? (integrat\w*|solution|methods?|stability|precision|error)|numerically (stable|unstable|solve|integrat\w*|evaluat\w*|comput\w*|approximat\w*)|integrat(e|ing|ion) (this |the |an? )?(ODEs?|PDEs?|equations?|system|trajector(y|ies)|orbits?|over|from)|integrators?|integrals? (of|over|from)|quadrature (rule|method|integration)|monte[- ]?carlo|convergence (stud(y|ies)|tests?|checks?|order|rate|criteri\w*)|(order|rate) of convergence|stiff(ness)?( ODEs?| systems?| equations?| problems?| solvers?)?|eigen(value|vector|state|function|mode|system|problem|decomposition)s?|root[- ]find(ing|er)|newton[- ]raphson|runge[- ]kutta|RK4|solve_ivp|odeint|finite[- ](difference|element|volume)s?|floating[- ]point (error|precision|rounding)|round[- ]?off error|catastrophic cancellation|condition number|ill[- ]conditioned)\b|^(?=[\s\S]*\bsimulat\w*)(?=[\s\S]*\b(physics|particles?|ODEs?|PDEs?|equations? of motion|trajector(y|ies)|orbits?|time ?steps?|dynamics|lattice|n-body|monte[- ]?carlo|diffusion|ising|spins?|fluid|heat|waves?|pendulum|oscillators?|planet\w*|molecul\w*)\b)/i],
	["physical-constants", /\b((physical|fundamental|physics) constants?|(planck|boltzmann|avogadro|gravitational|fine[- ]structure|rydberg|coulomb|stefan[- ]boltzmann|hubble|fermi|coupling) constants?|speed of light|elementary charge|(electron|proton|neutron|muon|pion|kaon|higgs|top quark|[WZ] boson) (mass|charge|lifetime|width)|(masses|mass|lifetimes?|widths?) of (the )?(electron|proton|neutron|muon|tau|pion|kaon|higgs|top|bottom|charm|[a-z]+ quark|[WZ]|[WZ] boson|B meson|D meson|neutrinos?|nucle(us|i)|particles?|mesons?|baryons?|hadrons?|leptons?)|branching (ratio|fraction)s?|(strong|weak|electromagnetic|yukawa|gauge) couplings?|PDG|CODATA|particle data group)\b/i],
	["physics-documents", /\b(slides|slide ?deck|beamer|lectures?|lecture notes|problem sheets?|lab reports?|(physics|research|scientific|journal|conference) (paper|report|article)s?|(write|draft)( up)? (a |the |my )?(paper|thesis)|thesis|dissertation|latex|\.tex|bibtex|siunitx|overleaf)\b/i],
	["scientific-cpp", /(\bC\+\+|\bcpp\b|\bcmake\b|\bEigen\b|\bGSL\b|\bg\+\+|\bclang\b|\bROOT macros?\b)/i],
	["scientific-python", /\b(python|numpy|scipy|matplotlib|pandas|jupyter|ipynb|plot(s|ted|ting)?)\b/i],
	["containers", /\b(docker|podman|texlive|tex live|latexmk|pdflatex|xelatex|lualatex|compile (the |this |my |a )?(pdf|latex|\.?tex|document|paper|thesis|slides))\b/i],
];
const MAX_ROUTED = 4;
/** How many of the matches are inlined in full rather than named. */
const MAX_INLINED = 2;

/**
 * The part of a prompt that is the request. A sub-agent's prompt carries its
 * agent instructions, read/write paths and an output footer around the task;
 * a `/skill:` command carries the whole skill. None of that is what was asked.
 */
export function requestText(prompt: string): string {
	return prompt
		.replace(/<subagent_instructions>[\s\S]*?<\/subagent_instructions>/g, "")
		.replace(/<skill name="[^"]*"[^>]*>[\s\S]*?<\/skill>/g, "")
		.replace(/^\s*Task:\s*/, "")
		.replace(/^\[(Read from|Write to): [^\]\n]*\]$/gm, "")
		.replace(/\n---\n(\*\*Output:\*\*|Create and maintain progress at:|Update progress at:|Previous step output:)[\s\S]*$/, "")
		.trim();
}

/** Skills the request matches, best first. */
export function routesFor(prompt: string): string[] {
	const text = requestText(prompt);
	return ROUTES.filter(([, pattern]) => pattern.test(text)).map(([name]) => name);
}

/**
 * Skills whose text is already in these entries: routed in full by this
 * extension, read with `read`, or expanded from a `/skill:` command.
 */
function skillsIn(entries: readonly SessionEntry[]): Set<string> {
	const seen = new Set<string>();
	for (const entry of entries) {
		if (entry.type === "custom_message" && entry.customType === MESSAGE_TYPE) {
			for (const name of (entry.details as RoutingDetails | undefined)?.inlined ?? []) seen.add(name);
			continue;
		}
		if (entry.type !== "message") continue;
		const message = entry.message;
		if (message.role === "assistant") {
			for (const part of message.content) {
				if (part.type !== "toolCall" || part.name !== "read") continue;
				const name = skillFromPath(part.arguments?.path);
				if (name) seen.add(name);
			}
		} else if (message.role === "user") {
			const content = typeof message.content === "string" ? message.content
				: message.content.map((part) => (part.type === "text" ? part.text : "")).join("\n");
			for (const match of content.matchAll(/<skill name="([^"]+)"/g)) seen.add(match[1]);
		}
	}
	return seen;
}

function skillFromPath(path: unknown): string | undefined {
	return typeof path === "string" ? /([^/\\]+)[/\\]SKILL\.md$/.exec(path)?.[1] : undefined;
}

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

/** The text the model sees after the request. */
function routingMessage(inlined: string[], named: string[]): string {
	return [
		"# Skills for this request",
		"",
		`The request above matches ${inlined.length > 1 ? "these skills" : "this skill"}, included here in full: ` +
			`${inlined.join(" and ")}. Apply ${inlined.length > 1 ? "them" : "it"} to the parts of the work ` +
			`${inlined.length > 1 ? "they cover" : "it covers"}; where the request is not about that, ignore ${inlined.length > 1 ? "them" : "it"}.`,
		...(named.length
			? ["", "Also possibly relevant - read with `read` before work that they cover:",
				...named.map((name) => `- ${name}: ${skillPath(name)}`)]
			: []),
		...inlined.flatMap((name) => ["", `## Skill: ${name}`, "", skillBody(name)]),
	].join("\n");
}

/** One dim line in the conversation, so the user sees what was added; expanded, the paths. */
function renderRouting(details: RoutingDetails | undefined, expanded: boolean, outputPad: number, theme: Theme) {
	const inlined = details?.inlined ?? [];
	const named = details?.named ?? [];
	const lines = [`skills: ${inlined.join(", ")}${named.length ? ` (also named: ${named.join(", ")})` : ""}`];
	if (expanded) lines.push(...[...inlined, ...named].map((name) => `  ${skillPath(name)}`));
	const pad = " ".repeat(outputPad);
	return {
		render(width: number): string[] {
			const room = Math.max(1, width - outputPad);
			return lines.map((line) => pad + theme.fg("dim", line.length > room ? `${line.slice(0, room - 1)}…` : line));
		},
		invalidate(): void {},
	};
}

export default function (pi: ExtensionAPI) {
	/** Skills read with `read` in this runtime; the session's entries cover earlier runtimes. */
	const read = new Set<string>();

	pi.registerMessageRenderer<RoutingDetails>(MESSAGE_TYPE, (message, { expanded, outputPad }, theme) =>
		renderRouting(message.details, expanded, outputPad, theme));

	pi.on("before_agent_start", (event, ctx) => {
		if (event.messageType !== "user") return undefined;
		// Compaction-aware: a skill summarised away is no longer in these entries.
		const present = skillsIn(ctx.sessionManager.buildContextEntries());
		const matched = routesFor(event.prompt)
			.filter((name) => !present.has(name) && existsSync(skillPath(name)))
			.slice(0, MAX_ROUTED);
		if (matched.length === 0) return undefined;
		const inlined = matched.slice(0, MAX_INLINED);
		const named = matched.slice(MAX_INLINED);
		for (const name of inlined) read.add(name);
		const details: RoutingDetails = { inlined, named };
		return {
			message: { customType: MESSAGE_TYPE, content: routingMessage(inlined, named), display: true, details },
		};
	});

	pi.on("tool_call", async (event, ctx) => {
		const input = (event.input ?? {}) as Record<string, unknown>;
		if (event.toolName === "read") {
			const name = skillFromPath(input.path);
			if (name) read.add(name);
			return undefined;
		}
		const skill = requiredSkill(event.toolName, input);
		if (!skill || read.has(skill) || !existsSync(skillPath(skill))) return undefined;
		// The whole branch, compacted part included: the gate asks for one read per session.
		if (skillsIn(ctx.sessionManager.getBranch()).has(skill)) return undefined;
		return {
			block: true,
			reason:
				`Read the ${skill} skill before the first ${event.toolName} call of this session: ` +
				`read ${skillPath(skill)}, then make this call again following it.`,
		};
	});
}
