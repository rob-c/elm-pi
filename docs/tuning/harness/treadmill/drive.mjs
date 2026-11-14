// Drive one elm-pi session over RPC the way a new user at the keyboard would: send the prompts, say yes
// to each permission dialog (once, not for the session), take the recommended answer to a question, and
// wait for background agents to report before calling the session done.
//
//   node drive.mjs <pi> <cwd> <log.jsonl> '<flags json>' '<prompts json>' <maxSecs>
import { spawn } from "node:child_process";
import { appendFileSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const [pi, cwd, logPath, flagsJson, promptsJson, maxSecsArg] = process.argv.slice(2);
const flags = JSON.parse(flagsJson);
const prompts = JSON.parse(promptsJson);
const maxMs = Number(maxSecsArg || 3600) * 1000;
const log = (o) => appendFileSync(logPath, JSON.stringify({ t: new Date().toISOString().slice(11, 19), ...o }) + "\n");
writeFileSync(logPath, "");

const child = spawn(pi, [...flags, "--mode", "rpc"], { cwd, stdio: ["pipe", "pipe", "pipe"], env: process.env });
child.stderr.on("data", (d) => log({ stderr: String(d).slice(0, 400) }));
child.on("exit", (code, signal) => { log({ exit: code, signal }); process.exit(0); });
const send = (o) => child.stdin.write(JSON.stringify(o) + "\n");

const started = Date.now();
let buf = "";
let running = false;
let lastActivity = Date.now();
let next = 0;
let dialogs = 0;
let lastPrompt = "";
let finished = false;

const finish = (why) => {
	if (finished) return;
	finished = true;
	log({ finish: why, secs: Math.round((Date.now() - started) / 1000), dialogs });
	child.kill("SIGTERM");
	setTimeout(() => { child.kill("SIGKILL"); process.exit(0); }, 8000);
};

/** Background runs launched and not yet reported, from the session file. */
function pending() {
	let file;
	try {
		const dir = join(cwd, ".pi/sessions");
		file = readdirSync(dir).filter((f) => f.endsWith(".jsonl")).sort()[0]; // the driven session, not a later trial
		if (!file) return 0;
		file = join(dir, file);
	} catch { return 0; }
	const launched = new Set();
	let finishedNotices = 0;
	for (const line of readFileSync(file, "utf8").split("\n")) {
		if (!line) continue;
		let r; try { r = JSON.parse(line); } catch { continue; }
		const m = r.message;
		if (m?.role === "toolResult" && (m.toolName === "subagent" || m.toolName === "workflow")) {
			const text = (m.content ?? []).map((c) => c.text ?? "").join("\n");
			for (const x of text.matchAll(/\bAsync\b[^\n[]*\[([0-9a-f-]{8,})\]/gi)) launched.add(x[1]);
			for (const x of text.matchAll(/started in the background[^\n]*?([0-9a-z-]{8,})/gi)) launched.add(x[1]);
		}
		if (r.type === "custom_message" && /notify|complete/i.test(r.customType ?? "")) {
			const text = typeof r.content === "string" ? r.content : JSON.stringify(r.content ?? "");
			// one final notice per launch (a parallel run's children each send a "Workflow child completed" first)
			if (r.customType === "subagent-notify" && /Background task (?:completed|failed)/i.test(text)) finishedNotices++;
		}
	}
	return Math.max(0, launched.size - finishedNotices);
}

child.stdout.on("data", (d) => {
	buf += d;
	let i;
	while ((i = buf.indexOf("\n")) >= 0) {
		const line = buf.slice(0, i);
		buf = buf.slice(i + 1);
		let ev; try { ev = JSON.parse(line); } catch { continue; }
		lastActivity = Date.now();
		if (ev.type === "extension_ui_request") {
			if (ev.method === "select") {
				dialogs++;
				const options = ev.options ?? [];
				// The test runs on the user's own Mac: what changes software shared with the rest of it is
				// declined, as a careful user would (auto08b's approved `brew install imagemagick`).
				const shared = /\b(brew|sudo|softwareupdate|port)\b|--user(?![-\w])|break-system|--system\b|npm (i|install) -g|\bgem install\b/i
					.test(`${ev.title ?? ""} ${ev.message ?? ""}`);
				const pick =
					(shared ? options.find((o) => /^(deny|no|block|reject|cancel)\b/i.test(o)) : undefined) ??
					options.find((o) => /recommended/i.test(o)) ??
					options.find((o) => /^(allow|yes|approve)\b/i.test(o) && !/session|always|forever|all /i.test(o)) ??
					options.find((o) => /allow|yes|approve|continue|proceed/i.test(o) && !/session|always|forever/i.test(o)) ??
					// anything else (a settings prompt, an unknown question): the choice that changes nothing
					options.find((o) => /^(cancel|skip|not now|later|no)\b/i.test(o)) ??
					options[0];
				log({ dialog: "select", title: String(ev.title ?? "").slice(0, 400), options, answered: pick, shared });
				send({ type: "extension_ui_response", id: ev.id, value: pick });
			} else if (ev.method === "confirm") {
				dialogs++;
				log({ dialog: "confirm", title: String(ev.title ?? "").slice(0, 300), message: String(ev.message ?? "").slice(0, 300) });
				send({ type: "extension_ui_response", id: ev.id, confirmed: true });
			} else if (ev.method === "input" || ev.method === "editor") {
				dialogs++;
				log({ dialog: ev.method, title: String(ev.title ?? "").slice(0, 300) });
				send({ type: "extension_ui_response", id: ev.id, value: "Go ahead with what you think is best." });
			} else if (ev.method === "notify") log({ notify: String(ev.message ?? "").slice(0, 300) });
			continue;
		}
		if (ev.type === "agent_start") { running = true; log({ agent_start: true }); }
		else if (ev.type === "agent_end") { running = false; log({ agent_end: true }); }
		else if (ev.type === "tool_execution_start") log({ tool: ev.toolName, args: JSON.stringify(ev.args ?? {}).slice(0, 240) });
		else if (ev.type === "tool_execution_end") log({ toolEnd: ev.toolName, isError: ev.isError, result: JSON.stringify(ev.result?.content ?? ev.result ?? {}).slice(0, 300) });
		else if (ev.type === "response" && ev.success === false) {
			log({ error: JSON.stringify(ev).slice(0, 400) });
			// pi is mid-run (a rate-limit retry counts): the terminal UI would queue what was typed, so queue it.
			if (/already processing/.test(String(ev.error)) && lastPrompt) {
				log({ requeued: lastPrompt.slice(0, 80) });
				send({ id: `q${next}`, type: "prompt", message: lastPrompt, streamingBehavior: "followUp" });
				running = true;
			}
		}
		else if (ev.type === "auto_retry_start" || ev.type === "auto_retry_end") log({ retry: ev.type, attempt: ev.attempt, error: String(ev.errorMessage ?? "").slice(0, 200) });
	}
});

const sendNext = () => {
	if (next >= prompts.length) return false;
	const message = prompts[next++];
	lastPrompt = message;
	log({ prompt: message.slice(0, 300) });
	send({ id: `p${next}`, type: "prompt", message });
	lastActivity = Date.now();
	return true;
};

setTimeout(() => sendNext(), 5000);
setInterval(() => {
	const now = Date.now();
	if (now - started > maxMs) return finish("time limit");
	if (running) return;
	const quiet = now - lastActivity;
	if (quiet < 20000) return;
	const waiting = pending();
	// A slash command answers without an agent turn: move on once it has gone quiet.
	if (next < prompts.length && waiting === 0) { sendNext(); return; }
	if (waiting > 0) {
		if (quiet > 30 * 60000) finish(`no activity for 30 minutes with ${waiting} background run(s) unreported`);
		return;
	}
	if (quiet > 90000) finish("done");
}, 5000);
