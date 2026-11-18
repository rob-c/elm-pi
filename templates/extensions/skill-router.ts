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
 * Three tiers, since 2026-11-17, when fifty particle and nuclear physics skills,
 * six for batch systems and the K-Dense library (167 more) were added on request:
 *
 * - The table below: the methods every analysis shares. Its best two matches
 *   are inlined, as before; nothing about them changed.
 * - Domain skills: any skill folder with a `route.json` beside its SKILL.md
 *   (`patterns`, `caseSensitive`, and the examples its tests run). They are
 *   hidden from pi's own listing (`disable-model-invocation: true`): 56 more
 *   descriptions would be 12,000 characters in every session's system prompt,
 *   for skills most sessions never need. The best match is inlined after the
 *   table's two - a method skill and the domain skill that applies it, not one
 *   in place of the other - and the next two are named.
 * - The library: agent/skills/kdense, a community collection that
 *   scripts/skill_library.py installs and indexes. These are 6-30 kB each and
 *   written for other agents, so they are never inlined: up to three that the
 *   request mentions by name are named with their paths, once per session,
 *   with a line saying whose rules win where a library skill and this install
 *   disagree.
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

import { existsSync, readdirSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, join } from "node:path";
import type { ExtensionAPI, SessionEntry, Theme } from "@earendil-works/pi-coding-agent";

/** The custom message type the routed skills are stored under. */
const MESSAGE_TYPE = "skill-routing";
interface RoutingDetails {
	/** Skills whose full text the message carries. */
	inlined: string[];
	/** Skills it only names, with their paths. */
	named: string[];
	/** Library skills it names; absent when there are none. */
	library?: string[];
}

/**
 * The pattern with \b made Unicode-aware. JavaScript's \b knows only ASCII word
 * characters, even under the u flag, so the \b after "5σ" or around "χ²" could
 * never match and those requests routed nothing.
 */
function unicodeWords(pattern: RegExp): RegExp {
	const word = "[\\p{L}\\p{N}_]";
	const boundary = `(?:(?<=${word})(?!${word})|(?<!${word})(?=${word}))`;
	return new RegExp(pattern.source.replaceAll("\\b", boundary), `${pattern.flags}u`);
}

/**
 * Skill -> what a request that needs it tends to say. Order is priority.
 *
 * Every word here is one that everyday software work does not use the same
 * way. Those that it does ("report", "constant", "integration", "propagate",
 * "systematic", "efficiency", "coupling", "fit", "regression", "simulate",
 * "lifetime") count only with a qualifier or with physics or data in the
 * request. "Fits in with", "fits into" and a clause-ending "fits in" are the
 * idiom, not a fit: "where CP violation fits in with this" beside "kaon decay"
 * routed data-fitting into a request for a Beamer deck. A `^(?=...)(?=...)` alternative is that second kind: both words
 * anywhere in the request - "fit" with "data", "curve", "peak"..., but not
 * "fits on one line" or "overrides fit()". tests/test_skill_router.py runs this
 * table against both kinds of request. A skill may have a second, case-sensitive
 * entry for a name that is only a physics term in its own casing ("ROOT file",
 * not "root file system").
 *
 * A peak to be measured is a fit whether or not the request says so: "measure the peak's position and width
 * ... on a smoothly falling background" (peak.1 and peak.2, 2026-11-17) routed only uncertainty-propagation,
 * and both sessions reported the fitted height as the number of events. "Peak" counts with a width word and
 * a data word, so "the sidebar width at peak load" stays software.
 */
