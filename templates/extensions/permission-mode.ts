/**
 * permission-mode: show and change how much the agent may do without asking.
 *
 *   manual  nothing runs without your yes: commands, edits, Python, notebooks,
 *           sub-agents and every other tool ask first. Reading files in the
 *           project, and the tools that only talk to you or keep the session's
 *           own notes (config/elm-pi.json permissionModes.manualNoPrompt), do not
 *   auto    the permission gate's rules as written: most commands and edits in
 *           the project run, the ones its rules mark ask (git push, brew
 *           install, pi update, ...) ask first
 *   yolo    every ask is answered yes, for the rest of this session only; a
 *           deny is still a deny
 *
 * A new session starts in this install's default: manual, unless /mode has
 * made auto the default (agent/permission-mode). The default is manual or
 * auto, never yolo. A flag picks the mode for one run (pi --manual/--auto/
 * --yolo) without changing it.
 *
 * /mode opens a menu of the three modes, marking the one this session is in
 * and the one new sessions start in. Picking manual or auto offers "Change for
 * this session", or "Change default mode", which switches this session and
 * makes new ones start that way too; picking yolo offers only "Change for this
 * session only": it lasts until this session ends, is never saved, and the
 * next session - a resumed one included - starts in the default again.
 * /mode manual, /mode auto and /mode yolo go straight to that second menu.
 * Escape, at either menu, changes nothing.
 *
 * Sub-agents you allowed. In manual, a sub-agent launch asks like any other call,
 * and each of its agents' calls used to ask too, forwarded to you one by one - a
 * five-page website was a prompt for every page each child wrote. With
 * permissionModes.approvedAgents "auto" (PI_ELM_APPROVED_AGENTS), allowing the
 * launch - the ask says so, through patch-pi.py --gate - is the permission for
 * its agents to work in auto: this extension, loaded in the process pi-subagents
 * starts for that run, switches PI_ELM_PERMISSION_MODE there to auto before any
 * of them makes a call. That process exists only because you allowed the launch.
 * It is told apart by what pi-subagents sets in it - PI_SUBAGENT_CHILD=1, and
 * PI_SUBAGENT_RUNNER_PID equal to its own pid, which a program its agents start
 * does not share - so a `pi` started from an agent's shell is not switched. What
 * auto asks about (git push, installs, ...) is forwarded to you as before; your
 * session stays manual. Workflow agents are not covered: they run in your
 * session's process, and in manual what would ask is refused there.
 *
 * The mode is PI_ELM_PERMISSION_MODE, which the launcher sets. This extension
 * enforces nothing: pi-permission-system, patched by patch-pi.py --gate, reads
 * that variable on every decision, so a change takes effect at the next tool
 * call. A sub-agent started after a change runs in the new mode (a yolo
 * session's runs as auto and sends its asks here, where they are answered
 * yes); one already running keeps the mode it started with.
 */
import { chmodSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { isAbsolute, join, resolve } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const MODES = ["manual", "auto", "yolo"] as const;
export type Mode = (typeof MODES)[number];
/** What a default may be: yolo is never one. */
export type DefaultMode = Exclude<Mode, "yolo">;

/** Where /mode keeps this install's default, under the agent directory. */
export const DEFAULT_FILE = "permission-mode";

export const ABOUT: Record<Mode, string> = {
	manual: "nothing runs without your yes - commands, edits, Python, sub-agents; reading files in the project does not ask",
	auto: "the permission gate's rules - most commands and edits in the project run, the risky ones ask first",
	yolo: "every ask is answered yes until this session ends; a deny is still a deny",
};

/** One line per mode in the /mode menu. */
export const SHORT: Record<Mode, string> = {
	manual: "asks before every command and edit",
	auto: "the risky commands ask, the rest run",
	yolo: "answers every ask yes, this session only",
};

/** The /mode menu's line for `mode`, marking the current one and the default. */
export function menuLabel(mode: Mode, current: Mode, fallback: DefaultMode): string {
	const marks = [mode === current ? "now" : "", mode === fallback ? "default" : ""].filter(Boolean);
	return `${mode} - ${SHORT[mode]}${marks.length ? ` (${marks.join(", ")})` : ""}`;
}

export function isMode(value: unknown): value is Mode {
	return typeof value === "string" && (MODES as readonly string[]).includes(value);
}

export function isDefaultMode(value: unknown): value is DefaultMode {
	return value === "manual" || value === "auto";
}

/**
 * The mode the agents of an allowed launch run in, in the process pi-subagents started for the
 * run: auto when the session is manual and approvedAgents is auto; otherwise undefined (no change).
 */
export function approvedRunMode(env: NodeJS.ProcessEnv = process.env, pid: number = process.pid): Mode | undefined {
	const runner = env.PI_SUBAGENT_CHILD === "1" && env.PI_SUBAGENT_RUNNER_PID === String(pid);
	return runner && env.PI_ELM_PERMISSION_MODE === "manual" && env.PI_ELM_APPROVED_AGENTS === "auto" ? "auto" : undefined;
}

/**
 * Words in a workflow script that ask its agents to change something: files, or anything a
 * command does. Negated uses ("do not modify any file") are taken out first.
 */
export const WRITE_INTENT =
	/\b(?:write|writes|create|creates|save|saves|download|downloads|edit|edits|modify|fix|fixes|implement|build|generate|mkdir|install|update|delete|remove|rename|refactor|apply)\b/i;
const NEGATED =
	/\b(?:do not|don't|never|must not|should not|without)\s+(?:\w+\s+){0,2}?(?:write|create|save|download|edit|modify|fix|implement|build|generate|install|update|delete|remove|rename|refactor|apply)\w*/gi;

/**
 * Why a `workflow` call should not start, or undefined. In manual, a workflow agent can only read:
 * it runs in this session's process, so the gate asks about its writes and commands as about
 * yours, and with no screen of its own the answer is no. test13 (2026-11-13), /ultracode on in a
 * manual session: nine agents, thirteen minutes and 629k tokens, each reporting "BLOCKED", no
 * file written. So a script that asks its agents to write or run something is refused before it
 * starts, and says what works instead. A script of agents that only read and report still runs; a
 * saved or built-in workflow (`name`) is not read here.
 */
/**
 * A `workflow` call's script: its text, or the file it names (`script: ".pi/tmp/x.mjs"`, which
 * workflow-script.ts reads in - before or after this extension, as pi happens to load them).
 */
export function scriptText(input: Record<string, unknown>, cwd: string): string {
	const script = input.script;
	if (typeof script !== "string") return "";
	const named = script.trim().replace(/^["'`]+|["'`]+$/g, "");
	if (named.length > 1024 || /[\n;(){}=`]/.test(named) || !/\.m?js$/i.test(named)) return script;
	try {
		return readFileSync(isAbsolute(named) ? named : resolve(cwd, named), "utf8");
	} catch {
		return script;
	}
}

export function workflowRefusal(
	mode: Mode,
	input: Record<string, unknown>,
	env: NodeJS.ProcessEnv = process.env,
	cwd: string = process.cwd(),
): string | undefined {
	const script = scriptText(input, cwd);
	if (mode !== "manual" || !script) return undefined;
	if (!WRITE_INTENT.test(script.replace(NEGATED, " "))) return undefined;
	const children =
		env.PI_ELM_APPROVED_AGENTS === "auto"
			? "allowing its launch lets its agents work in auto"
			: "its agents' writes and commands come to the user to allow";
	return (
		"Not started: this session is in manual mode, and there a workflow agent can only read - a write or a command it " +
		"makes needs the user's yes, and with nobody to ask it is refused (a run of nine agents here wrote nothing in " +
		`thirteen minutes). For work that writes files or runs commands, fan out with \`subagent\` instead: ${children}. ` +
		"A workflow whose agents only read and report runs here. Or ask the user to switch with `/mode auto`."
	);
}

/** The mode this process runs in: what the launcher set, manual when unset. */
export function currentMode(env: NodeJS.ProcessEnv = process.env): Mode {
	const mode = env.PI_ELM_PERMISSION_MODE;
	return isMode(mode) ? mode : "manual";
}

/** The mode a new session starts in, as the launcher worked it out. */
export function defaultMode(env: NodeJS.ProcessEnv = process.env): DefaultMode {
	const mode = env.PI_ELM_PERMISSION_DEFAULT;
	return isDefaultMode(mode) ? mode : "manual";
}

/**
 * Make `mode` the default for new sessions: agent/permission-mode, written
 * whole and then renamed into place, so a launcher never reads half of it.
 */
export function saveDefault(mode: DefaultMode, agentDir: string | undefined = process.env.PI_CODING_AGENT_DIR): void {
	if (!agentDir) throw new Error("PI_CODING_AGENT_DIR is not set");
	const target = join(agentDir, DEFAULT_FILE);
	const temporary = `${target}.${process.pid}.tmp`;
	writeFileSync(temporary, `${mode}\n`, { mode: 0o600 });
	chmodSync(temporary, 0o600);
	renameSync(temporary, target);
}

/**
 * Whether the installed gate reads the mode at all. Without patch-pi.py
 * --gate's edits it answers as auto whatever /mode says, so a switch is
 * refused rather than reported as done.
 */
export function gateApplies(agentDir: string | undefined = process.env.PI_CODING_AGENT_DIR): boolean {
	if (!agentDir) return false;
	const src = join(agentDir, "npm/node_modules/@gotgenes/pi-permission-system/src");
	try {
		return (
			readFileSync(join(src, "policy/permission-manager.ts"), "utf8").includes('PI_ELM_PERMISSION_MODE === "manual"') &&
			readFileSync(join(src, "index.ts"), "utf8").includes('PI_ELM_PERMISSION_MODE === "yolo"')
		);
	} catch {
		return false;
	}
}

/**
 * What a manual session is told about asking. auto02 (2026-11-13, manual) put 31 dialogs to the user in
 * 16 minutes; seven were `ls -la`, `grep` and `cat` through bash, which the read, grep, find and ls tools
 * would have done without asking.
 */
export const MANUAL_NOTE =
	"This session is in manual mode: each bash command, write and edit waits for the user to allow it. `read`, " +
	"`grep`, `find`, `ls` and `view` never ask - look with them, not with bash `ls`, `grep`, `cat` or `head`, so " +
	"the user is asked only about what changes something.";

export function statusText(mode: Mode): string {
	return mode === "yolo" ? "mode: yolo (this session)" : `mode: ${mode}`;
}

/** The answers /mode offers: manual and auto can become the default, yolo never. */
export const SESSION = "Change for this session";
export const DEFAULT = "Change default mode";
export const YOLO_SESSION = "Change for this session only";

export function choicesFor(mode: Mode): string[] {
	return mode === "yolo" ? [YOLO_SESSION] : [SESSION, DEFAULT];
}

export default function (pi: ExtensionAPI) {
	// Before any agent of an allowed launch makes a call: the gate reads this on every decision.
	const approved = approvedRunMode();
	if (approved) process.env.PI_ELM_PERMISSION_MODE = approved;
	const showStatus = (ctx: any) => ctx.ui?.setStatus?.("permission-mode", statusText(currentMode()));

	pi.on("tool_call", async (event, ctx) => {
		if (event.toolName !== "workflow") return undefined;
		const reason = workflowRefusal(currentMode(), (event.input ?? {}) as Record<string, unknown>, process.env, ctx.cwd);
		return reason ? { block: true, reason } : undefined;
	});

	pi.on("session_start", async (_event, ctx: any) => {
		if (ctx.hasUI) showStatus(ctx);
	});

	pi.on("before_agent_start", (event) => {
		const sections = event.systemPromptOptions.sections;
		if (currentMode() === "manual") sections.permission_mode = MANUAL_NOTE;
		else delete sections.permission_mode;
	});

	pi.registerCommand("mode", {
		description: "Choose the permission mode: manual, auto or yolo (a menu; or /mode <mode>)",
		getArgumentCompletions: (prefix: string) => {
			const items = MODES.filter((mode) => mode.startsWith(prefix.trim().toLowerCase())).map((mode) => ({
				value: mode,
				label: mode,
				description: ABOUT[mode],
			}));
			return items.length > 0 ? items : null;
		},
		handler: async (args, ctx: any) => {
			const typed = String(args ?? "").trim().toLowerCase();
			const mode = currentMode();
			const fallback = defaultMode();
			if (typed && !isMode(typed)) {
				ctx.ui.notify(`Unknown mode "${typed}". Choose manual, auto or yolo.`, "error");
				return;
			}
			if (!gateApplies()) {
				ctx.ui.notify(
					`Permission mode: ${mode}. This install's permission gate does not apply the modes (an install ` +
						"made with --no-patch or --no-packages, or one that needs `pi update --extensions`), so it " +
						"stays as it is.",
					"error",
				);
				return;
			}
			let wanted: Mode;
			if (isMode(typed)) {
				wanted = typed;
			} else {
				const labels = MODES.map((option) => menuLabel(option, mode, fallback));
				const choice = await ctx.ui.select(`Permission mode: ${mode} now, new sessions start in ${fallback}`, labels);
				const picked: Mode | undefined = MODES[labels.indexOf(choice)];
				if (!picked) return;
				wanted = picked;
			}

			if (wanted === "yolo") {
				if (mode === "yolo") {
					ctx.ui.notify("Already in yolo mode until this session ends.", "info");
					return;
				}
				const choice = await ctx.ui.select(
					"Switch to yolo: every ask is answered yes - here and in the sub-agents this session starts - " +
						`until this session ends. Denies still apply, and the next session starts in ${fallback}.`,
					choicesFor("yolo"),
				);
				if (choice !== YOLO_SESSION) return;
				process.env.PI_ELM_PERMISSION_MODE = "yolo";
				showStatus(ctx);
				ctx.ui.notify(`Permission mode: yolo until this session ends - ${ABOUT.yolo}.`, "warning");
				return;
			}

			// manual or auto: for this session, or as the default too.
			if (wanted === mode && wanted === fallback) {
				ctx.ui.notify(`Already in ${mode} mode, and new sessions start in it - ${ABOUT[mode]}.`, "info");
				return;
			}
			const choice = await ctx.ui.select(
				`Switch to ${wanted}: ${ABOUT[wanted]}. New sessions start in ${fallback}.`,
				choicesFor(wanted),
			);
			if (choice !== SESSION && choice !== DEFAULT) return;
			const remember = choice === DEFAULT;
			process.env.PI_ELM_PERMISSION_MODE = wanted;
			showStatus(ctx);
			if (remember) {
				try {
					saveDefault(wanted);
					process.env.PI_ELM_PERMISSION_DEFAULT = wanted;
				} catch (error) {
					ctx.ui.notify(
						`Switched to ${wanted} for this session, but could not make it the default: ${(error as Error).message}`,
						"error",
					);
					return;
				}
			}
			const after = remember ? `${wanted} is now the default for new sessions.` : `New sessions start in ${defaultMode()}.`;
			ctx.ui.notify(`Permission mode: ${wanted} - ${ABOUT[wanted]}.\n${after}`, "info");
		},
	});
}
