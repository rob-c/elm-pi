"""The request body pi sends to each ELM model, case by case, by pi's own code.

ELM is a vLLM gateway, and what it accepts was measured request by request
(2026-11-11). These tests hold pi to those measurements, so a change to
templates/models.json, to the elm-shim provider or to pi itself that alters a
request shows up here rather than as a 400 in a researcher's session:

  - Mistral rejects the `developer` role, so its system prompt must go out as
    `system` (compat.supportsDeveloperRole false). Qwen's goes out as pi
    decides for a reasoning model on an endpoint it does not know, which is
    `developer`, and the gateway takes it.
  - Thinking off sends reasoning_effort "none", thinking high sends "high".
    Every level the thinkingLevelMap maps to null is unsupported, and pi clamps
    it to the nearest supported one above (else below): for these models every
    level but off becomes high. Llama is not a reasoning model and never gets a
    reasoning_effort, whatever level a session (or a sub-agent launched with
    its parent's level) asks for.
  - Sampling: the model's samplingParams, with samplingParamsByThinkingLevel
    of the level actually sent merged over them.
  - Output: maxTokens goes out as max_completion_tokens, cut to the room the
    context leaves (pi's clampMaxTokensToContext), checked at several context
    sizes up to the edge of the window.
  - Tools: definitions go out when the session has tools and not otherwise
    (not even an empty list after tool calls); tool call ids made by Qwen
    (chatcmpl-tool-<16 hex>) reach Mistral unchanged, which the gateway accepts.
  - The body has exactly the keys pi sends now: a new one is a change to what
    the gateway was shown to accept, and should be measured before it is
    added here.

The expected values are read from templates/models.json (rendered with the ids
in config/elm-pi.json, as bootstrap.sh renders it) and from the provider
templates/extensions/elm-shim.ts registers, so the generated cases follow the
config; a few named tests also pin the measured numbers, so a silent change to
the config is caught too.

The requests are built by the pi the launcher runs - the bundled
pi-coding-agent (dist/bundle) that pi.orig starts, with its own copy of pi-ai -
through ModelRuntime.streamSimple, as an agent session calls it. elm-shim.ts is
run for real to get the Llama provider it registers, with its health check
answered in-process. Every request is answered by a stub fetch that records
the body: nothing leaves the process, and any other connection attempt fails
the run. Skipped on a checkout without pi installed (bootstrap.sh) or node.
"""

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
IDS = CONFIG["models"]
BUNDLE = ROOT / "node_modules/@earendil-works/pi-coding-agent/dist/bundle/index.js"
MODELS_TEMPLATE = ROOT / "templates/models.json"
SHIM_EXTENSION = ROOT / "templates/extensions/elm-shim.ts"
SHIM_PORT = 8811  # elm-shim.ts's default, which the launcher does not change

LEVELS = ("off", "minimal", "low", "medium", "high", "xhigh", "max")
MODELS = ("qwen", "mistral", "llama")
PROVIDER = {"qwen": "elm", "mistral": "elm", "llama": "elm-shim"}
# pi's token estimate (pi-ai utils/estimate.js) and its output clamp
# (api/simple-options.js clampMaxTokensToContext).
CHARS_PER_TOKEN = 3.5
SAFETY_TOKENS, SAFETY_RATIO, MIN_OUTPUT_WITH_RATIO = 4096, 0.15, 32768
# Every body has these; the rest depend on the model, the level and the tools.
# `store: false` is pi's for any OpenAI-compatible endpoint it does not know to
# be non-standard; vLLM ignores it.
BASE_KEYS = {"model", "messages", "stream", "stream_options", "store", "max_completion_tokens"}
REASONING_FIELDS = ("reasoning_content", "reasoning", "reasoning_text", "reasoning_details")


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def as_json(text):
    return json.dumps(text)[1:-1]


