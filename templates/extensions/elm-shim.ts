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
const MODEL = "meta-llama/Llama-3.3-70B-Instruct";

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

async function ensureShim(): Promise<boolean> {
  // A shim of the current vintage resolves its own proxy per request, so one
  // that is already listening is reusable whichever session started it.
  if (await health()) return true;
  if (await listening(PORT) && !replaceStaleShim()) return false;
  for (let i = 0; i < 15 && (await listening(PORT)); i++) {
    await new Promise((r) => setTimeout(r, 200));  // wait up to ~3s for the port
  }
  if (!existsSync(SHIM)) return false;
  const child = spawn("python3", [SHIM], {
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

  pi.registerProvider("elm-shim", {
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
        maxTokens: 16384,
        // Meta publishes no sampling advice in the model card; these are the
        // values in Llama-3.3-70B-Instruct's own generation_config.json.
        samplingParams: { temperature: 0.6, top_p: 0.9 },
      },
    ],
  });
}
