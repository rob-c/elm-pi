"""bootstrap.sh's internals, cut out block by block and run against throwaway
installs.

Proves: the installer-owned merge (each OWNED key reapplied from templates/,
every other key kept - edited, removed, nested, malformed and missing files -
and, as a property over random edits, idempotent and never losing a key the repo
does not own); the models.json rules (Qwen's three per-model keys, stray Llama
entries); the hashline and workflow settings; the package list and its theme
filter; the agent/ refresh (required extensions and --no-shim, agent
definitions, reference, skills and their manifest, install_if_absent, links,
the auth lock); install_tool's download, cache and checksum rules; the Node
download; when pi and the packages are rebuilt; the rollback trap; the agent's
Python and PyPI index branches; the version record and the tool-exclusion checks.

Each block is taken from bootstrap.sh between anchor strings, so these follow the
script as it changes. Python heredocs run in one interpreter per class, bash
blocks in one bash per class (a subshell per case). Nothing is downloaded:
curl, uv and the config renderer are stubs, and every write is under a
temporary directory.
"""

import ast
import hashlib
import io
import json
import os
import random
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from collections import OrderedDict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = (ROOT / "bootstrap.sh").read_text()
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")
PY = sys.executable
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
# Not the ids in config/elm-pi.json, so a merge that read those instead of
# agent/model-ids.json (what configure.sh writes) would show.
MODEL_IDS = {"qwen": "Qwen/Qwen-Test-397B", "llama": "meta-llama/Llama-Test-70B"}


def block(text, start, end):
    if text.count(start) != 1:
        raise AssertionError(f"anchor is not unique: {start!r}")
    i = text.index(start)
    return text[i:text.index(end, i)]


def heredoc(text, opener):
    """The body of the one heredoc opened by `opener` (which ends <<'TAG'\\n)."""
    if text.count(opener) != 1:
        raise AssertionError(f"heredoc opener is not unique: {opener!r}")
    tag = re.search(r"<<'(\w+)'", opener).group(1)
    i = text.index(opener) + len(opener)
    return text[i:text.index(f"\n{tag}\n", i) + 1]


def slug(text):
    return re.sub(r"\W+", "_", text).strip("_").lower()


def q(value):
    return shlex.quote(str(value))


