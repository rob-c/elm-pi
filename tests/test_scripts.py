"""The Python scripts behind bootstrap.sh and the agent's search tools, run
against throwaway inputs: scripts/elm_config.py, check_config.py,
pin_versions.py, pypi_index.py (and the pypi-search / conda-search wrappers),
verify_install.py, and patch-pi.py on synthetic bundles.

Most cases are tables: one test method per row, generated at import, so a
failure names the exact input. Nothing here touches the network, the real
agent/ directory or the real pi bundle; every root is a temp directory.
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_config  # noqa: E402
import elm_config  # noqa: E402
import pin_versions  # noqa: E402
import pypi_index  # noqa: E402
import verify_install  # noqa: E402

_spec = importlib.util.spec_from_file_location("patch_pi", ROOT / "patch-pi.py")
patch_pi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(patch_pi)


def write(path: Path, text: str, mode: int = 0o644) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)
    return path


def call(main, argv):
    """Run a script's main() in-process: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sys, "argv", ["prog", *argv]), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main()
        except SystemExit as exit_:
            code = exit_.code
    return code, out.getvalue(), err.getvalue()


def generate(cls, cases, check, expected_failures=()):
    """One test_<slug> method on cls per (slug, *args) row; a slug listed in
    expected_failures is a known bug, marked rather than hidden."""
    for slug, *args in cases:
        name = f"test_{slug}"
        assert not hasattr(cls, name), name
        def method(self, _args=tuple(args)):
            check(self, *_args)
        method.__name__ = name
        if slug in expected_failures:
            method = unittest.expectedFailure(method)
        setattr(cls, name, method)


# A small config/elm-pi.json with every value write_runtime() reads, some of
# them with the spaces, quotes and $ that the shell quoting has to survive.
CONFIG = {
    "nodeVersion": "v24.0.1",
    "python": {"version": "3.12", "packages": ["numpy", "scipy"]},
    "models": {"qwen": "Qwen/Config-1", "llama": "meta/Config-2"},
    "allowedProviders": ["elm", "elm-shim"],
    "builtinProviders": ["anthropic", "openai"],
    "providerCredentials": ["A_KEY", "B_KEY"],
    "webTools": ["web_search", "fetch_content"],
    "excludedTools": {"always": ["nb_merge", "nb_move"], "workflows": ["workflow"]},
    "untrustedFolders": {"exact": ["/", "~/Library/Mobile Documents"], "tree": ["~/.ssh", "/it's $HOME"]},
    "proxyAllow": {"hosts": ["pypi.org", "x.io"]},
}


def make_root(base: Path, state: dict | None = None) -> Path:
    root = base / "install"
    write(root / "config/elm-pi.json", json.dumps(CONFIG))
    if state is not None:
        write(root / "agent/model-ids.json", json.dumps(state))
    return root


# --- scripts/elm_config.py ----------------------------------------------------

class RenderedTests(unittest.TestCase):
    """elm_config.rendered(): only the two model tokens, nothing else."""

MODELS = {"qwen": "Q/q-1", "llama": "L/l-2"}
generate(RenderedTests, [
    ("qwen_token_becomes_the_qwen_id", "m=@QWEN_MODEL@", "m=Q/q-1"),
    ("llama_token_becomes_the_llama_id", "@LLAMA_MODEL@", "L/l-2"),
    ("every_occurrence_is_replaced", "@QWEN_MODEL@ @LLAMA_MODEL@ @QWEN_MODEL@", "Q/q-1 L/l-2 Q/q-1"),
    ("adjacent_tokens_both_replaced", "@QWEN_MODEL@@LLAMA_MODEL@", "Q/q-1L/l-2"),
    ("unterminated_token_is_left", "@QWEN_MODEL", "@QWEN_MODEL"),
    # render_file() substitutes this one; rendered() must not
    ("agent_dir_token_is_not_rendered_here", "@AGENT_DIR@/x", "@AGENT_DIR@/x"),
    # bootstrap.sh seds this one into the permission config itself
    ("install_dir_token_is_left_for_bootstrap", "@INSTALL_DIR@/**", "@INSTALL_DIR@/**"),
], lambda self, text, expected: self.assertEqual(expected, elm_config.rendered(text, MODELS)))


class RenderFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def render(self, text, state=None):
        root = make_root(self.base, state)
        source = write(self.base / "src.md", text)
        dest = self.base / "out/deep/er/dest.md"
        elm_config.render_file(root, source, dest)
        return root, dest.read_text()

    def test_agent_dir_becomes_the_installs_agent_folder(self):
        root, text = self.render("read @AGENT_DIR@/reference/x.md")
        self.assertEqual(f"read {root / 'agent'}/reference/x.md", text)

    def test_missing_destination_folders_are_created(self):
        _, text = self.render("plain")
        self.assertEqual("plain", text)

    def test_the_state_file_wins_over_the_config(self):
        _, text = self.render("@QWEN_MODEL@|@LLAMA_MODEL@", state={"qwen": "Qwen/State-9"})
        # a state file naming only qwen leaves llama at the config's value
        self.assertEqual("Qwen/State-9|meta/Config-2", text)

    def test_without_a_state_file_the_config_models_are_used(self):
        _, text = self.render("@QWEN_MODEL@|@LLAMA_MODEL@")
        self.assertEqual("Qwen/Config-1|meta/Config-2", text)


