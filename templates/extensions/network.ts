/**
 * network: show and change what a session may reach - offline, trusted-remote or yolo.
 *
 *   offline         the ELM gateway and nothing else
 *   trusted-remote  the gateway, the package sources and the research hosts, through this install's
 *                   proxy; what a session starts in unless something says otherwise ("default" names it)
 *   yolo            every destination, no OS fence
 *
 * Why: asked for on 2026-11-16, to sit beside /mode. Until then the mode was a flag at launch
 * (pi --offline, --trusted-remote, --remote) or PI_ELM_NETWORK in a shell profile, with nowhere to
 * see which one a session was in, and no way to make one the usual.
 *
 * /network opens a menu of the three, marking the one this session is in and the one new sessions
 * start in; /network <mode> goes straight to the second menu. What that menu offers depends on the
 * direction, because the two directions are not alike:
 *
 *   tighter (trusted-remote -> offline, yolo -> either)
 *       "Change for this session" or "Change for this session and new ones". The proxy is told to
 *       keep only the tighter list (proxy/egress.py, POST .../narrow), the web tools are switched
 *       off for offline, and sub-agents started afterwards get the same.
 *   looser (offline -> trusted-remote, anything -> yolo)
 *       only "Make it the default for new sessions". A running session cannot be opened up: the OS
 *       fence around it cannot be taken off a process that is already inside, and the proxy accepts
 *       a narrower list from anyone but a wider one from nobody - a secret that would let this
 *       extension widen it is one the agent's own shell could read. The menu says how to start again
 *       in the wider mode, continuing the conversation.
 *
 * A session that left yolo this way has a tighter proxy and still no OS fence, and is told so.
 *
 * The default is agent/network-mode, read by the launcher below a flag and below PI_ELM_NETWORK.
 * Escape, at either menu, changes nothing.
 *
 * It also says, once, when the session is running without its fence because this machine could not
 * make one (the launcher's warning is above pi's screen by then), and keeps the mode in the footer.
 *
 * This extension enforces nothing itself: the proxy holds the list, the OS holds the fence, and the
 * launcher chose both. It reads PI_ELM_NETWORK, PI_ELM_NETWORK_DEFAULT, ELM_PI_UNFENCED, ELM_PI_NO_JAIL
 * and the proxy's address; never the ELM key.
 */
import { chmodSync, renameSync, writeFileSync } from "node:fs";
import { request } from "node:http";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const MODES = ["offline", "trusted-remote", "yolo"] as const;
export type Mode = (typeof MODES)[number];

/** How much each mode reaches: a change to a lower number is a tightening. */
export const REACH: Record<Mode, number> = { offline: 0, "trusted-remote": 1, yolo: 2 };

/** Where /network keeps this install's default, under the agent directory. */
export const DEFAULT_FILE = "network-mode";
export const NARROW_PATH = "/__elm_pi_egress__/narrow";
export const HEALTH_PATH = "/__elm_pi_egress__/health";

export const ABOUT: Record<Mode, string> = {
	offline: "the ELM gateway and nothing else: no web tools, no PyPI, no package registries",
	"trusted-remote": "the gateway, the package sources and the research hosts, through this install's proxy",
	yolo: "every destination, and no OS fence around the session",
};

/** One line per mode in the /network menu. */
export const SHORT: Record<Mode, string> = {
	offline: "the ELM gateway only",
	"trusted-remote": "the gateway, packages and research hosts",
	yolo: "every destination, no OS fence",
};

/** The flag that starts a session in `mode`. */
export const FLAG: Record<Mode, string> = { offline: "--offline", "trusted-remote": "--trusted-remote", yolo: "--remote" };

export function isMode(value: unknown): value is Mode {
	return typeof value === "string" && (MODES as readonly string[]).includes(value);
}

/** What was typed after /network, as a mode: "default" and "trusted" are trusted-remote. */
export function parseMode(typed: string): Mode | undefined {
	const word = typed.trim().toLowerCase();
	if (word === "default" || word === "trusted" || word === "remote-trusted") return "trusted-remote";
	return isMode(word) ? word : undefined;
}