def touch(path, text="", mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    path.chmod(mode)
    return path


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def brief(value):
    # bootstrap.sh's report format: the JSON, cut to 57 characters and "..."
    # past 60.
    text = json.dumps(value)
    return text if len(text) <= 60 else text[:57] + "..."


class Case:
    def __init__(self, name, bug=None, **kw):
        self.name, self.bug, self.kw = name, bug, kw


C = Case


def generate(cls):
    names = set()
    for case in cls.CASES:
        name = "test_" + slug(case.name)
        if name in names or hasattr(cls, name):
            raise ValueError(f"duplicate case {name} in {cls.__name__}")
        names.add(name)

        def test(self, case=case):
            skip = case.kw.get("skip")
            if skip:
                raise unittest.SkipTest(skip)
            r = type(self).results[case.name]
            case.kw["check"](self, r, type(self).dirs[case.name])
        test.__name__ = name
        if case.bug:
            test = unittest.expectedFailure(test)
        setattr(cls, name, test)
    return cls


def cleanup_tree(path):
    for root, dirs, _ in os.walk(path):   # a case may leave a folder read-only
        for d in dirs:
            try:
                os.chmod(os.path.join(root, d), 0o700)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


# --- running Python heredocs ----------------------------------------------------------
# One interpreter for every job of a class: each job is one run of a block, in
# its install directory, with its environment and argv, the way elm_py runs it
# (-E -S). After each run the files a case asks about are read back, so a
# second run can be compared with the first.

DRIVER = r'''
import contextlib, io, json, os, sys
jobs_path, out_path = sys.argv[1], sys.argv[2]
jobs = json.load(open(jobs_path))
results = []
base_env = dict(os.environ)
for job in jobs:
    os.chdir(job["cwd"])
    os.environ.clear(); os.environ.update(base_env); os.environ.update(job.get("env", {}))
    sys.argv = ["-"] + job.get("argv", [])
    out = io.StringIO(); rc = 0; error = None
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(job["code"], "<bootstrap.sh>", "exec"), {"__name__": "__main__"})
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception as e:
        rc = "raised"; error = type(e).__name__
    snap = {}
    for rel in job.get("snap", []):
        p = os.path.join(job["cwd"], rel)
        snap[rel] = open(p).read() if os.path.isfile(p) else None
    results.append({"rc": rc, "out": out.getvalue(), "error": error, "snap": snap})
json.dump(results, open(out_path, "w"))
'''


class PyRun:
    def __init__(self, raw):
        self.rc, self.out, self.error, self.snap = raw["rc"], raw["out"], raw["error"], raw["snap"]


class PyBatch(unittest.TestCase):
    """Runs every case's jobs in one Python process; one test method per case."""

    CODE = ""
    CASES = ()
    SNAP = ()

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            jobs, owners = [], []
            cls.dirs = {}
            for i, case in enumerate(cls.CASES):
                d = cls.tmp / f"c{i}"
                d.mkdir()
                cls.dirs[case.name] = d
                cls.prepare(case, d)
                for job in cls.jobs(case, d):
                    jobs.append(job)
                    owners.append(case.name)
            (cls.tmp / "jobs.json").write_text(json.dumps(jobs))
            done = subprocess.run([PY, "-E", "-S", "-c", DRIVER, str(cls.tmp / "jobs.json"), str(cls.tmp / "out.json")],
                                  capture_output=True, text=True, timeout=120,
                                  env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"})
            if done.returncode != 0:
                raise AssertionError(f"the block driver failed:\n{done.stderr}")
            raw = json.loads((cls.tmp / "out.json").read_text())
            cls.results = {c.name: [] for c in cls.CASES}
            for owner, result in zip(owners, raw):
                cls.results[owner].append(PyRun(result))
        except BaseException:
            cleanup_tree(cls.tmp)
            raise

    @classmethod
    def tearDownClass(cls):
        cleanup_tree(cls.tmp)

    @classmethod
    def prepare(cls, case, d):
        pass

    @classmethod
    def jobs(cls, case, d):
        job = {"code": cls.CODE, "cwd": str(d), "env": {"HERE": str(d)}, "argv": [str(d)],
               "snap": list(cls.SNAP)}
        return [job] * case.kw.get("runs", 1)


# --- running bash blocks ---------------------------------------------------------------
# One bash for a class, one subshell per case, each with its own install
# directory; groups of cases run side by side.

DUMP = r'''
_v() { local _n _s _x; for _n in "$@"; do eval "_s=\${$_n+x}"
  if [ -n "$_s" ]; then eval "_x=\${$_n}"; printf '@@%s=%s\n' "$_n" "$_x"; else printf '@@%s\n' "$_n"; fi; done; }
'''


class ShRun:
    def __init__(self, rc, out, err):
        self.rc, self.out, self.err = rc, out, err
        self.vars = {}
        for line in out.splitlines():
            if line.startswith("@@"):
                key, sep, value = line[2:].partition("=")
                self.vars[key] = value if sep else None


def run_sh_batch(prelude, bodies, env, tmp, parallel=8):
    parts = ['T="$1"', DUMP, prelude]
    for i, body in enumerate(bodies):
        parts.append(f'(\n{body}\n) >"$T/.r{i}.out" 2>"$T/.r{i}.err" </dev/null &\n'
                     f'_pids="${{_pids:-}} $!:{i}"')
        if (i + 1) % parallel == 0 or i == len(bodies) - 1:
            parts.append('for _p in $_pids; do wait "${_p%%:*}"; echo $? >"$T/.r${_p##*:}.rc"; done; _pids=""')
    subprocess.run([BASH, "-c", "\n".join(parts), "batch", str(tmp)], env=env, cwd=str(tmp),
                   check=True, capture_output=True, text=True, timeout=300)
    return [ShRun(int((tmp / f".r{i}.rc").read_text()), (tmp / f".r{i}.out").read_text(),
                  (tmp / f".r{i}.err").read_text()) for i in range(len(bodies))]


class ShBatch(unittest.TestCase):
    CASES = ()

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            cls.dirs = {}
            cls.shared(cls.tmp / "shared")
            for i, case in enumerate(cls.CASES):
                d = cls.tmp / f"c{i}"
                d.mkdir()
                cls.dirs[case.name] = d
                cls.prepare(case, d)
            env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(cls.tmp / "home"), "LANG": "C",
                   "TMPDIR": str(cls.tmp)}
            (cls.tmp / "home").mkdir()
            bodies = [cls.body(case, cls.dirs[case.name]) for case in cls.CASES]
            runs = run_sh_batch(cls.prelude(), bodies, env, cls.tmp)
            cls.results = {c.name: r for c, r in zip(cls.CASES, runs)}
        except BaseException:
            cleanup_tree(cls.tmp)
            raise

    @classmethod
    def tearDownClass(cls):
        cleanup_tree(cls.tmp)

    @classmethod
    def prelude(cls):
        return ""

    @classmethod
    def prepare(cls, case, d):
        pass

    @classmethod
    def shared(cls, path):
        pass


# macOS checks each new executable the first time it runs (about half a second
# here). Cases link to one copy that has already run, rather than each running
# a fresh file of their own.
def shared_executables(path, scripts):
    path.mkdir(parents=True, exist_ok=True)
    for name, text in scripts.items():
        touch(path / name, text, 0o755)
    subprocess.run([BASH, "-c", 'for f in "$@"; do "$f" --version; done', "warm", *(str(path / n) for n in scripts)],
                   capture_output=True, timeout=120)
    return path


STUBS = 'say() { echo "== $*"; }; warn() { echo "WARN $*"; }; die() { echo "DIE $*"; exit 1; }'


# =====================================================================================
# installer-owned settings: the OWNED merge
# =====================================================================================

OWNED_CODE = heredoc(BOOTSTRAP, "HERE=\"$HERE\" elm_py - <<'PYX'\n")
OWNED = ast.literal_eval(OWNED_CODE[OWNED_CODE.index("OWNED = {") + len("OWNED = "):
                                    OWNED_CODE.index("\n}\n") + 2])
TEMPLATE_RAW = {rel: (ROOT / "templates" / rel).read_text() for rel in [*OWNED, "models.json"]}


def render_text(raw, here):
    """A template as the install writes it: model ids from agent/model-ids.json,
    and @AGENT_DIR@/@INSTALL_DIR@ as the permission config's sed fills them."""
    raw = raw.replace("@QWEN_MODEL@", MODEL_IDS["qwen"]).replace("@LLAMA_MODEL@", MODEL_IDS["llama"])
    return raw.replace("@AGENT_DIR@", f"{here}/agent").replace("@INSTALL_DIR@", str(here))


def template_value(rel, here):
    return json.loads(render_text(TEMPLATE_RAW[rel], here), object_pairs_hook=OrderedDict)


def write_owned_tree(d, edits=None, template_edits=None):
    """templates/ and agent/ for the merge: each live file as installed, then
    edited. An edit is a function of the parsed file (returns nothing), or a
    string - the raw text to write - or None to leave the file out."""
    edits, template_edits = edits or {}, template_edits or {}
    touch(d / "agent/model-ids.json", json.dumps(MODEL_IDS))
    # Only the files a case names: the merge skips a file it does not find.
    for rel in [r for r in [*OWNED, "models.json"] if r in edits]:
        raw = TEMPLATE_RAW[rel]
        if rel in template_edits:
            data = json.loads(raw, object_pairs_hook=OrderedDict)
            template_edits[rel](data)
            raw = json.dumps(data, indent=2) + "\n"
        touch(d / "templates" / rel, raw)
        edit = edits.get(rel, "as-installed")
        if edit is None:
            continue
        if edit == "as-installed":
            touch(d / "agent" / rel, render_text(raw, d))
        elif isinstance(edit, str):
            touch(d / "agent" / rel, edit)
        else:
            live = json.loads(render_text(raw, d), object_pairs_hook=OrderedDict)
            edit(live)
            touch(d / "agent" / rel, json.dumps(live, indent=2) + "\n")


def setter(**values):
    def edit(live):
        for k, v in values.items():
            live[k.replace("__", "$")] = v
    return edit


def deleter(*keys):
    def edit(live):
        for k in keys:
            live.pop(k, None)
    return edit


def chain(*edits):
    def edit(live):
        for e in edits:
            e(live)
    return edit


def report(out, rel):
    """The lines bootstrap.sh printed under agent/<rel>, without the indent."""
    lines = out.splitlines()
    try:
        i = lines.index(f"    agent/{rel}")
    except ValueError:
        return None
    found = []
    for line in lines[i + 1:]:
        if not line.startswith("      "):
            break
        found.append(line.strip())
    return found


def live(d, rel):
    return json.loads((d / "agent" / rel).read_text(), object_pairs_hook=OrderedDict)


def owned_case(name, edits=None, template_edits=None, check=None, runs=1, here=None, bug=None):
    return C(name, edits=edits, template_edits=template_edits, check=check, runs=runs, here=here, bug=bug)


OWNED_CASES = []
NOT_OWNED = {rel: [k for k in json.loads(TEMPLATE_RAW[rel]) if k not in keys] for rel, keys in OWNED.items()}


def _edited_owned(rel, key):
    def check(t, r, d):
        want = template_value(rel, d)[key]
        t.assertEqual(0, r[0].rc, r[0].error)
        t.assertEqual(want, live(d, rel)[key])
        t.assertIn(f'{key}: yours "mine" -> repo {brief(want)}', report(r[0].out, rel))
    return check


def _removed_owned(rel, key):
    def check(t, r, d):
        want = template_value(rel, d)[key]
        t.assertEqual(want, live(d, rel)[key])
        t.assertEqual([f"{key}: yours null -> repo {brief(want)}"], report(r[0].out, rel))
    return check


for _rel, _keys in OWNED.items():
    _s = slug(_rel)
    for _key in _keys:
        OWNED_CASES.append(owned_case(f"{_s}_{slug(_key)}_you_edited_is_reapplied",
                                      edits={_rel: setter(**{_key: "mine"})}, check=_edited_owned(_rel, _key)))
        OWNED_CASES.append(owned_case(f"{_s}_{slug(_key)}_you_removed_is_put_back",
                                      edits={_rel: deleter(_key)}, check=_removed_owned(_rel, _key)))
    _first = _keys[0]
    OWNED_CASES += [
        # The file is rewritten (an owned key changed), and your own key survives it.
        owned_case(f"{_s}_keeps_a_key_of_your_own_through_a_rewrite",
                   edits={_rel: setter(**{_first: "mine", "myOwnKey": {"nested": [1, "two", None]}})},
                   check=lambda t, r, d, rel=_rel, first=_first: (
                       t.assertEqual({"nested": [1, "two", None]}, live(d, rel)["myOwnKey"]),
                       t.assertEqual(template_value(rel, d)[first], live(d, rel)[first]))),
        owned_case(f"{_s}_a_second_run_changes_nothing",
                   edits={_rel: setter(**{k: f"mine-{i}" for i, k in enumerate(_keys)})}, runs=2,
                   check=lambda t, r, d, rel=_rel: (
                       t.assertEqual(len(OWNED[rel]), len(report(r[0].out, rel))),
                       t.assertIn(f"    agent/{rel} matches", r[1].out.splitlines()),
                       t.assertEqual(r[0].snap[f"agent/{rel}"], r[1].snap[f"agent/{rel}"]))),
        owned_case(f"{_s}_as_installed_matches_and_is_not_rewritten", edits={_rel: "as-installed"},
                   check=lambda t, r, d, rel=_rel: (
                       t.assertIn(f"    agent/{rel} matches", r[0].out.splitlines()),
                       t.assertEqual(render_text(TEMPLATE_RAW[rel], d), (d / "agent" / rel).read_text()))),
        owned_case(f"{_s}_that_is_absent_is_not_created", edits={_rel: None},
                   check=lambda t, r, d, rel=_rel: (
                       t.assertFalse((d / "agent" / rel).exists()),
                       t.assertNotIn(f"agent/{rel}", r[0].out),
                       t.assertEqual(0, r[0].rc))),
        # A file you broke stops the run (set -e) rather than being replaced by
        # the template: what you had is still there to fix.
        owned_case(f"{_s}_that_does_not_parse_stops_the_run_and_is_left_as_it_is",
                   edits={_rel: '{"half": '},
                   check=lambda t, r, d, rel=_rel: (
                       t.assertEqual(("raised", "JSONDecodeError"), (r[0].rc, r[0].error)),
                       t.assertEqual('{"half": ', (d / "agent" / rel).read_text()))),
        owned_case(f"{_s}_reports_every_change_in_the_order_owned_lists_them",
                   edits={_rel: setter(**{k: f"mine-{i}" for i, k in enumerate(reversed(_keys))})},
                   check=lambda t, r, d, rel=_rel: t.assertEqual(
                       list(OWNED[rel]), [line.split(":", 1)[0] for line in report(r[0].out, rel)])),
    ]

for _rel, _keys in NOT_OWNED.items():
    for _key in _keys:
        _first = OWNED[_rel][0]
        OWNED_CASES.append(owned_case(
            f"{slug(_rel)}_{slug(_key)}_is_yours_and_kept_through_a_rewrite",
            edits={_rel: setter(**{_first: "mine", _key.replace("$", "__"): ["your", "value"]})},
            check=lambda t, r, d, rel=_rel, key=_key: (
                t.assertEqual(["your", "value"], live(d, rel)[key]),
                t.assertNotIn(key, [line.split(":", 1)[0] for line in report(r[0].out, rel)]))))


def _many(t, r, d):
    for rel in OWNED:
        t.assertEqual({k: template_value(rel, d)[k] for k in OWNED[rel]}, {k: live(d, rel)[k] for k in OWNED[rel]})


OWNED_CASES += [
    owned_case("settings_a_key_you_deleted_that_the_repo_does_not_own_stays_deleted",
               edits={"settings.json": chain(deleter("theme", "quietStartup"), setter(compaction="mine"))},
               check=lambda t, r, d: (t.assertNotIn("theme", live(d, "settings.json")),
                                      t.assertNotIn("quietStartup", live(d, "settings.json")))),
    owned_case("settings_your_nested_value_in_a_key_you_own_is_kept",
               edits={"settings.json": chain(
                   lambda s: s["modelThinkingLevels"].update({"elm/mine": "high"}), setter(retry=None))},
               check=lambda t, r, d: t.assertEqual("high", live(d, "settings.json")["modelThinkingLevels"]["elm/mine"])),
    # Owned keys are replaced whole: what you add inside one is the repo's to drop.
    owned_case("settings_an_agent_override_you_added_inside_subagents_is_dropped",
               edits={"settings.json": lambda s: s["subagents"]["agentOverrides"].update({"mine": {"model": "x"}})},
               check=lambda t, r, d: (
                   t.assertNotIn("mine", live(d, "settings.json")["subagents"]["agentOverrides"]),
                   t.assertEqual(["subagents"], [l.split(":")[0] for l in report(r[0].out, "settings.json")]))),
    owned_case("settings_one_nested_retry_value_you_changed_is_put_back",
               edits={"settings.json": lambda s: s["retry"].update({"maxRetries": 99})},
               check=lambda t, r, d: t.assertEqual(
                   template_value("settings.json", d)["retry"]["maxRetries"], live(d, "settings.json")["retry"]["maxRetries"])),
    owned_case("permission_a_path_rule_you_added_is_dropped",
               edits={"extensions/pi-permission-system/config.json":
                      lambda s: s["permission"]["path"].update({"~/secret/*": "deny"})},
               check=lambda t, r, d: t.assertNotIn(
                   "~/secret/*", live(d, "extensions/pi-permission-system/config.json")["permission"]["path"])),
    # The live file is read as OrderedDicts but the repo's value as plain dicts,
    # and that comparison ignores order: a reordered value is not a change.
    owned_case("an_owned_value_you_only_reordered_matches",
               edits={"settings.json": lambda s: s.__setitem__("retry", OrderedDict(reversed(list(s["retry"].items()))))},
               check=lambda t, r, d: (t.assertIn("    agent/settings.json matches", r[0].out.splitlines()),
                                      t.assertEqual(["provider", "baseDelayMs", "maxRetries", "enabled"],
                                                    list(live(d, "settings.json")["retry"])))),
    owned_case("an_owned_key_you_changed_keeps_its_place_in_the_file",
               edits={"settings.json": setter(sessionDir="elsewhere")},
               check=lambda t, r, d: t.assertEqual(list(template_value("settings.json", d)),
                                                   list(live(d, "settings.json")))),
    owned_case("an_owned_key_you_removed_comes_back_at_the_end",
               edits={"settings.json": deleter("defaultProjectTrust")},
               check=lambda t, r, d: t.assertEqual("defaultProjectTrust", list(live(d, "settings.json"))[-1])),
    owned_case("an_owned_key_the_template_no_longer_has_is_left_as_you_have_it",
               edits={"web-search.json": setter(pdf="mine")}, template_edits={"web-search.json": deleter("pdf")},
               check=lambda t, r, d: (t.assertEqual("mine", live(d, "web-search.json")["pdf"]),
                                      t.assertIn("    agent/web-search.json matches", r[0].out.splitlines()))),
    owned_case("a_long_value_is_cut_to_sixty_characters_in_the_report",
               edits={"config/pi-auto-compact/config.json": setter(autoCompactThreshold="x" * 100)},
               check=lambda t, r, d: t.assertEqual(
                   [f'autoCompactThreshold: yours "{"x" * 56}... -> repo 70'],
                   report(r[0].out, "config/pi-auto-compact/config.json"))),
    owned_case("a_sixty_character_value_is_reported_whole",
               edits={"config/pi-auto-compact/config.json": setter(autoCompactThreshold="y" * 58)},
               check=lambda t, r, d: t.assertEqual(
                   [f'autoCompactThreshold: yours "{"y" * 58}" -> repo 70'],
                   report(r[0].out, "config/pi-auto-compact/config.json"))),
    owned_case("the_repos_model_ids_come_from_agent_model_ids_json",
               edits={"settings.json": setter(subagents={})},
               check=lambda t, r, d: (
                   t.assertEqual(f"elm/{MODEL_IDS['qwen']}",
                                 live(d, "settings.json")["subagents"]["agentOverrides"]["oracle"]["model"]),
                   t.assertNotIn(CONFIG["models"]["qwen"], (d / "agent/settings.json").read_text()))),
    owned_case("the_permission_paths_name_this_install",
               edits={"extensions/pi-permission-system/config.json": setter(permission={})},
               check=lambda t, r, d: (
                   t.assertEqual("allow", live(d, "extensions/pi-permission-system/config.json")
                                 ["permission"]["external_directory_read"][f"{d}/agent/workflows/**"]),
                   t.assertNotIn("@AGENT_DIR@", (d / "agent/extensions/pi-permission-system/config.json").read_text()),
                   t.assertNotIn("@INSTALL_DIR@", (d / "agent/extensions/pi-permission-system/config.json").read_text()))),
    # load() fills model tokens in the live file too, so one you typed into a
    # key of your own is rewritten when (and only when) the file is.
    owned_case("a_model_token_in_your_own_key_is_filled_when_the_file_is_rewritten",
               edits={"settings.json": setter(myNote="use @QWEN_MODEL@", compaction="mine")},
               check=lambda t, r, d: t.assertEqual(f"use {MODEL_IDS['qwen']}", live(d, "settings.json")["myNote"])),
    owned_case("a_model_token_in_your_own_key_is_left_when_nothing_changed",
               edits={"settings.json": setter(myNote="use @QWEN_MODEL@")},
               check=lambda t, r, d: t.assertEqual("use @QWEN_MODEL@", live(d, "settings.json")["myNote"])),
    owned_case("non_ascii_text_of_yours_survives_as_json_escapes",
               edits={"settings.json": setter(myNote="Schrödinger ψ", compaction="mine")},
               check=lambda t, r, d: (
                   t.assertEqual("Schrödinger ψ", live(d, "settings.json")["myNote"]),
                   t.assertIn('"Schr\\u00f6dinger \\u03c8"', (d / "agent/settings.json").read_text()))),
    owned_case("a_rewritten_file_is_indented_two_spaces_and_ends_in_a_newline",
               edits={"config/pi-auto-compact/config.json": '{"autoCompactThreshold": 50}'},
               check=lambda t, r, d: t.assertEqual('{\n  "autoCompactThreshold": 70\n}\n',
                                                   (d / "agent/config/pi-auto-compact/config.json").read_text())),
    # 70.0 == 70 in Python and in JavaScript alike: nothing to reapply.
    owned_case("a_numerically_equal_float_is_left_alone",
               edits={"config/pi-auto-compact/config.json": '{"autoCompactThreshold": 70.0}\n'},
               check=lambda t, r, d: (
                   t.assertIn("    agent/config/pi-auto-compact/config.json matches", r[0].out.splitlines()),
                   t.assertEqual('{"autoCompactThreshold": 70.0}\n',
                                 (d / "agent/config/pi-auto-compact/config.json").read_text()))),
    # Python's 0 == False: compared that way, a non-boolean that pi's schema
    # rejects would pass the merge as "matches".
    owned_case("an_integer_where_the_repo_decides_a_boolean_is_reapplied",
               edits={"settings.json": setter(compaction={"enabled": 0})},
               check=lambda t, r, d: t.assertIs(False, live(d, "settings.json")["compaction"]["enabled"])),
    owned_case("every_owned_file_edited_at_once_is_reapplied_in_one_run",
               edits={rel: setter(**{k: "mine" for k in keys}) for rel, keys in OWNED.items()}, check=_many),
    owned_case("an_install_path_with_a_space_is_written_whole",
               here="with space", edits={"extensions/pi-permission-system/config.json": setter(permission={})},
               check=lambda t, r, d: t.assertIn(
                   f"{d}/agent/workflows", live(d, "extensions/pi-permission-system/config.json")
                   ["permission"]["external_directory_read"])),
    # The paths are pasted into json.dumps() text, so they are JSON-escaped
    # first: a backslash would become an escape and a quote end the string.
    owned_case("an_install_path_with_a_backslash_is_written_whole",
               here="back\\slash", edits={"extensions/pi-permission-system/config.json": '{"permission": {}}\n'},
               check=lambda t, r, d: t.assertIn(
                   f"{d}/agent/workflows", live(d, "extensions/pi-permission-system/config.json")
                   ["permission"]["external_directory_read"])),
    owned_case("an_install_path_with_a_double_quote_is_written_whole",
               here='dq"uote', edits={"extensions/pi-permission-system/config.json": '{"permission": {}}\n'},
               check=lambda t, r, d: t.assertIn(
                   f"{d}/agent/workflows", live(d, "extensions/pi-permission-system/config.json")
                   ["permission"]["external_directory_read"])),
]


# --- the property: random edits, any mix --------------------------------------------

def random_edits(seed, here):
    """Random edits to every owned file, and what must hold after the merge:
    the owned keys are the repo's, every other key is exactly what you left."""
    rng = random.Random(seed)
    edits, expect = {}, {}

    def value():
        return rng.choice([rng.randint(-5, 500), f"s{rng.randint(0, 99)}", [rng.randint(0, 9)], None, True,
                           {"k": {"deep": rng.random()}}])

    for rel, keys in OWNED.items():
        data = template_value(rel, here)
        for key in list(data):
            roll = rng.random()
            if roll < 0.3:
                data[key] = value()
            elif roll < 0.45:
                del data[key]
            elif roll < 0.6 and isinstance(data[key], dict):
                data[key][f"added{rng.randint(0, 9)}"] = value()
        for _ in range(rng.randint(0, 3)):
            data[f"user{rng.randint(0, 999)}"] = value()
        if rng.random() < 0.2:
            edits[rel] = "as-installed"
            continue
        expect[rel] = {k: v for k, v in data.items() if k not in keys}
        text = json.dumps(data, indent=rng.choice([None, 2, 4])) + "\n"
        edits[rel] = text
    return edits, expect


def _property(seed):
    def check(t, r, d):
        _, expect = random_edits(seed, d)
        for rel, keys in OWNED.items():
            got = live(d, rel)
            want = template_value(rel, d)
            t.assertEqual({k: want[k] for k in keys if k in want}, {k: got[k] for k in keys if k in want}, rel)
            if rel in expect:
                t.assertEqual(expect[rel], {k: v for k, v in got.items() if k not in keys}, rel)
            t.assertIn(f"    agent/{rel} matches", r[1].out.splitlines())
        t.assertEqual(r[0].snap, r[1].snap)
    return check


for _seed in range(8):
    OWNED_CASES.append(owned_case(f"property_random_edits_seed_{_seed}_owned_reapplied_yours_kept_then_stable",
                                  edits=("seed", _seed), runs=2, check=_property(_seed)))


@generate
class OwnedMergeTests(PyBatch):
    """The OWNED merge in bootstrap.sh, one file and one key at a time."""

    CODE = OWNED_CODE
    CASES = OWNED_CASES
    SNAP = tuple(f"agent/{rel}" for rel in [*OWNED, "models.json"])

    @classmethod
    def setUpClass(cls):
        # A case may need its install at a path with odd characters in it.
        super().setUpClass()

    @classmethod
    def prepare(cls, case, d):
        kw = case.kw
        if kw.get("here"):
            d = d / kw["here"]
            d.mkdir()
            cls.dirs[case.name] = d
        edits = kw.get("edits")
        if isinstance(edits, tuple) and edits[0] == "seed":
            edits, _ = random_edits(edits[1], d)
        write_owned_tree(d, edits, kw.get("template_edits"))

    @classmethod
    def jobs(cls, case, d):
        d = cls.dirs[case.name]
        job = {"code": cls.CODE, "cwd": str(d), "env": {"HERE": str(d)}, "snap": list(cls.SNAP)}
        return [job] * case.kw.get("runs", 1)


# =====================================================================================
# models.json: Qwen's per-model keys and stray Llama entries
# =====================================================================================

QWEN_KEYS = ("samplingParams", "samplingParamsByThinkingLevel", "compat")
TEMPLATE_QWEN = json.loads(TEMPLATE_RAW["models.json"])["providers"]["elm"]["models"][0]


def models_edit(fn):
    def edit(m):
        fn(m, m["providers"]["elm"]["models"])
    return {"models.json": edit}


def elm_models(d):
    return live(d, "models.json")["providers"]["elm"]["models"]


def models_lines(out):
    return [l.strip() for l in out.splitlines() if "agent/models.json" in l or l.startswith("      the shim")]


MODELS_CASES = []
for _key in QWEN_KEYS:
    MODELS_CASES += [
        C(f"qwen_{slug(_key)}_you_changed_is_reset",
          edits=models_edit(lambda m, ms, k=_key: ms[0].__setitem__(k, {"mine": 1})),
          check=lambda t, r, d, k=_key: (
              t.assertEqual(TEMPLATE_QWEN[k], elm_models(d)[0][k]),
              t.assertIn(f'agent/models.json: {k} {{"mine": 1}} -> {json.dumps(TEMPLATE_QWEN[k])}',
                         models_lines(r[0].out)))),
        C(f"qwen_{slug(_key)}_missing_is_added",
          edits=models_edit(lambda m, ms, k=_key: ms[0].pop(k)),
          check=lambda t, r, d, k=_key: (
              t.assertEqual(TEMPLATE_QWEN[k], elm_models(d)[0][k]),
              t.assertIn(f"agent/models.json: {k} null -> {json.dumps(TEMPLATE_QWEN[k])}", models_lines(r[0].out)))),
    ]

MODELS_CASES += [
    C("qwen_context_window_you_tuned_is_kept",
      edits=models_edit(lambda m, ms: (ms[0].__setitem__("contextWindow", 1000), ms[0].pop("compat"))),
      check=lambda t, r, d: t.assertEqual(1000, elm_models(d)[0]["contextWindow"])),
    C("qwen_thinking_level_map_you_tuned_is_kept",
      edits=models_edit(lambda m, ms: (ms[0].__setitem__("thinkingLevelMap", {"off": "x"}), ms[0].pop("compat"))),
      check=lambda t, r, d: t.assertEqual({"off": "x"}, elm_models(d)[0]["thinkingLevelMap"])),
    C("qwen_name_you_changed_is_kept",
      edits=models_edit(lambda m, ms: (ms[0].__setitem__("name", "My Qwen"), ms[0].pop("compat"))),
      check=lambda t, r, d: t.assertEqual("My Qwen", elm_models(d)[0]["name"])),
    C("a_direct_llama_entry_is_removed_and_named",
      edits=models_edit(lambda m, ms: ms.append({"id": "meta-llama/Llama-3.3-70B-Instruct"})),
      check=lambda t, r, d: (
          t.assertEqual([MODEL_IDS["qwen"]], [e["id"] for e in elm_models(d)]),
          t.assertEqual(["agent/models.json: removed elm/meta-llama/Llama-3.3-70B-Instruct - it cannot call tools;",
                         "the shim entry elm-shim/meta-llama/... is the supported one"], models_lines(r[0].out)))),
    C("llama_is_matched_in_any_case",
      edits=models_edit(lambda m, ms: ms.append({"id": "LLAMA-UPPER"})),
      check=lambda t, r, d: t.assertEqual([MODEL_IDS["qwen"]], [e["id"] for e in elm_models(d)])),
    C("two_llama_entries_are_both_removed",
      edits=models_edit(lambda m, ms: ms.extend([{"id": "a-llama"}, {"id": "b-llama"}])),
      check=lambda t, r, d: (t.assertEqual(1, len(elm_models(d))),
                             t.assertEqual(2, r[0].out.count("removed elm/")))),
    C("a_llama_under_another_provider_is_not_touched",
      edits=models_edit(lambda m, ms: (m["providers"].__setitem__("elm-shim", {"models": [{"id": "meta-llama/x"}]}),
                                       ms.append({"id": "llama-stray"}))),
      check=lambda t, r, d: t.assertEqual([{"id": "meta-llama/x"}],
                                          live(d, "models.json")["providers"]["elm-shim"]["models"])),
    C("every_qwen_entry_gets_the_three_keys",
      edits=models_edit(lambda m, ms: ms.append({"id": "Qwen/Second-qwen"})),
      check=lambda t, r, d: t.assertEqual({k: TEMPLATE_QWEN[k] for k in QWEN_KEYS},
                                          {k: elm_models(d)[1].get(k) for k in QWEN_KEYS})),
    C("another_model_on_elm_is_left_without_the_keys",
      edits=models_edit(lambda m, ms: (ms.append({"id": "mistral/Other"}), ms[0].pop("compat"))),
      check=lambda t, r, d: t.assertEqual({"id": "mistral/Other"}, elm_models(d)[1])),
    C("an_entry_without_an_id_is_kept_as_it_is",
      edits=models_edit(lambda m, ms: (ms.append({"name": "anonymous"}), ms[0].pop("compat"))),
      check=lambda t, r, d: t.assertEqual({"name": "anonymous"}, elm_models(d)[1])),
    C("an_id_that_names_both_is_removed_as_a_llama",
      edits=models_edit(lambda m, ms: ms.append({"id": "qwen-llama-merge"})),
      check=lambda t, r, d: t.assertEqual([MODEL_IDS["qwen"]], [e["id"] for e in elm_models(d)])),
    C("as_installed_matches_and_is_not_rewritten", edits={"models.json": "as-installed"},
      check=lambda t, r, d: (t.assertIn("    agent/models.json matches", r[0].out.splitlines()),
                             t.assertEqual(render_text(TEMPLATE_RAW["models.json"], d),
                                           (d / "agent/models.json").read_text()))),
    C("a_second_run_changes_nothing", runs=2,
      edits=models_edit(lambda m, ms: (ms[0].pop("compat"), ms.append({"id": "llama"}))),
      check=lambda t, r, d: (t.assertIn("    agent/models.json matches", r[1].out.splitlines()),
                             t.assertEqual(r[0].snap["agent/models.json"], r[1].snap["agent/models.json"]))),
    C("without_a_models_file_nothing_is_said", edits={"models.json": None},
      check=lambda t, r, d: (t.assertNotIn("models.json", r[0].out), t.assertEqual(0, r[0].rc),
                             t.assertFalse((d / "agent/models.json").exists()))),
    C("a_file_without_providers_matches", edits={"models.json": '{"$schema": "x"}\n'},
      check=lambda t, r, d: (t.assertIn("    agent/models.json matches", r[0].out.splitlines()),
                             t.assertEqual('{"$schema": "x"}\n', (d / "agent/models.json").read_text()))),
    C("the_rest_of_the_file_survives_a_rewrite",
      edits=models_edit(lambda m, ms: (m["providers"]["elm"].__setitem__("baseUrl", "https://mine"),
                                       m.__setitem__("myKey", 1), ms[0].pop("compat"))),
      check=lambda t, r, d: (t.assertEqual("https://mine", live(d, "models.json")["providers"]["elm"]["baseUrl"]),
                             t.assertEqual(1, live(d, "models.json")["myKey"]))),
    C("a_key_reset_in_place_keeps_the_entrys_key_order",
      edits=models_edit(lambda m, ms: ms[0].__setitem__("compat", "x")),
      check=lambda t, r, d: t.assertEqual(list(TEMPLATE_QWEN), list(elm_models(d)[0]))),
    C("a_key_added_back_goes_at_the_end_of_the_entry",
      edits=models_edit(lambda m, ms: ms[0].pop("samplingParams")),
      check=lambda t, r, d: t.assertEqual("samplingParams", list(elm_models(d)[0])[-1])),
    # The per-model keys are compared as mappings: as OrderedDicts the same
    # values in another order would be reported as yours and rewritten.
    C("equal_sampling_params_in_another_key_order_match",
      edits=models_edit(lambda m, ms: ms[0].__setitem__(
          "samplingParams", dict(reversed(list(ms[0]["samplingParams"].items()))))),
      check=lambda t, r, d: t.assertIn("    agent/models.json matches", r[0].out.splitlines())),
    C("a_llama_removed_from_the_list_keeps_the_others_in_order",
      edits=models_edit(lambda m, ms: (ms.insert(0, {"id": "first-other"}), ms.insert(1, {"id": "llama-x"}))),
      check=lambda t, r, d: t.assertEqual(["first-other", MODEL_IDS["qwen"]], [e["id"] for e in elm_models(d)])),
]


@generate
class ModelsMergeTests(PyBatch):
    """The models.json half of the installer-owned settings block."""

    CODE = OWNED_CODE
    CASES = MODELS_CASES
    SNAP = ("agent/models.json",)

    @classmethod
    def prepare(cls, case, d):
        write_owned_tree(d, case.kw.get("edits"))


# =====================================================================================
# hashline and workflow settings
# =====================================================================================

HASHLINE_CODE = heredoc(BOOTSTRAP, "HERE=\"$HERE\" elm_py - <<'PYHL'\n")
WORKFLOW_CODE = heredoc(BOOTSTRAP, "HERE=\"$HERE\" elm_py - <<'PYWF'\n")
HASHLINE_WANT = json.loads((ROOT / "templates/hashline/config.json").read_text())
WORKFLOW_WANT = json.loads((ROOT / "templates/workflows/settings.json").read_text())


def flip(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, list):
        return value[:-1]
    return "mine"


def _hl(d):
    return json.loads((d / "agent/hashline/config.json").read_text())


def _wf(d):
    return json.loads((d / "agent/workflows/settings.json").read_text())


HASHLINE_CASES = [
    C("absent_is_written_with_both_keys", live=None,
      check=lambda t, r, d: (t.assertEqual(HASHLINE_WANT, _hl(d)),
                             t.assertEqual("    agent/hashline/config.json: set copyMoveEnabled, requirePath",
                                           r[0].out.strip("\n")))),
    *(C(f"{slug(k)}_you_changed_is_set_back", live={**HASHLINE_WANT, k: flip(v)},
        check=lambda t, r, d, k=k: (t.assertEqual(HASHLINE_WANT, _hl(d)),
                                    t.assertEqual(f"    agent/hashline/config.json: set {k}", r[0].out.strip("\n"))))
      for k, v in HASHLINE_WANT.items()),
    C("a_key_of_your_own_is_kept", live={"mine": [1], "requirePath": False},
      check=lambda t, r, d: t.assertEqual([1], _hl(d)["mine"])),
    C("matching_says_matches", live=HASHLINE_WANT,
      check=lambda t, r, d: t.assertEqual("    agent/hashline/config.json: matches", r[0].out.strip("\n"))),
    # Unlike the other merges, this one writes the file every run.
    C("a_matching_file_is_still_rewritten_in_the_installs_format", live='{"requirePath":true,"copyMoveEnabled":false}',
      check=lambda t, r, d: t.assertEqual(json.dumps(HASHLINE_WANT, indent=2) + "\n",
                                          (d / "agent/hashline/config.json").read_text())),
    C("a_file_that_does_not_parse_is_replaced", live="{oops",
      check=lambda t, r, d: t.assertEqual(HASHLINE_WANT, _hl(d))),
    C("a_second_run_matches_and_leaves_the_same_bytes", live={"x": 1}, runs=2,
      check=lambda t, r, d: (t.assertIn("matches", r[1].out),
                             t.assertEqual(r[0].snap, r[1].snap))),
    # Valid JSON that is not an object is replaced, saying so, rather than
    # crashing the install with AttributeError.
    C("a_file_holding_a_json_list_is_replaced", live="[]\n",
      check=lambda t, r, d: (t.assertEqual(0, r[0].rc), t.assertEqual(HASHLINE_WANT, _hl(d)),
                             t.assertIn("    agent/hashline/config.json was not a JSON object - replaced",
                                        r[0].out.splitlines()))),
    C("a_file_holding_json_null_is_replaced", live="null\n",
      check=lambda t, r, d: (t.assertEqual(0, r[0].rc), t.assertEqual(HASHLINE_WANT, _hl(d)))),
]


@generate
class HashlineSettingsTests(PyBatch):
    """agent/hashline/config.json: requirePath and copyMoveEnabled reapplied every run."""

    CODE = HASHLINE_CODE
    CASES = HASHLINE_CASES
    SNAP = ("agent/hashline/config.json",)

    @classmethod
    def prepare(cls, case, d):
        touch(d / "templates/hashline/config.json", (ROOT / "templates/hashline/config.json").read_text())
        (d / "agent/hashline").mkdir(parents=True)
        value = case.kw.get("live")
        if value is not None:
            touch(d / "agent/hashline/config.json", value if isinstance(value, str) else json.dumps(value))


WORKFLOW_CASES = [
    C("absent_with_its_folder_is_written", live=None,
      check=lambda t, r, d: (t.assertEqual(WORKFLOW_WANT, _wf(d)),
                             t.assertEqual(f"    {d}/agent/workflows/settings.json: set "
                                           + ", ".join(sorted(WORKFLOW_WANT)), r[0].out.strip("\n")))),
    *(C(f"{slug(k)}_you_changed_is_set_back", live={**WORKFLOW_WANT, k: flip(v)},
        check=lambda t, r, d, k=k: (t.assertEqual(WORKFLOW_WANT[k], _wf(d)[k]),
                                    t.assertEqual(f"    {d}/agent/workflows/settings.json: set {k}",
                                                  r[0].out.strip("\n"))))
      for k, v in WORKFLOW_WANT.items()),
    C("a_key_of_your_own_is_kept", live={"maxDepth": 3, "inheritMainModel": False},
      check=lambda t, r, d: t.assertEqual(3, _wf(d)["maxDepth"])),
    C("a_middleware_you_added_is_dropped",
      live={**WORKFLOW_WANT, "providerMiddlewareExtensions": [*WORKFLOW_WANT["providerMiddlewareExtensions"], "mine"]},
      check=lambda t, r, d: t.assertNotIn("mine", _wf(d)["providerMiddlewareExtensions"])),
    # Not rewritten when it matches: your formatting stays.
    C("a_matching_file_keeps_its_bytes", live=json.dumps(WORKFLOW_WANT),
      check=lambda t, r, d: (t.assertEqual(json.dumps(WORKFLOW_WANT), (d / "agent/workflows/settings.json").read_text()),
                             t.assertTrue(r[0].out.rstrip().endswith("settings.json matches")))),
    C("a_file_that_does_not_parse_is_replaced", live="not json",
      check=lambda t, r, d: t.assertEqual(WORKFLOW_WANT, _wf(d))),
    C("a_second_run_matches", live={"maxDepth": 3}, runs=2,
      check=lambda t, r, d: (t.assertTrue(r[1].out.rstrip().endswith("settings.json matches")),
                             t.assertEqual(r[0].snap, r[1].snap))),
    C("nothing_is_written_under_home", live=None,
      check=lambda t, r, d: t.assertEqual([str(d / "agent/workflows/settings.json")],
                                          [str(p) for p in d.rglob("settings.json") if "templates" not in p.parts])),
    C("a_file_holding_a_json_list_is_replaced", live="[1]\n",
      check=lambda t, r, d: (t.assertEqual(0, r[0].rc), t.assertEqual(WORKFLOW_WANT, _wf(d)))),
    C("a_file_holding_a_json_string_is_replaced", live='"x"\n',
      check=lambda t, r, d: (t.assertEqual(0, r[0].rc), t.assertEqual(WORKFLOW_WANT, _wf(d)))),
]


@generate
class WorkflowSettingsTests(PyBatch):
    """agent/workflows/settings.json: the four pi-dynamic-workflows keys reapplied."""

    CODE = WORKFLOW_CODE
    CASES = WORKFLOW_CASES
    SNAP = ("agent/workflows/settings.json",)

    @classmethod
    def prepare(cls, case, d):
        touch(d / "templates/workflows/settings.json", (ROOT / "templates/workflows/settings.json").read_text())
        value = case.kw.get("live")
        if value is not None:
            touch(d / "agent/workflows/settings.json", value if isinstance(value, str) else json.dumps(value))


# =====================================================================================
# the package list pi is told to load, and its theme filter
# =====================================================================================

PACKAGES_CODE = heredoc(BOOTSTRAP, "  elm_py - <<'PYX'\n")
CHOSEN_CODE = heredoc(BOOTSTRAP, "  CHOSEN=\"$(elm_py - <<'PYC'\n")
NO_PACKAGES_CODE = heredoc(BOOTSTRAP, "  elm_py - <<'PY'\n")
TEMPLATE_PACKAGES = json.loads((ROOT / "templates/settings.json").read_text())["packages"]
THEMES = next(p for p in TEMPLATE_PACKAGES if isinstance(p, dict))


def pkg_name(spec):
    spec = spec["source"] if isinstance(spec, dict) else spec
    return spec[4:] if spec.startswith("npm:") else spec


def _settings(d):
    return json.loads((d / "agent/settings.json").read_text())


LOADING = "    loading: " + ", ".join(pkg_name(p) for p in TEMPLATE_PACKAGES)

PACKAGE_CASES = [
    C("the_template_list_is_loaded_and_said_in_order", settings={"packages": TEMPLATE_PACKAGES},
      check=lambda t, r, d: (t.assertEqual(LOADING, r[0].out.splitlines()[0]),
                             t.assertNotIn("corrected", r[0].out))),
    C("a_package_you_added_is_removed", settings={"packages": [*TEMPLATE_PACKAGES, "npm:left-pad"]},
      check=lambda t, r, d: t.assertEqual(TEMPLATE_PACKAGES, _settings(d)["packages"])),
    C("a_package_you_added_is_named_as_removed", settings={"packages": [*TEMPLATE_PACKAGES, "npm:left-pad"]},
      check=lambda t, r, d: (
          t.assertIn(f"    (agent/settings.json listed {len(TEMPLATE_PACKAGES) + 1} package(s); corrected to match)",
                     r[0].out.splitlines()),
          t.assertIn("    not in templates/: left-pad - removed. Packages come from templates/packages.json",
                     r[0].out.splitlines()))),
    C("a_package_you_dropped_comes_back_without_a_removal_line", settings={"packages": TEMPLATE_PACKAGES[1:]},
      check=lambda t, r, d: (t.assertEqual(TEMPLATE_PACKAGES, _settings(d)["packages"]),
                             t.assertIn("corrected to match", r[0].out), t.assertNotIn("not in templates/", r[0].out))),
    # What --no-packages used to leave for ever.
    C("an_empty_list_from_an_earlier_no_packages_is_refilled", settings={"packages": []},
      check=lambda t, r, d: (t.assertEqual(TEMPLATE_PACKAGES, _settings(d)["packages"]),
                             t.assertIn("    (agent/settings.json listed 0 package(s); corrected to match)",
                                        r[0].out.splitlines()))),
    C("no_packages_key_at_all_is_filled", settings={"theme": "dark"},
      check=lambda t, r, d: t.assertEqual(TEMPLATE_PACKAGES, _settings(d)["packages"])),
    # Compared as sets: the same packages in your order is not a correction,
    # though the file takes the template's order.
    C("the_same_packages_reordered_is_not_reported", settings={"packages": list(reversed(TEMPLATE_PACKAGES))},
      check=lambda t, r, d: (t.assertNotIn("corrected", r[0].out),
                             t.assertEqual(TEMPLATE_PACKAGES, _settings(d)["packages"]))),
    C("a_theme_filter_you_removed_is_put_back",
      settings={"packages": [THEMES["source"] if isinstance(p, dict) else p for p in TEMPLATE_PACKAGES]},
      check=lambda t, r, d: (t.assertIn(THEMES, _settings(d)["packages"]),
                             t.assertIn("corrected to match", r[0].out),
                             t.assertNotIn("not in templates/", r[0].out))),
    C("a_theme_filter_you_widened_is_narrowed_again",
      settings={"packages": [{**p, "themes": []} if isinstance(p, dict) else p for p in TEMPLATE_PACKAGES]},
      check=lambda t, r, d: t.assertEqual(THEMES["themes"], next(
          p for p in _settings(d)["packages"] if isinstance(p, dict))["themes"])),
    C("the_rest_of_settings_is_left_exactly", settings={"packages": [], "theme": "mine", "my": {"a": 1}},
      check=lambda t, r, d: t.assertEqual({"theme": "mine", "my": {"a": 1}},
                                          {k: v for k, v in _settings(d).items() if k != "packages"})),
    C("a_second_run_is_silent_and_stable", settings={"packages": ["npm:x"]}, runs=2,
      check=lambda t, r, d: (t.assertEqual([LOADING], r[1].out.splitlines()),
                             t.assertEqual(r[0].snap, r[1].snap))),
    C("a_non_npm_package_is_named_as_written", settings={"packages": [*TEMPLATE_PACKAGES, "git:github.com/a/b"]},
      check=lambda t, r, d: t.assertIn("    not in templates/: git:github.com/a/b - removed.", r[0].out)),
    C("several_removed_packages_are_named_sorted",
      settings={"packages": [*TEMPLATE_PACKAGES, "npm:zeta", {"source": "npm:alpha"}]},
      check=lambda t, r, d: t.assertIn("    not in templates/: alpha, zeta - removed.", r[0].out)),
]


@generate
class PackageListTests(PyBatch):
    """agent/settings.json's "packages", derived from templates/settings.json every run."""

    CODE = PACKAGES_CODE
    CASES = PACKAGE_CASES
    SNAP = ("agent/settings.json",)

    @classmethod
    def prepare(cls, case, d):
        touch(d / "templates/settings.json", (ROOT / "templates/settings.json").read_text())
        touch(d / "agent/settings.json", json.dumps(case.kw["settings"], indent=2))


CHOSEN_CASES = [
    C("chosen_names_drop_npm_and_read_the_object_form", settings={"packages": TEMPLATE_PACKAGES},
      check=lambda t, r, d: t.assertEqual(" ".join(pkg_name(p) for p in TEMPLATE_PACKAGES) + "\n", r[0].out)),
    C("chosen_with_no_packages_is_an_empty_line", settings={"packages": []},
      check=lambda t, r, d: t.assertEqual("\n", r[0].out)),
    C("chosen_keeps_a_spec_without_npm_as_written", settings={"packages": ["git:x/y", {"source": "npm:@s/p"}]},
      check=lambda t, r, d: t.assertEqual("git:x/y @s/p\n", r[0].out)),
    C("chosen_without_a_packages_key_is_empty", settings={},
      check=lambda t, r, d: t.assertEqual("\n", r[0].out)),
]


@generate
class ChosenPackagesTests(PyBatch):
    """$CHOSEN: the names install_packages checks for in the staged tree."""

    CODE = CHOSEN_CODE
    CASES = CHOSEN_CASES

    @classmethod
    def prepare(cls, case, d):
        touch(d / "agent/settings.json", json.dumps(case.kw["settings"]))


NO_PACKAGES_CASES = [
    C("no_packages_empties_the_list_and_says_so", settings={"packages": TEMPLATE_PACKAGES, "theme": "t"},
      check=lambda t, r, d: (t.assertEqual({"packages": [], "theme": "t"}, _settings(d)),
                             t.assertEqual("    packages disabled in agent/settings.json\n", r[0].out))),
    C("no_packages_adds_an_empty_list_where_there_was_none", settings={"theme": "t"},
      check=lambda t, r, d: t.assertEqual([], _settings(d)["packages"])),
    C("no_packages_writes_two_space_indent_and_a_newline", settings={"packages": ["npm:a"]},
      check=lambda t, r, d: t.assertEqual('{\n  "packages": []\n}\n', (d / "agent/settings.json").read_text())),
]


@generate
class NoPackagesTests(PyBatch):
    """--no-packages: nothing is loaded, everything else in settings.json stays."""

    CODE = NO_PACKAGES_CODE
    CASES = NO_PACKAGES_CASES

    @classmethod
    def prepare(cls, case, d):
        touch(d / "agent/settings.json", json.dumps(case.kw["settings"]))


# =====================================================================================
# the version record, and the web-tool exclusion check
# =====================================================================================

VERSIONS_CODE = heredoc(BOOTSTRAP, "elm_py - \"$HERE\" <<'PYV'\n")


def _versions_tree(d, core=None, packages=None, tested=None, manifests=None):
    manifests = manifests or {"core": ["pi-core"], "packages": ["pkg-a", "@s/pkg-b"]}
    touch(d / "package.json", json.dumps({"dependencies": {n: "latest" for n in manifests["core"]}}))
    touch(d / "templates/packages.json", json.dumps({"dependencies": {n: "latest" for n in manifests["packages"]}}))
    for name, version in (core or {}).items():
        touch(d / "node_modules" / name / "package.json", json.dumps({"version": version}))
    for name, version in (packages or {}).items():
        touch(d / "agent/npm/node_modules" / name / "package.json", json.dumps({"version": version}))
    if tested is not None:
        touch(d / "config/versions.json", json.dumps(tested))
    (d / "agent").mkdir(exist_ok=True)


def _record(d):
    return json.loads((d / "agent/installed-versions.json").read_text())


VERSIONS_CASES = [
    C("installed_versions_are_recorded_by_section",
      tree=dict(core={"pi-core": "1.0.0"}, packages={"pkg-a": "2.0.0", "@s/pkg-b": "3.0.0"},
                tested={"core": {"pi-core": "1.0.0"}, "packages": {"pkg-a": "2.0.0", "@s/pkg-b": "3.0.0"}}),
      check=lambda t, r, d: (t.assertEqual({"core": {"pi-core": "1.0.0"},
                                            "packages": {"pkg-a": "2.0.0", "@s/pkg-b": "3.0.0"}}, _record(d)),
                             t.assertEqual("    versions: agent/installed-versions.json\n", r[0].out))),
    C("a_version_other_than_the_tested_one_is_listed",
      tree=dict(core={"pi-core": "1.1.0"}, packages={"pkg-a": "2.0.0"},
                tested={"core": {"pi-core": "1.0.0"}, "packages": {"pkg-a": "2.0.0"}}),
      check=lambda t, r, d: t.assertIn("      differs from config/versions.json: pi-core 1.1.0", r[0].out)),
    C("a_package_not_on_disk_is_left_out_of_the_record",
      tree=dict(core={"pi-core": "1.0.0"}, packages={}, tested={}),
      check=lambda t, r, d: t.assertEqual({}, _record(d)["packages"])),
    C("a_package_the_tested_set_does_not_name_is_not_a_difference",
      tree=dict(core={"pi-core": "1.0.0"}, packages={"pkg-a": "9.9.9"}, tested={"core": {"pi-core": "1.0.0"}}),
      check=lambda t, r, d: t.assertNotIn("differs", r[0].out)),
    C("without_versions_json_nothing_differs",
      tree=dict(core={"pi-core": "5.0.0"}, packages={"pkg-a": "1.0.0"}),
      check=lambda t, r, d: (t.assertNotIn("differs", r[0].out), t.assertEqual("5.0.0", _record(d)["core"]["pi-core"]))),
    C("every_difference_is_listed_core_first",
      tree=dict(core={"pi-core": "2.0.0"}, packages={"pkg-a": "3.0.0"},
                tested={"core": {"pi-core": "1.0.0"}, "packages": {"pkg-a": "2.0.0"}}),
      check=lambda t, r, d: t.assertIn("differs from config/versions.json: pi-core 2.0.0, pkg-a 3.0.0", r[0].out)),
    C("the_record_ends_in_a_newline",
      tree=dict(core={}, packages={}),
      check=lambda t, r, d: t.assertEqual('{\n  "core": {},\n  "packages": {}\n}\n',
                                          (d / "agent/installed-versions.json").read_text())),
]


@generate
class VersionRecordTests(PyBatch):
    """agent/installed-versions.json, written once every check has passed."""

    CODE = VERSIONS_CODE
    CASES = VERSIONS_CASES

    @classmethod
    def prepare(cls, case, d):
        _versions_tree(d, **case.kw["tree"])


WEB_CODE = heredoc(BOOTSTRAP, "HERE=\"$HERE\" elm_py - <<'PYW' || warn \"could not check the web-tool exclusion list\"\n")


def _web(names, loader=None, excluded=("web_search", "fetch_content")):
    files = {"index.ts": "export default {};\n"}
    if names is not None:
        files["web-tool-core.ts"] = ("const DEFAULT_TOOL_NAMES: Record<string, string> = {\n"
                                     + "".join(f'  k{i}: "{n}",\n' for i, n in enumerate(names)) + "};\n")
    if loader:
        files["loader.ts"] = f'const LOADER_NAME = "{loader}";\n'
    return {"files": files, "excluded": list(excluded)}


WEB_CASES = [
    C("every_registered_tool_excluded", web=_web(["web_search", "fetch_content"]),
      check=lambda t, r, d: (t.assertEqual(0, r[0].rc),
                             t.assertEqual("    web tools: 2 registered, all excluded by default (pi --remote enables them)\n",
                                           r[0].out))),
    C("a_new_tool_not_excluded_fails_naming_it", web=_web(["web_search", "fetch_content", "web_crawl"]),
      check=lambda t, r, d: (t.assertEqual(1, r[0].rc),
                             t.assertIn("web tools: web_crawl registered but NOT excluded", r[0].out))),
    C("the_loader_tool_counts_as_registered", web=_web(["web_search"], loader="web_enable", excluded=["web_search"]),
      check=lambda t, r, d: (t.assertEqual(1, r[0].rc), t.assertIn("web_enable registered but NOT excluded", r[0].out))),
    C("an_exclusion_no_longer_registered_is_harmless", web=_web(["web_search"]),
      check=lambda t, r, d: (t.assertEqual(0, r[0].rc),
                             t.assertIn("web tools: fetch_content excluded but no longer registered - harmless", r[0].out))),
    C("a_package_without_the_name_block_cannot_be_read", web=_web(None),
      check=lambda t, r, d: (t.assertEqual(1, r[0].rc), t.assertIn("could not read one of the two lists", r[0].out))),
    C("an_empty_exclusion_list_cannot_be_read", web=_web(["web_search"], excluded=()),
      check=lambda t, r, d: (t.assertEqual(1, r[0].rc), t.assertIn("could not read one of the two lists", r[0].out))),
    C("without_pi_web_access_there_is_nothing_to_exclude", web=None,
      check=lambda t, r, d: (t.assertEqual(0, r[0].rc),
                             t.assertEqual("    web tools: pi-web-access is not installed, nothing to exclude\n", r[0].out))),
]


@generate
class WebToolCheckTests(PyBatch):
    """The check that every pi-web-access tool is in config/elm-pi.json's webTools."""

    CODE = WEB_CODE
    CASES = WEB_CASES

    @classmethod
    def prepare(cls, case, d):
        web = case.kw["web"]
        touch(d / "config/elm-pi.json", json.dumps({"webTools": web["excluded"] if web else ["x"]}))
        if web:
            for name, text in web["files"].items():
                touch(d / "agent/npm/node_modules/pi-web-access" / name, text)


# =====================================================================================
# bash: the agent/ refresh (section 3)
# =====================================================================================

AGENT_BLOCK = block(BOOTSTRAP, "chmod +x pi pi.orig configure.sh 2>/dev/null || true", "# --- 3b. command-line tools")
SANDBOX = ROOT / "lib/sandbox.sh"
REQUIRED = CONFIG["requiredExtensions"]
SKILLS = sorted(p.parent.name for p in (ROOT / "templates/skills").glob("*/SKILL.md"))
REFERENCES = sorted(p.name for p in (ROOT / "templates/reference").glob("*.md"))
AGENTS = sorted(p.name for p in (ROOT / "templates/agents").glob("*.md"))
ABSENT_CONFIGS = ("extensions/subagent/config.json", "config/pi-task-models/config.json",
                  "config/pi-auto-compact/config.json", "settings.json", "models.json", "web-search.json")

# The config renderer, stubbed: model tokens only, and a log of what was
# rendered where. scripts/elm_config.py's own rendering is tested in
# tests/test_scripts.py; here it is which files go where that matters.
AGENT_PRELUDE = f'''
. {q(SANDBOX)}
PY={q(PY)}
elm_py() {{
  if [ "$1" = "$CONFIG_TOOL" ]; then
    case "$4" in
      init) printf '%s\\n' '{json.dumps(MODEL_IDS)}' > "$HERE/agent/model-ids.json" ;;
      render) mkdir -p "${{6%/*}}"
              sed -e 's|@QWEN_MODEL@|{MODEL_IDS["qwen"]}|g' -e 's|@LLAMA_MODEL@|{MODEL_IDS["llama"]}|g' "$5" > "$6"
              echo "$5 -> $6" >> "$HERE/.renders" ;;
    esac
  else
    ( cd "$ELM_PI_ROOT" && exec "$PY" -E -S "$@" )
  fi
}}
{STUBS}
'''


def agent_body(d, before="", between=None, env=None, flags=None):
    flags = {"WITH_SHIM": 1, "AUTH_LOCK": 1, **(flags or {})}
    head = "\n".join([
        "set -euo pipefail", f"cd {q(d)}", 'HERE="$PWD"; ELM_PI_ROOT="$HERE"; CONFIG_TOOL="$HERE/scripts/elm_config.py"',
        f"ELM_PI_PYTHON={q(PY)}", "ELM_PI_USER_PATH=/usr/bin:/bin",
        *(f"{k}={v}" for k, v in flags.items()),
        *(f"export {k}={q(v)}" for k, v in (env or {}).items()), before])
    parts = [head, AGENT_BLOCK]
    if between is not None:
        parts += ['echo "@@RUN2"', between, AGENT_BLOCK]
    return "\n".join(parts)


def agent_tree(d):
    for name in ("templates", "config"):
        shutil.copytree(ROOT / name, d / name)
    touch(d / "lib/state.sh", (ROOT / "lib/state.sh").read_text())
    for name in ("pi", "pi.orig", "configure.sh"):
        touch(d / name, "#!/bin/sh\n", 0o644)


def snapshot(d):
    """Every file under agent/, with its content (links by their target)."""
    out = {}
    for p in sorted((d / "agent").rglob("*")):
        rel = str(p.relative_to(d))
        if p.is_symlink():
            out[rel] = "-> " + os.readlink(p)
        elif p.is_file():
            out[rel] = p.read_bytes()
    return out


# Every file under agent/ by content (a link by its target), for comparing runs.
SNAP_CODE = ("import hashlib,json,os\nout={}\nfor r,_,fs in os.walk('agent'):\n for f in fs:\n  p=os.path.join(r,f)\n"
             "  out[p]=('-> '+os.readlink(p)) if os.path.islink(p) else hashlib.sha256(open(p,'rb').read()).hexdigest()\n"
             "print(json.dumps(out))")
SNAP_SHELL = f'"$PY" -c {q(SNAP_CODE)} > "$HERE/.snap1"'

# Scenarios: each is one run (or two) of the block in its own install.
SCENARIOS = {
    # In a folder with a space in its name, with Homebrew last on the account's PATH.
    "fresh install": dict(before='mkdir -p fakebrew && : > fakebrew/brew && chmod 755 fakebrew/brew && ELM_PI_USER_PATH="$HERE/fakebrew"'),
    "twice": dict(between=""),
    "edited": dict(between="\n".join([
        # config you tune: kept
        *(f"echo '{{\"mine\": \"{rel}\"}}' > agent/{rel}" for rel in ABSENT_CONFIGS),
        "echo '{\"mine\": \"perm\"}' > agent/extensions/pi-permission-system/config.json",
        # code the repo owns: replaced
        "echo edited > agent/extensions/elm-only.ts",
        "echo edited > agent/agents/qwen.md",
        "echo edited > agent/AGENTS.md",
        "echo edited > agent/APPEND_SYSTEM.md",
        "echo edited > agent/shell/colour.sh",
        f"echo edited > agent/skills/{SKILLS[0]}/SKILL.md",
        f"echo extra > agent/skills/{SKILLS[0]}/notes.txt",
        "echo stale > agent/reference/stale.md",
        # yours: kept
        "echo mine > agent/extensions/mine.ts",
        "echo mine > agent/agents/mine.md",
        "mkdir -p agent/skills/my-skill && echo mine > agent/skills/my-skill/SKILL.md",
        "chmod 600 agent/auth.json && echo '{\"tok\": 1}' > agent/auth.json",
        # a skill the repo dropped since: removed
        "mkdir -p agent/skills/retired && echo old > agent/skills/retired/SKILL.md && echo retired >> agent/skills/.elm-pi-managed",
        # manifest lines that are not a skill's name: never acted on
        "mkdir -p agent/outside && echo keep > agent/outside/file",
        "mkdir -p agent/skills/.hidden agent/skills/a/b",
        "printf '%s\\n' '../outside' '.hidden' 'a/b' '' '..' >> agent/skills/.elm-pi-managed",
    ])),
    # Several independent conditions share one install where they cannot
    # interfere, so each costs one run of the block rather than one each.
    "misc": dict(before="\n".join([
        # no skills manifest yet (an install from before it existed)
        "mkdir -p agent/skills/old-managed && echo x > agent/skills/old-managed/SKILL.md",
        # a template folder that is not a skill, a skill with supporting files,
        # one of yours that takes its name, and an agent file using @AGENT_DIR@
        "mkdir -p templates/skills/no-skill-file && echo x > templates/skills/no-skill-file/README.md",
        "mkdir -p templates/skills/with-files/scripts && printf -- '---\\nname: with-files\\n---\\n' > templates/skills/with-files/SKILL.md",
        "echo 'print(1)' > templates/skills/with-files/scripts/run.py",
        "printf 'dir: @AGENT_DIR@/x\\n' > templates/agents/probe.md",
        "mkdir -p agent/skills/with-files && echo mine > agent/skills/with-files/SKILL.md",
        # a required extension whose template is gone, with an old copy installed
        "rm templates/extensions/todo.ts && mkdir -p agent/extensions && echo old > agent/extensions/todo.ts",
        # Homebrew early on the account's PATH
        'mkdir -p fakebrew && : > fakebrew/brew && chmod 755 fakebrew/brew && ELM_PI_USER_PATH="$HERE/fakebrew:$HERE/nothing"'])),
    "variant": dict(flags={"WITH_SHIM": 0, "AUTH_LOCK": 0}, before="\n".join([
        "mkdir -p agent/extensions && echo old > agent/extensions/elm-shim.ts",
        'printf "{\\"k\\":1}\\n" > agent/auth.json && chmod 400 agent/auth.json',
        # a managed skill that is a link out of the install
        "mkdir -p elsewhere/kept agent/skills && echo keep > elsewhere/kept/SKILL.md",
        'ln -s "$HERE/elsewhere/kept" agent/skills/gone', "echo gone > agent/skills/.elm-pi-managed",
        "mkdir -p agent/bin && ln -s /nowhere agent/bin/brew"])),
    "required_missing": dict(before="rm templates/extensions/todo.ts"),
}


def S(name, scenario, check, bug=None, skip=None):
    return C(name, scenario=scenario, check=check, bug=bug, skip=skip)


def _read(d, rel):
    return (d / rel).read_text()


def _render(d, src):
    text = (d / src).read_text()
    return text.replace("@QWEN_MODEL@", MODEL_IDS["qwen"]).replace("@LLAMA_MODEL@", MODEL_IDS["llama"])


def _runs(r):
    return r.out.split("@@RUN2\n", 1) if "@@RUN2" in r.out else [r.out]


def _brew_anywhere():
    return any(os.access(f"{d}/brew", os.X_OK) for d in ("/opt/homebrew/bin", "/usr/local/bin",
                                                          "/home/linuxbrew/.linuxbrew/bin", "/usr/bin", "/bin"))


AGENT_CASES = [
    *(S(f"fresh_installs_extension_{slug(f)}", "fresh install",
        lambda t, r, d, f=f: t.assertEqual(_render(d, f"templates/extensions/{f}"), _read(d, f"agent/extensions/{f}")))
      for f in REQUIRED),
    *(S(f"fresh_writes_{slug(rel)}_from_its_template", "fresh install",
        lambda t, r, d, rel=rel: (t.assertEqual(_render(d, f"templates/{rel}"), _read(d, f"agent/{rel}")),
                                  t.assertIn(f"    wrote agent/{rel}", r.out.splitlines())))
      for rel in ABSENT_CONFIGS),
    *(S(f"fresh_renders_agent_{slug(a)}", "fresh install",
        lambda t, r, d, a=a: (t.assertEqual(_render(d, f"templates/agents/{a}"), _read(d, f"agent/agents/{a}")),
                              t.assertFalse((d / f"agent/agents/{a}.tmp").exists())))
      for a in AGENTS),
    *(S(f"fresh_renders_reference_{slug(f)}", "fresh install",
        lambda t, r, d, f=f: t.assertEqual(_render(d, f"templates/reference/{f}"), _read(d, f"agent/reference/{f}")))
      for f in REFERENCES),
    *(S(f"fresh_installs_and_lists_skill_{slug(s)}", "fresh install",
        lambda t, r, d, s=s: (t.assertEqual(_render(d, f"templates/skills/{s}/SKILL.md"),
                                            _read(d, f"agent/skills/{s}/SKILL.md")),
                              t.assertIn(s, _read(d, "agent/skills/.elm-pi-managed").splitlines())))
      for s in SKILLS),
    S("fresh_manifest_lists_exactly_the_template_skills_in_order", "fresh install",
      lambda t, r, d: t.assertEqual(SKILLS, _read(d, "agent/skills/.elm-pi-managed").splitlines())),
    S("fresh_says_how_many_skills", "fresh install",
      lambda t, r, d: t.assertIn(f"    refreshed agent/skills ({len(SKILLS)} skills)", r.out.splitlines())),
    S("fresh_permission_config_names_this_install", "fresh install",
      lambda t, r, d: t.assertEqual(
          _read(d, "templates/extensions/pi-permission-system/config.json")
          .replace("@AGENT_DIR@", f"{d}/agent").replace("@INSTALL_DIR@", str(d)),
          _read(d, "agent/extensions/pi-permission-system/config.json"))),
    S("fresh_renders_agents_md_and_append_system", "fresh install",
      lambda t, r, d: t.assertEqual([_render(d, "templates/AGENTS.md"), _render(d, "templates/APPEND_SYSTEM.md")],
                                    [_read(d, "agent/AGENTS.md"), _read(d, "agent/APPEND_SYSTEM.md")])),
    S("fresh_copies_the_colour_prefix_byte_for_byte", "fresh install",
      lambda t, r, d: t.assertEqual((ROOT / "templates/shell/colour.sh").read_bytes(),
                                    (d / "agent/shell/colour.sh").read_bytes())),
    S("fresh_creates_an_empty_read_only_auth_file", "fresh install",
      lambda t, r, d: (t.assertEqual("{}\n", _read(d, "agent/auth.json")),
                       t.assertEqual(0o400, (d / "agent/auth.json").stat().st_mode & 0o777))),
    S("fresh_records_the_python_the_launcher_starts", "fresh install",
      lambda t, r, d: t.assertEqual(PY + "\n", _read(d, "agent/python-path"))),
    *(S(f"fresh_links_agent_bin_{slug(n)}", "fresh install",
        lambda t, r, d, n=n, target=target: t.assertEqual(f"{d}/{target}", os.readlink(d / f"agent/bin/{n}")))
      for n, target in (("pi", "pi"), ("workflow-check", "scripts/workflow-check"),
                        ("conda-search", "scripts/conda-search"))),
    S("fresh_makes_the_launcher_executable", "fresh install",
      lambda t, r, d: t.assertEqual([True] * 3, [os.access(d / n, os.X_OK) for n in ("pi", "pi.orig", "configure.sh")])),
    S("fresh_keeps_agent_private", "fresh install",
      lambda t, r, d: t.assertEqual(0o700, (d / "agent").stat().st_mode & 0o777)),
    S("fresh_says_the_shim_is_among_the_extensions", "fresh install",
      lambda t, r, d: t.assertIn("    refreshed required agent extensions (policy, protections, tools, shim)",
                                 r.out.splitlines())),
    S("fresh_installs_no_extension_that_is_not_required", "fresh install",
      lambda t, r, d: t.assertEqual(sorted(REQUIRED), sorted(p.name for p in (d / "agent/extensions").glob("*.ts")))),
    # property: the refresh is idempotent - a second run leaves every file under
    # agent/ exactly as the first did.
    S("a_second_run_leaves_agent_exactly_as_the_first", "twice",
      lambda t, r, d: t.assertEqual(json.loads(_read(d, ".snap1")), json.loads(_read(d, ".snap2")))),
    S("a_second_run_keeps_every_config_and_says_so", "twice",
      lambda t, r, d: t.assertEqual(
          sorted(f"    keeping existing agent/{rel}" for rel in [*ABSENT_CONFIGS, "extensions/pi-permission-system/config.json"]),
          sorted(l for l in _runs(r)[1].splitlines() if l.startswith("    keeping existing")))),
    S("a_second_run_rewrites_no_config_byte", "twice",
      lambda t, r, d: t.assertEqual(json.loads(_read(d, ".hash1")), json.loads(_read(d, ".hash2")))),
    # what you tune is kept, what the repo owns is replaced
    *(S(f"edited_{slug(rel)}_is_kept", "edited",
        lambda t, r, d, rel=rel: t.assertEqual({"mine": rel}, json.loads(_read(d, f"agent/{rel}"))))
      for rel in ABSENT_CONFIGS),
    S("edited_permission_config_is_not_rewritten_by_sed", "edited",
      lambda t, r, d: t.assertEqual({"mine": "perm"}, json.loads(_read(d, "agent/extensions/pi-permission-system/config.json")))),
    S("edited_required_extension_is_replaced", "edited",
      lambda t, r, d: t.assertEqual(_render(d, "templates/extensions/elm-only.ts"), _read(d, "agent/extensions/elm-only.ts"))),
    S("edited_agent_definition_is_rendered_again", "edited",
      lambda t, r, d: t.assertEqual(_render(d, "templates/agents/qwen.md"), _read(d, "agent/agents/qwen.md"))),
    S("edited_agents_md_is_rendered_again", "edited",
      lambda t, r, d: t.assertEqual(_render(d, "templates/AGENTS.md"), _read(d, "agent/AGENTS.md"))),
    S("edited_append_system_is_rendered_again", "edited",
      lambda t, r, d: t.assertEqual(_render(d, "templates/APPEND_SYSTEM.md"), _read(d, "agent/APPEND_SYSTEM.md"))),
    S("edited_colour_prefix_is_copied_again", "edited",
      lambda t, r, d: t.assertEqual(_read(d, "templates/shell/colour.sh"), _read(d, "agent/shell/colour.sh"))),
    S("edited_managed_skill_is_refreshed", "edited",
      lambda t, r, d: t.assertEqual(_render(d, f"templates/skills/{SKILLS[0]}/SKILL.md"),
                                    _read(d, f"agent/skills/{SKILLS[0]}/SKILL.md"))),
    S("a_file_added_inside_a_managed_skill_goes", "edited",
      lambda t, r, d: t.assertFalse((d / f"agent/skills/{SKILLS[0]}/notes.txt").exists())),
    S("a_reference_file_the_repo_does_not_have_goes", "edited",
      lambda t, r, d: t.assertEqual(REFERENCES, sorted(p.name for p in (d / "agent/reference").iterdir()))),
    S("an_extension_of_your_own_is_kept", "edited",
      lambda t, r, d: t.assertEqual("mine\n", _read(d, "agent/extensions/mine.ts"))),
    S("an_agent_definition_of_your_own_is_kept", "edited",
      lambda t, r, d: t.assertEqual("mine\n", _read(d, "agent/agents/mine.md"))),
    S("a_skill_of_your_own_is_kept_and_not_listed", "edited",
      lambda t, r, d: (t.assertEqual("mine\n", _read(d, "agent/skills/my-skill/SKILL.md")),
                       t.assertNotIn("my-skill", _read(d, "agent/skills/.elm-pi-managed").splitlines()))),
    S("a_skill_the_repo_dropped_is_removed", "edited",
      lambda t, r, d: t.assertFalse((d / "agent/skills/retired").exists())),
    S("a_manifest_line_leading_out_of_skills_is_ignored", "edited",
      lambda t, r, d: t.assertEqual("keep\n", _read(d, "agent/outside/file"))),
    S("a_manifest_line_naming_a_hidden_folder_is_ignored", "edited",
      lambda t, r, d: t.assertTrue((d / "agent/skills/.hidden").is_dir())),
    S("a_manifest_line_with_a_slash_is_ignored", "edited",
      lambda t, r, d: t.assertTrue((d / "agent/skills/a/b").is_dir())),
    S("the_manifest_is_rewritten_without_the_lines_that_were_not_skills", "edited",
      lambda t, r, d: t.assertEqual(SKILLS, _read(d, "agent/skills/.elm-pi-managed").splitlines())),
    S("an_existing_auth_file_keeps_its_content_and_is_locked_again", "edited",
      lambda t, r, d: (t.assertEqual('{"tok": 1}\n', _read(d, "agent/auth.json")),
                       t.assertEqual(0o400, (d / "agent/auth.json").stat().st_mode & 0o777))),
    # --no-shim
    S("no_shim_removes_an_installed_shim_extension", "variant",
      lambda t, r, d: t.assertFalse((d / "agent/extensions/elm-shim.ts").exists())),
    S("no_shim_installs_every_other_required_extension", "variant",
      lambda t, r, d: t.assertEqual(sorted(f for f in REQUIRED if f != "elm-shim.ts"),
                                    sorted(p.name for p in (d / "agent/extensions").glob("*.ts")))),
    S("no_shim_never_renders_the_shim", "variant",
      lambda t, r, d: t.assertNotIn("elm-shim.ts", _read(d, ".renders"))),
    S("no_shim_says_no_shim", "variant",
      lambda t, r, d: t.assertIn("    refreshed required agent extensions (policy, protections, tools; no shim)",
                                 r.out.splitlines())),
    S("no_auth_lock_leaves_auth_writable_by_its_owner", "variant",
      lambda t, r, d: (t.assertEqual(0o600, (d / "agent/auth.json").stat().st_mode & 0o777),
                       t.assertIn("    agent/auth.json is writable (--no-auth-lock)", r.out.splitlines()))),
    S("no_auth_lock_keeps_an_existing_auth_file", "variant",
      lambda t, r, d: t.assertEqual('{"k":1}\n', _read(d, "agent/auth.json"))),
    # the skills manifest's edges
    S("without_a_manifest_an_old_skill_is_not_touched", "misc",
      lambda t, r, d: t.assertEqual("x\n", _read(d, "agent/skills/old-managed/SKILL.md"))),
    S("a_stale_skill_that_is_a_link_goes_without_its_target", "variant",
      lambda t, r, d: (t.assertFalse(os.path.lexists(d / "agent/skills/gone")),
                       t.assertEqual("keep\n", _read(d, "elsewhere/kept/SKILL.md")))),
    S("a_template_folder_without_skill_md_is_not_a_skill", "misc",
      lambda t, r, d: (t.assertFalse((d / "agent/skills/no-skill-file").exists()),
                       t.assertNotIn("no-skill-file", _read(d, "agent/skills/.elm-pi-managed")))),
    S("a_skills_supporting_files_are_copied", "misc",
      lambda t, r, d: t.assertEqual("print(1)\n", _read(d, "agent/skills/with-files/scripts/run.py"))),
    # A skill of yours that takes the name of a new one of the repo's is replaced.
    S("your_skill_with_the_name_of_a_new_template_skill_is_replaced", "misc",
      lambda t, r, d: t.assertEqual("---\nname: with-files\n---\n", _read(d, "agent/skills/with-files/SKILL.md"))),
    S("agent_dir_in_an_agent_definition_becomes_this_install", "misc",
      lambda t, r, d: t.assertEqual(f"dir: {d}/agent/x\n", _read(d, "agent/agents/probe.md"))),
    S("a_required_extension_with_no_template_stops_the_install", "required_missing",
      lambda t, r, d: (t.assertEqual(1, r.rc),
                       t.assertIn("DIE required policy extension was not installed: todo.ts", r.out))),
    # A stale copy passes: the check is for presence, not for being current.
    S("a_required_extension_with_no_template_but_an_old_copy_passes", "misc",
      lambda t, r, d: (t.assertEqual(0, r.rc, r.out), t.assertEqual("old\n", _read(d, "agent/extensions/todo.ts")))),
    S("brew_early_on_the_accounts_path_is_linked", "misc",
      lambda t, r, d: t.assertIn(f"    agent/bin/brew -> scripts/brew (Homebrew at {d}/fakebrew)", r.out.splitlines())),
    # elm_clean_path prints no trailing newline: unless one is added, the last
    # PATH entry is glued to /opt/homebrew/bin and neither is ever looked in.
    S("brew_last_on_the_accounts_path_is_linked", "fresh install",
      check=lambda t, r, d: (t.assertEqual(f"{d}/scripts/brew", os.readlink(d / "agent/bin/brew")),
                       t.assertIn(f"    agent/bin/brew -> scripts/brew (Homebrew at {d}/fakebrew)", r.out.splitlines()))),
    S("a_stale_brew_link_goes_when_there_is_no_homebrew", "variant",
      lambda t, r, d: t.assertFalse(os.path.lexists(d / "agent/bin/brew")),
      skip="this machine has Homebrew in a standard place" if _brew_anywhere() else None),
    S("an_install_path_with_a_space_works_throughout", "fresh install",
      lambda t, r, d: (t.assertEqual(0, r.rc, r.out + r.err),
                       t.assertIn(f'"{d}/agent/workflows"', _read(d, "agent/extensions/pi-permission-system/config.json")),
                       t.assertEqual(f"{d}/pi", os.readlink(d / "agent/bin/pi")))),
]


# When each config was last written: install_if_absent leaves one that exists alone.
HASH_SHELL = ('"$PY" -c ' + q("import json,os; print(json.dumps({p: os.stat('agent/' + p).st_mtime_ns for p in "
                              + repr([*ABSENT_CONFIGS, "extensions/pi-permission-system/config.json"]) + "}))"))


@generate
class AgentRefreshTests(ShBatch):
    """bootstrap.sh section 3: what each run writes, refreshes and keeps under agent/."""

    CASES = AGENT_CASES

    @classmethod
    def prepare(cls, case, d):
        pass

    @classmethod
    def setUpClass(cls):
        # One install per scenario, not per case: every case reads its scenario's.
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            names = sorted({c.kw["scenario"] for c in cls.CASES})
            homes = {}
            bodies = []
            for i, name in enumerate(names):
                d = cls.tmp / f"s{i}" / name
                d.mkdir(parents=True)
                agent_tree(d)
                homes[name] = d
                sc = SCENARIOS[name]
                between = sc.get("between")
                if name == "twice":
                    between = (SNAP_SHELL + "\n" + HASH_SHELL + ' > "$HERE/.hash1"')
                body = agent_body(d, sc.get("before", ""), between, flags=sc.get("flags"))
                if name == "twice":
                    body += "\n" + SNAP_SHELL.replace(".snap1", ".snap2") + "\n" + HASH_SHELL + ' > "$HERE/.hash2"'
                bodies.append(body)
            env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(cls.tmp), "LANG": "C", "TMPDIR": str(cls.tmp)}
            runs = run_sh_batch(AGENT_PRELUDE, bodies, env, cls.tmp)
            by_name = dict(zip(names, runs))
            cls.results = {c.name: by_name[c.kw["scenario"]] for c in cls.CASES}
            cls.dirs = {c.name: homes[c.kw["scenario"]] for c in cls.CASES}
        except BaseException:
            cleanup_tree(cls.tmp)
            raise

    def test_every_scenario_but_the_stopped_one_finishes(self):
        for case in self.CASES:
            if case.kw["scenario"] != "required_missing":
                r = self.results[case.name]
                self.assertEqual(0, r.rc, f"{case.kw['scenario']}:\n{r.out}\n{r.err}")