class RuntimeEnvTests(unittest.TestCase):
    """agent/runtime.env, sourced by a real bash: what the launcher sees."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = make_root(Path(cls.tmp.name), state={"qwen": "Qwen/State-3", "llama": "meta/Config-2"})
        elm_config.write_runtime(cls.root)
        cls.path = cls.root / "agent/runtime.env"
        # NUL-separated so values with newlines in them come back whole
        script = ('set -eu; . "$1"; for n in $(sed -n "s/^export \\([A-Z_]*\\)=.*/\\1/p" "$1"); do '
                  'eval "v=\\$$n"; printf "%s=%s\\0" "$n" "$v"; done')
        out = subprocess.run(["bash", "-c", script, "probe", str(cls.path)], capture_output=True, check=True).stdout
        cls.env = dict(item.decode().split("=", 1) for item in out.split(b"\0") if item)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_file_is_private(self):
        self.assertEqual(0o600, stat.S_IMODE(self.path.stat().st_mode))

    def test_eleven_exports_and_nothing_else(self):
        # the two one-path-per-line values continue inside their quotes
        lines = self.path.read_text().splitlines()
        exports = [line.split("=", 1)[0] for line in lines if line.startswith("export ")]
        self.assertEqual(11, len(set(exports)))
        self.assertEqual(13, len(lines))
        self.assertEqual(set(self.env), {e[len("export "):] for e in exports})


generate(RuntimeEnvTests, [
    ("qwen_id_comes_from_the_state_file", "ELM_QWEN_MODEL_ID", "Qwen/State-3"),
    ("llama_id", "ELM_LLAMA_MODEL_ID", "meta/Config-2"),
    ("allowed_providers_are_space_separated", "ELM_ALLOWED_PROVIDERS", "elm elm-shim"),
    ("builtin_providers_are_space_separated", "ELM_BUILTIN_PROVIDERS", "anthropic openai"),
    ("credentials_are_space_separated", "ELM_PROVIDER_CREDENTIALS", "A_KEY B_KEY"),
    ("web_tools_are_comma_separated", "ELM_WEB_TOOLS", "web_search,fetch_content"),
    ("always_excluded_tools", "ELM_EXCLUDED_TOOLS", "nb_merge,nb_move"),
    ("workflow_tools", "ELM_WORKFLOW_TOOLS", "workflow"),
    # one path per line: a path with a space must not split
    ("untrusted_exact_is_one_path_per_line", "ELM_UNTRUSTED_EXACT", "/\n~/Library/Mobile Documents"),
    # a quote and a $ survive the shell quoting literally
    ("untrusted_tree_keeps_quotes_and_dollars", "ELM_UNTRUSTED_TREE", "~/.ssh\n/it's $HOME"),
    ("proxy_hosts_are_comma_separated", "ELM_PROXY_ALLOW", "pypi.org,x.io"),
], lambda self, key, expected: self.assertEqual(expected, self.env[key]))


class ReplaceJsonTests(unittest.TestCase):
    pass


generate(ReplaceJsonTests, [
    # a whole id inside a longer string; "x-old-y" no longer changes, as "old"
    # there is part of a longer id (SetModelTests: Q-1 and a hand-added Q-1-NEW)
    ("inside_a_string", "old (ELM, university-hosted)", "new (ELM, university-hosted)"),
    ("a_longer_id_is_kept", ["old-v2", "v2-old", "old.5"], ["old-v2", "v2-old", "old.5"]),
    # modelThinkingLevels is keyed by model id
    ("dictionary_keys", {"elm/old": 1}, {"elm/new": 1}),
    ("nested_lists_and_dicts", {"a": ["old", {"b": "old"}]}, {"a": ["new", {"b": "new"}]}),
    ("numbers_booleans_and_null_are_kept", [1, 2.5, True, None], [1, 2.5, True, None]),
    ("unrelated_strings_are_kept", {"k": "other"}, {"k": "other"}),
], lambda self, value, expected: self.assertEqual(expected, elm_config.replace_json(value, "old", "new")))


class SetModelTests(unittest.TestCase):
    """configure.sh's set-model: every generated consumer follows the new id."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self.tmp.name), state={"qwen": "Q-1", "llama": "L-1"})
        a = self.root / "agent"
        write(a / "models.json", json.dumps({"providers": {"elm": {"models": [{"id": "Q-1"}, {"id": "L-1"}]}}}))
        write(a / "settings.json", json.dumps({"defaultModel": "Q-1", "modelThinkingLevels": {"elm/Q-1": "off"},
                                               "theme": "dark"}))
        write(a / "agents/qwen.md", "model: elm/Q-1\n")
        # what bootstrap.sh rendered those from: set-model renders them again
        write(self.root / "templates/agents/qwen.md", "model: elm/@QWEN_MODEL@\n")
        write(self.root / "templates/agents/llama.md", "model: elm-shim/@LLAMA_MODEL@\n")

    def tearDown(self):
        self.tmp.cleanup()

    def agent(self, rel):
        return (self.root / "agent" / rel).read_text()

    def test_state_file_records_the_new_id_and_stays_private(self):
        elm_config.set_model(self.root, "qwen", "Q-2")
        self.assertEqual({"qwen": "Q-2", "llama": "L-1"}, json.loads(self.agent("model-ids.json")))
        self.assertEqual(0o600, stat.S_IMODE((self.root / "agent/model-ids.json").stat().st_mode))

    def test_settings_keys_and_values_move_and_the_rest_is_kept(self):
        elm_config.set_model(self.root, "qwen", "Q-2")
        self.assertEqual({"defaultModel": "Q-2", "modelThinkingLevels": {"elm/Q-2": "off"}, "theme": "dark"},
                         json.loads(self.agent("settings.json")))

    def test_only_the_named_model_changes_in_models_json(self):
        elm_config.set_model(self.root, "llama", "L-2")
        ids = [m["id"] for m in json.loads(self.agent("models.json"))["providers"]["elm"]["models"]]
        self.assertEqual(["Q-1", "L-2"], ids)

    def test_agent_definitions_are_rendered_again(self):
        elm_config.set_model(self.root, "qwen", "Q-2")
        self.assertEqual("model: elm/Q-2\n", self.agent("agents/qwen.md"))

    def test_runtime_env_carries_the_new_id(self):
        elm_config.set_model(self.root, "qwen", "Q-2")
        self.assertIn("export ELM_QWEN_MODEL_ID=Q-2\n", self.agent("runtime.env"))

    def test_consumers_that_are_not_installed_are_not_created(self):
        elm_config.set_model(self.root, "qwen", "Q-2")
        self.assertFalse((self.root / "agent/agents/llama.md").exists())
        self.assertFalse((self.root / "agent/config/pi-task-models/config.json").exists())

    # a hand-added "Q-1-NEW" merely starts with the old id: it is not "Q-2-NEW"
    def test_an_id_that_contains_the_old_one_is_left_alone(self):
        write(self.root / "agent/models.json",
              json.dumps({"providers": {"elm": {"models": [{"id": "Q-1"}, {"id": "Q-1-NEW"}]}}}))
        elm_config.set_model(self.root, "qwen", "Q-2")
        ids = [m["id"] for m in json.loads(self.agent("models.json"))["providers"]["elm"]["models"]]
        self.assertEqual(["Q-2", "Q-1-NEW"], ids)


class SetModelReachesEveryRenderedTemplateTests(unittest.TestCase):
    """Every template with a model token, rendered the way bootstrap.sh does it,
    must lose the old id when configure.sh changes the model."""

    INSTALLED = {
        "models.json": "models.json",
        "settings.json": "settings.json",
        "config/pi-task-models/config.json": "config/pi-task-models/config.json",
        "agents/qwen.md": "agents/qwen.md",
        "agents/llama.md": "agents/llama.md",
        "extensions/elm-shim.ts": "extensions/elm-shim.ts",
        "extensions/workflow-model-scope.ts": "extensions/workflow-model-scope.ts",
        "AGENTS.md": "AGENTS.md",
    }

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "install"
        shutil.copytree(ROOT / "config", cls.root / "config")
        # set-model renders AGENTS.md and the extensions again from the install's templates/
        shutil.copytree(ROOT / "templates", cls.root / "templates", ignore=shutil.ignore_patterns(".pi"))
        cls.old = json.loads((ROOT / "config/elm-pi.json").read_text())["models"]
        for template, installed in cls.INSTALLED.items():
            elm_config.render_file(cls.root, ROOT / "templates" / template, cls.root / "agent" / installed)
        elm_config.set_model(cls.root, "qwen", "Qwen/Replacement-A")
        elm_config.set_model(cls.root, "llama", "meta/Replacement-B")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check(self, template):
        source = (ROOT / "templates" / template).read_text()
        text = (self.root / "agent" / self.INSTALLED[template]).read_text()
        for name, token, new in (("qwen", "@QWEN_MODEL@", "Qwen/Replacement-A"),
                                 ("llama", "@LLAMA_MODEL@", "meta/Replacement-B")):
            if token in source:
                self.assertNotIn(self.old[name], text, f"{template} still names the old {name} id")
                self.assertIn(new, text, template)


generate(SetModelReachesEveryRenderedTemplateTests,
         [(rel.replace("/", "_").replace(".", "_").replace("-", "_").lower(), rel)
          for rel in SetModelReachesEveryRenderedTemplateTests.INSTALLED],
         lambda self, rel: self.check(rel))


class ElmConfigCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return call(elm_config.main, ["--root", str(self.root), *args])

    def test_value_node_version(self):
        self.assertEqual((0, "v24.0.1\n", ""), self.run_cli("value", "nodeVersion"))

    def test_value_python_version(self):
        self.assertEqual((0, "3.12\n", ""), self.run_cli("value", "pythonVersion"))

    def test_value_python_packages_are_space_separated(self):
        self.assertEqual((0, "numpy scipy\n", ""), self.run_cli("value", "pythonPackages"))

    def test_value_of_a_model_reads_the_state_file(self):
        write(self.root / "agent/model-ids.json", json.dumps({"qwen": "Qwen/S", "llama": "meta/S"}))
        self.assertEqual((0, "meta/S\n", ""), self.run_cli("value", "llama"))

    def test_value_of_an_unknown_key_fails_naming_it(self):
        self.assertEqual("unknown key: nope", self.run_cli("value", "nope")[0])

    def test_init_writes_the_state_from_the_config(self):
        self.assertEqual(0, self.run_cli("init")[0])
        self.assertEqual(CONFIG["models"], json.loads((self.root / "agent/model-ids.json").read_text()))
        self.assertTrue((self.root / "agent/runtime.env").is_file())

    def test_init_keeps_a_state_file_configure_wrote(self):
        write(self.root / "agent/model-ids.json", json.dumps({"qwen": "Qwen/Resolved", "llama": "meta/Config-2"}))
        self.run_cli("init")
        self.assertEqual("Qwen/Resolved", json.loads((self.root / "agent/model-ids.json").read_text())["qwen"])
        self.assertIn("ELM_QWEN_MODEL_ID=Qwen/Resolved", (self.root / "agent/runtime.env").read_text())

    def test_set_model_accepts_only_the_two_slots(self):
        code, _, err = self.run_cli("set-model", "gpt", "x")
        self.assertEqual(2, code)
        self.assertIn("invalid choice: 'gpt'", err)


# --- scripts/check_config.py ---------------------------------------------------

class ValidateTests(unittest.TestCase):
    """check_config.validate(): each JSON Schema keyword pi's schemas use."""


def _validate(self, schema, value, expected):
    problems = []
    check_config.validate(value, schema, schema, "v", problems)
    self.assertEqual(expected, problems)


S_OR_N = {"anyOf": [{"type": "string"}, {"type": "number"}]}
X_PROPS = {"patternProperties": {"^x-": {"type": "string"}}, "additionalProperties": False}
generate(ValidateTests, [
    ("string_accepted", {"type": "string"}, "a", []),
    # bool is an int in Python, never one in JSON
    ("true_is_not_an_integer", {"type": "integer"}, True, ["v: expected integer, not true"]),
    ("false_is_not_a_number", {"type": "number"}, False, ["v: expected number, not false"]),
    ("a_float_is_a_number", {"type": "number"}, 1.5, []),
    ("a_fraction_is_not_an_integer", {"type": "integer"}, 1.5, ["v: expected integer, not 1.5"]),
    # JSON Schema (and pi, in JavaScript) counts 2.0 as an integer
    ("a_whole_float_is_an_integer", {"type": "integer"}, 2.0, []),
    ("type_list_accepts_any_listed", {"type": ["string", "null"]}, None, []),
    ("type_list_names_every_type", {"type": ["string", "null"]}, 3, ["v: expected string or null, not 3"]),
    ("enum_miss", {"enum": ["a", "b"]}, "c", ["v: \"c\" is not one of ['a', 'b']"]),
    ("const_miss", {"const": "x"}, "y", ['v: must be "x", not "y"']),
    ("min_length", {"type": "string", "minLength": 2}, "a", ["v: shorter than 2 characters"]),
    ("pattern_miss", {"pattern": "^#[0-9a-f]{6}$"}, "red", ['v: "red" does not match ^#[0-9a-f]{6}$']),
    # JSON Schema patterns are unanchored
    ("pattern_is_a_search_not_a_full_match", {"pattern": "b"}, "abc", []),
    ("minimum", {"minimum": 0}, -1, ["v: below the minimum 0"]),
    ("maximum", {"maximum": 1}, 2, ["v: above the maximum 1"]),
    ("exclusive_minimum_rejects_equal", {"exclusiveMinimum": 0}, 0, ["v: must be greater than 0"]),
    ("number_bounds_ignore_booleans", {"minimum": 5}, True, []),
    ("max_items", {"maxItems": 1}, [1, 2], ["v: more than 1 items"]),
    ("items_path_has_the_index", {"items": {"type": "string"}}, ["a", 1], ["v[1]: expected string, not 1"]),
    ("required", {"required": ["a", "b"]}, {"a": 1}, ["v: missing required b"]),
    ("unknown_key", {"properties": {"a": {}}, "additionalProperties": False}, {"a": 1, "z": 2}, ["v: unknown key z"]),
    ("additional_properties_schema", {"additionalProperties": {"type": "number"}}, {"k": "s"},
     ['v.k: expected number, not "s"']),
    ("pattern_property_counts_as_known", X_PROPS, {"x-a": "s", "y": 1}, ["v: unknown key y"]),
    ("pattern_property_is_validated", X_PROPS, {"x-a": 2}, ["v.x-a: expected string, not 2"]),
    ("nested_path", {"properties": {"a": {"properties": {"b": {"type": "string"}}}}}, {"a": {"b": 1}},
     ["v.a.b: expected string, not 1"]),
    ("local_ref_resolves", {"$defs": {"s": {"type": "string"}}, "$ref": "#/$defs/s"}, 1,
     ["v: expected string, not 1"]),
    ("external_ref_is_reported", {"$ref": "other.json#/x"}, 1, ["v: cannot resolve $ref other.json#/x"]),
    # a keyword this script does not implement is its own problem, not a pass
    ("unknown_keyword_is_reported", {"oneOf": [{}]}, 1,
     ["v: schema keyword(s) ['oneOf'] not understood by check_config.py"]),
    ("annotations_constrain_nothing", {"title": "t", "description": "d", "default": 1, "deprecated": True,
                                       "$comment": "c", "$id": "x", "$schema": "y"}, 1, []),
    ("false_schema_forbids", {"properties": {"a": False}}, {"a": 1}, ["v.a: not allowed here"]),
    ("true_schema_allows", {"properties": {"a": True}}, {"a": [1]}, []),
    ("any_of_passes_on_one_branch", S_OR_N, 1, []),
    ("any_of_of_types_has_a_generic_message", S_OR_N, None, ["v: null matches none of the allowed forms"]),
    ("long_values_are_truncated", {"type": "string"}, list(range(30)),
     ["v: expected string, not [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11..."]),
    # enum runs before type; a type mismatch then stops the string checks
    ("type_mismatch_stops_later_checks", {"enum": ["abcdef"], "type": "string", "minLength": 9}, 3,
     ["v: 3 is not one of ['abcdef']", "v: expected string, not 3"]),
], _validate)


class SelectedTests(unittest.TestCase):
    """pi's per-package resource filters (cases tests/test_project.py does not cover)."""


generate(SelectedTests, [
    ("plus_prefix_includes", "themes/a.json", ["+themes/a.json"], True),
    ("glob_include_matches", "themes/dark-x.json", ["themes/dark-*.json"], True),
    ("glob_include_misses", "themes/light.json", ["themes/dark-*.json"], False),
    ("exclusion_overrides_inclusion", "themes/dark-x.json", ["themes/dark-*.json", "!themes/dark-x.json"], False),
    # "-" is an exact path, unlike "!"
    ("minus_is_not_a_glob", "themes/a.json", ["-themes/*.json"], True),
], lambda self, rel, filters, expected: self.assertIs(expected, check_config._selected(rel, filters)))