export const ROUTES: Array<[string, RegExp]> = ([
	["data-fitting", /^(?=[\s\S]*\b(fit|fits|fitting|fitted|slopes?|calibrat\w*)\b(?!\s*\(|\s+in\s+with\b|\s+into\b|\s+in\s*(?:$|[,.;:!?)])))(?=[\s\S]*\b(data|dataset|points|measure\w*|curves?|spectr\w*|peaks?|counts|events|histograms?|decays?|gaussian|exponential|polynomial|straight line|parameters|residuals|calibration|resonance|lineshape)\b)|\b(half[- ]?li(fe|ves)|decay (constant|curve|rate)s?|chi2|chi-?squared?|χ²|least[- ]squares|curve_fit|iminuit|lmfit|best[- ]fit|goodness[- ]of[- ]fit|fit (function|range|parameters|results?|quality)|(linear|polynomial|logistic|nonlinear|weighted) regression|pulls)\b|^(?=[\s\S]*\bpeak(s|'s)?\b)(?=[\s\S]*\b(widths?|sigma|fwhm|centroid)\b)(?=[\s\S]*\b(background|events|spectr\w*|histograms?|gaussian|counts|mass(es)?)\b)/i],
	["statistics-and-significance", /\b(p[- ]?values?|\d+(\.\d+)?\s*(σ|sigma)|\d+(\.\d+)?\s*% (CL|C\.L|confidence level|credibility)|(statistical|discovery|observed|expected|local|global) significance|statistically significant|confidence (level|interval|belt)s?|credible intervals?|CLs (method|limits?|values?)|exclusion (limit|contour|region)s?|(null|alternative|background[- ]only|signal[- ]plus[- ]background) hypothes[ie]s|likelihood[- ]ratio|test statistic|look[- ]elsewhere|feldman[- ]cousins|(detector|trigger|selection|reconstruction|tagging|signal|cut|event|identification) efficienc(y|ies)|efficiency (correction|map|curve)s?)\b|^(?=[\s\S]*\bupper limits?\b)(?=[\s\S]*\b(CLs?|confidence|credible|cross[- ]sections?|signal|branching (ratio|fraction)s?|exclusion|frequentist|bayesian|poisson)\b)/i],
	["uncertainty-propagation", /\b(uncertaint(y|ies)|error bars?|error propagation|(statistical|systematic|measurement) (errors?|uncertaint\w*)|systematics|significant figures|sig figs|weighted (average|mean)s?|(in|added in) quadrature|covariance matrix|correlated (errors|inputs|uncertaint\w*))\b/i],
	["histogram-analysis", /\b(histograms?|binning|(equal|variable|log|fixed|fine|coarse|\d+) bins|bin (width|edges|contents|counts?)|cut ?flow|event selection|uproot|TTree|TH1\w*)\b/i],
	["histogram-analysis", /\bROOT files?\b/],
	// Two numbers said to disagree: the comparison rules, and the check that they are one quantity in two conventions.
	// "Which report is wrong?" about a batch's spread routed nothing (conventions.1-3, both arms, 2026-11-17).
	["statistics-and-significance", /^(?=[\s\S]*\b(which (?:\w+ )?is (?:wrong|right|correct)|disagree\w*|discrepan\w*|(?:different|conflicting) (?:numbers|values|figures)|do(?:es)? not agree)\b)(?=[\s\S]*\b(spread|standard deviation|variance|uncertaint\w*|measure\w*|frequenc\w*|datasets?|batch|samples?)\b)/i],
	["derivation-checks", /\b(derive(?!\s*(\(|from\b))|deriving(?!\s*(\(|from\b))|derivations?|derivatives?|closed[- ]form|analytic(al)? (solution|result|expression|form|continuation)s?|analytically|dimensional analysis|limiting cases?|natural units|sympy)\b|^(?=[\s\S]*\b(prove|show that)\b)(?=[\s\S]*\b(equations?|formula|identity|integral|expression|theorem|lemma|operator|commutator|hamiltonian|lagrangian|potential|eigenvalues?|inequality|series)\b)/i],
	["numerical-methods", /\b(ODEs?|PDEs?|differential equations?|numerical(ly)? (integrat\w*|solution|methods?|stability|precision|error)|numerically (stable|unstable|solve|integrat\w*|evaluat\w*|comput\w*|approximat\w*)|integrat(e|ing|ion) (this |the |an? )?(ODEs?|PDEs?|equations?|system|trajector(y|ies)|orbits?|over|from)|integrators?|integrals? (of|over|from)|quadrature (rule|method|integration)|monte[- ]?carlo|convergence (stud(y|ies)|tests?|checks?|order|rate|criteri\w*)|(order|rate) of convergence|stiff(ness)?( ODEs?| systems?| equations?| problems?| solvers?)?|eigen(value|vector|state|function|mode|system|problem|decomposition)s?|root[- ]find(ing|er)|newton[- ]raphson|runge[- ]kutta|RK4|solve_ivp|odeint|finite[- ](difference|element|volume)s?|floating[- ]point (error|precision|rounding)|round[- ]?off error|catastrophic cancellation|condition number|ill[- ]conditioned|(point|reactor|reaction|chemical|population) kinetics|kinetics (model|equations?)|rate equations?|(good|accurate|correct|right) to \w+ (significant (figures|digits)|digits|decimal places))\b|^(?=[\s\S]*\bsimulat\w*)(?=[\s\S]*\b(physics|particles?|ODEs?|PDEs?|equations? of motion|trajector(y|ies)|orbits?|time ?steps?|dynamics|lattice|n-body|monte[- ]?carlo|diffusion|ising|spins?|fluid|heat|waves?|pendulum|oscillators?|planet\w*|molecul\w*)\b)/i],
	["physical-constants", /\b((physical|fundamental|physics) constants?|(planck|boltzmann|avogadro|gravitational|fine[- ]structure|rydberg|coulomb|stefan[- ]boltzmann|hubble|fermi|coupling) constants?|speed of light|elementary charge|(electron|proton|neutron|muon|pion|kaon|higgs|top quark|[WZ] boson) (mass|charge|lifetime|width)|(masses|mass|lifetimes?|widths?) of (the )?(electron|proton|neutron|muon|tau|pion|kaon|higgs|top|bottom|charm|quarks|[a-z]+ quarks?|[WZ]|[WZ] boson|B meson|D meson|neutrinos?|nucle(us|i)|particles?|mesons?|baryons?|hadrons?|leptons?)|branching (ratio|fraction)s?|(strong|weak|electromagnetic|yukawa|gauge) couplings?|PDG|CODATA|particle data group|de Broglie|constants? (you|we|I) used?|where (each|the|every) constants? (came|comes?) from)\b/i],
	["physics-documents", /\b(slides|slide ?deck|beamer|lectures?|lecture notes|problem sheets?|lab reports?|(physics|research|scientific|journal|conference) (paper|report|article)s?|(write|draft)( up)? (a |the |my )?(paper|thesis)|thesis|dissertation|latex|\.tex|bibtex|siunitx|overleaf)\b/i],
	// A bug, a failing test or code from a spec. On eight harder coding tasks run twice (2026-11-14) the
	// five failures were all fixes that stopped at the reported example; nothing routed, since every other
	// skill here is a physics or analysis method.
	// Widened the same day: the first pattern reached three of eight task wordings ("Fix HitCounter so",
	// "prints 3000 but", "takes minutes" went unmatched), and the gain - 11 to 14 of 16 - was all in those three.
	["changing-code", /\b((fix|find|track down|hunt)\w* (a |the |this |that |my )?bugs?|debug(ging)?|tracebacks?|stack traces?|crash(es|ed|ing)?|(tests?|builds?)[`'"]? (is |are |keeps? )?(fail(s|ing|ed)?|broken)|failing tests?|wrong (answer|output|result|number|value|total)s?|cannot be right|refactor(ing|ed)?|fix (it|the (code|bug|cause|function|mistake|error))|find (the|out) (mistake|why|cause)|(add|write|implement) (a |an |two |the |some )?(function|method|parser|class|module)s?|fix [A-Za-z_][\w.]*(\(\))?( in \S+)? so\b|fix [a-z_]+_[a-z_]+\b|fix \w+\.(py|cpp|hpp|c|h|js|ts|rs|go)\b|(prints?|returns?|gives?|says|shows?) [^.\n]{0,90}\b(but|instead of|should (print|return|be|give))\b|takes (minutes|hours|too long|forever)|too slow|speed (it|this|\w+\(\)) up|add [^.\n]{0,60}\bto \w+\.(py|cpp|hpp|c|h|js|ts|rs|go)\b)\b/i],
	["scientific-cpp", /(\bC\+\+|\bcpp\b|\bcmake\b|\bEigen\b|\bGSL\b|\bg\+\+|\bclang\b)/i],
	// CERN's ROOT by its capitals, as for histogram-analysis: "root macro" is not it.
	["scientific-cpp", /\bROOT macros?\b/],
	// "python3" too: "in Python3" routed nothing while \bpython\b needed a boundary after the n.
	["scientific-python", /\b(python[23]?|numpy|scipy|matplotlib|pandas|jupyter|ipynb|plot(s|ted|ting)?)\b/i],
	// Asked for a script's statistics without the word Python: "the median with a 68% bootstrap interval ... keep the
	// script as analysis.py" routed nothing (the SkillsBench task for this skill, 2026-11-17).
	["scientific-python", /^(?=[\s\S]*\b(bootstrap\w*|standard error|median|percentiles?|quantiles?)\b)(?=[\s\S]*(\.csv\b|\.py\b|\b(dataset|measurements?)\b))/i],
	["installing-software", /\b(install(ing|ed|s)?|brew|homebrew|apt-get|apt (install|search|show|policy|update|upgrade)|yum|dnf|zypper|command not found|not installed|(module|import)error|no module named|missing (tool|program|package|library|libraries|dependenc(y|ies)|compiler))\b/i],
	["containers", /\b(docker|podman|texlive|tex live|latexmk|pdflatex|xelatex|lualatex|compile (the |this |my |a )?(pdf|latex|\.?tex|document|paper|thesis|slides))\b/i],
	// A service or a cluster to stand up, with no recipe here: research it step by step. Both words anywhere in the
	// request - "set up" with "cluster", "deploy" with "server" - so "set up the test fixture" stays software.
	["package-admin", /^(?=[\s\S]*\b(set(ting)?( \w+){0,3}? ?up(?! to\b)|stand(ing)?( \w+){0,3}? up(?! to\b)|bring(ing)?( \w+){0,3}? up(?! to\b)|spin(ning)?( \w+){0,3}? up(?! to\b)|deploy(s|ed|ing|ment)?|provision(s|ed|ing)?|install(s|ed|ing)?|configur(e|es|ed|ing))\b)(?=[\s\S]*\b(clusters?|schedulers?|daemons?|(batch|queu(e|ing)|storage|grid) systems?|grid engine|sge|xrootd|redirectors?|(compute|computing) elements?|(central manager|head|compute|worker|execute|data|login|submit) nodes?|condor pools?|(database|web|mail|message|ldap|dns|nfs|file|license) servers?|message (queue|broker)s?|slurm|kubernetes|k8s|htcondor|nordugrid|arc ce|opensearch|elasticsearch|postgres(ql)?|mariadb|mysql|redis|rabbitmq|kafka|nginx|apache|ceph|lustre|openldap|kerberos)\b)/i],
	// Asked for workers by name ("use 5 workers in parallel", "use 5 agents"): the rules for
	// briefing children, one writer per file and what to do after the launch, before the first
	// call rather than after the gate below sends the model back for them. A count, or "fan out":
	// the bare word "subagent" is in every child's own task preamble. Routed only where the
	// session can delegate (orchestrationOnly).
	// A plugin for elm-pi itself (the treadmill, 2026-11-13): with only the repository's AGENTS.md in its
	// system prompt, one session wrote the files by hand and never set the clone up.
	// "I'd like a plugin for elm-pi: ... Build it" (dev05) has its verb after the noun: any order.
	["developing-elm-pi", /^(?=[\s\S]*\belm-?pi\b)(?=[\s\S]*\b(plugins?|extensions?|tools?|(slash )?commands?)\b)(?=[\s\S]*\b(add|make|write|build|creat\w*|develop\w*|implement\w*|new|like|want|need|give)\b)/i],
	["elm-delegation", /\b((\d+|two|three|four|five|six|seven|eight|nine|ten|twelve|several|multiple) (parallel )?(workers|sub-?agents)|(use|using|with|spawn|launch|run) (\d+|two|three|four|five|six|seven|eight|nine|ten|twelve|several|multiple) (parallel )?agents|fan(ning)? (it |this |the work )?out)\b/i],
] as Array<[string, RegExp]>).map(([name, pattern]): [string, RegExp] => [name, unicodeWords(pattern)]);
const MAX_ROUTED = 4;
/** How many of the matches are inlined in full rather than named. */
const MAX_INLINED = 2;
/** Domain skills (a `route.json` beside the SKILL.md) a request gets, and how many of those in full. */
const MAX_DOMAIN_ROUTED = 3;
const MAX_DOMAIN_INLINED = 1;
/** Library skills named for one request. */
const MAX_LIBRARY_NAMED = 3;
/** The community library's folder in agent/skills, and what the model is told about it. */
const LIBRARY = "kdense";
const LIBRARY_CAUTION =
	"From the K-Dense library - community skills written for other agents: where one says to install software, " +
	"set an API key or call another AI service, this install's rules decide, not the skill. Read before using the tool:";

/**
 * The part of a prompt that is the request. A sub-agent's prompt carries its
 * agent instructions, read/write paths and an output footer around the task;
 * a `/skill:` command carries the whole skill. None of that is what was asked.
 */
export function requestText(prompt: string): string {
	return prompt
		// pi-subagents' preamble to a forked child's task ("You are a delegated subagent running from a
		// fork ... Task:"): its "subagent" routed elm-delegation into every child of test5.
		.replace(/^\s*(?:Task:\s*)?You are a delegated subagent[\s\S]*?\n\s*Task:\s*\n/, "")
		.replace(/<subagent_instructions>[\s\S]*?<\/subagent_instructions>/g, "")
		.replace(/<skill name="[^"]*"[^>]*>[\s\S]*?<\/skill>/g, "")
		.replace(/^\s*Task:\s*/, "")
		.replace(/^\[(Read from|Write to): [^\]\n]*\]$/gm, "")
		.replace(/\n---\n(\*\*Output:\*\*|Create and maintain progress at:|Update progress at:|Previous step output:)[\s\S]*$/, "")
		// /ultracode's note, which says "subagents", "parallel" and "workflow" whatever was asked
		.replace(/\n\n---\n\[workflows mode armed[\s\S]*$/, "")
		.trim();
}

/** Skills the request matches, best first. */
export function routesFor(prompt: string): string[] {
	const text = requestText(prompt);
	return [...new Set(ROUTES.filter(([, pattern]) => pattern.test(text)).map(([name]) => name))];
}

/** One domain skill's route: its name and the patterns of its route.json. */
interface DomainRoute {
	name: string;
	patterns: RegExp[];
}

function compiled(sources: unknown, flags: string): RegExp[] {
	if (!Array.isArray(sources)) return [];
	const patterns: RegExp[] = [];
	for (const source of sources) {
		if (typeof source !== "string" || source === "") continue;
		try {
			// g: a request that says more of a skill's words ranks it higher (domainRoutesFor).
			const pattern = unicodeWords(new RegExp(source, flags));
			patterns.push(new RegExp(pattern.source, `${pattern.flags}g`));
		} catch {
			// A pattern that does not compile routes nothing; the skill's test says so.
		}
	}
	return patterns;
}

const domainCache = new Map<string, DomainRoute[]>();

/** The domain routes in a skills folder: every `<name>/route.json` beside a SKILL.md. Read once per folder. */
export function domainRoutes(dir: string = skillsDir()): DomainRoute[] {
	const cached = domainCache.get(dir);
	if (cached) return cached;
	const routes: DomainRoute[] = [];
	let names: string[] = [];
	try {
		names = readdirSync(dir).sort();
	} catch {
		// no skills folder: no domain routes
	}
	for (const name of names) {
		if (name.startsWith(".") || !existsSync(join(dir, name, "SKILL.md"))) continue;
		try {
			const route = JSON.parse(readFileSync(join(dir, name, "route.json"), "utf8")) as Record<string, unknown>;
			const patterns = [...compiled(route.patterns, "i"), ...compiled(route.caseSensitive, "")];
			if (patterns.length) routes.push({ name, patterns });
		} catch {
			// no route.json, or not JSON: a skill the table or the user reaches, not this
		}
	}
	domainCache.set(dir, routes);
	return routes;
}

/**
 * Domain skills the request matches, best first: the one more of whose words it says, then the
 * one it names earliest, then by name. Earliest, because a request leads with its subject: "set
 * up a Geant4 simulation of a calorimeter and get the energy resolution" matched four skills
 * once each, and in name order the simulation skill came fourth and was dropped.
 */
export function domainRoutesFor(prompt: string, dir: string = skillsDir()): string[] {
	const text = requestText(prompt);
	const scored: Array<[string, number, number]> = [];
	for (const { name, patterns } of domainRoutes(dir)) {
		let score = 0;
		let first = text.length;
		for (const pattern of patterns) {
			for (const match of text.matchAll(pattern)) {
				score += 1;
				// A both-words-anywhere pattern (`^(?=...)(?=...)`) matches nothing at 0: it says where neither word is.
				if (match[0] !== "" && match.index < first) first = match.index;
			}
		}
		if (score > 0) scored.push([name, score, first]);
	}
	return scored.sort((a, b) => b[1] - a[1] || a[2] - b[2] || (a[0] < b[0] ? -1 : 1)).map(([name]) => name);
}

const libraryCache = new Map<string, Array<[string, RegExp]>>();

/** The library's index, as scripts/skill_library.py wrote it: skill -> the words a request calls it by. */
function libraryRoutes(dir: string): Array<[string, RegExp]> {
	const cached = libraryCache.get(dir);
	if (cached) return cached;
	const routes: Array<[string, RegExp]> = [];
	try {
		const index = JSON.parse(readFileSync(join(dir, LIBRARY, "index.json"), "utf8")) as { skills?: unknown };
		for (const entry of Array.isArray(index.skills) ? index.skills : []) {
			const { name, match } = entry as { name?: unknown; match?: unknown };
			if (typeof name !== "string" || !Array.isArray(match)) continue;
			const words = match.filter((word): word is string => typeof word === "string" && word.length > 2)
				// "scikit-learn" is also written "scikit learn"; nothing else in a name is a pattern.
				.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/[- ]/g, "[- ]"));
			if (words.length) routes.push([name, unicodeWords(new RegExp(`\\b(?:${words.join("|")})\\b`, "i"))]);
		}
	} catch {
		// the library was left out of this install, or its index is not there yet
	}
	libraryCache.set(dir, routes);
	return routes;
}

/** Library skills the request mentions by name, in the index's order. */
export function libraryRoutesFor(prompt: string, dir: string = skillsDir()): string[] {
	const text = requestText(prompt);
	return libraryRoutes(dir).filter(([, pattern]) => pattern.test(text)).map(([name]) => name);
}

/** The commands that build a LaTeX document. */
const TEX_COMMANDS = ["latexmk", "pdflatex", "xelatex", "lualatex", "tectonic"];

/** Whether this PATH has any of them. */
export function texOnPath(pathEnv: string | undefined): boolean {
	return (pathEnv ?? "").split(delimiter).some((dir) => dir !== "" && TEX_COMMANDS.some((cmd) => existsSync(join(dir, cmd))));
}

/**
 * The routes for this machine. A document request where no TeX is installed
 * also needs `containers`, which says how to build it in Docker or Podman - and
 * a request rarely says "compile": "build a beamer presentation about kaon
 * decay" routed physics-documents alone, the session found no TeX, ran a docker
 * command nobody had checked would answer, and reported a deck it never built.
 * So `containers` goes right after `physics-documents`, where it is inlined with
 * it, not merely named.
 */
/** Where pi-dynamic-workflows' /ultracode and /effort note starts in a message (ultracode-note.ts). */
const ARMED = "[workflows mode armed";

/**
 * The orchestration skill a message armed by /ultracode or /effort needs, by
 * whether this session has the `workflow` tool: its own skill when it does, and
 * otherwise the `subagent` one, which says what the note means without the
 * tool. Twice the model went for `subagent({ workflow: true })` first, hit the
 * gate below, and only then read why - 11 to 14 turns later.
 */
export function orchestrationSkill(prompt: string, activeTools: readonly string[]): string | undefined {
	if (!prompt.includes(ARMED) || !canDelegate(activeTools)) return undefined;
	return activeTools.includes("workflow") ? "elm-dynamic-workflows" : "elm-subagent-workflows";
}

/** The skills for launching children: no use, and harm, in a session that cannot launch any. */
const ORCHESTRATION = new Set(["elm-delegation", "elm-subagent-workflows", "elm-dynamic-workflows"]);

/**
 * Whether this session can start children. A sub-agent cannot: pi-subagents takes the `subagent`
 * tool away. In test5 every child was given elm-delegation anyway, the parent's playbook for
 * fanning out and waiting, and acted as the parent: two waited on and polled the parent's run,
 * and one wrote all five pages over its siblings'.
 */
export function canDelegate(activeTools: readonly string[]): boolean {
	return activeTools.includes("subagent") || activeTools.includes("workflow");
}

/** The skills to route here: orchestration ones only where children can be launched. */
export function sessionRoutes(prompt: string, activeTools: readonly string[], pathEnv?: string): string[] {
	const armed = orchestrationSkill(prompt, activeTools);
	const routed = [...new Set([...(armed ? [armed] : []), ...routesHere(prompt, pathEnv)])];
	return canDelegate(activeTools) ? routed : routed.filter((name) => !ORCHESTRATION.has(name));
}

export function routesHere(prompt: string, pathEnv: string | undefined = process.env.PATH): string[] {
	const routed = routesFor(prompt);
	if (!routed.includes("physics-documents") || texOnPath(pathEnv)) return routed;
	const rest = routed.filter((name) => name !== "containers");
	rest.splice(rest.indexOf("physics-documents") + 1, 0, "containers");
	return rest;
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

/** Library skills an earlier routing message of this session named. */
function libraryNamedIn(entries: readonly SessionEntry[]): Set<string> {
	const named = new Set<string>();
	for (const entry of entries) {
		if (entry.type !== "custom_message" || entry.customType !== MESSAGE_TYPE) continue;
		for (const name of (entry.details as RoutingDetails | undefined)?.library ?? []) named.add(name);
	}
	return named;
}

function skillFromPath(path: unknown): string | undefined {
	return typeof path === "string" ? /([^/\\]+)[/\\]SKILL\.md$/.exec(path)?.[1] : undefined;
}

function libraryPath(name: string): string {
	return join(skillsDir(), LIBRARY, name, "SKILL.md");
}

/** A skill's instructions without its frontmatter. */
function skillBody(name: string): string {
	return readFileSync(skillPath(name), "utf8").replace(/^---\n[\s\S]*?\n---\n/, "").trim();
}

/** Tool -> the skill that must have been read before its first call. */
export function requiredSkill(toolName: string, input: Record<string, unknown>): string | undefined {
	if (toolName === "workflow") return "elm-dynamic-workflows";
	if (toolName !== "subagent") return undefined;
	// The built-in parallel workflow is data, not a script: elm-delegation covers it. In test6
	// (2026-11-12) the gate bounced a correct parallel call until the script skill was read.
	if (input.workflow === "parallel") return "elm-delegation";
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
function routingMessage(inlined: string[], named: string[], library: string[] = []): string {
	return [
		"# Skills for this request",
		// Only library skills matched: nothing is included, so nothing is said to be.
		...(inlined.length
			? ["",
				`The request above matches ${inlined.length > 1 ? "these skills" : "this skill"}, included here in full: ` +
					`${inlined.join(" and ")}. Apply ${inlined.length > 1 ? "them" : "it"} to the parts of the work ` +
					`${inlined.length > 1 ? "they cover" : "it covers"}; where the request is not about that, ignore ${inlined.length > 1 ? "them" : "it"}.`]
			: []),
		...(named.length
			? ["", "Also possibly relevant - read with `read` before work that they cover:",
				...named.map((name) => `- ${name}: ${skillPath(name)}`)]
			: []),
		...(library.length ? ["", LIBRARY_CAUTION, ...library.map((name) => `- ${name}: ${libraryPath(name)}`)] : []),
		...inlined.flatMap((name) => ["", `## Skill: ${name}`, "", skillBody(name)]),
	].join("\n");
}

/** One dim line in the conversation, so the user sees what was added; expanded, the paths. */
function renderRouting(details: RoutingDetails | undefined, expanded: boolean, outputPad: number, theme: Theme) {
	const inlined = details?.inlined ?? [];
	const named = details?.named ?? [];
	const library = details?.library ?? [];
	const also = [...(named.length ? [`also named: ${named.join(", ")}`] : []),
		...(library.length ? [`library: ${library.join(", ")}`] : [])];
	const lines = [`skills: ${inlined.join(", ")}${also.length ? `${inlined.length ? " " : ""}(${also.join("; ")})` : ""}`];
	if (expanded) {
		lines.push(...[...inlined, ...named].map((name) => `  ${skillPath(name)}`), ...library.map((name) => `  ${libraryPath(name)}`));
	}
	const pad = " ".repeat(outputPad);
	return {
		render(width: number): string[] {
			const room = Math.max(1, width - outputPad);
			return lines.map((line) => pad + theme.fg("dim", line.length > room ? `${line.slice(0, room - 1)}…` : line));
		},
		invalidate(): void {},
	};
}

/**
 * Asked for agents in a session that has none. `pi --fast` loads no sub-agent package: batch 4,
 * newts-fast (2026-11-14) called `subagent` and `workflow`, got "Tool not found" for each, and built
 * the site alone over 18 minutes without a word that the agents asked for did not exist; a later one
 * ran `pi -p` twice from bash and reported "both agents agree". Here because --fast loads this
 * extension: the note was first put in wait-guard.ts, which --fast does not load, and never fired.
 */
export const ASKS_FOR_AGENTS =
	/\b(\d+|two|three|four|five|six|seven|eight|nine|ten|several|multiple|many) (parallel )?(sub-?agents|agents|workers)\b|\b(use|using|with|spawn|launch|run) (parallel |some |a few )?(sub-?agents|agents|workers)\b/i;
export const NO_AGENTS_TYPE = "no-agents-note";
export const NO_AGENTS_NOTE =
	"This session has no sub-agents: it was started in a mode that leaves them out (`pi --fast`), so `subagent` and " +
	"`workflow` are not among its tools, and starting `pi` from bash is not a substitute. Do the work yourself, and say " +
	"in your first line that you are - the user asked for agents and should know they can restart without `--fast` to " +
	"have them. Do not call tools you do not have.";

/** The note for a request that asks for agents where none can be launched, or undefined. */
export function noAgentsNote(prompt: string, activeTools: readonly string[], env: NodeJS.ProcessEnv = process.env): string | undefined {
	if (env.PI_SUBAGENT_CHILD === "1" || canDelegate(activeTools)) return undefined;
	return ASKS_FOR_AGENTS.test(prompt) ? NO_AGENTS_NOTE : undefined;
}

export default function (pi: ExtensionAPI) {
	/** Skills read with `read` in this runtime; the session's entries cover earlier runtimes. */
	const read = new Set<string>();
	let saidNoAgents = false;

	pi.registerMessageRenderer<RoutingDetails>(MESSAGE_TYPE, (message, { expanded, outputPad }, theme) =>
		renderRouting(message.details, expanded, outputPad, theme));

	pi.on("before_agent_start", (event, ctx) => {
		if (event.messageType !== "user") return undefined;
		// Compaction-aware: a skill summarised away is no longer in these entries.
		const present = skillsIn(ctx.sessionManager.buildContextEntries());
		const matched = sessionRoutes(event.prompt, pi.getActiveTools?.() ?? [], process.env.PATH)
			.filter((name) => !present.has(name) && existsSync(skillPath(name)))
			.slice(0, MAX_ROUTED);
		const domain = domainRoutesFor(event.prompt)
			.filter((name) => !present.has(name) && !matched.includes(name))
			.slice(0, MAX_DOMAIN_ROUTED);
		const alreadyNamed = libraryNamedIn(ctx.sessionManager.buildContextEntries());
		const library = libraryRoutesFor(event.prompt)
			.filter((name) => !present.has(name) && !alreadyNamed.has(name) && existsSync(libraryPath(name)))
			.slice(0, MAX_LIBRARY_NAMED);
		const noAgents = saidNoAgents ? undefined : noAgentsNote(event.prompt, pi.getActiveTools?.() ?? []);
		if (noAgents) saidNoAgents = true;
		if (matched.length === 0 && domain.length === 0 && library.length === 0) {
			return noAgents ? { message: { customType: NO_AGENTS_TYPE, content: noAgents, display: true } } : undefined;
		}
		const inlined = [...matched.slice(0, MAX_INLINED), ...domain.slice(0, MAX_DOMAIN_INLINED)];
		const named = [...matched.slice(MAX_INLINED), ...domain.slice(MAX_DOMAIN_INLINED)];
		for (const name of inlined) read.add(name);
		const details: RoutingDetails = library.length ? { inlined, named, library } : { inlined, named };
		const content = routingMessage(inlined, named, library) + (noAgents ? `\n\n${noAgents}` : "");
		return {
			message: { customType: MESSAGE_TYPE, content, display: true, details },
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
