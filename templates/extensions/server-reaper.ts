/**
 * Server reaper: a web server a session starts in the background stops when the session ends.
 *
 * test4, test5 and test7 (2026-11-12) each left a `python3 -m http.server` running after the
 * work was done: started with `&` to look at a page, never stopped, still serving the folder
 * hours later. test7's parent never even used its server - `view` draws the .html file itself.
 * command-guard already makes such a server bind 127.0.0.1; this makes it go away.
 *
 * A bash command that starts a known web or dev server in the background is watched. A TCP
 * port that is listening after it, was not before, and belongs to a server process started
 * during the call is that command's server: it is recorded with its process group (pi runs
 * each bash command in a group of its own, and a background job stays in it). The command's
 * result then tells the model the server stops when the session does, and that `view` needs
 * none. When the session ends - quit, `pi -p` finishing, a new or resumed session, a sub-agent
 * finishing - each recorded server still running the same command is stopped (SIGTERM to its
 * group, or to it alone when the group is pi's own), and a line on stderr says so.
 *
 * Only servers. A server started in the foreground ends with its command, and any other
 * background job is left alone: a long computation the user asked for must not die with the
 * session.
 */
import { execFileSync } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Commands that serve HTTP until stopped. */
export const SERVER =
	/(?:\bpython[0-9.]*["']?\s+-m\s+(?:http\.server|SimpleHTTPServer)\b|\bhttp-server\b|\blive-server\b|\bnpx\s+(?:-y\s+)?serve\b|\bserve\s+-[sl]\b|\bphp\s+-S\b|\bruby\s+-run\s+-e\s+httpd\b|\bbusybox\s+httpd\b|\bvite\b|\bnext\s+(?:dev|start)\b|\bnpm\s+run\s+(?:dev|serve|preview|start)\b|\bflask\s+run\b|\buvicorn\b|\bgunicorn\b|\bmanage\.py\s+runserver\b|\bjupyter[- ](?:lab|notebook)\b)/i;
/** A job put in the background: `&` (not `&&`, `>&` or `&>`), nohup, setsid or disown. */
export const BACKGROUND = /(?:^|[^&>|])&(?![&>])|\bnohup\b|\bsetsid\b|\bdisown\b/;
/** How long after its command a server has to start listening. */
const BIND_WAIT_MS = 3000;
const POLL_MS = 250;

export function startsServer(command: string): boolean {
	return SERVER.test(command) && BACKGROUND.test(command);
}

export interface Listener {
	pid: number;
	addr: string;
}

/** `lsof -nP -iTCP -sTCP:LISTEN -Fpn`: a `p<pid>` line, then an `n<address>` line per socket. */
export function parseLsof(out: string): Listener[] {
	const found: Listener[] = [];
	let pid = 0;
	for (const line of out.split("\n")) {
		if (line.startsWith("p")) pid = Number(line.slice(1));
		else if (line.startsWith("n") && pid) found.push({ pid, addr: line.slice(1) });
	}
	return found;
}

/** `ss -ltnpH`: `LISTEN 0 5 127.0.0.1:8080 0.0.0.0:* users:(("python3",pid=1234,fd=3))`. */
export function parseSs(out: string): Listener[] {
	const found: Listener[] = [];
	for (const line of out.split("\n")) {
		const addr = line.trim().split(/\s+/)[3];
		if (addr) for (const m of line.matchAll(/pid=(\d+)/g)) found.push({ pid: Number(m[1]), addr });
	}
	return found;
}

/** `ps -o etime=`: [[dd-]hh:]mm:ss, in seconds. */
export function parseEtime(etime: string): number | undefined {
	const m = /^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$/.exec(etime.trim());
	if (!m) return undefined;
	return Number(m[1] ?? 0) * 86400 + Number(m[2] ?? 0) * 3600 + Number(m[3]) * 60 + Number(m[4]);
}

function run(command: string, args: string[]): string | undefined {
	try {
		return execFileSync(command, args, { encoding: "utf8", timeout: 3000, stdio: ["ignore", "pipe", "ignore"] });
	} catch (error) {
		// lsof exits 1 when nothing matches, with its output still on stdout
		const out = (error as { stdout?: unknown }).stdout;
		return typeof out === "string" && out ? out : undefined;
	}
}

function listeners(): Listener[] {
	const lsof = run("lsof", ["-nP", "-iTCP", "-sTCP:LISTEN", "-Fpn"]);
	if (lsof !== undefined) return parseLsof(lsof);
	const ss = run("ss", ["-ltnpH"]);
	return ss === undefined ? [] : parseSs(ss);
}

function ps(pid: number, field: "pgid" | "command" | "etime"): string | undefined {
	return run("ps", ["-o", `${field}=`, "-p", String(pid)])?.trim() || undefined;
}

interface Server {
	pid: number;
	pgid?: number;
	command: string;
	addrs: string[];
}

export default function (pi: ExtensionAPI) {
	const before = new Map<string, { keys: Set<string>; at: number }>();
	const servers: Server[] = [];
	const key = (l: Listener) => `${l.pid} ${l.addr}`;

	pi.on("tool_call", async (event) => {
		if (event.toolName !== "bash") return undefined;
		const command = String((event.input as { command?: unknown } | undefined)?.command ?? "");
		if (startsServer(command)) before.set(event.toolCallId, { keys: new Set(listeners().map(key)), at: Date.now() });
		return undefined;
	});

	pi.on("tool_result", async (event) => {
		const was = before.get(event.toolCallId);
		if (!was) return undefined;
		before.delete(event.toolCallId);
		const added: Server[] = [];
		for (let waited = 0; added.length === 0 && waited <= BIND_WAIT_MS; waited += POLL_MS) {
			for (const l of listeners()) {
				if (was.keys.has(key(l)) || l.pid === process.pid) continue;
				const command = ps(l.pid, "command");
				const age = parseEtime(ps(l.pid, "etime") ?? "");
				// A server, and one started during this call - not another session's.
				if (!command || !SERVER.test(command) || age === undefined || age * 1000 > Date.now() - was.at + 2000) continue;
				const known = [...servers, ...added].find((s) => s.pid === l.pid);
				if (known) {
					if (!known.addrs.includes(l.addr)) known.addrs.push(l.addr);
					continue;
				}
				const pgid = Number(ps(l.pid, "pgid"));
				added.push({ pid: l.pid, pgid: Number.isFinite(pgid) && pgid > 0 ? pgid : undefined, command, addrs: [l.addr] });
			}
			if (added.length === 0) await new Promise((r) => setTimeout(r, POLL_MS));
		}
		if (added.length === 0) return undefined;
		servers.push(...added);
		const which = added.map((s) => `PID ${s.pid} on ${s.addrs.join(", ")}`).join("; ");
		const note =
			`elm-pi stops this server (${which}) when the session ends. To look at a page yourself, \`view\` its ` +
			".html file - no server is needed. Stop it sooner with `kill <PID>` once nobody needs it.";
		return { content: [...event.content, { type: "text", text: note }] };
	});

	pi.on("session_shutdown", async (event) => {
		if (event.reason === "reload") return; // the same session carries on
		const own = Number(ps(process.pid, "pgid"));
		for (const server of servers.splice(0)) {
			if (ps(server.pid, "command") !== server.command) continue; // gone, or the PID is someone else's now
			try {
				if (server.pgid && server.pgid !== own) process.kill(-server.pgid, "SIGTERM");
				else process.kill(server.pid, "SIGTERM");
				process.stderr.write(`elm-pi: stopped the server this session started: ${server.command} (PID ${server.pid}, ${server.addrs.join(", ")})\n`);
			} catch {
				// already gone
			}
		}
	});
}