THEME_SCHEMA = {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}},
                "additionalProperties": False}


class CheckConfigFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.schemas = self.root / "schemas"
        write(self.schemas / "models.schema.json", json.dumps({"type": "object", "required": ["providers"]}))
        write(self.schemas / "settings.schema.json", json.dumps({"properties": {"theme": {"type": "string"}}}))
        write(self.schemas / "theme.schema.json", json.dumps(THEME_SCHEMA))
        self.modules = self.root / "agent/npm/node_modules"

    def tearDown(self):
        self.tmp.cleanup()

    def package(self, name, manifest, themes=()):
        write(self.modules / name / "package.json", json.dumps(manifest))
        for rel, value in themes:
            write(self.modules / name / rel, json.dumps(value))

    def settings(self, packages):
        write(self.root / "agent/settings.json", json.dumps({"packages": packages}))

    def test_a_file_that_does_not_parse_says_so(self):
        bad = write(self.root / "models.json", "{ nope")
        problems = check_config.check_file(bad, self.schemas / "models.schema.json")
        self.assertEqual(1, len(problems))
        self.assertTrue(problems[0].startswith("models.json: does not parse ("), problems)

    def test_absent_config_files_are_not_problems(self):
        (self.root / "agent").mkdir()
        self.assertEqual([], check_config.config_problems(self.root / "agent", self.schemas))

    def test_each_file_is_checked_against_its_own_schema(self):
        write(self.root / "agent/models.json", "{}")
        write(self.root / "agent/settings.json", json.dumps({"theme": 3}))
        self.assertEqual(["models.json: missing required providers", "settings.json.theme: expected string, not 3"],
                         check_config.config_problems(self.root / "agent", self.schemas))

    def test_declared_theme_folder_is_listed_in_order(self):
        self.package("t", {"pi": {"themes": ["themes"]}}, [("themes/b.json", {}), ("themes/a.json", {})])
        self.settings(["npm:t"])
        self.assertEqual(["themes/a.json", "themes/b.json"],
                         [p.relative_to(self.modules / "t").as_posix() for p in check_config.theme_files(self.root)])

    def test_package_without_a_pi_manifest_loads_themes_by_convention(self):
        self.package("t", {"name": "t"}, [("themes/a.json", {})])
        self.settings(["npm:t"])
        self.assertEqual(1, len(check_config.theme_files(self.root)))

    def test_pi_manifest_without_themes_loads_none(self):
        self.package("t", {"pi": {"extensions": ["x.js"]}}, [("themes/a.json", {})])
        self.settings(["npm:t"])
        self.assertEqual([], check_config.theme_files(self.root))

    def test_missing_package_is_left_to_verify_install(self):
        self.settings(["npm:absent"])
        self.assertEqual([], check_config.theme_files(self.root))

    def test_theme_problems_name_the_file_and_join_its_problems(self):
        self.package("t", {"pi": {"themes": ["themes"]}},
                     [("themes/bad.json", {"extra": 1}), ("themes/ok.json", {"name": "ok"})])
        self.settings([{"source": "npm:t", "themes": ["!themes/skip.json"]}])
        self.assertEqual(["theme t/themes/bad.json: missing required name; unknown key extra"],
                         check_config.theme_problems(self.root, self.schemas))

    def test_main_without_schemas_fails_and_says_where_it_looked(self):
        code, out, _ = call(check_config.main, ["--root", str(self.root), "--schemas", str(self.root / "none")])
        self.assertEqual(1, code)
        self.assertIn("no pi schemas at", out)


# --- scripts/pin_versions.py ---------------------------------------------------

PI = pin_versions.PI


class PinVersionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.versions = self.dir / "versions.json"
        self.manifest = write(self.dir / "package.json", json.dumps(
            {"name": "x", "dependencies": {PI: "latest", "mupdf": "latest"}}))
        self.dest = self.dir / "staged.json"

    def tearDown(self):
        self.tmp.cleanup()

    def pins(self, core=None, packages=None):
        write(self.versions, json.dumps({"core": core or {}, "packages": packages or {}}))

    def stage(self, section="core", update=False, pi_version=""):
        message = pin_versions.stage(str(self.manifest), str(self.dest), section, str(self.versions), update, pi_version)
        return message, json.loads(self.dest.read_text())

    def test_all_pinned_message(self):
        self.pins({PI: "1.0.0", "mupdf": "2.0.0"})
        self.assertEqual("    versions: all 2 at the tested versions", self.stage()[0])

    def test_partly_pinned_message(self):
        self.pins({"mupdf": "2.0.0"})
        self.assertEqual("    versions: 1 of 2 at the tested versions, the rest latest", self.stage()[0])

    def test_nothing_pinned_message(self):
        self.pins()
        self.assertEqual("    versions: the latest of each", self.stage()[0])

    def test_update_message(self):
        self.pins({PI: "1.0.0"})
        message, data = self.stage(update=True)
        self.assertEqual("    versions: the latest of each, as --update asks", message)
        self.assertEqual("latest", data["dependencies"][PI])

    def test_pi_version_applies_to_the_core_section_only(self):
        self.pins()
        self.assertEqual("latest", self.stage("packages", pi_version="9.9.9")[1]["dependencies"][PI])

    def test_staged_manifest_keeps_its_other_fields_and_ends_in_a_newline(self):
        self.pins({PI: "1.0.0"})
        _, data = self.stage()
        self.assertEqual("x", data["name"])
        self.assertTrue(self.dest.read_text().endswith("}\n"))

    def test_no_versions_file_means_no_pins(self):
        self.assertEqual({}, pin_versions.load_pins(str(self.dir / "absent.json"), "core"))
        self.assertEqual("    versions: the latest of each", self.stage()[0])

    def test_a_section_the_file_lacks_means_no_pins(self):
        write(self.versions, json.dumps({"core": {PI: "1.0.0"}}))
        self.assertEqual({}, pin_versions.load_pins(str(self.versions), "packages"))

    def test_digest_changes_with_the_manifest_bytes(self):
        self.pins({PI: "1.0.0"})
        before = pin_versions.digest(str(self.manifest), "core", str(self.versions))
        self.manifest.write_text(self.manifest.read_text() + "\n")
        self.assertNotEqual(before, pin_versions.digest(str(self.manifest), "core", str(self.versions)))

    def test_digest_ignores_the_order_of_the_pins(self):
        self.pins({PI: "1.0.0", "mupdf": "2.0.0"})
        before = pin_versions.digest(str(self.manifest), "core", str(self.versions))
        write(self.versions, '{"core": {"mupdf": "2.0.0", "%s": "1.0.0"}}' % PI)
        self.assertEqual(before, pin_versions.digest(str(self.manifest), "core", str(self.versions)))

    def test_dev_without_a_pi_pin_leaves_the_siblings(self):
        self.pins({"mupdf": "2.0.0"})
        write(self.manifest, json.dumps({"dependencies": {"mupdf": "latest"},
                                         "devDependencies": {"@earendil-works/pi-ai": "latest"}}))
        data = pin_versions.dev(str(self.manifest), str(self.versions))
        self.assertEqual({"mupdf": "2.0.0"}, data["dependencies"])
        self.assertEqual({"@earendil-works/pi-ai": "latest"}, data["devDependencies"])

    def test_pinned_with_no_versions_file_prints_nothing(self):
        code, out, _ = call(pin_versions.main, ["--versions", str(self.dir / "absent.json"), "pinned", "core", PI])
        self.assertEqual((0, ""), (code, out))


