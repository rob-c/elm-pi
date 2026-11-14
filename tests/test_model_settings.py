"""Each model's settings, against what was measured and what the vendor says.

Pure Python over the templates, so it runs on any checkout. For Qwen and Mistral
(templates/models.json) and Llama (the provider elm-shim.ts registers):

  - the limits pi is given: context, output, input kinds, cost;
  - the thinking map: every level pi knows, and only values the gateway accepts;
  - compat: what the gateway refuses (Mistral and the developer role);
  - sampling: only keys vLLM takes, in ranges it takes, and the values the
    measurements in docs/tuning chose;
  - everything else that names a model - settings.json's thinking levels, the
    task-model routes, the sub-agent overrides and definitions - names a served
    model at a level that model supports;
  - every model token in every template renders, and configure.sh's defaults
    agree with the template.

docs/tuning/README.md has the measurements; the numbers here come from it.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
MODELS = json.loads((TEMPLATES / "models.json").read_text())
ELM = MODELS["providers"]["elm"]
ENTRIES = {e["id"]: e for e in ELM["models"]}
QWEN, MISTRAL = ENTRIES["@QWEN_MODEL@"], ENTRIES["@MISTRAL_MODEL@"]
SETTINGS = json.loads((TEMPLATES / "settings.json").read_text())
TASK_MODELS = json.loads((TEMPLATES / "config/pi-task-models/config.json").read_text())
SHIM_TS = (TEMPLATES / "extensions/elm-shim.ts").read_text()

# pi's thinking levels, in order (pi-ai's ThinkingLevel).
LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "max"]
# What the gateway takes for reasoning_effort: Qwen and Mistral both, measured.
GATEWAY_EFFORTS = {"none", "high"}
# Sampling keys vLLM's OpenAI server accepts, with the range each takes.
SAMPLING_RANGES = {"temperature": (0.0, 2.0), "top_p": (0.0, 1.0), "top_k": (-1, 1000), "min_p": (0.0, 1.0),
                   "presence_penalty": (-2.0, 2.0), "frequency_penalty": (-2.0, 2.0),
                   "repetition_penalty": (0.0, 2.0)}


def shim_number(key):
    return int(re.search(rf"{key}: (\d+)", SHIM_TS).group(1))


def shim_sampling():
    body = re.search(r"samplingParams: \{([^}]*)\}", SHIM_TS).group(1)
    return {k: float(v) for k, v in re.findall(r"(\w+): ([\d.]+)", body)}


LLAMA = {
    "contextWindow": shim_number("contextWindow"),
    "maxTokens": shim_number("maxTokens"),
    "reasoning": re.search(r"reasoning: (true|false)", SHIM_TS).group(1) == "true",
    "input": re.findall(r'"(\w+)"', re.search(r"input: \[([^\]]*)\]", SHIM_TS).group(1)),
    "samplingParams": shim_sampling(),
}
SPECS = {"elm/@QWEN_MODEL@": QWEN, "elm/@MISTRAL_MODEL@": MISTRAL, "elm-shim/@LLAMA_MODEL@": LLAMA}


def supported_levels(model):
    """The levels a model takes as they are, not clamped: off, plus the mapped ones."""
    if not model.get("reasoning"):
        return {"off"}
    return {level for level, value in model["thinkingLevelMap"].items() if value is not None}


class LimitTests(unittest.TestCase):
    def test_elm_models_are_qwen_then_mistral(self):
        self.assertEqual(["@QWEN_MODEL@", "@MISTRAL_MODEL@"], [e["id"] for e in ELM["models"]])

    def test_the_provider_is_the_gateway_with_the_env_key(self):
        self.assertEqual(("https://elm.edina.ac.uk/api/v1", "openai-completions", "$ELM_API_KEY"),
                         (ELM["baseUrl"], ELM["api"], ELM["apiKey"]))

    def test_llama_limits_are_the_shims(self):
        # 8192 out: the shim buffers a reply, and pi gives up on 300 s of silence.
        self.assertEqual((128000, 8192, False, ["text"]),
                         (LLAMA["contextWindow"], LLAMA["maxTokens"], LLAMA["reasoning"], LLAMA["input"]))


def _limits(self, name, model):
    self.assertEqual(262144, model["contextWindow"], name)            # max_model_len on the gateway
    self.assertEqual(81920, model["maxTokens"], name)                 # streamed past 32768, measured
    self.assertLess(model["maxTokens"], model["contextWindow"], name)
    self.assertTrue(model["reasoning"], name)
    self.assertEqual(["text", "image"], model["input"], name)         # both read images, measured
    self.assertEqual({"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, model["cost"], name)
    self.assertIn("(ELM, university-hosted)", model["name"], name)


for _name, _model in (("qwen", QWEN), ("mistral", MISTRAL)):
    setattr(LimitTests, f"test_{_name}_limits", lambda self, n=_name, m=_model: _limits(self, n, m))


class ThinkingMapTests(unittest.TestCase):
    pass


def _map_covers_every_level(self, name, model):
    self.assertEqual(LEVELS, list(model["thinkingLevelMap"]), name)


def _map_values_are_what_the_gateway_takes(self, name, model):
    values = {v for v in model["thinkingLevelMap"].values() if v is not None}
    self.assertLessEqual(values, GATEWAY_EFFORTS, name)


def _off_is_none_and_high_is_high(self, name, model):
    self.assertEqual(("none", "high"), (model["thinkingLevelMap"]["off"], model["thinkingLevelMap"]["high"]), name)


def _between_levels_are_unsupported(self, name, model):
    # null: pi clamps them, rather than sending a value the gateway refuses
    for level in ("minimal", "low", "medium", "xhigh", "max"):
        self.assertIsNone(model["thinkingLevelMap"][level], f"{name} {level}")


for _name, _model in (("qwen", QWEN), ("mistral", MISTRAL)):
    for _check in (_map_covers_every_level, _map_values_are_what_the_gateway_takes, _off_is_none_and_high_is_high,
                   _between_levels_are_unsupported):
        setattr(ThinkingMapTests, f"test_{_name}_{_check.__name__.lstrip('_')}",
                lambda self, n=_name, m=_model, c=_check: c(self, n, m))


class CompatTests(unittest.TestCase):
    def test_both_take_reasoning_effort_in_openai_format(self):
        for name, model in (("qwen", QWEN), ("mistral", MISTRAL)):
            with self.subTest(model=name):
                self.assertTrue(model["compat"]["supportsReasoningEffort"])
                self.assertEqual("openai", model["compat"]["thinkingFormat"])

    def test_mistral_never_gets_the_developer_role(self):
        # measured: 400 "Unknown message role: developer"
        self.assertIs(False, MISTRAL["compat"]["supportsDeveloperRole"])

    def test_no_model_is_sent_long_cache_fields(self):
        # PI_CACHE_RETENTION=long added prompt_cache_key/_retention to every ELM
        # request. Accepted there, but no setting was measured with them;
        # tests/test_model_requests.py checks the wire.
        for name, model in (("qwen", QWEN), ("mistral", MISTRAL)):
            with self.subTest(model=name):
                self.assertIs(False, model["compat"]["supportsLongCacheRetention"])
        self.assertIn("compat: { supportsLongCacheRetention: false }", SHIM_TS)

    def test_qwen_keeps_pis_default_role(self):
        self.assertNotIn("supportsDeveloperRole", QWEN["compat"])

    def test_no_compat_key_pi_does_not_know(self):
        known = {"supportsReasoningEffort", "thinkingFormat", "supportsDeveloperRole", "maxTokensField",
                 "supportsStore", "supportsUsageInStreaming", "requiresToolResultName", "supportsLongCacheRetention"}
        for name, model in (("qwen", QWEN), ("mistral", MISTRAL)):
            with self.subTest(model=name):
                self.assertLessEqual(set(model["compat"]), known)


class SamplingTests(unittest.TestCase):
    """Only keys vLLM takes, in range, and the measured choices."""

    def test_qwen_instruct_profile_with_thinking_off(self):
        # Qwen3.5 card, instruct (non-thinking) profile; docs/tuning has the comparison.
        self.assertEqual({"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0},
                         {k: QWEN["samplingParams"][k] for k in ("temperature", "top_p", "top_k", "min_p")})

    def test_qwen_thinking_profile_with_thinking_on(self):
        self.assertEqual({"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0, "presence_penalty": 0.0},
                         QWEN["samplingParamsByThinkingLevel"]["high"])

    def test_mistral_is_cool_with_reasoning_off_and_0_7_with_it_on(self):
        # Mistral: 0.0-0.7 with reasoning off, 0.7 with it on; the gateway's default is 1.0
        self.assertEqual({"temperature": 0.15}, MISTRAL["samplingParams"])
        self.assertEqual({"high": {"temperature": 0.7}}, MISTRAL["samplingParamsByThinkingLevel"])

    def test_mistral_off_temperature_is_inside_mistrals_range(self):
        self.assertTrue(0.0 <= MISTRAL["samplingParams"]["temperature"] <= 0.7)

    def test_llama_sends_meta_style_sampling(self):
        self.assertEqual({"temperature", "top_p"}, set(LLAMA["samplingParams"]))


def _keys_and_ranges(self, label, params):
    for key, value in params.items():
        self.assertIn(key, SAMPLING_RANGES, f"{label}: {key} is not a vLLM sampling key")
        lo, hi = SAMPLING_RANGES[key]
        self.assertTrue(lo <= value <= hi, f"{label}: {key}={value} outside [{lo}, {hi}]")
        if key == "top_k":
            self.assertIsInstance(value, int, label)


def _by_level_only_for_supported_levels(self, name, model):
    for level in model.get("samplingParamsByThinkingLevel", {}):
        self.assertIn(level, supported_levels(model), f"{name}: sampling for {level}, which it does not take")


for _name, _model in (("qwen", QWEN), ("mistral", MISTRAL)):
    setattr(SamplingTests, f"test_{_name}_off_keys_and_ranges",
            lambda self, n=_name, m=_model: _keys_and_ranges(self, f"{n} off", m["samplingParams"]))
    for _level in _model.get("samplingParamsByThinkingLevel", {}):
        setattr(SamplingTests, f"test_{_name}_{_level}_keys_and_ranges",
                lambda self, n=_name, m=_model, lv=_level: _keys_and_ranges(self, f"{n} {lv}",
                                                                            m["samplingParamsByThinkingLevel"][lv]))
    setattr(SamplingTests, f"test_{_name}_sampling_only_for_levels_it_takes",
            lambda self, n=_name, m=_model: _by_level_only_for_supported_levels(self, n, m))
setattr(SamplingTests, "test_llama_keys_and_ranges", lambda self: _keys_and_ranges(self, "llama", LLAMA["samplingParams"]))


class ReferenceTests(unittest.TestCase):
    """Everything that names a model names a served one, at a level it takes."""

    def test_default_model_is_qwen_with_thinking_off(self):
        self.assertEqual(("elm", "@QWEN_MODEL@", "off"),
                         (SETTINGS["defaultProvider"], SETTINGS["defaultModel"], SETTINGS["defaultThinkingLevel"]))

    def test_thinking_levels_name_served_models(self):
        self.assertLessEqual(set(SETTINGS["modelThinkingLevels"]), set(SPECS))

    def test_mistral_thinks_and_qwen_does_not(self):
        self.assertEqual({"elm/@QWEN_MODEL@": "off", "elm/@MISTRAL_MODEL@": "high"}, SETTINGS["modelThinkingLevels"])

    def test_compaction_task_is_routed(self):
        self.assertEqual({"pi-auto-compact/autoCompact": "balanced"}, TASK_MODELS["tasks"])

    def test_compaction_falls_back_to_mistral_without_reasoning(self):
        self.assertEqual({"model": "elm/@MISTRAL_MODEL@", "thinkingLevel": "off"},
                         TASK_MODELS["profiles"]["balanced"]["fallback"])


def _level_supported(self, label, spec, level):
    self.assertIn(spec, SPECS, f"{label}: {spec} is not served")
    self.assertIn(level, supported_levels(SPECS[spec]), f"{label}: {spec} does not take {level}")


for _spec, _level in SETTINGS["modelThinkingLevels"].items():
    setattr(ReferenceTests, f"test_thinking_level_for_{re.sub(r'[^a-z]+', '_', _spec.lower()).strip('_')}",
            lambda self, s=_spec, lv=_level: _level_supported(self, "modelThinkingLevels", s, lv))
for _profile, _routes in TASK_MODELS["profiles"].items():
    for _role in ("primary", "fallback"):
        setattr(ReferenceTests, f"test_task_route_{_profile}_{_role}",
                lambda self, p=_profile, r=_role: _level_supported(
                    self, f"{p} {r}", TASK_MODELS["profiles"][p][r]["model"], TASK_MODELS["profiles"][p][r]["thinkingLevel"]))
    # A fallback to the model that just failed would fail the same way.
    setattr(ReferenceTests, f"test_task_profile_{_profile}_falls_back_to_another_model",
            lambda self, p=_profile: self.assertNotEqual(TASK_MODELS["profiles"][p]["primary"]["model"],
                                                         TASK_MODELS["profiles"][p]["fallback"]["model"]))

_OVERRIDES = SETTINGS["subagents"]["agentOverrides"]
for _agent, _override in _OVERRIDES.items():
    if "model" in _override:
        setattr(ReferenceTests, f"test_subagent_override_{_agent.replace('-', '_')}_names_a_served_model",
                lambda self, a=_agent: self.assertIn(_OVERRIDES[a]["model"], SPECS))
for _file in sorted((TEMPLATES / "agents").glob("*.md")):
    _m = re.search(r"^model: (\S+)$", _file.read_text(), re.M)
    if _m:
        setattr(ReferenceTests, f"test_agent_{_file.stem}_names_a_served_model",
                lambda self, s=_m.group(1): self.assertIn(s, SPECS))


class TokenRenderTests(unittest.TestCase):
    """Every model token in every template is one scripts/elm_config.py renders."""

    TOKENS = set(re.findall(r'"(@[A-Z]+_MODEL@)"', (ROOT / "scripts/elm_config.py").read_text()))

    def test_the_config_names_every_model_a_token_stands_for(self):
        self.assertEqual({"@QWEN_MODEL@", "@LLAMA_MODEL@", "@MISTRAL_MODEL@"}, self.TOKENS)
        self.assertEqual({"qwen", "llama", "mistral"}, set(CONFIG["models"]))

    def test_configure_sh_new_entry_matches_the_template_limits(self):
        configure = (ROOT / "configure.sh").read_text()
        self.assertIn(f'"contextWindow":{QWEN["contextWindow"]},"maxTokens":{QWEN["maxTokens"]}', configure)


_TEMPLATE_FILES = sorted(p for p in TEMPLATES.rglob("*") if p.is_file() and p.suffix in (".json", ".ts", ".md")
                         and re.search(r"@[A-Z]+_MODEL@", p.read_text(errors="ignore")))
for _path in _TEMPLATE_FILES:
    _rel = _path.relative_to(TEMPLATES).as_posix()
    setattr(TokenRenderTests, f"test_tokens_in_{re.sub(r'[^a-z0-9]+', '_', _rel.lower()).strip('_')}_are_known",
            lambda self, p=_path: self.assertLessEqual(set(re.findall(r"@[A-Z]+_MODEL@", p.read_text())), self.TOKENS))


if __name__ == "__main__":
    unittest.main()