/** The mode this session is in: what the launcher set, trusted-remote when unset. */
export function currentMode(env: NodeJS.ProcessEnv = process.env): Mode {
	return isMode(env.PI_ELM_NETWORK) ? env.PI_ELM_NETWORK : "trusted-remote";
}

/** The mode a new session starts in, as the launcher worked it out. */
export function defaultMode(env: NodeJS.ProcessEnv = process.env): Mode {
	return isMode(env.PI_ELM_NETWORK_DEFAULT) ? env.PI_ELM_NETWORK_DEFAULT : "trusted-remote";
}

/**
 * Whether the OS fences this session: "os" when it does; "unavailable" when this machine could not
 * make the fence and the launcher started without it; "off" when someone asked for that.
 */
export function fence(env: NodeJS.ProcessEnv = process.env): "os" | "unavailable" | "off" {
	if (env.ELM_PI_UNFENCED === "fallback") return "unavailable";
	if (currentMode(env) === "yolo" || env.ELM_PI_NO_JAIL || env.ELM_PI_NO_PROXY === "1") return "off";
	return "os";
}

export function statusText(env: NodeJS.ProcessEnv = process.env): string {
	const mode = currentMode(env);
	const state = fence(env);
	if (mode === "yolo") return "net: yolo";
	return state === "os" ? `net: ${mode}` : `net: ${mode} (no OS fence)`;
}

/** The /network menu's line for `mode`, marking the current one and the one new sessions start in. */
export function menuLabel(mode: Mode, current: Mode, fallback: Mode): string {
	const marks = [mode === current ? "now" : "", mode === fallback ? "new sessions" : ""].filter(Boolean);
	return `${mode} - ${SHORT[mode]}${marks.length ? ` (${marks.join(", ")})` : ""}`;
}

export const SESSION = "Change for this session";
export const SESSION_AND_DEFAULT = "Change for this session and new ones";
export const DEFAULT_ONLY = "Make it the default for new sessions";

/** The answers the second menu offers for a change from `current` to `wanted`. */
export function choicesFor(wanted: Mode, current: Mode): string[] {
	return REACH[wanted] < REACH[current] ? [SESSION, SESSION_AND_DEFAULT] : [DEFAULT_ONLY];
}

/** The gateway's host, from the same ELM_BASE_URL the launcher and the shim read. */
export function gatewayHost(env: NodeJS.ProcessEnv = process.env): string {
	const base = env.ELM_BASE_URL || "https://elm.edina.ac.uk/api/v1";
	try {
		return new URL(base.includes("://") ? base : `https://${base}`).hostname;
	} catch {
		return "";
	}
}

function listed(value: string | undefined): string[] {
	return (value ?? "")
		.split(",")
		.map((host) => host.trim())
		.filter((host) => host && host !== "*");
}

/**
 * The hosts the proxy keeps for `mode`, in the order the launcher lists them (python/elmpi/network.py,
 * Mode.hosts): a sub-agent started afterwards asks the proxy for exactly this list before it uses it.
 */
export function hostsFor(mode: Mode, env: NodeJS.ProcessEnv = process.env): string[] {
	const hosts = [gatewayHost(env)].filter(Boolean);
	if (mode === "offline") return hosts;
	for (const host of [...listed(env.ELM_PROXY_ALLOW), ...listed(env.ELM_PI_PROXY_ALLOW)]) {
		if (!hosts.includes(host)) hosts.push(host);
	}
	return hosts;
}

/** The port of this session's proxy, when HTTPS_PROXY names one on loopback. */
export function proxyPort(env: NodeJS.ProcessEnv = process.env): number | undefined {
	const match = /^https?:\/\/(?:127\.0\.0\.1|localhost|\[::1\]):(\d{1,5})\/?$/i.exec(env.HTTPS_PROXY ?? env.https_proxy ?? "");
	const port = match ? Number(match[1]) : 0;
	return port > 0 && port < 65536 ? port : undefined;
}

type Reply = { status: number; allow?: string[]; error?: string };