# --- scripts/pypi_index.py -----------------------------------------------------

def row(name, version="1.0", summary="", keywords="", classifiers="", requires_python="", downloads=0,
        uploaded="2020-01-01T00:00:00"):
    return {"name": name, "version": version, "summary": summary, "keywords": keywords,
            "classifiers": classifiers, "requires_python": requires_python,
            "recent_7d_downloads": downloads, "upload_time": uploaded}


SNAPSHOT = [
    row("lmfit", "1.3.0", "Least-squares minimization with bounds, curve fitting", "fitting",
        ["Topic :: Scientific/Engineering :: Physics"], ">=3.9", 500000, "2025-05-01T10:00:00"),
    row("lmfit", "1.2.0", "old summary", uploaded="2024-01-01T00:00:00"),
    row("curve-fitting", "0.1", "curve fitting", downloads=0, uploaded="2023-01-01T00:00:00"),
    row("Py_HDF", "2.0", "hdf5 and netcdf readers", downloads=10, uploaded="2025-06-30T23:59:59"),
    row("py-hdf", "1.0", "older spelling", uploaded="2020-01-01T00:00:00"),
    row("   ", "9.9", "blank name"),
    row(None, "9.9", "no name"),
    row("netcdf-only", "0.3", "  netcdf files  ", classifiers=("A", "B"), downloads=None),
    row("spectro", "0.2", "spectral line analysis " + "x" * 300, keywords="spectroscopy", downloads=10),
]


class PypiIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.db = cls.dir / "pypi-index.db"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            pypi_index.write(iter(SNAPSHOT), cls.db, "demo/dataset", "rev123")
        cls.build_output = out.getvalue()
        con = sqlite3.connect(cls.db)
        cls.meta = dict(con.execute("SELECT key, value FROM meta"))
        cls.rows = {r[0]: r for r in con.execute(
            "SELECT name, summary, keywords, classifiers, version, requires_python, downloads, uploaded FROM pkg")}
        con.close()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def search(self, *terms, all_terms=False, limit=20, db=None):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = pypi_index.search(list(terms), all_terms, limit, db or self.db)
        return code, out.getvalue(), err.getvalue()

    def names(self, *terms, **kw):
        out = self.search(*terms, **kw)[1]
        return [line.split(" ")[0] for line in out.splitlines() if line and not line.startswith((" ", "[", "no match"))]

    # --- build
    def test_one_row_per_package_after_normalising_names(self):
        self.assertEqual({"lmfit", "curve-fitting", "Py_HDF", "netcdf-only", "spectro"}, set(self.rows))
        self.assertEqual("5", self.meta["packages"])

    def test_latest_upload_wins(self):
        self.assertEqual("1.3.0", self.rows["lmfit"][4])

    def test_names_differing_in_case_and_separators_are_one_package(self):
        # py-hdf normalises to the same key as Py_HDF; the newer row and its spelling stay
        self.assertEqual(("Py_HDF", "2.0"), (self.rows["Py_HDF"][0], self.rows["Py_HDF"][4]))

    def test_snapshot_date_is_the_newest_upload(self):
        self.assertEqual("2025-06-30", self.meta["snapshot"])

    def test_dataset_and_revision_are_recorded(self):
        self.assertEqual(("demo/dataset", "rev123"), (self.meta["dataset"], self.meta["revision"]))

    def test_classifier_lists_and_tuples_are_joined(self):
        self.assertEqual("Topic :: Scientific/Engineering :: Physics", self.rows["lmfit"][3])
        self.assertEqual("A; B", self.rows["netcdf-only"][3])

    def test_missing_downloads_count_as_zero(self):
        self.assertEqual(0, self.rows["netcdf-only"][6])

    def test_build_reports_its_size_and_leaves_no_temp_file(self):
        self.assertEqual("    5 packages, newest upload 2025-06-30, 0 MB\n", self.build_output)
        self.assertFalse((self.dir / "pypi-index.db.tmp").exists())

    def test_a_rebuild_replaces_the_index(self):
        db = self.dir / "rebuilt.db"
        with contextlib.redirect_stdout(io.StringIO()):
            pypi_index.write(iter(SNAPSHOT), db, "d", "r1")
            pypi_index.write(iter([row("only-one")]), db, "d", "r2")
        con = sqlite3.connect(db)
        self.assertEqual([("only-one",)], con.execute("SELECT name FROM pkg").fetchall())
        self.assertEqual("r2", dict(con.execute("SELECT key, value FROM meta"))["revision"])
        con.close()

    # --- search
    def test_no_index_is_an_error_that_says_how_to_build_one(self):
        code, _, err = self.search("x", db=self.dir / "absent.db")
        self.assertEqual(1, code)
        self.assertIn("--with-pypi-index", err)

    def test_no_words_is_a_usage_error(self):
        code, _, err = self.search("!!", "--")
        self.assertEqual(2, code)
        self.assertIn("give some words to search for", err)

    def test_any_word_matches_by_default(self):
        self.assertEqual({"spectro", "netcdf-only", "Py_HDF"}, set(self.names("spectral", "netcdf")))

    def test_all_requires_every_word(self):
        self.assertEqual(["Py_HDF"], self.names("hdf5", "netcdf", all_terms=True))

    def test_popularity_lifts_a_used_package_over_a_name_match(self):
        # curve-fitting matches on its name; lmfit has 500k downloads a week
        self.assertEqual(["lmfit", "curve-fitting"], self.names("curve", "fitting"))

    def test_porter_stemming_matches_word_forms(self):
        self.assertIn("lmfit", self.names("fits"))

    def test_classifiers_are_searched(self):
        self.assertEqual(["lmfit"], self.names("physics"))

    def test_limit(self):
        self.assertEqual(["lmfit"], self.names("curve", "fitting", limit=1))

    def test_fts_syntax_in_a_request_is_plain_text(self):
        code, out, _ = self.search('netcdf"', "NOT", "OR(", "NEAR*")
        self.assertEqual(0, code)
        self.assertIn("netcdf-only 0.3", out)

    def test_result_lines_carry_version_downloads_and_python(self):
        out = self.search("physics")[1]
        self.assertEqual("lmfit 1.3.0 (500,000 downloads/7d, Python >=3.9)\n"
                         "    Least-squares minimization with bounds, curve fitting", "\n".join(out.splitlines()[:2]))

    def test_summary_is_stripped_and_cut_at_200_characters(self):
        lines = self.search("netcdf", all_terms=True)[1].splitlines()
        self.assertIn("    netcdf files", lines)
        summary = self.search("spectroscopy")[1].splitlines()[1]
        self.assertEqual(4 + 200, len(summary))

    def test_no_match_says_so_and_suggests_dropping_all(self):
        out = self.search("zzzz", "qqqq", all_terms=True)[1]
        self.assertTrue(out.startswith('no match for "zzzz" "qqqq" - try without --all\n'), out)

    def test_footer_states_the_snapshot(self):
        out = self.search("physics")[1]
        self.assertIn("[snapshot of 5 packages, uploads up to 2025-06-30:", out)

    def test_a_file_that_is_not_an_index_is_an_error(self):
        for name, content in (("garbage.db", "not sqlite at all " * 100), ("empty.db", "")):
            path = write(self.dir / name, content)
            code, _, err = self.search("x", db=path)
            self.assertEqual(1, code, name)
            self.assertIn("is not a usable index", err, name)

    # rows[:-1] would print every match but the last
    def test_a_negative_limit_is_refused(self):
        code, out, _ = self.search("curve", "fitting", limit=-1)
        self.assertNotEqual(0, code)