# =====================================================================================
# bash: install_tool and the sha256 tool
# =====================================================================================

SHA_BLOCK = block(BOOTSTRAP, "if command -v sha256sum >/dev/null 2>&1; then", "# --- disk space")
INSTALL_TOOL = block(BOOTSTRAP, "  install_tool() {", "\n  GH=https://github.com")
WANT_TOOL = re.search(r"^  want_tool\(\) \{.*\}$", BOOTSTRAP, re.M).group(0)

# curl, stubbed: serves files from $HERE/srv by the URL's last path part, logs
# every URL, and fails like `curl -f` for one it does not have.
CURL_STUB = r'''
curl() {
  local out="" url="" a
  while [ $# -gt 0 ]; do
    case "$1" in -o) out="$2"; shift 2; continue ;; --retry|-m|-H|-d) shift 2; continue ;; -*) shift; continue ;; esac
    url="$1"; shift
  done
  echo "$url" >> "$HERE/curl.log"
  local f="$HERE/srv/${url##*/}"
  [ -f "$f" ] || return 22
  if [ -n "$out" ]; then ln "$f" "$out" 2>/dev/null || cp "$f" "$out"; else cat "$f"; fi
}
'''


def tool_script(name, version, rc=0):
    return f'#!/bin/sh\necho "{name} {version}"\nexit {rc}\n'