def rendered_models():
    """templates/models.json as bootstrap.sh renders it into agent/models.json."""
    raw = MODELS_TEMPLATE.read_text()
    raw = raw.replace("@QWEN_MODEL@", as_json(IDS["qwen"])).replace("@MISTRAL_MODEL@", as_json(IDS["mistral"]))
    return raw


MODELS_JSON = json.loads(rendered_models())
ELM = MODELS_JSON["providers"]["elm"]
SPECS = {name: next(m for m in ELM["models"] if m["id"] == IDS[name]) for name in ("qwen", "mistral")}
SHIM_SOURCE = SHIM_EXTENSION.read_text()
_llama_sampling = re.search(r"samplingParams:\s*\{([^}]*)\}", SHIM_SOURCE)
# Only to name the generated cases: the values come from the provider the
# extension registers (test_llama_sampling_keys_match_the_extension).
LLAMA_SAMPLING_KEYS = tuple(re.findall(r"([A-Za-z_]\w*)\s*:", _llama_sampling.group(1))) if _llama_sampling else ()


def supported_levels(spec):
    """The levels pi offers for a model: a null in thinkingLevelMap removes one,
    and xhigh/max exist only when mapped."""
    if not spec.get("reasoning"):
        return ["off"]
    mapping = spec.get("thinkingLevelMap") or {}
    return [level for level in LEVELS
            if not (level in mapping and mapping[level] is None)
            and not (level in ("xhigh", "max") and level not in mapping)]


def effective_level(spec, level):
    """The level pi sends: an unsupported one becomes the nearest supported level
    above it, or below when there is none above."""
    available = supported_levels(spec)
    if level in available:
        return level
    i = LEVELS.index(level)
    for candidate in LEVELS[i:] + tuple(reversed(LEVELS[:i])):
        if candidate in available:
            return candidate
    return "off"


def expected_effort(spec, level):
    if not spec.get("reasoning"):
        return None
    mapping = spec.get("thinkingLevelMap") or {}
    # Off is no reasoning option at all, so pi has nothing to clamp: it sends
    # the map's value for off, if that is a string.
    sent = "off" if level == "off" else effective_level(spec, level)
    if sent == "off":
        return mapping.get("off") if isinstance(mapping.get("off"), str) else None
    return mapping.get(sent) if mapping.get(sent) is not None else sent


def expected_sampling(spec, level):
    by_level = (spec.get("samplingParamsByThinkingLevel") or {}).get(effective_level(spec, level), {})
    return {**(spec.get("samplingParams") or {}), **by_level}


def estimate_tokens(text):
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def clamp_max_tokens(window, max_tokens, input_tokens):
    margin = max(SAFETY_TOKENS, math.ceil(input_tokens * SAFETY_RATIO))
    room = window - input_tokens - margin
    if room < MIN_OUTPUT_WITH_RATIO:
        room = min(MIN_OUTPUT_WITH_RATIO, window - input_tokens - SAFETY_TOKENS)
    return min(max_tokens, max(1, room))


# --- the conversations -------------------------------------------------------

SYSTEM = "You are pi, a coding agent working for a physicist at the University of Edinburgh."
TOOLS = [
    {"name": "read", "description": "Read a file in the project.",
     "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "bash", "description": "Run a shell command in the project.",
     "parameters": {"type": "object", "properties": {"command": {"type": "string"},
                                                     "timeout": {"type": "number"}}, "required": ["command"]}},
]
# Two calls in one Qwen turn, with ids in the form ELM's Qwen gives them.
QWEN_CALLS = [
    {"id": "chatcmpl-tool-8f3a1c2b4d5e6f70", "name": "read", "arguments": {"path": "analysis/fit.py"}},
    {"id": "chatcmpl-tool-0b9e7d6c5a4f3e21", "name": "bash",
     "arguments": {"command": "python analysis/fit.py", "timeout": 60}},
]
FOLLOW_UP = "Go on."


def usage(total=0):
    return {"input": total, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": total,
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0}}