class PypiSearchWrapperTests(unittest.TestCase):
    """scripts/pypi-search: follows its agent/bin symlink and picks the Python."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.here = Path(self.tmp.name) / "install"
        for name in ("pypi-search", "pypi_index.py"):
            write(self.here / "scripts" / name, (SCRIPTS / name).read_text(), 0o755)
        (self.here / "agent/bin").mkdir(parents=True)
        os.symlink("../../scripts/pypi-search", self.here / "agent/bin/pypi-search")
        self.db = self.here / "agent/pypi-index.db"
        with contextlib.redirect_stdout(io.StringIO()):
            pypi_index.write(iter(SNAPSHOT), self.db, "d", "r")

    def tearDown(self):
        self.tmp.cleanup()

    def run_link(self, *args):
        return subprocess.run([str(self.here / "agent/bin/pypi-search"), *args], capture_output=True, text=True,
                              env={"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin", "HOME": self.tmp.name})

    def test_through_the_symlink_with_the_recorded_python(self):
        write(self.here / "agent/python-path", sys.executable + "\n")
        r = self.run_link("--db", str(self.db), "-n", "1", "curve", "fitting")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertTrue(r.stdout.startswith("lmfit 1.3.0 "), r.stdout)

    def test_the_agents_own_python_is_preferred(self):
        write(self.here / "agent/python-path", sys.executable + "\n")
        write(self.here / "agent/python/env/bin/python", '#!/bin/sh\necho "AGENT-PY $*"\n', 0o755)
        r = self.run_link("--all", "x")
        self.assertEqual(f"AGENT-PY -I {self.here}/scripts/pypi_index.py search --all x\n", r.stdout)

    def test_the_default_index_is_the_installs_own(self):
        write(self.here / "agent/python-path", sys.executable + "\n")
        r = self.run_link("physics")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("lmfit 1.3.0", r.stdout)


class CondaSearchTests(unittest.TestCase):
    """scripts/conda-search with a stub curl: argument handling and output."""

    @classmethod
    def setUpClass(cls):
        cls.jq = shutil.which("jq", path="/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin") or shutil.which("jq")
        if not cls.jq:
            raise unittest.SkipTest("jq is not installed")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.body = self.dir / "body.json"
        self.reply = self.dir / "reply.json"
        # Records the -d payload; answers with reply.json, or fails like curl -f
        write(self.dir / "bin/curl", f"""#!/bin/sh