def tgz(members, xz=False):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:xz" if xz else "w:gz") as tar:
        for name, text in members.items():
            data = text.encode()
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def zipped(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in members.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = 0o755 << 16
            z.writestr(info, text)
    return buf.getvalue()


BIN = tool_script("x", "1.2.3").encode()
TOOL_SHARED = {"x-1.2.3": BIN.decode(), "x-1.2.2": tool_script("x", "1.2.2"),
               "x-broken": tool_script("x", "1.2.3", rc=3), "x-0.17.10": tool_script("x", "0.17.10"),
               "x-rc1": tool_script("x", "1.2.3", rc=1)}


def T(name, check, bug=None, args=("x", "1.2.3", "x-asset", "https://h/dl/x-asset", ""), asset=BIN,
      sums=None, srv=None, pre="", toolset="x,fd,ast-grep,uv", **kw):
    """A case: install_tool called with args, the asset served by the stub
    curl (or not, when asset is None), sums the lines of templates/tools.sha256."""
    return C(name, check=check, bug=bug, args=args, asset=asset, sums=sums, srv=srv or {}, pre=pre,
             toolset=toolset, **kw)


def _installed(d, name="x"):
    p = d / "agent/bin" / name
    return p.read_bytes() if p.is_file() else None


def _cache(d, rel="x/1.2.3/x-asset"):
    p = d / "cache" / rel
    return p.read_bytes() if p.is_file() else None


def _curls(d):
    p = d / "curl.log"
    return p.read_text().splitlines() if p.exists() else []


GOOD = [f"{sha(BIN)}  x/1.2.3/x-asset"]
OTHER = sha(b"something else")

TOOL_CASES = [
    T("a_checksummed_binary_is_installed", sums=GOOD,
      check=lambda t, r, d: (t.assertEqual(BIN, _installed(d)),
                             t.assertIn("    x 1.2.3 -> agent/bin/x", r.out.splitlines()))),
    T("an_installed_tool_is_mode_755", sums=GOOD,
      check=lambda t, r, d: t.assertEqual(0o755, (d / "agent/bin/x").stat().st_mode & 0o777)),
    T("a_verified_download_is_kept_in_the_cache", sums=GOOD,
      check=lambda t, r, d: t.assertEqual(BIN, _cache(d))),
    T("a_wrong_checksum_stops_the_install", sums=[f"{OTHER}  x/1.2.3/x-asset"],
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE checksum mismatch for x-asset", r.out),
                             t.assertIsNone(_installed(d)))),
    T("a_wrong_checksum_is_not_cached", sums=[f"{OTHER}  x/1.2.3/x-asset"],
      check=lambda t, r, d: t.assertIsNone(_cache(d))),
    T("no_checksum_anywhere_installs_with_a_warning_naming_the_hash", sums=[],
      check=lambda t, r, d: (t.assertEqual(BIN, _installed(d)),
                             t.assertIn(f"WARN no published checksum for x-asset - installing unverified ({sha(BIN)})",
                                        r.out.splitlines()))),
    T("a_checksum_for_another_version_is_not_used", sums=[f"{OTHER}  x/1.2.4/x-asset"],
      check=lambda t, r, d: (t.assertEqual(BIN, _installed(d)), t.assertIn("installing unverified", r.out))),
    T("a_checksum_for_another_tool_with_the_same_asset_is_not_used", sums=[f"{OTHER}  y/1.2.3/x-asset"],
      check=lambda t, r, d: (t.assertEqual(BIN, _installed(d)), t.assertIn("installing unverified", r.out))),
    T("a_published_two_column_checksum_is_used", sums=[],
      args=("x", "1.2.3", "x-asset", "https://h/dl/x-asset", "https://h/dl/x.sha256"),
      srv={"x.sha256": f"{OTHER}  other-asset\n{sha(BIN)}  x-asset\n"},
      check=lambda t, r, d: (t.assertEqual(BIN, _installed(d)), t.assertNotIn("unverified", r.out))),
    T("a_published_bare_checksum_is_used", sums=[],
      args=("x", "1.2.3", "x-asset", "https://h/dl/x-asset", "https://h/dl/x.sha256"),
      srv={"x.sha256": f"{sha(BIN)}\n"},
      check=lambda t, r, d: (t.assertEqual(BIN, _installed(d)), t.assertNotIn("unverified", r.out))),
    T("a_wrong_published_checksum_stops_the_install", sums=[],
      args=("x", "1.2.3", "x-asset", "https://h/dl/x-asset", "https://h/dl/x.sha256"),
      srv={"x.sha256": f"{OTHER}  x-asset\n"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE checksum mismatch for x-asset", r.out))),
    T("a_published_list_without_this_asset_is_no_checksum", sums=[],
      args=("x", "1.2.3", "x-asset", "https://h/dl/x-asset", "https://h/dl/x.sha256"),
      srv={"x.sha256": f"{OTHER}  other-asset\n"},
      check=lambda t, r, d: (t.assertEqual(BIN, _installed(d)), t.assertIn("installing unverified", r.out))),
    # Under pipefail a failed fetch inside the assignment would fail it, and
    # set -e end the install there with no message at all.
    T("a_published_checksum_that_cannot_be_fetched_is_no_checksum", sums=[],
      args=("x", "1.2.3", "x-asset", "https://h/dl/x-asset", "https://h/dl/missing.sha256"),
      check=lambda t, r, d: (t.assertEqual(BIN, _installed(d)), t.assertIn("installing unverified", r.out),
                             t.assertIn("WARN could not fetch the published checksum https://h/dl/missing.sha256",
                                        r.out.splitlines()))),
    # sha256sum's binary-mode marker ("hash *asset") is the same checksum.
    T("a_published_checksum_in_binary_mode_form_is_used", sums=[],
      args=("x", "1.2.3", "x-asset", "https://h/dl/x-asset", "https://h/dl/x.sha256"),
      srv={"x.sha256": f"{sha(BIN)} *x-asset\n"},
      check=lambda t, r, d: t.assertNotIn("unverified", r.out)),
    T("a_wrong_published_checksum_in_binary_mode_form_stops_the_install", sums=[],
      args=("x", "1.2.3", "x-asset", "https://h/dl/x-asset", "https://h/dl/x.sha256"),
      srv={"x.sha256": f"{OTHER} *x-asset\n"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE checksum mismatch for x-asset", r.out))),
    T("the_repos_checksum_wins_and_the_published_one_is_not_fetched", sums=GOOD,
      args=("x", "1.2.3", "x-asset", "https://h/dl/x-asset", "https://h/dl/x.sha256"),
      srv={"x.sha256": f"{OTHER}  x-asset\n"},
      check=lambda t, r, d: (t.assertEqual(BIN, _installed(d)), t.assertEqual(["https://h/dl/x-asset"], _curls(d)))),
    T("a_wrong_repo_checksum_is_not_saved_by_a_right_published_one", sums=[f"{OTHER}  x/1.2.3/x-asset"],
      args=("x", "1.2.3", "x-asset", "https://h/dl/x-asset", "https://h/dl/x.sha256"),
      srv={"x.sha256": f"{sha(BIN)}  x-asset\n"},
      check=lambda t, r, d: t.assertEqual(1, r.rc)),
    T("a_failed_download_is_a_warning_not_a_failure", asset=None, sums=GOOD,
      check=lambda t, r, d: (t.assertEqual(0, r.rc), t.assertIsNone(_installed(d)),
                             t.assertIn("WARN could not download x-asset - x not installed", r.out.splitlines()))),
    T("the_pinned_version_already_there_is_not_downloaded", sums=GOOD,
      pre='ln "$SHARED/x-1.2.3" agent/bin/x',
      check=lambda t, r, d: (t.assertEqual([], _curls(d)),
                             t.assertIn("    x 1.2.3 already in agent/bin", r.out.splitlines()))),
    T("another_version_already_there_is_replaced", sums=GOOD,
      pre='ln "$SHARED/x-1.2.2" agent/bin/x',
      check=lambda t, r, d: t.assertEqual(BIN, _installed(d))),
    T("a_binary_there_that_does_not_run_is_replaced", sums=GOOD,
      pre='ln "$SHARED/x-broken" agent/bin/x',
      check=lambda t, r, d: t.assertEqual(BIN, _installed(d))),
    # The version is matched as a whole word: as a substring, 0.17.10 would
    # pass for a pin of 0.17.1 and never be brought back to it.
    T("a_longer_version_containing_the_pin_is_not_taken_for_it", sums=[f"{sha(BIN)}  x/0.17.1/x-asset"],
      args=("x", "0.17.1", "x-asset", "https://h/dl/x-asset", ""),
      pre='ln "$SHARED/x-0.17.10" agent/bin/x',
      check=lambda t, r, d: t.assertEqual(["https://h/dl/x-asset"], _curls(d))),
    T("force_downloads_even_the_pinned_version", sums=GOOD, force=1,
      pre='ln "$SHARED/x-1.2.3" agent/bin/x',
      check=lambda t, r, d: (t.assertEqual(["https://h/dl/x-asset"], _curls(d)), t.assertEqual(BIN, _installed(d)))),
    T("force_bypasses_the_cache", sums=GOOD, force=1, cached=BIN,
      check=lambda t, r, d: t.assertEqual(["https://h/dl/x-asset"], _curls(d))),
    T("a_cached_archive_is_used_without_a_download", sums=GOOD, cached=BIN, asset=None,
      check=lambda t, r, d: (t.assertEqual([], _curls(d)), t.assertEqual(BIN, _installed(d)),
                             t.assertIn("    x-asset from the tool cache", r.out.splitlines()))),
    T("a_corrupted_cache_entry_fails_like_a_bad_download", sums=GOOD, cached=b"tampered", asset=None,
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE checksum mismatch for x-asset", r.out))),
    T("an_unwritable_cache_does_not_stop_the_install", sums=GOOD, pre="printf x > cache",
      check=lambda t, r, d: (t.assertEqual(0, r.rc), t.assertEqual(BIN, _installed(d)))),
    T("a_tool_not_in_elm_pi_tools_is_skipped_without_a_download", sums=GOOD, toolset="fd,rg",
      check=lambda t, r, d: (t.assertEqual([], _curls(d)), t.assertIsNone(_installed(d)),
                             t.assertIn("    x skipped (not in ELM_PI_TOOLS)", r.out.splitlines()))),
    T("elm_pi_tools_names_whole_tools_not_prefixes", sums=GOOD, toolset="xy,ax",
      check=lambda t, r, d: t.assertIsNone(_installed(d))),
    T("a_binary_in_a_folder_of_a_tarball_is_found",
      args=("fd", "1.2.3", "fd.tar.gz", "https://h/dl/fd.tar.gz", ""),
      asset=tgz({"fd-v1/README": "r", "fd-v1/fd": tool_script("fd", "1.2.3")}), sums="auto",
      check=lambda t, r, d: t.assertEqual(tool_script("fd", "1.2.3").encode(), _installed(d, "fd"))),
    T("a_tarball_without_the_binary_is_a_warning",
      args=("fd", "1.2.3", "fd.tar.gz", "https://h/dl/fd.tar.gz", ""),
      asset=tgz({"fd-v1/README": "r"}), sums="auto",
      check=lambda t, r, d: (t.assertEqual(0, r.rc), t.assertIsNone(_installed(d, "fd")),
                             t.assertIn("WARN could not unpack fd from fd.tar.gz - fd not installed", r.out.splitlines()))),
    T("an_xz_tarball_is_unpacked",
      args=("uv", "1.2.3", "uv.tar.xz", "https://h/dl/uv.tar.xz", ""),
      asset=tgz({"uv-dir/uv": tool_script("uv", "1.2.3"), "uv-dir/uvx": "x"}, xz=True), sums="auto",
      check=lambda t, r, d: (t.assertEqual(tool_script("uv", "1.2.3").encode(), _installed(d, "uv")),
                             t.assertIsNone(_installed(d, "uvx")))),
    # The ast-grep zip also has `sg`, a real command on Linux: never installed.
    T("a_zip_is_unpacked_and_only_the_named_binary_installed",
      args=("ast-grep", "1.2.3", "app.zip", "https://h/dl/app.zip", ""),
      asset=zipped({"ast-grep": tool_script("ast-grep", "1.2.3"), "sg": tool_script("sg", "1.2.3")}), sums="auto",
      check=lambda t, r, d: (t.assertEqual(tool_script("ast-grep", "1.2.3").encode(), _installed(d, "ast-grep")),
                             t.assertIsNone(_installed(d, "sg")))),
    T("a_downloaded_binary_that_does_not_run_is_removed",
      asset=tool_script("x", "1.2.3", rc=1).encode(), sums="auto",
      check=lambda t, r, d: (t.assertEqual(0, r.rc), t.assertIsNone(_installed(d)),
                             t.assertIn("WARN the downloaded x does not run on this machine - x not installed",
                                        r.out.splitlines()))),
    T("without_a_sha256_tool_the_install_stops_saying_why", sums=GOOD, pre="SHA256_CMD=()",
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE cannot verify x-asset without a sha256 tool", r.out))),
    T("the_download_url_is_the_one_given", sums=GOOD,
      args=("x", "1.2.3", "x-asset", "https://h/elsewhere/x-asset", ""),
      check=lambda t, r, d: t.assertEqual(["https://h/elsewhere/x-asset"], _curls(d))),
    T("the_cache_is_keyed_by_tool_version_and_asset", sums=GOOD,
      check=lambda t, r, d: t.assertEqual(["x/1.2.3/x-asset"],
                                          [str(p.relative_to(d / "cache")) for p in (d / "cache").rglob("*") if p.is_file()])),
]


@generate
class InstallToolTests(ShBatch):
    """install_tool(): pinned checksums, published ones, the cache, and the archive forms."""

    CASES = TOOL_CASES

    @classmethod
    def shared(cls, path):
        cls.shared_dir = shared_executables(path, TOOL_SHARED)

    @classmethod
    def prepare(cls, case, d):
        kw = case.kw
        asset = kw["asset"]
        name = kw["args"][2]
        sums = kw["sums"]
        if sums == "auto":
            sums = [f"{sha(asset)}  {kw['args'][0]}/{kw['args'][1]}/{name}"]
        touch(d / "templates/tools.sha256", "# comment\n" + "".join(f"{l}\n" for l in sums or []))
        (d / "agent/bin").mkdir(parents=True)
        (d / "srv").mkdir()
        same = next((n for n, text in TOOL_SHARED.items() if text.encode() == asset), None)
        if same:
            os.link(cls.shared_dir / same, d / "srv" / name)
        elif asset is not None:
            touch(d / "srv" / name, asset)
        for fname, text in kw["srv"].items():
            touch(d / "srv" / fname, text)
        if kw.get("cached") is not None:
            touch(d / "cache" / kw["args"][0] / kw["args"][1] / name, kw["cached"])

    @classmethod
    def body(cls, case, d):
        kw = case.kw
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", 'HERE="$PWD"', f"SHARED={q(cls.shared_dir)}", STUBS, SHA_BLOCK, CURL_STUB,
            f"TOOLSET={q(kw['toolset'])}", WANT_TOOL, 'TOOL_CACHE="$HERE/cache"', 'TOOLS_TMP="$(mktemp -d "$HERE/tt.XXXXXX")"',
            f"FORCE={kw.get('force', 0)}", kw["pre"], INSTALL_TOOL,
            "install_tool " + " ".join(q(a) for a in kw["args"]), 'echo "@@DONE"'])


# =====================================================================================
# bash: the Node download
# =====================================================================================

NODE_BLOCK = block(BOOTSTRAP, 'say "Node $NODE_VERSION"', "# elm_install_env already put .node/bin first")


def node_tarball(version, os_, arch):
    top = f"node-{version}-{os_}-{arch}"
    return tgz({f"{top}/bin/node": f'#!/bin/sh\necho {version}\n', f"{top}/lib/node_modules/npm/bin/npm-cli.js": ""})


def N(name, check, uname=("Darwin", "arm64"), tar=("darwin", "arm64"), sums="good", pre="", bug=None):
    return C(name, check=check, bug=bug, uname=uname, tar=tar, sums=sums, pre=pre)


NODE_CASES = [
    N("a_verified_node_is_unpacked_into_dot_node",
      check=lambda t, r, d: (t.assertEqual(0, r.rc, r.out), t.assertIn("    installed v9.8.7", r.out.splitlines()),
                             t.assertTrue((d / ".node/lib/node_modules/npm/bin/npm-cli.js").exists()))),
    N("node_comes_from_nodejs_org_with_its_shasums",
      check=lambda t, r, d: t.assertEqual(["https://nodejs.org/dist/v9.8.7/node-v9.8.7-darwin-arm64.tar.gz",
                                           "https://nodejs.org/dist/v9.8.7/SHASUMS256.txt"], _curls(d))),
    N("a_node_tarball_that_does_not_match_stops_the_install", sums="bad",
      check=lambda t, r, d: (t.assertEqual(1, r.rc),
                             t.assertIn("DIE checksum mismatch for node-v9.8.7-darwin-arm64.tar.gz", r.out),
                             t.assertFalse((d / ".node").exists()))),
    # A grep finding no line would fail the pipeline under pipefail, and set -e
    # end the install before the "checksum mismatch" message is reached.
    N("a_node_tarball_not_in_shasums_stops_the_install_saying_why", sums="absent",
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE checksum mismatch", r.out))),
    N("a_node_tarball_not_in_shasums_is_never_unpacked", sums="absent",
      check=lambda t, r, d: (t.assertNotEqual(0, r.rc), t.assertFalse((d / ".node").exists()))),
    # " $TAR$": the .tar.xz line, or a longer name, is not this file's hash.
    N("only_the_exact_tarball_line_in_shasums_counts", sums="only-siblings",
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE checksum mismatch", r.out))),
    N("the_right_node_already_there_is_kept_without_a_download",
      pre='mkdir -p .node/bin && printf "#!/bin/sh\\necho v9.8.7\\n" > .node/bin/node && chmod 755 .node/bin/node',
      check=lambda t, r, d: (t.assertEqual([], _curls(d)), t.assertIn("    already present: v9.8.7", r.out.splitlines()))),
    N("another_node_is_replaced_whole",
      pre='mkdir -p .node/bin && printf "#!/bin/sh\\necho v1.0.0\\n" > .node/bin/node && chmod 755 .node/bin/node && touch .node/leftover',
      check=lambda t, r, d: (t.assertEqual("#!/bin/sh\necho v9.8.7\n", _read(d, ".node/bin/node")),
                             t.assertFalse((d / ".node/leftover").exists()))),
    N("an_intel_mac_gets_the_x64_build", uname=("Darwin", "x86_64"), tar=("darwin", "x64"),
      check=lambda t, r, d: t.assertIn("https://nodejs.org/dist/v9.8.7/node-v9.8.7-darwin-x64.tar.gz", _curls(d))),
    N("arm_linux_gets_the_arm64_build", uname=("Linux", "aarch64"), tar=("linux", "arm64"),
      check=lambda t, r, d: (t.assertEqual(0, r.rc), t.assertIn(
          "https://nodejs.org/dist/v9.8.7/node-v9.8.7-linux-arm64.tar.gz", _curls(d)))),
    N("amd64_is_x64", uname=("Linux", "amd64"), tar=("linux", "x64"),
      check=lambda t, r, d: t.assertIn("https://nodejs.org/dist/v9.8.7/node-v9.8.7-linux-x64.tar.gz", _curls(d))),
    N("an_unsupported_system_is_refused_before_any_download", uname=("FreeBSD", "amd64"),
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE unsupported OS: FreeBSD", r.out),
                             t.assertEqual([], _curls(d)))),
    N("an_unsupported_cpu_is_refused_before_any_download", uname=("Linux", "riscv64"),
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE unsupported architecture: riscv64", r.out),
                             t.assertEqual([], _curls(d)))),
]


@generate
class NodeDownloadTests(ShBatch):
    """Step 1: the bundled Node, from nodejs.org, checked against SHASUMS256.txt."""

    CASES = NODE_CASES

    @classmethod
    def prepare(cls, case, d):
        kw = case.kw
        os_, arch = kw["tar"]
        name = f"node-v9.8.7-{os_}-{arch}.tar.gz"
        data = node_tarball("v9.8.7", os_, arch)
        touch(d / "srv" / name, data)
        lines = {"good": f"{sha(data)}  {name}\n", "bad": f"{OTHER}  {name}\n", "absent": f"{OTHER}  other.tar.gz\n",
                 "only-siblings": f"{sha(data)}  {name[:-3]}.xz\n{sha(data)}  {name}.sig\n"}[kw["sums"]]
        touch(d / "srv/SHASUMS256.txt", lines)

    @classmethod
    def body(cls, case, d):
        s, m = case.kw["uname"]
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", 'HERE="$PWD"', STUBS, SHA_BLOCK, CURL_STUB,
            f'uname() {{ case "$1" in -s) echo {q(s)} ;; -m) echo {q(m)} ;; esac; }}',
            "NODE_VERSION=v9.8.7", 'TMP=""', case.kw["pre"], NODE_BLOCK])


# =====================================================================================
# bash: when pi and the packages are rebuilt, and the rollback trap
# =====================================================================================

NEED_PI_BLOCK = block(BOOTSTRAP, 'CORE_MANIFEST_DIGEST="$(manifest_digest package.json core)"',
                      'if [ "$NEED_PI" = "1" ]; then')
NEED_PKG_BLOCK = block(BOOTSTRAP, '  PACKAGE_STAMP="agent/npm/node_modules/.elm-pi-lock.sha256"',
                       '  if [ "$NEED_PACKAGES" = "1" ]; then\n    install_packages')


def P(name, want, out=None, rc=0, **env):
    base = {"FORCE": "0", "UPDATE": "0", "FORCE_PACKAGES": "0", "PI_INSTALLED": "1.0.0", "PI_VERSION": "",
            "TESTED": "1.0.0", "DIGEST": "d1", "STAMP": "d1"}
    return C(name, want=want, out=out, rc=rc, env={**base, **env},
             check=lambda t, r, d: (t.assertEqual(rc, r.rc, r.out + r.err),
                                    rc or t.assertEqual(want, r.vars.get("NEED_PI")),
                                    out is None or t.assertIn(out, r.out)))


NEED_PI_CASES = [
    P("nothing_changed_keeps_pi", "0"),
    P("force_reinstalls_pi", "1", FORCE="1"),
    P("update_reinstalls_pi", "1", UPDATE="1"),
    P("no_pi_installed_installs_it", "1", PI_INSTALLED=""),
    P("pi_version_other_than_installed_reinstalls", "1", out="    1.0.0 -> 2.0.0", PI_VERSION="2.0.0"),
    P("pi_version_equal_to_installed_keeps_it", "0", PI_VERSION="1.0.0"),
    P("force_packages_brings_pi_back_to_the_tested_version", "1",
      out="    1.1.0 -> 1.0.0, the tested version (--force-packages)", FORCE_PACKAGES="1", PI_INSTALLED="1.1.0"),
    P("force_packages_at_the_tested_version_keeps_pi", "0", FORCE_PACKAGES="1"),
    P("force_packages_without_a_tested_version_keeps_pi", "0", FORCE_PACKAGES="1", TESTED="", PI_INSTALLED="1.1.0"),
    P("a_tested_version_moving_alone_does_not_reinstall", "0", TESTED="1.2.0"),
    P("no_stamp_reinstalls_saying_the_list_changed", "1", out="    dependency list changed", STAMP=None),
    P("a_stamp_for_another_list_reinstalls", "1", out="    dependency list changed", STAMP="d0"),
    P("pi_version_is_reported_over_force_packages", "1", out="    1.1.0 -> 3.0.0\n",
      PI_VERSION="3.0.0", FORCE_PACKAGES="1", PI_INSTALLED="1.1.0"),
    P("a_manifest_that_cannot_be_hashed_stops_the_install", None, out="DIE cannot hash package.json", rc=1,
      DIGEST="FAIL"),
    P("a_versions_file_that_cannot_be_read_stops_the_install", None, out="DIE cannot read config/versions.json", rc=1,
      TESTED="FAIL"),
]


@generate
class PiRebuildTests(ShBatch):
    """NEED_PI: when step 2 reinstalls pi, and what it says about why."""

    CASES = NEED_PI_CASES

    @classmethod
    def prepare(cls, case, d):
        if case.kw["env"]["STAMP"] is not None:
            touch(d / "node_modules/.elm-pi-lock.sha256", case.kw["env"]["STAMP"] + "\n")

    @classmethod
    def body(cls, case, d):
        e = case.kw["env"]
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", STUBS,
            f"FORCE={e['FORCE']}; UPDATE={e['UPDATE']}; FORCE_PACKAGES={e['FORCE_PACKAGES']}",
            f"PI_INSTALLED={q(e['PI_INSTALLED'])}; PI_VERSION={q(e['PI_VERSION'])}",
            f'manifest_digest() {{ [ {q(e["DIGEST"])} != FAIL ] && echo {q(e["DIGEST"])}; }}',
            f'fake_pins() {{ [ {q(e["TESTED"])} != FAIL ] && echo {q(e["TESTED"])}; }}', "PINS=(fake_pins)",
            NEED_PI_BLOCK, "_v NEED_PI"])