def assistant(model, content, total=0, stop="stop", ts=2):
    return {"role": "assistant", "content": content, "api": "openai-completions", "provider": PROVIDER[model],
            "model": IDS[model], "usage": usage(total), "stopReason": stop, "timestamp": ts}


def user(text, ts):
    return {"role": "user", "content": text, "timestamp": ts}


def qwen_history():
    """A turn Qwen made with thinking on: it thought, called two tools, got
    their results and answered; then the user asks for more."""
    return [
        user("Run the fit and tell me if it converges.", 1),
        assistant("qwen", [{"type": "thinking", "thinking": "Read the script first, then run it.",
                            "thinkingSignature": "reasoning_content"},
                           *[{"type": "toolCall", **call} for call in QWEN_CALLS]], stop="toolUse", ts=2),
        *[{"role": "toolResult", "toolCallId": call["id"], "toolName": call["name"],
           "content": [{"type": "text", "text": text}], "isError": False, "timestamp": 3}
          for call, text in zip(QWEN_CALLS, ("import iminuit\n...", "Migrad converged, chi2/ndf = 1.02"))],
        assistant("qwen", [{"type": "text", "text": "It converges: chi2/ndf = 1.02."}], ts=4),
        user(FOLLOW_UP, 5),
    ]


def long_session(model, input_tokens):
    """A session whose last reply reported usage, so pi's estimate of the
    input is that usage plus the message after it: exactly input_tokens."""
    return [user("Start.", 1),
            assistant(model, [{"type": "text", "text": "Done."}], total=input_tokens - estimate_tokens(FOLLOW_UP)),
            user(FOLLOW_UP, 3)]


# Context sizes (pi's estimate of the input, in tokens) for the output clamp:
# from a short session to past the edge of the window.
ELM_SIZES = (10_000, 150_000, 160_000, 180_000, 200_000, 240_000, 258_000, 262_000)
# A first request after a resume has no usage yet: pi estimates from the text.
ELM_TEXT_SIZES = (100_000, 200_000)
LLAMA_SIZES = (1_000, 110_000, 118_000, 123_000, 127_000)

REQUESTS = {}
for _model in MODELS:
    for _level in LEVELS:
        REQUESTS[f"level/{_model}/{_level}"] = {"model": _model, "level": _level, "system": SYSTEM,
                                                "messages": [user("Hello.", 1)], "tools": []}
    REQUESTS[f"tools/{_model}"] = {"model": _model, "level": "off", "system": SYSTEM,
                                   "messages": [user("Hello.", 1)], "tools": TOOLS}
    REQUESTS[f"history/{_model}"] = {"model": _model, "level": "off", "system": SYSTEM,
                                     "messages": qwen_history(), "tools": TOOLS}
    REQUESTS[f"history-no-tools/{_model}"] = {"model": _model, "level": "off", "system": SYSTEM,
                                              "messages": qwen_history(), "tools": []}
    for _size in (LLAMA_SIZES if _model == "llama" else ELM_SIZES):
        REQUESTS[f"usage/{_model}/{_size}"] = {"model": _model, "level": "off", "system": SYSTEM,
                                               "messages": long_session(_model, _size), "tools": [],
                                               "input": _size}
    if _model != "llama":
        for _size in ELM_TEXT_SIZES:
            # One user message of that many tokens, less the system prompt's.
            _chars = math.floor((_size - estimate_tokens(SYSTEM)) * CHARS_PER_TOKEN)
            REQUESTS[f"text/{_model}/{_size}"] = {
                "model": _model, "level": "off", "system": SYSTEM, "tools": [],
                "messages": [{"role": "user", "fill": _chars, "timestamp": 1}],
                "input": estimate_tokens(SYSTEM) + math.ceil(_chars / CHARS_PER_TOKEN)}