/** One request to the proxy's own routes: never through a proxy, never off this machine. */
export function ask(port: number, method: "GET" | "POST", path: string, timeoutMs = 3000): Promise<Reply> {
	return new Promise((resolve) => {
		const call = request({ host: "127.0.0.1", port, method, path, timeout: timeoutMs, agent: false }, (response) => {
			let body = "";
			response.setEncoding("utf8");
			response.on("data", (chunk) => {
				if (body.length < 131072) body += chunk;
			});
			response.on("end", () => {
				try {
					const document = JSON.parse(body);
					if (document?.proxy !== "elm-pi-egress") throw new Error("not this install's proxy");
					resolve({ status: response.statusCode ?? 0, allow: document.allow, error: document.error });
				} catch (error) {
					resolve({ status: 0, error: (error as Error).message });
				}
			});
		});
		call.on("timeout", () => call.destroy(new Error("the proxy did not answer")));
		call.on("error", (error) => resolve({ status: 0, error: error.message }));
		call.end();
	});
}

/** Tell the proxy to keep only `hosts`. Resolves to "" when it has, else to why not. */
export async function narrow(port: number, hosts: string[]): Promise<string> {
	if (hosts.length === 0) return "could not work out the ELM gateway's host from ELM_BASE_URL";
	const reply = await ask(port, "POST", `${NARROW_PATH}?allow=${hosts.map(encodeURIComponent).join(",")}`);
	if (reply.status === 200) return "";
	return reply.error || `the proxy answered ${reply.status}`;
}

/**
 * Make `mode` the default for new sessions: agent/network-mode, written whole and then renamed
 * into place, so a launcher never reads half of it.
 */
export function saveDefault(mode: Mode, agentDir: string | undefined = process.env.PI_CODING_AGENT_DIR): void {
	if (!agentDir) throw new Error("PI_CODING_AGENT_DIR is not set");
	const target = join(agentDir, DEFAULT_FILE);
	const temporary = `${target}.${process.pid}.tmp`;
	writeFileSync(temporary, `${mode}\n`, { mode: 0o600 });
	chmodSync(temporary, 0o600);
	renameSync(temporary, target);
}

/** What the session and everything it starts afterwards read: the mode, and what follows from it. */
export function applyToEnvironment(mode: Mode, env: NodeJS.ProcessEnv = process.env): void {
	env.PI_ELM_NETWORK = mode;
	// The run's own extra hosts stay for trusted-remote; "*" was yolo's, and offline has none.
	const extra = mode === "offline" ? [] : listed(env.ELM_PI_PROXY_ALLOW);
	if (extra.length > 0) env.ELM_PI_PROXY_ALLOW = extra.join(",");
	else delete env.ELM_PI_PROXY_ALLOW;
	if (mode === "offline") {
		delete env.PI_ELM_WEB;
		delete env.PI_ELM_REMOTE;
	}
}

/** The web tools' names, from the launcher's own list (config/elm-pi.json webTools). */
export function webTools(env: NodeJS.ProcessEnv = process.env): string[] {
	return listed(env.ELM_WEB_TOOLS);
}

export const UNFENCED_NOTE =
	"⚠ This session is NOT fenced by the OS: this machine could not make the fence, so the launcher started without " +
	"it (its warning, above, says why and what would fix it). The proxy still filters what well-behaved programs " +
	"reach. /network shows the mode.";

