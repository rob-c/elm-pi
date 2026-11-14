/**
 * elm-shim: makes ELM's Llama 3.3 usable as a tool-calling sub-agent model.
 *
 * ELM's vLLM instance for Llama 3.3 was started without --enable-auto-tool-choice
 * / --tool-call-parser, so any request carrying `tools` returns HTTP 400. This
 * extension starts a local translating proxy (see shim/shim.py in this install)
 * and registers it as the `elm-shim` provider, so Qwen can delegate cheap work to
 * Llama sub-agents via `subagent({ model: "elm-shim/..." })`.
 *
 * The proxy is shared: if one is already listening the extension reuses it, so a
 * fleet of sub-agent child processes does not start dozens of copies. That makes
 * it outlive the session that started it, which is why shim.py resolves the
 * egress proxy per request instead of trusting the address in its environment -
 * that address belongs to one session and dies with it. A shim too old to do
 * that is identified by the absence of the health endpoint and replaced.
 */
import { execFileSync, spawn } from "node:child_process";
import { connect } from "node:net";
import { existsSync } from "node:fs";
import { join } from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const PORT = Number(process.env.ELM_SHIM_PORT ?? 8811);
const HOST = "127.0.0.1";
// The launcher exports ELM_SHIM_PATH; fall back to the shim shipped beside the agent dir.
const SHIM =
  process.env.ELM_SHIM_PATH ??
  join(process.env.PI_CODING_AGENT_DIR ?? ".", "..", "shim", "shim.py");
const MODEL = process.env.ELM_LLAMA_MODEL_ID ?? "@LLAMA_MODEL@";

const listening = (port: number) =>
  new Promise<boolean>((resolve) => {
    const s = connect({ host: HOST, port })
      .on("connect", () => { s.destroy(); resolve(true); })
      .on("error", () => resolve(false));
    setTimeout(() => { s.destroy(); resolve(false); }, 600);
  });

const HEALTH = "/__elm_shim__/health";

/** The shim's own answer, or null for "not our shim". */
async function health(): Promise<Record<string, unknown> | null> {
  try {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 900);
    const res = await fetch(`http://${HOST}:${PORT}${HEALTH}`, { signal: ctl.signal });
    clearTimeout(timer);
    if (!res.ok) return null;
    const body = (await res.json()) as Record<string, unknown>;
    return body?.shim === "elm-pi" ? body : null;
  } catch {
    return null;
  }
}

/**
 * Stop a shim of ours that predates the health endpoint.
 *
 * Such a shim holds the egress proxy address of whichever session started it,
 * and that proxy dies with its session - so it answers every request with
 * "Connection refused" and pi-subagents benches the model. It cannot be asked
 * to re-resolve, so it is replaced. Only processes running this install's own
 * shim.py are touched; anything else on the port is left alone and reported.
 */
function replaceStaleShim(): boolean {
  try {
    const out = execFileSync("pgrep", ["-f", SHIM], { encoding: "utf8" });
    const pids = out
      .split("\n")
      .map((line) => Number(line.trim()))
      .filter((pid) => Number.isInteger(pid) && pid > 0 && pid !== process.pid);
    if (pids.length === 0) return false;
    for (const pid of pids) {
      try { process.kill(pid, "SIGTERM"); } catch { /* already gone */ }
    }
    return true;
  } catch {
    return false;                                  // no pgrep, or no match
  }
}

/**
 * This session's egress proxy, when it has one: the launcher's, on loopback.
 * Sent with every Llama request so the shim reaches ELM through it - the one
 * proxy certain to be alive for as long as the request is (see shim.py).
 */
export function sessionProxy(env: NodeJS.ProcessEnv = process.env): string | undefined {
  const value = (env.HTTPS_PROXY || env.https_proxy || "").trim();
  return /^http:\/\/(127\.0\.0\.1|localhost):\d{1,5}\/?$/.test(value) ? value : undefined;
}