RUNNER = r"""
import net from "node:net";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [bundlePath, modelsPath, authPath, shimPath, requestsPath, idsJson, port] = process.argv.slice(1);
const ids = JSON.parse(idsJson);

// Nothing here may reach a network: every socket is refused, and fetch is
// answered in-process.
net.Socket.prototype.connect = function () { throw new Error("no connections in this test"); };
const health = `http://127.0.0.1:${port}/__elm_shim__/health`;
globalThis.fetch = async (url) => {
  if (String(url) === health) {
    return new Response(JSON.stringify({ shim: "elm-pi" }),
                        { status: 200, headers: { "content-type": "application/json" } });
  }
  throw new Error(`no network in this test: ${url}`);
};

// The extension, run as pi runs it: it finds "its" shim healthy and registers the provider.
const registered = {};
const shim = await import(pathToFileURL(shimPath).href);
await shim.default({ on: () => {}, registerProvider: (name, config) => { registered[name] = config; } });
globalThis.fetch = async (url) => { throw new Error(`no network in this test: ${url}`); };

const { ModelRuntime } = await import(pathToFileURL(bundlePath).href);
const runtime = await ModelRuntime.create({ modelsPath, authPath, refreshOnCreate: false, allowModelNetwork: false });
if (registered["elm-shim"]) runtime.registerProvider("elm-shim", registered["elm-shim"]);
const models = {
  qwen: runtime.getModel("elm", ids.qwen),
  mistral: runtime.getModel("elm", ids.mistral),
  llama: runtime.getModel("elm-shim", ids.llama),
};

const chunk = { id: "chatcmpl-1", object: "chat.completion.chunk",
                choices: [{ index: 0, delta: { content: "ok" }, finish_reason: "stop" }] };
const reply = `data: ${JSON.stringify(chunk)}\n\ndata: [DONE]\n\n`;
// Long message texts are reported by length: the clamp cases send hundreds of kilobytes.
const shrink = (body) => ({ ...body, messages: (body.messages ?? []).map((m) =>
  typeof m.content === "string" && m.content.length > 2000 ? { ...m, content: `<${m.content.length} chars>` } : m) });

const out = {};
for (const [key, r] of Object.entries(JSON.parse(readFileSync(requestsPath, "utf8")))) {
  const requests = [];
  const fetch = async (url, init) => {
    requests.push({ url: String(url), body: shrink(JSON.parse(init.body)) });
    return new Response(reply, { status: 200, headers: { "content-type": "text/event-stream" } });
  };
  const messages = r.messages.map((m) =>
    (m.fill ? { role: m.role, content: "x".repeat(m.fill), timestamp: m.timestamp } : m));
  const model = models[r.model];
  try {
    if (!model) throw new Error(`pi has no model for ${r.model}`);
    // As the agent loop calls it: thinking off is no reasoning option at all.
    const result = await runtime.streamSimple(model, { systemPrompt: r.system, tools: r.tools, messages }, {
      reasoning: r.level === "off" ? undefined : r.level, sessionId: "model-requests-test", maxRetries: 0, fetch,
    }).result();
    out[key] = { requests, stopReason: result.stopReason, error: result.errorMessage ?? null };
  } catch (e) {
    out[key] = { requests, stopReason: null, error: String(e && e.stack || e) };
  }
}
console.log(JSON.stringify({ error: runtime.getError() ?? null, models, registered, results: out }));
"""


