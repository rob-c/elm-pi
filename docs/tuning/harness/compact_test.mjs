// pi's own compaction, as pi-auto-compact runs it, with a chosen model.
//
//   node compact_test.mjs PI_PKG MODELS_JSON ENV_FILE SESSION.jsonl OUT.json MODEL...
//
// MODEL is qwen, mistral or llama. The ELM key is read from ENV_FILE into memory
// and never printed. Llama is called on ELM directly (no tools are sent, so the
// shim's tool parsing is not needed) with the shim's limits: 128K in, 8192 out.
import { readFileSync, writeFileSync } from "node:fs";

const [pkg, modelsPath, envFile, sessionFile, outFile, ...wanted] = process.argv.slice(2);
const { compact, prepareCompaction } = await import(`${pkg}/dist/core/compaction/compaction.js`);
const { SessionManager } = await import(`${pkg}/dist/index.js`);

const key = readFileSync(envFile, "utf8").split("\n").find((l) => l.startsWith("ELM_API_KEY="))
  .slice("ELM_API_KEY=".length).trim().replace(/^['"]|['"]$/g, "");
const elm = JSON.parse(readFileSync(modelsPath, "utf8")).providers.elm;
const common = { provider: "elm", api: elm.api, baseUrl: elm.baseUrl };
const byNeedle = (needle) => ({ ...common, ...elm.models.find((m) => m.id.toLowerCase().includes(needle)) });
const MODELS = {
  qwen: byNeedle("qwen"),
  mistral: byNeedle("mistral"),
  llama: { ...common, id: "meta-llama/Llama-3.3-70B-Instruct", name: "Llama 3.3 70B", reasoning: false,
           input: ["text"], contextWindow: 128000, maxTokens: 8192,
           cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } },
};

// The same settings pi-auto-compact compacts with: pi's defaults.
const settings = { enabled: true, reserveTokens: 16384, keepRecentTokens: 20000 };
const session = SessionManager.open(sessionFile);
const preparation = prepareCompaction(session.getBranch(), settings);
if (!preparation) throw new Error("nothing to compact in " + sessionFile);
const INSTRUCTIONS = "Preserve the current task and any unfinished work.";

const results = { tokensBefore: preparation.tokensBefore, toSummarize: preparation.messagesToSummarize.length,
                  splitTurn: preparation.isSplitTurn, runs: [] };
for (const name of wanted) {
  const started = Date.now();
  try {
    const result = await compact(preparation, MODELS[name], key, undefined, INSTRUCTIONS, undefined, "off");
    results.runs.push({ model: name, ok: true, seconds: (Date.now() - started) / 1000,
                        summaryChars: result.summary.length, usage: result.usage ?? null, summary: result.summary });
  } catch (error) {
    results.runs.push({ model: name, ok: false, seconds: (Date.now() - started) / 1000,
                        error: String(error?.message ?? error).slice(0, 600) });
  }
  writeFileSync(outFile, JSON.stringify(results, null, 1));
  const last = results.runs.at(-1);
  console.log(`${name}: ${last.ok ? "ok" : "FAILED"} in ${last.seconds.toFixed(1)}s` +
              (last.ok ? `, ${last.summaryChars} chars` : ` - ${last.error.slice(0, 200)}`));
}