async function ensureShim(): Promise<boolean> {
  // A shim that takes the caller's proxy is reusable whichever session started
  // it: each request names its own. An older one ignores that, so a session
  // behind the proxy replaces it if it is this install's - one started by
  // bootstrap.sh's checks had no proxy at all and sent every later session's
  // Llama traffic straight to ELM. Someone else's is used as it is.
  const current = await health();
  if (current && (current.callerProxy === true || !sessionProxy())) return true;
  if (current && !replaceStaleShim()) return true;
  // Only a session behind the egress proxy starts one. bootstrap.sh's extension
  // check, its `pi --list-models` and its guard probe (ELM_PI_NO_PROXY=1) all
  // load this file with no proxy, and each left a shim running with none in its
  // environment; every later session reused it, and its Llama traffic went
  // straight to ELM, past the proxy and its log. A session run unproxied on
  // purpose still uses a shim that is running; it does not leave one behind.
  // (Not PI_OFFLINE: the launcher sets that for every session - it only stops
  // pi's start-up network checks - and using it left no session with Llama.)
  if (!sessionProxy()) return false;
  if (!current && (await listening(PORT)) && !replaceStaleShim()) return false;
  for (let i = 0; i < 15 && (await listening(PORT)); i++) {
    await new Promise((r) => setTimeout(r, 200));  // wait up to ~3s for the port
  }
  if (!existsSync(SHIM)) return false;
  // The interpreter bootstrap.sh chose (exported by the launcher), isolated
  // from PYTHONPATH and site-packages: never whatever conda put first on PATH.
  const child = spawn(process.env.ELM_PI_PYTHON || "python3", ["-E", "-S", SHIM], {
    detached: true,
    stdio: "ignore",
    env: { ...process.env, SHIM_PORT: String(PORT) },
  });
  child.unref();
  for (let i = 0; i < 25; i++) {                   // wait up to ~5s for the port
    await new Promise((r) => setTimeout(r, 200));
    if (await health()) return true;
  }
  return false;
}

export default async function (pi: ExtensionAPI) {
  const up = await ensureShim();
  if (!up) {
    pi.on("session_start", async (_e, ctx: any) => {
      ctx.ui?.notify?.(
        `elm-shim: could not start ${SHIM} on :${PORT} - Llama sub-agents unavailable`,
        "warn",
      );
    });
    return;
  }

  const proxy = sessionProxy();
  pi.registerProvider("elm-shim", {
    ...(proxy ? { headers: { "X-Elm-Pi-Proxy": proxy } } : {}),
    name: "ELM (tool-shim)",
    baseUrl: `http://${HOST}:${PORT}`,
    apiKey: "$ELM_API_KEY",
    api: "openai-completions",
    models: [
      {
        id: MODEL,
        name: "Llama 3.3 70B (ELM, tool-shim)",
        reasoning: false,
        input: ["text"],
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
        contextWindow: 128000,
        // The shim buffers the whole upstream reply before sending a byte, and
        // pi gives up on a silent connection after httpIdleTimeoutMs (300 s),
        // then retries. At Llama's measured 30-47 tok/s, 16384 tokens is
        // 350-550 s: every long reply timed out and was generated again, up to
        // six times. 8192 finishes inside the window at the slow end.
        maxTokens: 8192,
        // Meta publishes no sampling advice in the model card; these are the
        // values in Llama-3.3-70B-Instruct's own generation_config.json. They
        // reach only requests without tools: shim.py sends every tool request at
        // SHIM_TEMPERATURE (0), measured 6/6 on the read-then-edit loop against
        // about half at the default. docs/tuning has the comparison.
        samplingParams: { temperature: 0.6, top_p: 0.9 },
        // pi takes an endpoint it does not know to support long prompt caching,
        // and with PI_CACHE_RETENTION=long in the user's shell it added
        // prompt_cache_key and prompt_cache_retention to every request, which the
        // shim passes on to ELM. The gateway accepts them (2026-11-11), but every
        // setting here was measured without them, so they are not sent - as for
        // Qwen and Mistral in models.json.
        compat: { supportsLongCacheRetention: false },
      } as any,
    ],
  });
}