def K(name, want, verify="ok", out=None, **env):
    base = {"FORCE": "0", "UPDATE": "0", "FORCE_PACKAGES": "0", "STAMP": "p1"}
    return C(name, want=want, verify=verify, out=out, env={**base, **env},
             check=lambda t, r, d: (t.assertEqual(0, r.rc, r.out + r.err), t.assertEqual(want, r.vars.get("NEED_PACKAGES")),
                                    out is None or t.assertIn(out, r.out)))


NEED_PKG_CASES = [
    K("packages_that_match_are_kept", "0"),
    K("force_reinstalls_the_packages", "1", FORCE="1"),
    K("update_reinstalls_the_packages", "1", UPDATE="1"),
    K("force_packages_reinstalls_the_packages", "1", FORCE_PACKAGES="1"),
    K("no_package_stamp_reinstalls", "1", STAMP=None),
    K("a_package_stamp_for_another_manifest_reinstalls", "1", STAMP="p0"),
    K("an_incomplete_tree_is_reinstalled_and_the_problem_shown", "1", verify="fail",
      out="    installed packages do not match agent/settings.json - reinstalling:"),
]


@generate
class PackageRebuildTests(ShBatch):
    """NEED_PACKAGES: a changed manifest, a flag, or a tree verify_install finds incomplete."""

    CASES = NEED_PKG_CASES

    @classmethod
    def prepare(cls, case, d):
        if case.kw["env"]["STAMP"] is not None:
            touch(d / "agent/npm/node_modules/.elm-pi-lock.sha256", case.kw["env"]["STAMP"] + "\n")

    @classmethod
    def body(cls, case, d):
        e = case.kw["env"]
        verify = "0" if case.kw["verify"] == "ok" else "1"
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", 'HERE="$PWD"', STUBS,
            f"FORCE={e['FORCE']}; UPDATE={e['UPDATE']}; FORCE_PACKAGES={e['FORCE_PACKAGES']}",
            "PACKAGE_MANIFEST_DIGEST=p1", f'elm_py() {{ echo "  verify: missing x"; return {verify}; }}',
            NEED_PKG_BLOCK, "_v NEED_PACKAGES"])