@unittest.skipUnless(BUNDLE.is_file(), "pi is not installed in this checkout (bootstrap.sh)")
@unittest.skipUnless(node(), "needs node")
class ModelRequestTests(unittest.TestCase):
    # Extra environment for the runner: what a user's shell might export.
    ENV_EXTRA = {}

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            (cls.tmp / "home").mkdir()
            (cls.tmp / "agent").mkdir()
            (cls.tmp / "models.json").write_text(rendered_models())
            # Rendered as bootstrap.sh renders the extensions.
            (cls.tmp / "elm-shim.ts").write_text(SHIM_SOURCE.replace("@LLAMA_MODEL@", IDS["llama"]))
            (cls.tmp / "requests.json").write_text(json.dumps(REQUESTS))
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(cls.tmp / "home"),
                   "PI_CODING_AGENT_DIR": str(cls.tmp / "agent"), "NO_COLOR": "1",
                   "ELM_API_KEY": "not-a-real-key", "ELM_SHIM_PATH": str(cls.tmp / "no-shim.py"), **cls.ENV_EXTRA}
            run = subprocess.run([node(), "--no-warnings", "--input-type=module", "-e", RUNNER, str(BUNDLE),
                                  str(cls.tmp / "models.json"), str(cls.tmp / "agent/auth.json"),
                                  str(cls.tmp / "elm-shim.ts"), str(cls.tmp / "requests.json"), json.dumps(IDS),
                                  str(SHIM_PORT)],
                                 capture_output=True, text=True, env=env, cwd=cls.tmp, timeout=300)
            if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
                raise unittest.SkipTest("this node cannot load TypeScript")
            if run.returncode != 0:
                raise AssertionError(f"runner failed:\n{run.stderr[-3000:]}")
            cls.out = json.loads(run.stdout)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # --- helpers ---------------------------------------------------------------

    def spec(self, model):
        """The model as configured: models.json, or the provider elm-shim.ts registers."""
        if model == "llama":
            return self.out["registered"]["elm-shim"]["models"][0]
        return SPECS[model]

    def request(self, key):
        got = self.out["results"][key]
        self.assertIsNone(got["error"], key)
        self.assertEqual("stop", got["stopReason"], key)
        self.assertEqual(1, len(got["requests"]), f"{key}: one request per turn")
        return got["requests"][0]

    def body(self, key):
        return self.request(key)["body"]

    def assistant_messages(self, key):
        return [m for m in self.body(key)["messages"] if m["role"] == "assistant"]

    # --- the generated checks --------------------------------------------------

    def check_reasoning_effort(self, model, level):
        body, effort = self.body(f"level/{model}/{level}"), expected_effort(self.spec(model), level)
        if effort is None:
            self.assertNotIn("reasoning_effort", body)
        else:
            self.assertEqual(effort, body.get("reasoning_effort"))

    def check_sampling(self, model, level, key):
        expected = expected_sampling(self.spec(model), level)
        self.assertIn(key, expected, f"{key} is not among {model}'s sampling params")
        self.assertEqual(expected[key], self.body(f"level/{model}/{level}").get(key, "<absent>"))

    def check_body_keys(self, model, level):
        spec = self.spec(model)
        expected = BASE_KEYS | set(expected_sampling(spec, level))
        if expected_effort(spec, level) is not None:
            expected.add("reasoning_effort")
        self.assertEqual(sorted(expected), sorted(self.body(f"level/{model}/{level}")))

    def check_system_role(self, model):
        system = [m for m in self.body(f"level/{model}/off")["messages"] if m.get("content") == SYSTEM]
        self.assertEqual(1, len(system), "the system prompt is sent once")
        self.assertEqual("developer" if model == "qwen" else "system", system[0]["role"])

    def check_endpoint(self, model):
        base = f"http://127.0.0.1:{SHIM_PORT}" if model == "llama" else ELM["baseUrl"]
        self.assertEqual(f"{base}/chat/completions", self.request(f"level/{model}/off")["url"])

    def check_model_id(self, model):
        self.assertEqual(IDS[model], self.body(f"level/{model}/off")["model"])

    def check_stream_usage(self, model):
        body = self.body(f"level/{model}/off")
        self.assertIs(True, body.get("stream"))
        self.assertEqual({"include_usage": True}, body.get("stream_options"))

    def check_output_limit(self, model):
        body = self.body(f"level/{model}/off")
        self.assertNotIn("max_tokens", body)
        self.assertEqual(self.spec(model)["maxTokens"], body.get("max_completion_tokens"))

    def check_tools_sent(self, model):
        body = self.body(f"tools/{model}")
        self.assertNotIn("tool_choice", body)
        self.assertEqual([{"type": "function", "function": tool} for tool in TOOLS], body.get("tools"))

    def check_no_tools(self, model):
        body = self.body(f"history-no-tools/{model}")
        self.assertTrue(any(m.get("tool_calls") for m in body["messages"]), "the history has tool calls")
        self.assertNotIn("tools", body)
        self.assertNotIn("tool_choice", body)

    def check_max_tokens(self, key):
        spec, input_tokens = self.spec(REQUESTS[key]["model"]), REQUESTS[key]["input"]
        window = spec["contextWindow"]
        sent = self.body(key).get("max_completion_tokens")
        self.assertEqual(clamp_max_tokens(window, spec["maxTokens"], input_tokens), sent)
        if window - input_tokens - SAFETY_TOKENS >= 1:
            self.assertLessEqual(input_tokens + sent, window - SAFETY_TOKENS, "the safety margin is kept")
        else:
            self.assertEqual(1, sent, "no room left: the least pi sends")

    def check_history_call_ids(self, model):
        calls = [call for m in self.assistant_messages(f"history/{model}") for call in m.get("tool_calls") or []]
        self.assertEqual([c["id"] for c in QWEN_CALLS], [c["id"] for c in calls])
        self.assertEqual([c["name"] for c in QWEN_CALLS], [c["function"]["name"] for c in calls])

    def check_history_result_ids(self, model):
        results = [m for m in self.body(f"history/{model}")["messages"] if m["role"] == "tool"]
        self.assertEqual([c["id"] for c in QWEN_CALLS], [m["tool_call_id"] for m in results])

    def check_history_arguments(self, model):
        calls = [call for m in self.assistant_messages(f"history/{model}") for call in m.get("tool_calls") or []]
        self.assertEqual(len(QWEN_CALLS), len(calls))
        for sent, call in zip(calls, QWEN_CALLS):
            self.assertIsInstance(sent["function"]["arguments"], str, "arguments go out as a JSON string")
            self.assertEqual(call["arguments"], json.loads(sent["function"]["arguments"]))

    def check_history_no_foreign_thinking(self, model):
        for message in self.assistant_messages(f"history/{model}"):
            self.assertEqual([], [f for f in REASONING_FIELDS if f in message], "Qwen's thinking is Qwen's only")

    # --- the measured values, by number ----------------------------------------

    def test_models_json_loads_into_pi_as_written(self):
        self.assertIsNone(self.out["error"])
        for model in ("qwen", "mistral"):
            loaded = self.out["models"][model]
            self.assertIsNotNone(loaded, model)
            for field in ("reasoning", "contextWindow", "maxTokens", "thinkingLevelMap", "samplingParams",
                          "samplingParamsByThinkingLevel", "compat"):
                with self.subTest(model=model, field=field):
                    self.assertEqual(SPECS[model].get(field), loaded.get(field))

    def test_llama_sampling_keys_match_the_extension(self):
        self.assertTrue(LLAMA_SAMPLING_KEYS, "samplingParams not found in elm-shim.ts")
        self.assertEqual(sorted(LLAMA_SAMPLING_KEYS), sorted(self.spec("llama").get("samplingParams") or {}))

    def test_mistral_system_prompt_is_never_developer(self):
        for key in self.out["results"]:
            if REQUESTS[key]["model"] == "mistral":
                with self.subTest(key=key):
                    self.assertEqual([], [m for m in self.body(key)["messages"] if m["role"] == "developer"])
                    self.assertEqual("system", self.body(key)["messages"][0]["role"])

    def test_qwen_system_prompt_is_developer(self):
        self.assertEqual({"role": "developer", "content": SYSTEM}, self.body("level/qwen/off")["messages"][0])

    def test_thinking_off_sends_reasoning_effort_none(self):
        for model in ("qwen", "mistral"):
            self.assertEqual("none", self.body(f"level/{model}/off")["reasoning_effort"], model)

    def test_thinking_high_sends_reasoning_effort_high(self):
        for model in ("qwen", "mistral"):
            self.assertEqual("high", self.body(f"level/{model}/high")["reasoning_effort"], model)

    def test_unsupported_levels_are_sent_as_high(self):
        for model in ("qwen", "mistral"):
            for level in ("minimal", "low", "medium", "xhigh", "max"):
                with self.subTest(model=model, level=level):
                    body = self.body(f"level/{model}/{level}")
                    self.assertEqual("high", body["reasoning_effort"])
                    self.assertEqual({k: body[k] for k in expected_sampling(SPECS[model], "high")},
                                     expected_sampling(SPECS[model], "high"))

    def test_llama_never_gets_reasoning_effort(self):
        for level in LEVELS:
            self.assertNotIn("reasoning_effort", self.body(f"level/llama/{level}"), level)

    def test_qwen_sampling_measured_with_thinking_off(self):
        body = self.body("level/qwen/off")
        self.assertEqual({"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0, "presence_penalty": 1.5,
                          "repetition_penalty": 1.0},
                         {k: body.get(k) for k in ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "repetition_penalty")})

    def test_qwen_sampling_measured_with_thinking_high(self):
        body = self.body("level/qwen/high")
        self.assertEqual({"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0, "presence_penalty": 0,
                          "repetition_penalty": 1.0},
                         {k: body.get(k) for k in ("temperature", "top_p", "top_k", "min_p", "presence_penalty", "repetition_penalty")})

    def test_mistral_temperature_measured(self):
        self.assertEqual(0.15, self.body("level/mistral/off")["temperature"])
        self.assertEqual(0.7, self.body("level/mistral/high")["temperature"])
        for level in ("off", "high"):
            body = self.body(f"level/mistral/{level}")
            self.assertEqual([], [k for k in ("top_p", "top_k", "min_p", "presence_penalty", "repetition_penalty") if k in body], level)

    def test_output_limit_measured(self):
        for model in ("qwen", "mistral"):
            with self.subTest(model=model):
                self.assertEqual(262144, SPECS[model]["contextWindow"])
                self.assertEqual(81920, self.body(f"level/{model}/off")["max_completion_tokens"])
                self.assertEqual(81920, self.body(f"level/{model}/high")["max_completion_tokens"])

    def test_output_limit_clamped_near_the_window(self):
        # 160k: 262144 - 160000 - 15% margin; 200k: the 15% margin would leave
        # under 32768, so 32768 with the fixed 4096 margin; 258k: 262144 -
        # 258000 - 4096 = 48; 262k: not even the 4096 margin is left, so 1.
        self.assertEqual(78144, self.body("usage/qwen/160000")["max_completion_tokens"])
        self.assertEqual(32768, self.body("usage/qwen/200000")["max_completion_tokens"])
        self.assertEqual(48, self.body("usage/mistral/258000")["max_completion_tokens"])
        self.assertEqual(1, self.body("usage/mistral/262000")["max_completion_tokens"])

    def test_llama_measured_settings(self):
        spec = self.spec("llama")
        self.assertEqual((128000, 8192), (spec["contextWindow"], spec["maxTokens"]))
        body = self.body("level/llama/off")
        self.assertEqual((8192, 0.6, 0.9), (body["max_completion_tokens"], body["temperature"], body["top_p"]))

    def test_qwen_tool_call_ids_reach_mistral_unchanged(self):
        body = self.body("history/mistral")
        for call_id in ("chatcmpl-tool-8f3a1c2b4d5e6f70", "chatcmpl-tool-0b9e7d6c5a4f3e21"):
            self.assertRegex(call_id, r"^chatcmpl-tool-[0-9a-f]{16}$")
            self.assertIn(call_id, [c["id"] for m in body["messages"] for c in m.get("tool_calls") or []])
            self.assertIn(call_id, [m.get("tool_call_id") for m in body["messages"]])


