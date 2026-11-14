/**
 * Cache log: what pi sends the gateway, request by request, measured against the request before.
 *
 * A harness tool, not part of an install. batch.sh copies it into a *test* install's agent/extensions/
 * (as zz-cache-log.ts, so that it loads last and sees the payload after every other extension has had
 * its say) when TREADMILL_EXTENSION names it.
 *
 * ELM reuses a prompt's prefix (cache_probe.py times it) and reports nothing about it: cacheRead and
 * cacheWrite were 0 in all 319 session files of 2026-11-14. So whether a pi session *can* be served from
 * that cache is a property of the bytes pi sends: each request must begin with the whole of the one
 * before. This writes, for every request, how many leading bytes it shares with the previous one and
 * where the first difference is, with the time to the response's headers and to its first stream event.
 *
 * It writes sizes, positions and times to <cwd>/.pi/cache-log.jsonl - never prompt text, headers or keys.
 */
import { appendFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

/** Bytes two strings share from the start. */
export function sharedPrefix(a: string, b: string): number {
	const n = Math.min(a.length, b.length);
	let i = 0;
	while (i < n && a.charCodeAt(i) === b.charCodeAt(i)) i++;
	return i;
}

type Payload = { messages?: unknown[]; tools?: unknown; [key: string]: unknown };

/** Which part of the request first differs from the previous one: "tools", "messages[3] (tool)", "temperature". */
export function firstDifference(prev: Payload, next: Payload): string | undefined {
	const text = (v: unknown) => JSON.stringify(v) ?? "";
	const a = prev.messages ?? [];
	const b = next.messages ?? [];
	for (let i = 0; i < a.length; i++) {
		if (i >= b.length) return `messages[${i}] removed (of ${a.length})`;
		if (text(a[i]) !== text(b[i])) return `messages[${i}] (${(b[i] as { role?: string })?.role ?? "?"}) of ${a.length}`;
	}
	if (text(prev.tools) !== text(next.tools)) return "tools";
	for (const key of new Set([...Object.keys(prev), ...Object.keys(next)]))
		if (key !== "messages" && key !== "tools" && text(prev[key]) !== text(next[key])) return key;
	return undefined;
}

export default function (pi: ExtensionAPI) {
	const last = new Map<string, { body: string; payload: Payload }>();
	let n = 0;
	let open: Record<string, unknown> | undefined;
	let sentAt = 0;
	let file: string | undefined;
	const flush = () => {
		if (!open || !file) return;
		try {
			appendFileSync(file, JSON.stringify(open) + "\n");
		} catch {
			// a log that cannot be written must not stop the session it is watching
		}
		open = undefined;
	};
	pi.on("before_provider_request", (event, ctx) => {
		flush();
		const payload = event.payload as Payload;
		const body = JSON.stringify(payload) ?? "";
		const model = String((payload as { model?: unknown }).model ?? ctx.model?.id ?? "?");
		if (!file) {
			const dir = join(ctx.cwd, ".pi");
			try {
				mkdirSync(dir, { recursive: true });
			} catch {
				// appendFileSync will say so
			}
			file = join(dir, "cache-log.jsonl");
		}
		const prev = last.get(model);
		const shared = prev ? sharedPrefix(prev.body, body) : 0;
		// The request's own fields (model, sampling) come before or after messages in the body depending on
		// the provider; what matters to a prefix cache is the prompt, so the messages are measured as well.
		const prevMessages = prev ? JSON.stringify(prev.payload.messages ?? []).slice(0, -1) : "";
		const messages = JSON.stringify(payload.messages ?? []);
		open = {
			event: "request",
			n: ++n,
			pid: process.pid,
			child: process.env.PI_SUBAGENT_CHILD === "1",
			model,
			at: new Date().toISOString(),
			bytes: body.length,
			messages: payload.messages?.length ?? 0,
			previous_bytes: prev ? prevMessages.length : 0,
			shared_prefix_bytes: prev ? sharedPrefix(prevMessages, messages) : 0,
			whole_body_shared_bytes: shared,
			tools_same: prev ? JSON.stringify(prev.payload.tools) === JSON.stringify(payload.tools) : undefined,
			first_difference: prev && sharedPrefix(prevMessages, messages) < prevMessages.length ? firstDifference(prev.payload, payload) : undefined,
			headers_ms: null,
			first_event_ms: null,
		};
		last.set(model, { body, payload: JSON.parse(body) as Payload });
		sentAt = Date.now();
		return undefined;
	});
	pi.on("after_provider_response", (event) => {
		if (!open || open.headers_ms !== null) return;
		open.headers_ms = Date.now() - sentAt;
		open.status = (event as { status?: number }).status;
	});
	pi.on("provider_stream_event", () => {
		if (!open || open.first_event_ms !== null) return;
		open.first_event_ms = Date.now() - sentAt;
		flush();
	});
	pi.on("turn_end", flush);
	pi.on("session_shutdown", flush);
}