TRAP_BLOCK = block(BOOTSTRAP, "restore() {   # $1 = the kept tree", "trap cleanup EXIT")


def R(name, script, check):
    return C(name, script=script, check=check)


TRAP_CASES = [
    R("a_failed_run_puts_the_previous_pi_back",
      'mkdir -p node_modules/new .elm-pi-old-core/old; CORE_OLD="$HERE/.elm-pi-old-core"; exit 3',
      lambda t, r, d: (t.assertEqual(3, r.rc), t.assertTrue((d / "node_modules/old").is_dir()),
                       t.assertFalse((d / "node_modules/new").exists()),
                       t.assertIn("    put back the previous node_modules", r.err))),
    R("a_failed_run_puts_the_previous_packages_back",
      'mkdir -p agent/npm/node_modules/new .pk/old; PKG_OLD="$HERE/.pk"; exit 1',
      lambda t, r, d: (t.assertTrue((d / "agent/npm/node_modules/old").is_dir()),
                       t.assertIn("    put back the previous agent/npm/node_modules", r.err))),
    R("a_run_that_finishes_drops_the_previous_trees",
      'mkdir -p node_modules/new .co/old .pk/old; CORE_OLD="$HERE/.co"; PKG_OLD="$HERE/.pk"; exit 0',
      lambda t, r, d: (t.assertTrue((d / "node_modules/new").is_dir()), t.assertFalse((d / ".co").exists()),
                       t.assertFalse((d / ".pk").exists()), t.assertEqual("", r.err))),
    R("a_failure_before_anything_was_replaced_changes_nothing",
      'mkdir -p node_modules/current; exit 2',
      lambda t, r, d: (t.assertTrue((d / "node_modules/current").is_dir()), t.assertEqual("", r.err))),
    R("every_temporary_tree_is_removed_either_way",
      'for v in TMP TOOLS_TMP PYPI_TMP CORE_STAGE PKG_STAGE VERIFY_ERR; do mkdir -p "$HERE/$v"; eval "$v=\\$HERE/\\$v"; done; exit 5',
      lambda t, r, d: t.assertEqual([], sorted(p.name for p in d.iterdir()))),
    R("a_kept_tree_that_is_gone_is_not_an_error",
      'mkdir -p node_modules/new; CORE_OLD="$HERE/.missing"; exit 4',
      lambda t, r, d: (t.assertEqual(4, r.rc), t.assertTrue((d / "node_modules/new").is_dir()))),
]