def _num(n):
    return f"{n // 1000}k" if n % 1000 == 0 else str(n)


def _add(name, fn):
    name = "test_" + name
    assert not hasattr(ModelRequestTests, name), name
    setattr(ModelRequestTests, name, fn)


for _model in MODELS:
    _keys = LLAMA_SAMPLING_KEYS if _model == "llama" else tuple(
        sorted(set(SPECS[_model].get("samplingParams") or {})
               | {k for p in (SPECS[_model].get("samplingParamsByThinkingLevel") or {}).values() for k in p}))
    for _level in LEVELS:
        _add(f"{_model}_{_level}_reasoning_effort",
             lambda self, m=_model, lv=_level: self.check_reasoning_effort(m, lv))
        _add(f"{_model}_{_level}_body_keys", lambda self, m=_model, lv=_level: self.check_body_keys(m, lv))
        for _key in _keys:
            _add(f"{_model}_{_level}_sampling_{_key}",
                 lambda self, m=_model, lv=_level, k=_key: self.check_sampling(m, lv, k))
    _add(f"{_model}_system_prompt_role", lambda self, m=_model: self.check_system_role(m))
    _add(f"{_model}_endpoint", lambda self, m=_model: self.check_endpoint(m))
    _add(f"{_model}_model_id", lambda self, m=_model: self.check_model_id(m))
    _add(f"{_model}_stream_with_usage", lambda self, m=_model: self.check_stream_usage(m))
    _add(f"{_model}_output_limit_field_and_value", lambda self, m=_model: self.check_output_limit(m))
    _add(f"{_model}_tools_sent", lambda self, m=_model: self.check_tools_sent(m))
    _add(f"{_model}_no_tools_after_tool_calls", lambda self, m=_model: self.check_no_tools(m))
    _add(f"{_model}_qwen_history_tool_call_ids", lambda self, m=_model: self.check_history_call_ids(m))
    _add(f"{_model}_qwen_history_tool_result_ids", lambda self, m=_model: self.check_history_result_ids(m))
    _add(f"{_model}_qwen_history_arguments_json", lambda self, m=_model: self.check_history_arguments(m))
    if _model != "qwen":
        _add(f"{_model}_qwen_history_thinking_not_replayed",
             lambda self, m=_model: self.check_history_no_foreign_thinking(m))