export default function (pi: ExtensionAPI) {
	/** The list this session narrowed its proxy to, kept so a restarted proxy can be told again. */
	let narrowedTo: string[] | undefined;
	const showStatus = (ctx: any) => ctx.ui?.setStatus?.("network", statusText());

	pi.on("session_start", async (_event, ctx: any) => {
		if (!ctx.hasUI) return;
		showStatus(ctx);
		if (fence() === "unavailable") ctx.ui.notify(UNFENCED_NOTE, "warning");
	});

	// The launcher's watchdog replaces a proxy that died with one holding the list the session
	// started with. Before each run, a session that narrowed its list asks, and narrows again.
	pi.on("before_agent_start", async () => {
		const port = proxyPort();
		if (!narrowedTo || !port) return;
		const now = await ask(port, "GET", HEALTH_PATH, 1500);
		if (now.status === 200 && JSON.stringify(now.allow) !== JSON.stringify(narrowedTo.map((h) => h.toLowerCase()))) {
			await narrow(port, narrowedTo);
		}
	});

	pi.registerCommand("network", {
		description: "Choose what this session may reach: offline, trusted-remote or yolo (a menu; or /network <mode>)",
		getArgumentCompletions: (prefix: string) => {
			const items = MODES.filter((mode) => mode.startsWith(prefix.trim().toLowerCase())).map((mode) => ({
				value: mode,
				label: mode,
				description: ABOUT[mode],
			}));
			return items.length > 0 ? items : null;
		},
		handler: async (args, ctx: any) => {
			const typed = String(args ?? "").trim();
			const mode = currentMode();
			const fallback = defaultMode();
			let wanted = typed ? parseMode(typed) : undefined;
			if (typed && !wanted) {
				ctx.ui.notify(`Unknown network mode "${typed}". Choose offline, trusted-remote (or "default") or yolo.`, "error");
				return;
			}
			if (!wanted) {
				const labels = MODES.map((option) => menuLabel(option, mode, fallback));
				const unfenced = fence() === "os" || mode === "yolo" ? "" : " (no OS fence)";
				const choice = await ctx.ui.select(`Network: ${mode}${unfenced} now, new sessions start in ${fallback}`, labels);
				wanted = MODES[labels.indexOf(choice)];
				if (!wanted) return;
			}

			if (wanted === mode && wanted === fallback) {
				ctx.ui.notify(`Already ${mode}, and new sessions start in it - ${ABOUT[mode]}.`, "info");
				return;
			}

			const tighter = REACH[wanted] < REACH[mode];
			let title: string;
			if (tighter) {
				const stillOpen = fence() === "os" ? "" : " The OS fence cannot be added to a running session, so it stays without one.";
				title = `Switch to ${wanted}: ${ABOUT[wanted]}.${stillOpen} New sessions start in ${fallback}.`;
			} else if (wanted === mode) {
				title = `This session is ${mode} already. New sessions start in ${fallback}.`;
			} else {
				title =
					`${wanted}: ${ABOUT[wanted]}. A running session cannot be opened up - its fence and its proxy's list ` +
					`were fixed when it started. To use it now, leave and run: pi ${FLAG[wanted]} -c (continues this conversation).`;
			}
			const choice = await ctx.ui.select(title, choicesFor(wanted, mode));
			if (choice !== SESSION && choice !== SESSION_AND_DEFAULT && choice !== DEFAULT_ONLY) return;

			if (choice !== DEFAULT_ONLY) {
				const port = proxyPort();
				if (!port) {
					ctx.ui.notify(
						`Not changed: this session has no proxy of this install's to narrow (ELM_PI_NO_PROXY=1?). ` +
							`Start it again with: pi ${FLAG[wanted]} -c`,
						"error",
					);
					return;
				}
				const hosts = hostsFor(wanted);
				const problem = await narrow(port, hosts);
				if (problem) {
					ctx.ui.notify(`Not changed: the proxy did not take the ${wanted} list - ${problem}.`, "error");
					return;
				}
				narrowedTo = hosts;
				applyToEnvironment(wanted);
				if (wanted === "offline") {
					const web = new Set(webTools());
					pi.setActiveTools(pi.getActiveTools().filter((name: string) => !web.has(name)));
				}
				showStatus(ctx);
			}

			let after = `New sessions start in ${fallback}.`;
			if (choice !== SESSION) {
				try {
					saveDefault(wanted);
					process.env.PI_ELM_NETWORK_DEFAULT = wanted;
					after = `${wanted} is now the default for new sessions.`;
				} catch (error) {
					ctx.ui.notify(
						`${choice === DEFAULT_ONLY ? "Not saved" : `Switched to ${wanted} for this session, but it was not saved`}` +
							` as the default: ${(error as Error).message}`,
						"error",
					);
					return;
				}
			}
			if (choice === DEFAULT_ONLY) {
				const now = wanted === mode ? "" : ` This session stays ${mode}; to use ${wanted} now: pi ${FLAG[wanted]} -c`;
				ctx.ui.notify(`Network: ${after}${now}`, wanted === "yolo" ? "warning" : "info");
				return;
			}
			const open = fence() === "os" ? "" : " This session still has no OS fence.";
			ctx.ui.notify(`Network: ${wanted} - ${ABOUT[wanted]}.${open}\n${after}`, "info");
		},
	});
}