@generate
class RollbackTrapTests(ShBatch):
    """The EXIT trap: the replaced pi and packages go back when a run fails."""

    CASES = TRAP_CASES

    @classmethod
    def body(cls, case, d):
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", 'HERE="$PWD"',
            'TMP=""; TOOLS_TMP=""; PYPI_TMP=""; CORE_STAGE=""; PKG_STAGE=""; VERIFY_ERR=""; CORE_OLD=""; PKG_OLD=""',
            TRAP_BLOCK, "trap cleanup EXIT", case.kw["script"]])


SHA_CASES = [
    C("sha256_of_prints_the_files_hash_alone",
      check=lambda t, r, d: t.assertEqual(sha(b"hello\n"), r.vars["OUT"])),
    C("sha256_of_without_a_tool_fails_saying_so", none=True,
      check=lambda t, r, d: (t.assertEqual("1", r.vars["RC"]),
                             t.assertIn("neither sha256sum nor shasum is installed", r.err))),
]


@generate
class Sha256Tests(ShBatch):
    """sha256_of: the hash on stdout, or a non-zero return that names the missing tool."""

    CASES = SHA_CASES

    @classmethod
    def body(cls, case, d):
        return "\n".join([f"cd {q(d)}", "printf 'hello\\n' > f", SHA_BLOCK,
                          "SHA256_CMD=()" if case.kw.get("none") else "",
                          'OUT="$(sha256_of f)"; RC=$?', "_v OUT RC"])