for _key, _request in REQUESTS.items():
    if "input" in _request:
        _kind, _model, _size = _key.split("/")
        _add(f"{_model}_max_tokens_at_{_num(int(_size))}_tokens_{'estimated' if _kind == 'text' else 'reported'}",
             lambda self, k=_key: self.check_max_tokens(k))


@unittest.skipUnless(BUNDLE.is_file(), "pi is not installed in this checkout (bootstrap.sh)")
@unittest.skipUnless(node(), "needs node")
class CacheRetentionTests(unittest.TestCase):
    """PI_CACHE_RETENTION=long in a user's shell adds nothing to an ELM request.

    pi takes an endpoint it does not know to support long prompt caching, and with
    the variable set it added prompt_cache_key and prompt_cache_retention ("24h")
    to every ELM request. The gateway accepts both (docs/tuning, gateway-fields),
    but the settings were all measured without them; the ELM models' compat says
    supportsLongCacheRetention false, so the request stays the measured one.
    """

    ENV_EXTRA = {"PI_CACHE_RETENTION": "long"}
    setUpClass = classmethod(ModelRequestTests.setUpClass.__func__)
    tearDownClass = classmethod(ModelRequestTests.tearDownClass.__func__)

    def bodies(self):
        return [r for result in self.out["results"].values() for r in result["requests"]]

    def test_the_requests_were_made(self):
        self.assertGreater(len(self.bodies()), 20)

    def test_no_prompt_cache_key(self):
        self.assertEqual([], [b for b in self.bodies() if "prompt_cache_key" in json.dumps(b)])

    def test_no_prompt_cache_retention(self):
        self.assertEqual([], [b for b in self.bodies() if "prompt_cache_retention" in json.dumps(b)])


if __name__ == "__main__":
    unittest.main()