while [ $# -gt 0 ]; do [ "$1" = "-d" ] && printf '%s' "$2" > "{self.body}"; shift; done
[ -f "{self.reply}" ] || exit 22
cat "{self.reply}"
""", 0o755)
        os.symlink(self.jq, self.dir / "bin/jq")

    def tearDown(self):
        self.tmp.cleanup()

    def run_search(self, *args, reply=None, path=None):
        if reply is not None:
            self.reply.write_text(json.dumps(reply))
        return subprocess.run([str(SCRIPTS / "conda-search"), *args], capture_output=True, text=True,
                              env={"PATH": path or f"{self.dir / 'bin'}:/usr/bin:/bin"})

    @staticmethod
    def page(*packages):
        return {"data": {"channel": {"packages": {"page": list(packages)}}}}

    def sent(self):
        return json.loads(self.body.read_text())["variables"]

    def test_no_term_is_a_usage_error(self):
        r = self.run_search()
        self.assertEqual(2, r.returncode)
        self.assertIn("usage: conda-search [-n N] NAME-FRAGMENT", r.stderr)

    def test_a_limit_that_is_not_a_number_is_refused(self):
        r = self.run_search("-n", "ten", "hdf5")
        self.assertEqual((2, "conda-search: -n takes a number\n"), (r.returncode, r.stderr))
        self.assertFalse(self.body.exists())   # nothing was asked

    def test_a_limit_with_no_value_is_refused(self):
        r = self.run_search("-n")
        self.assertNotEqual(0, r.returncode)
        self.assertIn("-n needs a number", r.stderr)

    def test_default_limit_and_a_multi_word_term(self):
        r = self.run_search("net", "cdf", reply=self.page())
        self.assertEqual({"t": "net cdf", "n": 15}, self.sent())
        self.assertIn('no conda-forge package name contains "net cdf"', r.stdout)

    def test_limit_is_sent_as_a_number_and_quotes_as_text(self):
        self.run_search("-n", "30", 'a"b $HOME', reply=self.page())
        self.assertEqual({"t": 'a"b $HOME', "n": 30}, self.sent())

    def test_results_are_name_version_and_a_one_line_summary(self):
        r = self.run_search("hdf5", reply=self.page(
            {"name": "hdf5", "summary": "HDF5\n  library\tfiles", "latestVersion": {"version": "1.14.6"}},
            {"name": "h5py", "summary": None, "latestVersion": None}))
        self.assertEqual(0, r.returncode, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(["hdf5 1.14.6", "    HDF5 library files", "h5py ?", "    "], lines[:4])
        self.assertTrue(lines[-1].startswith("[conda-forge, by name."), lines[-1])

    def test_long_summaries_are_cut_at_200_characters(self):
        r = self.run_search("x", reply=self.page({"name": "x", "summary": "y" * 500, "latestVersion": {"version": "1"}}))
        self.assertEqual("    " + "y" * 200, r.stdout.splitlines()[1])

    def test_graphql_errors_fail_with_their_message(self):
        r = self.run_search("x", reply={"errors": [{"message": "rate limited"}]})
        self.assertEqual((1, "rate limited\n"), (r.returncode, r.stderr))

    def test_no_answer_points_at_the_egress_log(self):
        r = self.run_search("x")
        self.assertEqual(1, r.returncode)
        self.assertIn("prefix.dev did not answer (check agent/egress.log)", r.stderr)

    def test_without_jq_it_says_so(self):
        only_bash = self.dir / "only-bash"
        only_bash.mkdir()
        os.symlink(shutil.which("bash"), only_bash / "bash")
        r = self.run_search("x", path=str(only_bash))
        self.assertEqual(1, r.returncode)
        self.assertIn("conda-search: needs jq", r.stderr)


# --- scripts/verify_install.py -------------------------------------------------

class VerifyInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.modules = self.root / "agent/npm/node_modules"

    def tearDown(self):
        self.tmp.cleanup()

    def package(self, name, manifest_text, files=()):
        write(self.modules / name / "package.json", manifest_text)
        for rel in files:
            write(self.modules / name / rel, "\n")
        write(self.root / "agent/settings.json", json.dumps({"packages": [f"npm:{name}"]}))

    def test_a_glob_entry_with_a_match_is_present(self):
        self.package("demo", json.dumps({"pi": {"extensions": ["./extensions/*.ts"]}}), ["extensions/a.ts"])
        self.assertEqual([], verify_install.package_problems(self.root))

    def test_a_glob_entry_with_no_match_is_missing(self):
        self.package("demo", json.dumps({"pi": {"extensions": ["./extensions/*.ts"]}}))
        self.assertEqual(["package demo: declared extension ./extensions/*.ts is missing"],
                         verify_install.package_problems(self.root))

    def test_a_package_json_that_does_not_parse(self):
        self.package("demo", "{ nope")
        problems = verify_install.package_problems(self.root)
        self.assertEqual(1, len(problems))
        self.assertTrue(problems[0].startswith("package demo: package.json does not parse ("), problems)

    def test_no_pi_manifest_is_loaded_by_convention(self):
        self.package("demo", json.dumps({"name": "demo"}))
        self.assertEqual([], verify_install.package_problems(self.root))

    def test_a_pi_field_that_is_not_an_object_is_not_checked(self):
        self.package("demo", json.dumps({"pi": ["extensions"]}))
        self.assertEqual([], verify_install.package_problems(self.root))

    def test_a_scoped_package_in_object_form(self):
        write(self.root / "agent/settings.json", json.dumps({"packages": [{"source": "npm:@s/p", "themes": []}]}))
        problems = verify_install.package_problems(self.root)
        self.assertEqual([f"package @s/p: not installed ({self.modules / '@s/p'})"], problems)

    def test_a_source_without_the_npm_prefix_is_used_as_is(self):
        write(self.root / "agent/settings.json", json.dumps({"packages": ["plain"]}))
        self.assertEqual([f"package plain: not installed ({self.modules / 'plain'})"],
                         verify_install.package_problems(self.root))

    def test_last_flags_line_is_the_record(self):
        write(self.root / "agent/install-options", "# made by bootstrap\nflags=--no-tools\nflags=--no-shim --no-tools\n")
        self.assertEqual(["--no-shim", "--no-tools"], verify_install.install_flags(self.root))

    def test_no_record_means_no_flags(self):
        self.assertEqual([], verify_install.install_flags(self.root))

    def extensions_root(self, required, present, flags=None):
        write(self.root / "config/elm-pi.json", json.dumps({"requiredExtensions": required}))
        for name in present:
            write(self.root / "agent/extensions" / name, "\n")
        if flags is not None:
            write(self.root / "agent/install-options", f"flags={flags}\n")
        return verify_install.extension_problems(self.root)

    def test_every_missing_extension_is_listed_in_config_order(self):
        self.assertEqual(["required extension b.ts is missing from agent/extensions",
                          "required extension a.ts is missing from agent/extensions"],
                         self.extensions_root(["b.ts", "c.ts", "a.ts"], ["c.ts"]))

    def test_no_shim_excuses_only_the_shim(self):
        self.assertEqual(["required extension todo.ts is missing from agent/extensions"],
                         self.extensions_root(["elm-shim.ts", "todo.ts"], [], flags="--no-shim"))

    def test_a_directory_is_not_an_extension_file(self):
        (self.root / "agent/extensions/a.ts").mkdir(parents=True)
        self.assertEqual(["required extension a.ts is missing from agent/extensions"],
                         self.extensions_root(["a.ts"], []))

    def skills(self, managed, files):
        for name, text in files.items():
            write(self.root / "agent/skills" / name / "SKILL.md", text)
        if managed is not None:
            write(self.root / "agent/skills/.elm-pi-managed", "\n".join(managed) + "\n")
        return verify_install.skill_problems(self.root)

    def test_no_manifest_checks_no_skills(self):
        self.assertEqual([], self.skills(None, {"x": "no frontmatter"}))

    def test_a_managed_skill_without_its_file(self):
        self.assertEqual(["skill gone: SKILL.md is missing"], self.skills(["gone"], {}))

    def test_a_name_that_does_not_match_the_directory(self):
        self.assertEqual(["skill a: frontmatter name 'b' does not match its directory"],
                         self.skills(["a"], {"a": "---\nname: b\ndescription: d\n---\n"}))

    def test_an_empty_description(self):
        self.assertEqual(["skill a: frontmatter does not parse or has no description"],
                         self.skills(["a"], {"a": "---\nname: a\ndescription:\n---\n"}))

    def test_skills_someone_added_are_not_checked(self):
        self.assertEqual([], self.skills(["a"], {"a": "---\nname: a\ndescription: d\n---\n", "mine": "broken"}))

    def test_packages_only_skips_extensions_and_skills(self):
        write(self.root / "agent/settings.json", json.dumps({"packages": []}))
        self.extensions_root(["a.ts"], [])
        self.assertEqual((0, "", ""), call(verify_install.main, ["--root", str(self.root), "--packages-only"]))
        self.assertEqual((1, "    required extension a.ts is missing from agent/extensions\n", ""),
                         call(verify_install.main, ["--root", str(self.root)]))


class FrontmatterTests(unittest.TestCase):
    """verify_install.frontmatter(): the two fields, read the way pi's YAML parser would."""


def _frontmatter(self, text, expected):
    self.assertEqual(expected, verify_install.frontmatter(text))


generate(FrontmatterTests, [
    ("quoted_value_may_hold_a_colon", '---\nname: a\ndescription: "x: y"\n---\nbody', {"name": "a", "description": "x: y"}),
    ("quoted_value_with_escapes", '---\nname: a\ndescription: "say \\"hi\\""\n---\n', {"name": "a", "description": 'say "hi"'}),
    ("broken_quotes_do_not_parse", '---\nname: a\ndescription: "open\n---\n', None),
    ("colon_without_a_space_is_plain_text", "---\nname: a\ndescription: ratio 1:2\n---\n",
     {"name": "a", "description": "ratio 1:2"}),
    ("unquoted_colon_space_in_the_name", "---\nname: a: b\ndescription: d\n---\n", None),
    ("surrounding_spaces_are_stripped", "---\nname:   a  \ndescription:  d \n---\n", {"name": "a", "description": "d"}),
    ("no_frontmatter", "# just a heading\n", None),
    ("frontmatter_must_open_the_file", "\n---\nname: a\ndescription: d\n---\n", None),
    ("other_keys_are_not_returned", "---\nname: a\nlicense: MIT\ndescription: d\n---\n", {"name": "a", "description": "d"}),
    # an unquoted ": " in any other key is a YAML error that makes pi drop the skill
    ("a_yaml_error_in_another_key_does_not_parse", "---\nname: a\ndescription: d\nlicense: x: y\n---\n", None),
    # pi normalises CRLF before parsing
    ("crlf_line_endings", "---\r\nname: a\r\ndescription: d\r\n---\r\n", {"name": "a", "description": "d"}),
    # a single-quoted YAML scalar is valid
    ("single_quoted_value", "---\nname: a\ndescription: 'a: b'\n---\n", {"name": "a", "description": "a: b"}),
    # the forms below parse as pi's yaml package parses them
    ("folded_block_description", "---\nname: a\ndescription: >-\n  one\n  two\n---\n", {"name": "a", "description": "one two"}),
    ("plain_value_over_two_lines", "---\nname: a\ndescription: one\n  two\n---\n", {"name": "a", "description": "one two"}),
    ("comment_after_a_plain_value", "---\nname: a\ndescription: d # note\n---\n", {"name": "a", "description": "d"}),
    ("list_and_mapping_under_other_keys", "---\nname: a\ndescription: d\ntools:\n- x\nmetadata:\n  k: v\n---\n",
     {"name": "a", "description": "d"}),
    ("a_yaml_error_in_a_nested_mapping", "---\nname: a\ndescription: d\nmetadata:\n  k: x: y\n---\n", None),
    ("a_duplicate_key_does_not_parse", "---\nname: a\ndescription: d\nname: b\n---\n", None),
    ("a_description_that_is_not_text_is_left_out", "---\nname: a\ndescription: true\n---\n", {"name": "a"}),
], _frontmatter)


# --- patch-pi.py ---------------------------------------------------------------

def _sample(anchor):
    """Bundle text that an edit's anchor matches: the anchor itself, or for the
    two list entries a description of the shape pi ships."""
    if isinstance(anchor, str):
        return anchor
    if "argumentHint" in anchor.pattern:
        return '{name:"bug",description:"Report a bug",argumentHint:"[hint]"},'
    return '{name:"share",description:"Share the session"},'


EDITS = {name: (anchor, replacement, sentinel) for name, anchor, replacement, sentinel in patch_pi.EDITS}
SAMPLES = {name: _sample(anchor) for name, (anchor, _, _) in EDITS.items()}
DELETIONS = {name for name, (_, replacement, _) in EDITS.items() if not replacement}


def slug(name):
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_").replace("__", "_")


class PatchPiTests(unittest.TestCase):
    """patch-pi.py on a synthetic bundle laid out like pi's: hash-named chunks,
    a subdirectory, and files the patch has no business touching."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bundle = Path(self.tmp.name) / "bundle"
        self.build()

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, samples=None):
        samples = dict(SAMPLES if samples is None else samples)
        names = list(EDITS)
        ui = "".join(samples.get(n, "") for n in names[:2])
        listing = "[" + "".join(samples.get(n, "") for n in names[2:4]) + '{name:"copy"}]'
        uploads = "".join(samples.get(n, "") + "}" for n in names[4:] if samples.get(n))
        write(self.bundle / "chunk-3fa9.js", f"export const ui=1;{ui};const cmds={listing};\n")
        write(self.bundle / "sub/chunk-77c1.js", uploads + "\n")
        write(self.bundle / "unrelated-0b2e.js", "export const x = 1;\n")

    def snapshot(self):
        return {p.relative_to(self.bundle).as_posix(): p.read_bytes() for p in sorted(self.bundle.rglob("*"))
                if p.is_file()}

    def run_patch(self, *args):
        return call(patch_pi.main, ["--bundle", str(self.bundle), *args])

    def text(self):
        return "".join(b.decode("utf-8", "surrogateescape") for b in self.snapshot().values())

    def test_apply_reports_seven_edits(self):
        self.assertEqual((0, "    disabled /share and /bug (7 edits applied)\n", ""), self.run_patch())

    def test_second_run_is_a_byte_identical_no_op(self):
        self.run_patch()
        before = self.snapshot()
        self.assertEqual((0, "    /share and /bug already disabled (7 edits in place)\n", ""), self.run_patch())
        self.assertEqual(before, self.snapshot())

    def test_check_on_an_unpatched_bundle_lists_every_edit_and_writes_nothing(self):
        before = self.snapshot()
        code, _, err = self.run_patch("--check")
        self.assertEqual(1, code)
        for name in EDITS:
            self.assertIn(f"    {name}: not applied\n", err)
        self.assertEqual(before, self.snapshot())

    def test_check_after_apply_passes_and_writes_nothing(self):
        self.run_patch()
        before = self.snapshot()
        self.assertEqual((0, "    /share and /bug are disabled (7 edits in place)\n", ""), self.run_patch("--check"))
        self.assertEqual(before, self.snapshot())

    def test_a_partly_patched_bundle_gets_the_rest(self):
        patched = dict(SAMPLES)
        for name in list(EDITS)[4:]:
            patched[name] = EDITS[name][1]
        self.build(patched)
        self.assertEqual((0, "    disabled /share and /bug (4 edits applied)\n", ""), self.run_patch())

    def test_a_file_with_no_anchor_is_not_rewritten(self):
        quiet = self.bundle / "unrelated-0b2e.js"
        os.utime(quiet, (1_000_000_000, 1_000_000_000))
        self.run_patch()
        self.assertEqual(1_000_000_000, int(quiet.stat().st_mtime))

    def test_other_entries_in_the_command_list_survive(self):
        self.run_patch()
        self.assertIn('const cmds=[{name:"copy"}];', (self.bundle / "chunk-3fa9.js").read_text())

    def test_bytes_that_are_not_utf8_survive_the_round_trip(self):
        chunk = self.bundle / "chunk-3fa9.js"
        chunk.write_bytes(b"/*\xff\xfe*/" + chunk.read_bytes())
        self.run_patch()
        self.assertTrue(chunk.read_bytes().startswith(b"/*\xff\xfe*/"))

    def test_only_js_files_are_scanned(self):
        # a .map file repeats the source; matching it would count every anchor twice
        write(self.bundle / "chunk-3fa9.js.map", self.text())
        self.assertEqual(0, self.run_patch()[0])

    def test_bundle_option_needs_a_path(self):
        self.assertEqual((2, "", "patch-pi: --bundle requires a path\n"), call(patch_pi.main, ["--bundle"]))

    def test_unknown_options_are_refused(self):
        self.assertEqual((2, "", "patch-pi: unknown option: --force\n"), call(patch_pi.main, ["--force"]))

    def test_a_bundle_that_is_not_there(self):
        code, _, err = call(patch_pi.main, ["--bundle", str(self.bundle / "absent")])
        self.assertEqual(1, code)
        self.assertIn("patch-pi: no pi install at", err)

    def test_the_refusal_points_at_a_file_that_exists(self):
        self.assertIn("See LOCKDOWN.md.", patch_pi.REFUSAL)
        self.assertTrue((ROOT / "LOCKDOWN.md").is_file())


def _missing_anchor(self, name):
    """An anchor that has gone is a hard error, and nothing is written."""
    samples = dict(SAMPLES)
    if name in DELETIONS:
        # the entry reworded into a shape the pattern does not match: the
        # command is still there, so it must not read as "already removed"
        samples[name] = '{name:"share",hidden:true},' if "share" in name else '{name:"bug",hidden:true},'
        message = f"    {name}: anchor absent but {EDITS[name][2]} is still in the bundle"
    else:
        samples[name] = "/* moved in a new release */"
        message = f"    {name}: anchor not found and no patched form present\n"
    self.build(samples)
    before = self.snapshot()
    code, out, err = self.run_patch()
    self.assertEqual(1, code)
    self.assertIn(message, err)
    self.assertIn("patch-pi: FAILED", err)
    self.assertEqual(before, self.snapshot())   # the six good edits were not applied either


def _duplicate_anchor(self, name):
    samples = dict(SAMPLES)
    samples[name] = SAMPLES[name] * 2
    self.build(samples)
    code, _, err = self.run_patch()
    self.assertEqual(1, code)
    self.assertIn(f"    {name}: anchor matched 2 times, expected 1\n", err)


def _applied(self, name):
    self.run_patch()
    text = self.text()
    anchor, replacement, _ = EDITS[name]
    if replacement:
        self.assertEqual(1, text.count(replacement))
        if replacement.startswith(SAMPLES[name]):
            # the throw is inserted after the function opens: still one copy
            self.assertEqual(1, text.count(SAMPLES[name]))
        else:
            self.assertNotIn(SAMPLES[name], text)
    else:
        self.assertNotIn(SAMPLES[name], text)
        self.assertNotIn(EDITS[name][2], text)


for _name in EDITS:
    generate(PatchPiTests, [(f"missing_anchor_fails_{slug(_name)}", _name)], _missing_anchor)
    generate(PatchPiTests, [(f"duplicate_anchor_fails_{slug(_name)}", _name)], _duplicate_anchor)
    generate(PatchPiTests, [(f"applied_{slug(_name)}", _name)], _applied)


if __name__ == "__main__":
    unittest.main()