# =====================================================================================
# bash: the agent's Python and the PyPI index
# =====================================================================================

PYTHON_BLOCK = block(BOOTSTRAP, 'if [ "$WITH_PYTHON" = "1" ]; then\n  say "the agent\'s Python (agent/python)"',
                     "# --- 3d. an offline search of PyPI")
PYPI_BLOCK = block(BOOTSTRAP, 'if [ "$WITH_PYPI_INDEX" = "1" ]; then\n  say "offline PyPI search',
                   "# --- installer-owned settings")

FAKE_UV = r'''#!/bin/sh
echo "UV $* NOCONFIG=${UV_NO_CONFIG-} INDEX=${UV_INDEX_URL-unset} PYDIR=${UV_PYTHON_INSTALL_DIR-}" >> "$FAKE_LOG"
case "$1" in
  --version) echo "uv 9.9.9" ;;
  venv) for a; do env="$a"; done
        mkdir -p "$env/bin"; ln -s "$FAKE_PYTHON" "$env/bin/python" ;;
  pip) exit "${FAKE_PIP_RC:-0}" ;;
esac
'''


def Y(name, check, with_python=1, uv=True, pre="", force=0, update=0, pip_rc=0, env=None):
    return C(name, check=check, with_python=with_python, uv=uv, pre=pre, force=force, update=update, pip_rc=pip_rc,
             env=env or {})


def _uv(d):
    p = d / "uv.log"
    return p.read_text().splitlines() if p.exists() else []


PYTHON_CASES = [
    Y("a_new_agent_python_is_a_uv_managed_venv",
      check=lambda t, r, d: t.assertIn(f"UV venv --quiet --seed --managed-python --python 3.12 agent/python/env "
                                       f"NOCONFIG=1 INDEX=unset PYDIR={d}/agent/python/interpreters", _uv(d))),
    Y("the_configured_packages_are_installed_into_it",
      check=lambda t, r, d: t.assertIn("UV pip install --quiet --python agent/python/env/bin/python numpy scipy "
                                       f"NOCONFIG=1 INDEX=unset PYDIR={d}/agent/python/interpreters", _uv(d))),
    Y("a_successful_install_is_stamped_with_python_uv_and_packages",
      check=lambda t, r, d: t.assertEqual("3.12 uv 9.9.9 numpy scipy\n", _read(d, "agent/python/.elm-pi-packages"))),
    Y("an_unchanged_stamp_installs_nothing",
      pre='mkdir -p agent/python/env/bin && ln -s "$FAKE_PYTHON" agent/python/env/bin/python && '
          'echo "3.12 uv 9.9.9 numpy scipy" > agent/python/.elm-pi-packages',
      check=lambda t, r, d: (t.assertEqual(["UV --version"], [l.split(" NOCONFIG")[0] for l in _uv(d)]),
                             t.assertIn("    agent/python/env: Python 3.12, packages unchanged", r.out.splitlines()))),
    Y("a_changed_package_list_installs_again",
      pre='mkdir -p agent/python && echo "3.12 uv 9.9.9 numpy" > agent/python/.elm-pi-packages',
      check=lambda t, r, d: t.assertTrue(any(l.startswith("UV pip install") for l in _uv(d)))),
    Y("update_upgrades_the_packages", update=1,
      check=lambda t, r, d: t.assertTrue(any(l.startswith("UV pip install --quiet --python agent/python/env/bin/python "
                                                          "--upgrade numpy") for l in _uv(d)))),
    Y("force_reinstalls_the_packages", force=1,
      check=lambda t, r, d: t.assertTrue(any(" --reinstall numpy" in l for l in _uv(d)))),
    Y("a_failed_package_install_is_a_warning_and_is_not_stamped", pip_rc=1,
      check=lambda t, r, d: (t.assertEqual(0, r.rc), t.assertFalse((d / "agent/python/.elm-pi-packages").exists()),
                             t.assertIn("WARN some packages did not install; the environment works, and the next run tries again",
                                        r.out.splitlines()))),
    # The account's uv settings are not the install's.
    Y("uv_variables_from_the_account_are_dropped", env={"UV_INDEX_URL": "https://evil.example/simple"},
      check=lambda t, r, d: t.assertTrue(all("INDEX=unset" in l for l in _uv(d)))),
    Y("without_uv_the_python_is_skipped_with_a_warning", uv=False,
      check=lambda t, r, d: (t.assertEqual(0, r.rc), t.assertFalse((d / "agent/python").exists()),
                             t.assertIn("WARN uv is not in agent/bin (--no-tools, or ELM_PI_TOOLS without uv) - skipped",
                                        r.out.splitlines()))),
    Y("not_with_python_removes_an_agent_python", with_python=0, pre="mkdir -p agent/python/env/lib && touch agent/python/env/lib/x",
      check=lambda t, r, d: (t.assertFalse((d / "agent/python").exists()),
                             t.assertIn("    removed agent/python (not --with-python): the agent uses the python3 on PATH",
                                        r.out.splitlines()))),
    Y("not_with_python_and_no_agent_python_says_nothing", with_python=0,
      check=lambda t, r, d: t.assertEqual("", r.out)),
]


@generate
class AgentPythonTests(ShBatch):
    """Step 3c: agent/python, built with uv when --with-python, removed when not."""

    CASES = PYTHON_CASES

    @classmethod
    def shared(cls, path):
        cls.shared_dir = shared_executables(path, {"uv": FAKE_UV, "python": "#!/bin/sh\necho Python 3.12.0\n"})

    @classmethod
    def prepare(cls, case, d):
        if case.kw["uv"]:
            (d / "agent/bin").mkdir(parents=True)
            os.symlink(cls.shared_dir / "uv", d / "agent/bin/uv")

    @classmethod
    def body(cls, case, d):
        kw = case.kw
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", 'HERE="$PWD"', STUBS, 'CONFIG_TOOL="$HERE/scripts/elm_config.py"',
            'elm_py() { case "$4 $5" in "value pythonVersion") echo 3.12 ;; "value pythonPackages") echo numpy scipy ;; esac; }',
            f'export FAKE_LOG="$HERE/uv.log" FAKE_PIP_RC={kw["pip_rc"]} FAKE_PYTHON={q(cls.shared_dir / "python")}',
            *(f"export {k}={q(v)}" for k, v in kw["env"].items()),
            f"WITH_PYTHON={kw['with_python']}; FORCE={kw['force']}; UPDATE={kw['update']}", kw["pre"], PYTHON_BLOCK])


def _index_db(path, revision):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE meta (key TEXT, value TEXT)")
    con.execute("INSERT INTO meta VALUES ('revision', ?)", (revision,))
    con.commit()
    con.close()


REVISION = CONFIG["pypiIndex"]["revision"]

PYPI_CASES = [
    C("an_index_at_the_pinned_revision_is_kept_and_linked", db=REVISION, agent_py=True,
      check=lambda t, r, d: (t.assertIn(f"    agent/pypi-index.db: {CONFIG['pypiIndex']['dataset']} at {REVISION[:7]}, unchanged",
                                        r.out.splitlines()),
                             t.assertEqual(f"{d}/scripts/pypi-search", os.readlink(d / "agent/bin/pypi-search")),
                             t.assertEqual([], _curls(d)))),
    C("an_index_at_another_revision_is_fetched_again", db="0" * 40, agent_py=True,
      check=lambda t, r, d: t.assertEqual(
          [f"https://huggingface.co/api/datasets/{CONFIG['pypiIndex']['dataset']}/tree/{REVISION}/{CONFIG['pypiIndex']['folder']}"],
          _curls(d))),
    C("a_listing_that_cannot_be_fetched_keeps_the_old_index", db="0" * 40, agent_py=True,
      check=lambda t, r, d: (t.assertEqual(0, r.rc), t.assertTrue((d / "agent/pypi-index.db").exists()),
                             t.assertIn(f"WARN could not list the files of {CONFIG['pypiIndex']['dataset']}", r.out),
                             t.assertIn("WARN no index built this run (the existing one is kept); the next run tries again",
                                        r.out.splitlines()),
                             t.assertEqual([], [p.name for p in (d / "agent").glob(".pypi-download.*")]))),
    C("a_downloaded_file_that_does_not_match_its_listing_stops_the_install", db=None, agent_py=True, listing=True,
      check=lambda t, r, d: (t.assertEqual(1, r.rc),
                             t.assertIn("DIE checksum mismatch for packages_data/part-0.parquet", r.out))),
    C("without_the_agents_python_the_index_is_skipped", db=None, agent_py=False,
      check=lambda t, r, d: (t.assertIn("WARN needs the agent's Python (it has pyarrow), which did not build - skipped",
                                        r.out.splitlines()), t.assertEqual([], _curls(d)))),
    C("an_empty_file_is_not_taken_for_an_index", db="empty", agent_py=True,
      check=lambda t, r, d: t.assertEqual(1, len(_curls(d)))),
    C("not_with_pypi_index_removes_the_index_and_its_command", db=REVISION, with_index=0, link=True,
      check=lambda t, r, d: (t.assertFalse((d / "agent/pypi-index.db").exists()),
                             t.assertFalse(os.path.lexists(d / "agent/bin/pypi-search")),
                             t.assertIn("    removed the offline PyPI index (this install is not --with-pypi-index)",
                                        r.out.splitlines()))),
    C("not_with_pypi_index_removes_a_dangling_command", db=None, with_index=0, link=True,
      check=lambda t, r, d: t.assertFalse(os.path.lexists(d / "agent/bin/pypi-search"))),
    C("not_with_pypi_index_and_no_index_says_nothing", db=None, with_index=0,
      check=lambda t, r, d: t.assertEqual("", r.out)),
]


@generate
class PypiIndexBranchTests(ShBatch):
    """Step 3d: whether the PyPI index is kept, fetched again, skipped or removed."""

    CASES = PYPI_CASES

    @classmethod
    def prepare(cls, case, d):
        kw = case.kw
        touch(d / "config/elm-pi.json", json.dumps({"pypiIndex": CONFIG["pypiIndex"]}))
        (d / "agent/bin").mkdir(parents=True)
        if kw.get("agent_py"):
            (d / "agent/python/env/bin").mkdir(parents=True)
            os.symlink(PY, d / "agent/python/env/bin/python")
        if kw["db"] == "empty":
            touch(d / "agent/pypi-index.db", "")
        elif kw["db"]:
            _index_db(d / "agent/pypi-index.db", kw["db"])
        if kw.get("link"):
            os.symlink(d / "scripts/pypi-search", d / "agent/bin/pypi-search")
        (d / "srv").mkdir()
        if kw.get("listing"):
            touch(d / "srv" / CONFIG["pypiIndex"]["folder"], json.dumps(
                [{"path": "packages_data/part-0.parquet", "lfs": {"oid": OTHER}}]))
            touch(d / "srv/part-0.parquet", "data")

    @classmethod
    def body(cls, case, d):
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", 'HERE="$PWD"', STUBS, SHA_BLOCK, CURL_STUB,
            f'PY={q(PY)}; elm_py() {{ "$PY" -E -S "$@"; }}', 'PYPI_TMP=""',
            f"WITH_PYPI_INDEX={case.kw.get('with_index', 1)}; FORCE=0", PYPI_BLOCK])


# =====================================================================================
# bash: excluded tools still registered
# =====================================================================================

EXCLUDED_BLOCK = block(BOOTSTRAP, "if [ -d agent/npm/node_modules ]; then\n  _xt_missing=\"\"",
                       "# Match the sentence both refusal paths share.")

EXCLUDED_CASES = [
    C("every_excluded_tool_still_registered", sources={"a/index.ts": 'name: "t_one"\n', "b/x.js": '"t_two"'},
      check=lambda t, r, d: t.assertEqual(
          "    other excluded tools: all 2 still registered, left out by default (pi --workflows brings back the workflow tools)\n",
          r.out)),
    C("a_renamed_tool_is_warned_about_by_name", sources={"a/index.ts": '"t_one"'},
      check=lambda t, r, d: t.assertIn("WARN excluded tools that no installed package registers: t_two - a renamed tool",
                                       r.out)),
    # Only .ts and .js are read: a name in a README is not a registration.
    C("a_name_in_another_kind_of_file_does_not_count", sources={"a/index.ts": '"t_one"', "b/README.md": '"t_two"'},
      check=lambda t, r, d: t.assertIn("registers: t_two", r.out)),
    C("the_name_must_be_a_whole_quoted_string", sources={"a/index.ts": '"t_one" "t_two_more"'},
      check=lambda t, r, d: t.assertIn("registers: t_two", r.out)),
    C("without_packages_nothing_is_checked", sources=None,
      check=lambda t, r, d: t.assertEqual("", r.out)),
]


@generate
class ExcludedToolsCheckTests(ShBatch):
    """The excludedTools check: a renamed tool would be back in every request."""

    CASES = EXCLUDED_CASES

    @classmethod
    def prepare(cls, case, d):
        touch(d / "config/elm-pi.json", json.dumps({"excludedTools": {"always": ["t_one"], "workflows": ["t_two"]}}))
        for rel, text in (case.kw["sources"] or {}).items():
            touch(d / "agent/npm/node_modules" / rel, text)

    @classmethod
    def body(cls, case, d):
        return "\n".join(["set -euo pipefail", f"cd {q(d)}", STUBS, f'elm_py() {{ {q(PY)} -E -S "$@"; }}',
                          EXCLUDED_BLOCK])


if __name__ == "__main__":
    unittest.main()
