"""The launcher's guards agree with what they guard, input by input.

Two pairs of implementations must say the same thing:

1. lib/policy.sh's argument guard (elm_policy_check_args, elm_policy_takes_value,
   elm_policy_extensions_disabled) and pi's own argument parser,
   node_modules/@earendil-works/pi-coding-agent/dist/cli/args.js. Every argument
   list here is parsed by pi's real parseArgs, imported under the bundled node
   (pi itself never runs), and what pi would use - provider, model, --models
   patterns, api key, extensions, --no-extensions - decides what the guard must
   say: refuse exactly when pi gets a non-ELM provider, model or pattern, an api
   key or an extension, with the message naming what pi got, and report
   discovery off exactly when pi turns it off. The lists are generated: every
   option pi names followed by an option it might swallow, random mixes of
   options in every order with "--" as a value and as the end of options,
   repeated options, short aliases and prompt text that looks like options, and
   the spellings only the guard reads (--model=, -m) or that pi reads late
   (an option left without its value).

2. The untrusted-folder check, which exists twice: lib/policy.sh
   elm_untrusted_folder (the launcher refuses to start a session there) and
   templates/extensions/trust-guard.ts (project trust is refused there). For
   folders in temporary homes - every exact and tree entry of
   config/elm-pi.json untrustedFolders, their children, look-alike siblings,
   trailing slashes, "." and ".." segments, symlinks to and from protected
   folders, spaces and unicode in names, case variants - both must give the
   answer an inode comparison gives, the launcher from $PWD after a cd as a
   shell does it, trust-guard from the folder pi's process is in.

One bash process and one node process per TestCase class run every case; one
generated test method checks each. tests/test_launcher_cases.py,
tests/test_shell_libs.py and tests/test_policy_extensions.py hold the hand
tables these differential cases do not repeat.
"""

import json
import os
import random
import re
import shlex
import shutil
import string
import subprocess
import tempfile
import unicodedata
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
POLICY = ROOT / "lib/policy.sh"
ARGS_JS = ROOT / "node_modules/@earendil-works/pi-coding-agent/dist/cli/args.js"
TRUST_GUARD = ROOT / "templates/extensions/trust-guard.ts"
# macOS's /bin/bash is 3.2, which the launcher must run under.
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")
ALLOWED = [p.lower() for p in CONFIG["allowedProviders"]]
QWEN = CONFIG["models"]["qwen"]
LLAMA = CONFIG["models"]["llama"]
EXACT = CONFIG["untrustedFolders"]["exact"]
TREE = CONFIG["untrustedFolders"]["tree"]
BASE_ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C"}


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def q(value):
    return shlex.quote(str(value))


def attach(cls, name, check, case, bug=None, doc=None):
    if hasattr(cls, name):
        raise ValueError(f"duplicate test {name} in {cls.__name__}")

    def test(self, case=case):
        check(self, case)

    test.__name__ = name
    test.__doc__ = doc
    if bug:
        test = unittest.expectedFailure(test)
    setattr(cls, name, test)


def run_bash(prelude, lines, args, env, cwd):
    """Run lines after prelude in one bash process, spread over background
    subshells: each line forks dozens of times (every $(...) in lib/policy.sh),
    and on macOS that, not the logic, is what takes the time. Returns stdout."""
    groups = max(1, min(8, os.cpu_count() or 1))
    out = Path(tempfile.mkdtemp()).resolve()
    try:
        script = [prelude]
        for g in range(groups):
            chunk = lines[g::groups]
            if chunk:
                script.append("(\n" + "\n".join(chunk) + f"\n) >{q(out / str(g))} &")
        script.append("wait")
        run = subprocess.run([BASH, "-c", "\n".join(script), "batch", *args], capture_output=True, text=True,
                             env=env, cwd=cwd, timeout=300)
        if run.returncode != 0:
            raise AssertionError(f"bash failed:\n{run.stderr}")
        return "".join((out / str(g)).read_text() for g in range(groups) if (out / str(g)).exists())
    finally:
        shutil.rmtree(out, ignore_errors=True)


# =============================================================================
# 1. The argument guard against pi's parser
# =============================================================================

# Every option pi 1.5.0's parseArgs compares an argument with, "--" aside.
# PiOptionListTests checks this against args.js, so a new pi option shows up.
PI_OPTIONS = (
    "--help", "-h", "--version", "-v", "--mode", "--continue", "-c", "--resume", "-r", "--provider",
    "--model", "--api-key", "--system-prompt", "--append-system-prompt", "--name", "-n", "--no-session",
    "--session", "--session-id", "--fork", "--session-dir", "--models", "--no-tools", "-nt",
    "--no-builtin-tools", "-nbt", "--tools", "-t", "--exclude-tools", "-xt", "--thinking", "--print", "-p",
    "--export", "--extension", "-e", "--no-extensions", "-ne", "--no-mcp", "--skill", "--prompt-template",
    "--theme", "--use-theme", "--no-skills", "-ns", "--no-prompt-templates", "-np", "--no-themes",
    "--no-context-files", "-nc", "--list-models", "--tui-mode", "--verbose", "--approve", "-a",
    "--no-approve", "-na", "--offline",
)
# What pi does with arguments it does not name: an unknown long flag (which
# takes a following word as its value), an unknown short one, a bare "-", a
# "---" word, and an @file.
OTHER_TOKENS = ("--plan", "-x", "-", "---", "@notes.md")

P = 'provider "{}" is not available.'
M = 'model "{}" is outside the allowed providers.'
MP = 'model pattern "{}" is outside the allowed providers.'
API = "--api-key is disabled: it can route a session to another provider."
EXT = "-e/--extension is disabled: \"{}\" would run unreviewed, with this install's access and its own network code."

ASCII_LOWER = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)


def trim(value):
    # elm_policy_trim strips [:space:] in the C locale.
    return value.strip(" \t\n\v\f\r")


def provider_ok(value):
    return value.translate(ASCII_LOWER) in ALLOWED


def model_ok(value):
    """The allowlist rule (an allowed provider before the slash, or an exact bare
    ELM id); tests/test_launcher_cases.py covers the rule itself. What is
    differential here is which value pi ends up holding."""
    c = trim(value)
    lower = c.translate(ASCII_LOWER)
    if lower in (QWEN.translate(ASCII_LOWER), LLAMA.translate(ASCII_LOWER)):
        return True
    return "/" in c and provider_ok(c.split("/", 1)[0])


def pi_verdict(p):
    """What the guard must answer for pi's parse p: refuse when pi holds an
    extension, an api key, or a non-ELM provider, model or pattern, reporting
    them in the guard's order with the value pi holds."""
    if p["extensions"]:
        return "DENY:" + EXT.format(p["extensions"][-1])
    if p["apiKey"] is not None:
        return "DENY:" + API
    if p["provider"] and not provider_ok(trim(p["provider"])):
        return "DENY:" + P.format(p["provider"])
    if p["model"] and not model_ok(p["model"]):
        return "DENY:" + M.format(p["model"])
    for item in p["models"] or []:
        if not model_ok(item):
            return "DENY:" + MP.format(trim(item))
    return "ALLOW"


def pi_acts_on_forbidden(p):
    """What pi would really do with something non-ELM, accounting for where it
    stops: a parse error stops it before anything loads; --version and --export
    exit before extensions load; an extension then loads (its code runs) even if
    pi stops afterwards on an option it does not know; a provider, model,
    pattern or key is used only when nothing stops pi before the session."""
    if p["errors"] or p["version"] or p["export"] is not None:
        return False
    if p["extensions"]:
        return True
    if p["unknown"] or (p["provider"] and not p["model"]):
        return False   # pi exits: "Unknown option --model", "--provider requires --model"
    return pi_verdict(p) != "ALLOW"


PI_RUNNER = r"""
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
const { parseArgs } = await import(pathToFileURL(process.argv[1]).href);
const lists = JSON.parse(readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify(lists.map((args) => {
  const r = parseArgs(args);
  return {
    provider: r.provider ?? null, model: r.model ?? null, models: r.models ?? null,
    apiKey: r.apiKey ?? null, extensions: r.extensions ?? [], noExtensions: r.noExtensions === true,
    version: r.version === true, export: r.export ?? null, unknown: [...r.unknownFlags.keys()],
    errors: r.diagnostics.filter((d) => d.type === "error").map((d) => d.message),
  };
})));
"""

BASH_ARGS_RUNNER = r"""
. "$1"
c() { local id="$1" v d; shift
  if elm_policy_check_args "$@"; then v=ALLOW; else v="DENY:$ELM_POLICY_ERROR"; fi
  if elm_policy_extensions_disabled "$@"; then d=1; else d=0; fi
  printf '@@%s\t%s\t%s\n' "$id" "$d" "$v"; }
"""

ARG_LISTS = []        # every argument list any class below needs, run once
_ARG_RESULTS = {}


def need(args):
    args = tuple(args)
    if args not in _ARG_RESULTS:
        _ARG_RESULTS[args] = None
        ARG_LISTS.append(args)
    return args


def parse_with_pi(lists):
    """pi's parseArgs on each list, in one node process. Done at import: which
    generated lists are kept, and which are known bugs, depends on pi's answer.
    Returns {} when node or pi is missing; the tests then skip."""
    binary = node()
    if not binary or not ARGS_JS.exists():
        return {}
    work = Path(tempfile.mkdtemp()).resolve()
    try:
        (work / "agent").mkdir()
        env = {**BASE_ENV, "HOME": str(work), "PI_CODING_AGENT_DIR": str(work / "agent")}
        # The lists go in a file: a large stdin pipe reads back EAGAIN in node.
        (work / "lists.json").write_text(json.dumps([list(a) for a in lists]))
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", PI_RUNNER, str(ARGS_JS),
                              str(work / "lists.json")], capture_output=True, text=True, env=env, cwd=work,
                             timeout=120)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if run.returncode != 0:
        raise RuntimeError(f"pi's parser failed:\n{run.stderr}")
    return {tuple(a): p for a, p in zip(lists, json.loads(run.stdout))}


PI = {}   # tuple(args) -> pi's parse, filled once below


def run_arg_lists():
    """Run every list through the bash guard, once for the module."""
    if all(v is not None for v in _ARG_RESULTS.values()):
        return _ARG_RESULTS
    if not PI:
        raise unittest.SkipTest("needs node and pi in node_modules (npm install)")
    work = Path(tempfile.mkdtemp()).resolve()
    try:
        lines = [f"c {i} " + " ".join(q(a) for a in args) for i, args in enumerate(ARG_LISTS)]
        env = {**BASE_ENV, "HOME": str(work), "ELM_ALLOWED_PROVIDERS": " ".join(CONFIG["allowedProviders"]),
               "ELM_QWEN_MODEL_ID": QWEN, "ELM_LLAMA_MODEL_ID": LLAMA}
        stdout = run_bash(BASH_ARGS_RUNNER, lines, [str(POLICY)], env, work)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    rows = {}
    for line in stdout.splitlines():
        if line.startswith("@@"):
            i, disabled, verdict = line[2:].split("\t", 2)
            rows[int(i)] = (disabled == "1", verdict)
    for i, args in enumerate(ARG_LISTS):
        disabled, verdict = rows[i]
        _ARG_RESULTS[args] = {"pi": PI[args], "disabled": disabled, "verdict": verdict}
    return _ARG_RESULTS


class ArgTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = run_arg_lists()


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def option_slug(token):
    named = {"-": "bare_dash", "---": "triple_dash", "@notes.md": "at_file"}
    if token in named:
        return named[token]
    if token.startswith("--"):
        return "long_" + slug(token[2:])
    return "short_" + slug(token[1:])


# --- every option, followed by an option it might swallow -------------------------


class PiOptionListTests(unittest.TestCase):
    def test_the_option_list_is_every_option_pis_parser_names(self):
        if not ARGS_JS.exists():
            raise unittest.SkipTest("pi is not installed in node_modules")
        named = re.findall(r'arg === "([^"]+)"', ARGS_JS.read_text())
        self.assertEqual(sorted(set(PI_OPTIONS) | {"--"}), sorted(set(named)))


class OptionValueTests(ArgTest):
    """For each option pi names (and the kinds it does not), whether it swallows
    the next argument: pi's answer decides what the guard must refuse when that
    next argument is --model, when it is the "--" before an -e, and whether a
    following --no-extensions turns discovery off."""


def _option_cases():
    for opt in PI_OPTIONS + OTHER_TOKENS:
        s = option_slug(opt)
        model = need([opt, "--model", "openai/gpt-5"])
        dash = need([opt, "--", "-e", "./ssh.ts"])
        noext = need([opt, "--no-extensions"])

        def guard(self, args):
            r = self.results[args]
            self.assertEqual(pi_verdict(r["pi"]), r["verdict"])

        def discovery(self, args):
            r = self.results[args]
            self.assertEqual(r["pi"]["noExtensions"], r["disabled"])

        attach(OptionValueTests, f"test_{s}_then_model", guard, model, doc=shlex.join(model))
        attach(OptionValueTests, f"test_{s}_then_double_dash_extension", guard, dash, doc=shlex.join(dash))
        attach(OptionValueTests, f"test_{s}_then_no_extensions", discovery, noext, doc=shlex.join(noext))


_option_cases()


# --- random mixes of the spellings pi reads -----------------------------------

ROUTING = {
    "--provider": ["elm", "ELM-SHIM", " elm ", "openai", "elmx", "", "Anthropic"],
    "--model": ["elm/qwen", "Elm-Shim/x", " elm/x ", "openai/gpt-5", "gpt-5", LLAMA, QWEN.lower(), "", "elm",
                "elm-shim2/x", f"{QWEN}:high"],
    "--models": ["elm/*", "elm/*,elm-shim/*", "elm/a, openai/b", " , ", "", "google/*", "elm/a,,ELM-SHIM/b",
                 f"{LLAMA},elm/x", "*/*"],
    "--api-key": ["k-123", ""],
    "-e": ["./ssh.ts", "npm:pi-telegram"],
    "--extension": ["./ssh.ts", "npm:pi-telegram"],
}
# Options pi gives the next argument to whatever it is, with the values that
# would be options if they were read as such.
TAKERS = ("--system-prompt", "--append-system-prompt", "--name", "-n", "--session", "--session-id", "--fork",
          "--session-dir", "--tools", "-t", "--exclude-tools", "-xt", "--thinking", "--skill",
          "--prompt-template", "--theme")
TRICKY = ("--", "--model", "--provider", "-e", "--api-key", "-ne", "--no-extensions", "--models", "plain text")
# Options that take the next argument only when it is not option-like.
CONDITIONAL = ("-p", "--print", "--mode", "--list-models", "--use-theme", "--tui-mode", "--plan")
CONDITIONAL_PAIRS = (("-p", "hello"), ("-p", "---model openai/x"), ("--mode", "json"), ("--list-models", "qwen"),
                     ("--use-theme", "dark"), ("--tui-mode", "regular"), ("--plan", "on"))
FLAGS = ("-c", "--continue", "-r", "--verbose", "--offline", "-a", "-na", "--no-session", "-nt", "-nc",
         "--no-mcp", "--help", "@notes.md", "-ne", "--no-extensions")
PROMPTS = ("hello", "--model openai/x", "-e ./ssh.ts", "fix it")
TAIL = ("--model=openai/x", "--provider", "openai", "-e", "x.ts", "--api-key", "-ne", "--no-extensions", "--",
        "hello", "--models", "google/*")


def random_unit(rng):
    kind = rng.random()
    if kind < 0.42:
        opt = rng.choice(list(ROUTING))
        return [opt, rng.choice(ROUTING[opt])]
    if kind < 0.60:
        return [rng.choice(TAKERS), rng.choice(TRICKY)]
    if kind < 0.70:
        return [rng.choice(CONDITIONAL)]
    if kind < 0.78:
        return list(rng.choice(CONDITIONAL_PAIRS))
    if kind < 0.92:
        return [rng.choice(FLAGS)]
    return [rng.choice(PROMPTS)]


def random_list(rng, units, end_chance, must=None):
    args = []
    for _ in range(units):
        args += random_unit(rng)
    if must:
        # Anywhere, including as the value of the option before it.
        at = rng.randrange(len(args) + 1)
        args[at:at] = [must]
    if rng.random() < end_chance:
        args += ["--"] + [rng.choice(TAIL) for _ in range(rng.randrange(4))]
    return args


class GeneratedGuardTests(ArgTest):
    """Random argument lists in pi's own spellings: the guard refuses exactly when
    pi's parse holds something non-ELM, and names the value pi holds."""


class GeneratedDiscoveryTests(ArgTest):
    """Random argument lists with --no-extensions or -ne somewhere - as an option,
    as an option's value, after "--": the launcher adds the policy extensions
    back exactly when pi turns discovery off."""


def _generated_cases():
    rng = random.Random(20261103)
    seen = set()
    count = 0
    while count < 90:
        args = random_list(rng, rng.randint(1, 5), 0.3)
        if tuple(args) in seen or tuple(args) in _ARG_RESULTS:
            continue
        seen.add(tuple(args))
        key = need(args)

        def check(self, args):
            r = self.results[args]
            self.assertEqual(pi_verdict(r["pi"]), r["verdict"])

        attach(GeneratedGuardTests, f"test_list_{count:03d}_{slug(' '.join(args[:2]))[:40]}", check, key,
               doc=shlex.join(args))
        count += 1
    count = 0
    while count < 30:
        args = random_list(rng, rng.randint(1, 4), 0.35, must=rng.choice(("-ne", "--no-extensions")))
        if tuple(args) in seen or tuple(args) in _ARG_RESULTS:
            continue
        seen.add(tuple(args))
        key = need(args)

        def check(self, args):
            r = self.results[args]
            self.assertEqual(r["pi"]["noExtensions"], r["disabled"])

        attach(GeneratedDiscoveryTests, f"test_list_{count:03d}_{slug(' '.join(args[:2]))[:40]}", check, key,
               doc=shlex.join(args))
        count += 1


_generated_cases()


# --- spellings only the guard reads, and options left without a value -----------

# pi has no -m and no --opt=value for its own options: -m, -mX and -m=X are
# parse errors, and --model=X is an unknown flag, which stops pi after the
# extensions have loaded. An option left without its value at the end is an
# unknown flag too (-e and -m at the end are parse errors). The guard reads the
# guard-only spellings as the option with a value, and an option left waiting
# as one without, still checking everything before it. What must hold: it
# refuses whenever pi would act on something non-ELM - load an extension, or
# start a session on a non-ELM route - and allows a list that names only ELM
# values.

GOOD_MODELS = ("elm/qwen", "ELM-SHIM/x", LLAMA)
BAD_MODELS = ("openai/gpt-5", "gpt-5", "elmx/q")


def guard_only_units():
    units = []   # (tokens, harmful, guard_only)
    for v in GOOD_MODELS + BAD_MODELS:
        bad = v in BAD_MODELS
        units += [((f"--model={v}",), bad, True), (("-m", v), bad, True), ((f"-m{v}",), bad, True),
                  ((f"-m={v}",), bad, True), (("--model", v), bad, False)]
    for v, bad in (("elm", False), ("elm-shim", False), ("openai", True)):
        units += [((f"--provider={v}",), bad, True), (("--provider", v), bad, False)]
    for v, bad in (("elm/*", False), ("elm/*,elm-shim/*", False), ("anthropic/*", True), ("elm/a,google/b", True)):
        units += [((f"--models={v}",), bad, True), (("--models", v), bad, False)]
    units += [(("--api-key=k",), True, True), (("--api-key", "k"), True, False),
              (("--extension=./ssh.ts",), True, True), (("--extension=",), False, True),
              (("-e=./ssh.ts",), True, True), (("-e", "./ssh.ts"), True, False),
              (("--extension", "npm:pi-telegram"), True, False), (("-e", ""), True, False),
              (("--extension", ""), True, False)]
    units += [(t, False, False) for t in (("-p", "hello"), ("--name", "--"), ("-c",), ("--offline",),
                                           ("--thinking", "high"), ("-ne",), ("fix it",))]
    return units


DANGLING = ("--provider", "--model", "--models", "--api-key", "--extension", "-e", "-m")
DANGLING_LONG = DANGLING[:5]


class GuardOnlySpellingTests(ArgTest):
    """Lists with a spelling pi does not read as the guard does: the guard must
    refuse whenever pi would act on a non-ELM value, and allow lists that name
    only ELM values."""


GUARD_ONLY_CURATED = (
    ("short_e_then_empty_short_e", ["-e", "./ssh.ts", "-e", ""]),
    ("long_extension_then_empty_long_extension", ["--extension", "./ssh.ts", "--extension", ""]),
    # An empty -e is the working folder to pi: resolvePath("", cwd).
    ("empty_short_e_alone", ["-e", ""]),
    ("empty_long_extension_alone", ["--extension", ""]),
    ("short_e_then_extension_equals_nothing", ["-e", "./ssh.ts", "--extension="]),
    ("long_extension_then_extension_equals_nothing", ["--extension", "npm:pi-telegram", "--extension="]),
    *((f"short_e_then_dangling_{slug(d)}", ["-e", "./ssh.ts", d]) for d in DANGLING_LONG),
    ("short_e_then_dangling_models_after_text", ["-e", "./ssh.ts", "-p", "hello", "--models"]),
    ("name_hides_double_dash_then_e_then_dangling_model", ["--name", "--", "-e", "./ssh.ts", "--model"]),
)
# pi stops on a waiting -e or -m at parse time, before any extension loads; the
# guard does not mirror pi's parse errors, and refuses the -e before them.
GUARD_ONLY_STOPPED = (["-e", "./ssh.ts", "-e"], ["-e", "./ssh.ts", "-m"])


def guard_only_pool():
    """Random lists mixing guard-only spellings, pi's spellings and an option
    left waiting at the end, each with whether it names only ELM values."""
    rng = random.Random(1103)
    units = guard_only_units()
    pool, seen = [], set()
    while len(pool) < 400:
        picked = [rng.choice(units) for _ in range(rng.randint(1, 4))]
        args = [t for u in picked for t in u[0]]
        dangling = rng.random() < 0.45
        if dangling:
            args.append(rng.choice(DANGLING))
        if not (dangling or any(u[2] for u in picked)) or tuple(args) in seen:
            continue
        seen.add(tuple(args))
        pool.append((args, not any(u[1] for u in picked)))
    return pool


def _register_all():
    for _, args in GUARD_ONLY_CURATED:
        need(args)
    for args in GUARD_ONLY_STOPPED:
        need(args)
    pool = guard_only_pool()
    PI.update(parse_with_pi(ARG_LISTS + [tuple(a) for a, _ in pool]))
    if not PI:
        return
    # Keep the lists whose answer is fixed: pi would act on a non-ELM value (the
    # guard must refuse), or the list names only ELM values (it must allow).
    # A non-ELM value pi never gets to act on may go either way.
    kept = {"must_refuse": [], "may_run": []}
    curated = {tuple(a) for _, a in GUARD_ONLY_CURATED} | {tuple(a) for a in GUARD_ONLY_STOPPED}
    for args, harmless in pool:
        if tuple(args) in curated:
            continue
        bucket = "must_refuse" if pi_acts_on_forbidden(PI[tuple(args)]) else "may_run" if harmless else None
        if bucket and len(kept[bucket]) < {"must_refuse": 30, "may_run": 20}[bucket]:
            kept[bucket].append(need(args))

    def must_refuse(self, args):
        r = self.results[args]
        self.assertTrue(pi_acts_on_forbidden(r["pi"]), r["pi"])
        self.assertTrue(r["verdict"].startswith("DENY:"), r["verdict"])

    def may_run(self, args):
        r = self.results[args]
        self.assertFalse(pi_acts_on_forbidden(r["pi"]), r["pi"])
        self.assertEqual("ALLOW", r["verdict"])

    for bucket, check in (("must_refuse", must_refuse), ("may_run", may_run)):
        for i, args in enumerate(kept[bucket]):
            attach(GuardOnlySpellingTests, f"test_{bucket}_{i:02d}_{slug(' '.join(args[:2]))[:36]}", check, args,
                   doc=shlex.join(args))
    for name, args in GUARD_ONLY_CURATED:
        args = tuple(args)
        attach(GuardOnlySpellingTests, f"test_{name}", must_refuse, args, doc=shlex.join(args))

    def stopped(self, args):
        r = self.results[args]
        self.assertFalse(pi_acts_on_forbidden(r["pi"]), r["pi"])
        self.assertTrue(r["pi"]["errors"], r["pi"])
        self.assertTrue(r["verdict"].startswith("DENY:"), r["verdict"])

    for args in GUARD_ONLY_STOPPED:
        attach(GuardOnlySpellingTests, f"test_short_e_then_dangling_{slug(args[-1])}_is_stopped_by_pi", stopped,
               tuple(args), doc=shlex.join(args))


_register_all()


# =============================================================================
# 2. The untrusted-folder check: lib/policy.sh against trust-guard.ts
# =============================================================================

HOME_EXACT = [e[2:] for e in EXACT if e.startswith("~/")]
HOME_TREE = [e[2:] for e in TREE if e.startswith("~/")]
SYSTEM_EXACT = [e for e in EXACT if e.startswith("/")]
SYSTEM_TREE = [e for e in TREE if e.startswith("/")]

NFC_NAME = unicodedata.normalize("NFC", "café")
NFD_NAME = unicodedata.normalize("NFD", NFC_NAME)


class F:
    """A folder case. path is a template ({h} home as created, {r} the config's
    root, {t} a folder under /tmp); mode "cd" starts a session there (launcher:
    cd then $PWD; trust-guard: the folder pi's process is in), mode "arg" passes
    the text itself to both."""

    def __init__(self, name, path, want, mode="cd", bug=None, needs=None):
        self.name, self.path, self.want, self.mode, self.bug, self.needs = name, path, want, mode, bug, needs


TRUST_RUNNER = r"""
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
const INPUT = JSON.parse(readFileSync(process.argv[2], "utf8"));
delete process.env.PI_CODING_AGENT_DIR;   // no saved decisions: the answer is untrusted() alone
Object.assign(process.env, INPUT.env);
const mod = await import(pathToFileURL(process.argv[1]).href);
let handler;
mod.default({ on: (event, h) => { if (event === "project_trust") handler = h; } });
const out = {};
for (const c of INPUT.cases) {
  let cwd;
  if (c.mode === "cd") {
    // A shell's cd is logical (a/link/.. is a), so the folder pi starts in is
    // the lexically resolved one; pi then sees it through process.cwd().
    try { process.chdir(resolve(INPUT.base, c.path)); } catch { out[c.id] = "CDFAIL"; continue; }
    cwd = process.cwd();
  } else {
    process.chdir(INPUT.base);
    cwd = c.path;
  }
  out[c.id] = (await handler({ type: "project_trust", cwd }, { hasUI: false })).trusted === "no" ? "YES" : "NO";
}
console.log(JSON.stringify(out));
"""

BASH_FOLDER_RUNNER = r"""
. "$1"
cd "$2" || exit 3
r() {
  if [ "$2" = cd ]; then
    ( cd "$3" 2>/dev/null || { printf '@@%s=CDFAIL\n' "$1"; exit 0; }
      if elm_untrusted_folder "$PWD"; then v=YES; else v=NO; fi; printf '@@%s=%s\n' "$1" "$v" )
  else
    if elm_untrusted_folder "$3"; then v=YES; else v=NO; fi; printf '@@%s=%s\n' "$1" "$v"
  fi
}
"""


def ident(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_dev, st.st_ino)


def expand(entry, home):
    if entry == "~":
        return home
    if entry.startswith("~/"):
        return home.rstrip("/") + "/" + entry[2:]
    return entry


class FolderTest(unittest.TestCase):
    """One temporary home; LAYOUT builds it, CASES are checked against it."""

    CASES = ()
    HOME_REL = "home"       # HOME, relative to the config root
    HOME_ENV = None         # HOME as exported, when not the folder itself
    LISTS = True            # export untrustedFolders, or leave both lists empty
    BASE = "{h}/src/proj"   # where relative paths start

    @classmethod
    def layout(cls, r, h):
        pass

    @classmethod
    def setUpClass(cls):
        binary = node()
        if not binary:
            raise unittest.SkipTest("needs node")
        cls.root = Path(tempfile.mkdtemp()).resolve()
        cls.slashtmp = None
        try:
            r, h = cls.root, cls.root / cls.HOME_REL
            h.mkdir(parents=True)
            (h / "src/proj").mkdir(parents=True)
            cls.layout(r, h)
            if Path("/tmp").is_dir():
                cls.slashtmp = Path(tempfile.mkdtemp(dir="/tmp"))
            cls.home_env = cls.HOME_ENV.format(r=r, h=h) if cls.HOME_ENV else str(h)
            cls.base = cls.fill(cls.BASE)
            cls.exact = "\n".join(EXACT) if cls.LISTS else ""
            cls.tree = "\n".join(TREE) if cls.LISTS else ""
            cases = [c for c in cls.CASES if cls.usable(c)]
            cls.skipped = {c.name for c in cls.CASES} - {c.name for c in cases}
            env = {**BASE_ENV, "HOME": cls.home_env, "ELM_UNTRUSTED_EXACT": cls.exact,
                   "ELM_UNTRUSTED_TREE": cls.tree, "TMPDIR": str(r)}
            lines = [f"r {c.name} {c.mode} {q(cls.fill(c.path))}" for c in cases]
            stdout = run_bash(BASH_FOLDER_RUNNER, lines, [str(POLICY), cls.base], env, str(r))
            cls.bash = dict(line[2:].split("=", 1) for line in stdout.splitlines() if line.startswith("@@"))
            work = r / "ext"
            work.mkdir()
            shutil.copy(TRUST_GUARD, work / "trust-guard.ts")
            payload = {"base": cls.base, "env": {"HOME": cls.home_env, "ELM_UNTRUSTED_EXACT": cls.exact,
                                                 "ELM_UNTRUSTED_TREE": cls.tree},
                       "cases": [{"id": c.name, "mode": c.mode, "path": cls.fill(c.path)} for c in cases]}
            (work / "cases.json").write_text(json.dumps(payload))
            run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", TRUST_RUNNER,
                                  str(work / "trust-guard.ts"), str(work / "cases.json")], capture_output=True,
                                 text=True, env=env, cwd=str(r), timeout=120)
            if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
                raise unittest.SkipTest("this node cannot load TypeScript")
            if run.returncode != 0:
                raise AssertionError(f"node failed:\n{run.stderr}")
            cls.node = json.loads(run.stdout)
        except BaseException:
            cls.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.cleanup()

    @classmethod
    def cleanup(cls):
        if cls.slashtmp is not None and str(cls.slashtmp).startswith("/tmp/"):
            shutil.rmtree(cls.slashtmp, ignore_errors=True)
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def fill(cls, text):
        return text.format(r=cls.root, h=cls.root / cls.HOME_REL, t=cls.slashtmp or "/nonexistent")

    @classmethod
    def usable(cls, case):
        for need_path in case.needs or ():
            if not os.path.isdir(cls.fill(need_path)):
                return False
        return True

    def oracle(self, case):
        """Which folder it is, by inode: home and every folder above it, an exact
        entry itself, or anything under a tree entry. A path that does not exist
        is compared as normalised text against the canonical entries."""
        home = os.path.realpath(self.home_env)
        path = expand(self.fill(case.path), self.home_env) if case.mode == "arg" else self.fill(case.path)
        target = os.path.normpath(os.path.join(self.base, path))
        chain = [home]
        while chain[-1] != os.path.dirname(chain[-1]):
            chain.append(os.path.dirname(chain[-1]))
        exact = [expand(e, self.home_env) for e in (EXACT if self.LISTS else [])]
        tree = [expand(e, self.home_env) for e in (TREE if self.LISTS else [])]
        if ident(target) is None:
            canon = {os.path.realpath(p) for p in chain + exact}
            if target in canon:
                return True
            return any(target == os.path.realpath(t) or target.startswith(os.path.realpath(t) + "/") for t in tree)
        if ident(target) in {ident(p) for p in chain + exact} - {None}:
            return True
        tree_ids = {ident(p) for p in tree} - {None}
        p = os.path.realpath(target)
        while True:
            if ident(p) in tree_ids:
                return True
            if p == os.path.dirname(p):
                return False
            p = os.path.dirname(p)

    def check(self, case):
        if case.name in self.skipped:
            self.skipTest(f"needs {case.needs} on this machine")
        # The expected answer by construction, and the same by inode.
        self.assertEqual(case.want, self.oracle(case), "the case's expectation is wrong")
        want = "YES" if case.want else "NO"
        self.assertEqual({"lib/policy.sh": want, "trust-guard.ts": want},
                         {"lib/policy.sh": self.bash.get(case.name), "trust-guard.ts": self.node.get(case.name)})


def folder_tests(cls):
    for case in cls.CASES:
        attach(cls, "test_" + case.name, FolderTest.check, case, bug=case.bug,
               doc=f"{case.mode} {case.path}")
    return cls


def plain_cases():
    cases = [F("home_itself", "{h}", True)]
    for rel in HOME_EXACT:
        s = slug(rel)
        cases += [F(f"exact_{s}", "{h}/" + rel, True),
                  F(f"exact_{s}_child", "{h}/" + rel + "/proj", False)]
    for rel in HOME_TREE:
        s = slug(rel)
        cases += [F(f"tree_{s}", "{h}/" + rel, True),
                  F(f"tree_{s}_child", "{h}/" + rel + "/k", True),
                  F(f"tree_{s}_lookalike_sibling", "{h}/" + rel + "-old", False)]
    cases += [
        F("tree_ssh_grandchild_with_a_space", "{h}/.ssh/k/old keys", True),
        F("tree_application_support_deep", "{h}/Library/Application Support/Code/User", True),
        F("tree_docker_trailing_slash", "{h}/.docker/k/", True),
        F("exact_downloads_trailing_slash", "{h}/Downloads/", True),
        F("exact_downloads_dot_segment", "{h}/./Downloads/.", True),
        F("exact_documents_via_dot_dot", "{h}/src/proj/../../Documents", True),
        F("home_via_dot_dot_from_a_project", "{h}/src/proj/../..", True),
        F("project_via_dot_dot_out_of_ssh", "{h}/.ssh/../src/proj", False),
        F("parent_of_home", "{r}", True),
        F("sibling_of_home", "{r}/homework", False),
        F("sibling_named_like_home_with_a_space", "{r}/home x", False),
        F("downloads_with_a_trailing_space", "{h}/Downloads ", False),
        F("downloads_with_a_leading_space", "{h}/ Downloads", False),
        F("project_with_a_space", "{h}/src/my proj", False),
        F("project_with_unicode", "{h}/src/" + NFC_NAME, False),
        F("aws_child_with_a_space", "{h}/.aws/my creds", True),
        F("gnupg_child_with_unicode", "{h}/.gnupg/日本", True),
        F("dotfile_project_beside_ssh", "{h}/.ssh.d", False),
        # Symlinks to protected folders, and out of them.
        F("link_to_ssh", "{r}/links/ssh", True),
        F("link_to_inside_ssh", "{r}/links/sshkey", True),
        F("link_to_a_link_to_ssh", "{r}/links/chain", True),
        F("link_to_downloads", "{r}/links/dl", True),
        F("link_to_a_project_in_downloads", "{r}/links/dlproj", False),
        F("link_to_home", "{r}/links/home", True),
        F("link_in_a_project_to_ssh", "{h}/src/proj/sshlink", True),
        F("link_in_a_project_to_home", "{h}/src/proj/homelink", True),
        F("link_in_ssh_to_a_project", "{h}/.ssh/k/projlink", False),
        F("link_in_downloads_to_home", "{h}/Downloads/homelink", True),
        F("link_in_library_to_a_project", "{h}/Library/projlink", False),
        F("dot_dot_after_a_link_is_logical", "{h}/src/proj/sshlink/..", False),
        # Unicode decomposed where the disk has it composed, under a tree entry:
        # the tree prefix is still there, so both agree.
        F("aws_child_typed_decomposed", "{h}/.aws/" + NFD_NAME, True, needs=["{h}/.aws/" + NFD_NAME]),
        F("project_typed_decomposed", "{h}/src/" + NFD_NAME, False, needs=["{h}/src/" + NFD_NAME]),
        # Case variants on a case-insensitive volume.
        F("project_in_another_case", "{h}/SRC/proj", False, needs=["{h}/SRC/proj"]),
        F("ssh_child_in_another_case", "{h}/.ssh/K", True, needs=["{h}/.ssh/K"]),
        F("downloads_in_another_case", "{h}/downloads", True, needs=["{h}/downloads"]),
        F("ssh_in_another_case", "{h}/.SSH/k", True, needs=["{h}/.SSH/k"]),
        F("keychains_in_another_case", "{h}/library/keychains", True,
          needs=["{h}/library/keychains"]),
        F("home_in_another_case", "{r}/HOME", True, needs=["{r}/HOME"]),
        # Doubled and tripled leading slashes.
        F("home_with_two_leading_slashes", "/{h}", True),
        F("ssh_child_with_two_leading_slashes", "/{h}/.ssh/k", True),
        F("project_with_two_leading_slashes", "/{h}/src/proj", False),
        F("home_with_three_leading_slashes", "//{h}", True),
        F("home_with_a_doubled_inner_slash", "{h}//", True),
        F("ssh_with_a_doubled_inner_slash", "{h}//.ssh//k", True),
        F("root_with_two_slashes", "//", True),
        F("etc_with_two_leading_slashes", "//etc", True, needs=["/etc"]),
        F("usr_bin_with_two_leading_slashes", "//usr/bin", True, needs=["/usr/bin"]),
        # The machine's own folders.
        F("root", "/", True),
        *(F(f"system_exact_{slug(e) or 'root'}", e, True, needs=[e]) for e in SYSTEM_EXACT if e != "/"),
        *(F(f"system_tree_{slug(e)}", e, True, needs=[e]) for e in SYSTEM_TREE),
        F("system_tree_child_usr_local", "/usr/local", True, needs=["/usr/local"]),
        F("system_tree_child_etc_ssh", "/etc/ssh", True, needs=["/etc/ssh"]),
        F("system_tree_child_system_library", "/System/Library", True, needs=["/System/Library"]),
        F("system_tree_child_library_preferences", "/Library/Preferences", True, needs=["/Library/Preferences"]),
        F("system_tree_child_applications_utilities", "/Applications/Utilities", True,
          needs=["/Applications/Utilities"]),
        F("users_shared_is_not_users", "/Users/Shared", False, needs=["/Users/Shared"]),
        F("a_folder_under_slash_tmp", "{t}", False, needs=["{t}"]),
        F("slash_tmp_through_dot_dot", "{t}/..", True, needs=["{t}"]),
        # Text passed as it is, without a cd first.
        F("arg_tilde", "~", True, mode="arg"),
        F("arg_tilde_slash", "~/", True, mode="arg"),
        F("arg_tilde_ssh", "~/.ssh", True, mode="arg"),
        F("arg_tilde_ssh_trailing_slash", "~/.ssh/", True, mode="arg"),
        F("arg_tilde_downloads_trailing_slash", "~/Downloads/", True, mode="arg"),
        F("arg_tilde_dot_documents", "~/./Documents", True, mode="arg"),
        F("arg_tilde_project", "~/src/proj", False, mode="arg"),
        F("arg_tilde_project_through_ssh_dot_dot", "~/.ssh/../src/proj/", False, mode="arg"),
        F("arg_relative_dot", ".", False, mode="arg"),
        F("arg_relative_parent", "..", False, mode="arg"),
        F("arg_relative_home", "../..", True, mode="arg"),
        F("arg_relative_into_ssh", "../../.ssh/k", True, mode="arg"),
        F("arg_relative_into_downloads_project", "../../Downloads/proj", False, mode="arg"),
        F("arg_relative_link_to_ssh", "./sshlink", True, mode="arg"),
        F("arg_relative_dot_dot_after_link", "sshlink/..", False, mode="arg"),
        F("arg_tilde_without_slash_is_a_name", "~src", False, mode="arg"),
        F("arg_home_with_two_leading_slashes", "/{h}", True, mode="arg"),
        # Folders that do not exist: compared as text by both.
        F("arg_missing_inside_ssh", "~/.ssh/missing", True, mode="arg"),
        F("arg_missing_inside_downloads", "~/Downloads/missing", False, mode="arg"),
        F("arg_dangling_link_inside_ssh", "~/.ssh/dangling", True, mode="arg"),
        F("arg_dangling_link_in_a_project", "~/src/proj/dangling", False, mode="arg"),
        F("arg_missing_through_ssh_into_downloads", "~/.ssh/missing/../../Downloads", True, mode="arg"),
        F("arg_missing_then_dot_dot_is_home", "~/missing/..", True, mode="arg"),
        F("arg_missing_then_dot_dot_out_of_ssh", "~/.ssh/missing/../../src", False, mode="arg"),
    ]
    return cases


def make_tree(h):
    for rel in HOME_EXACT:
        (h / rel / "proj").mkdir(parents=True, exist_ok=True)
    for rel in HOME_TREE + [".ssh"]:
        (h / rel / "k").mkdir(parents=True, exist_ok=True)
        (h / (rel + "-old")).mkdir(parents=True, exist_ok=True)


@folder_tests
class PlainHomeFolderTests(FolderTest):
    """A home with every listed folder, children, look-alikes and symlinks."""

    CASES = plain_cases()

    @classmethod
    def layout(cls, r, h):
        make_tree(h)
        for rel in (".ssh/k/old keys", "Library/Application Support/Code/User", ".docker/k", "src/my proj",
                    "src/" + NFC_NAME, ".aws/my creds", ".aws/" + NFC_NAME, ".gnupg/日本", ".ssh.d",
                    "Downloads ", " Downloads"):
            (h / rel).mkdir(parents=True, exist_ok=True)
        for rel in ("homework", "home x", "links"):
            (r / rel).mkdir(exist_ok=True)
        links = r / "links"
        (links / "ssh").symlink_to(h / ".ssh")
        (links / "sshkey").symlink_to(h / ".ssh/k")
        (links / "chain").symlink_to(links / "ssh")
        (links / "dl").symlink_to(h / "Downloads")
        (links / "dlproj").symlink_to(h / "Downloads/proj")
        (links / "home").symlink_to(h)
        (h / "src/proj/sshlink").symlink_to(h / ".ssh")
        (h / "src/proj/homelink").symlink_to(h)
        (h / ".ssh/k/projlink").symlink_to(h / "src/proj")
        (h / "Downloads/homelink").symlink_to(h)
        (h / "Library/projlink").symlink_to(h / "src/proj")
        (h / ".ssh/dangling").symlink_to(r / "nowhere")
        (h / "src/proj/dangling").symlink_to(r / "nowhere")


@folder_tests
class LinkedHomeFolderTests(FolderTest):
    """HOME is a symlink to the real home, ~/.ssh a symlink into a dotfiles
    folder and ~/Downloads one to a folder elsewhere: both checks follow them."""

    HOME_REL = "real-home"
    HOME_ENV = "{r}/homelink"
    BASE = "{r}/homelink/src/proj"
    CASES = (
        F("real_home", "{h}", True),
        F("home_through_its_link", "{r}/homelink", True),
        F("folder_holding_the_real_home", "{r}", True),
        F("ssh_target_in_dotfiles", "{r}/dotfiles/ssh", True),
        F("child_of_ssh_target", "{r}/dotfiles/ssh/k", True),
        F("dotfiles_folder_itself", "{r}/dotfiles", False),
        F("dotfiles_sibling_of_ssh_target", "{r}/dotfiles/sshx", False),
        F("downloads_target_elsewhere", "{r}/elsewhere/dl", True),
        F("child_of_downloads_target", "{r}/elsewhere/dl/proj", False),
        F("folder_holding_downloads_target", "{r}/elsewhere", False),
        F("ssh_child_through_home_link", "{r}/homelink/.ssh/k", True),
        F("downloads_through_home_link", "{r}/homelink/Downloads", True),
        F("project_through_home_link", "{r}/homelink/src/proj", False),
        F("project_in_real_home", "{h}/src/proj", False),
        F("arg_tilde", "~", True, mode="arg"),
        F("arg_tilde_ssh_child", "~/.ssh/k", True, mode="arg"),
        F("arg_tilde_downloads_child", "~/Downloads/proj", False, mode="arg"),
        F("arg_tilde_parent", "~/..", True, mode="arg"),
        F("arg_relative_home", "../..", True, mode="arg"),
    )

    @classmethod
    def layout(cls, r, h):
        (r / "homelink").symlink_to(h)
        for rel in ("dotfiles/ssh/k", "dotfiles/sshx", "elsewhere/dl/proj"):
            (r / rel).mkdir(parents=True)
        (h / ".ssh").symlink_to(r / "dotfiles/ssh")
        (h / "Downloads").symlink_to(r / "elsewhere/dl")


@folder_tests
class TrailingSlashHomeFolderTests(FolderTest):
    """HOME exported with a trailing slash."""

    HOME_ENV = "{h}/"
    CASES = (
        F("home", "{h}", True),
        F("ssh_child", "{h}/.ssh/k", True),
        F("downloads", "{h}/Downloads", True),
        F("project", "{h}/src/proj", False),
        F("arg_tilde_aws", "~/.aws", True, mode="arg"),
        F("arg_tilde_library", "~/Library", True, mode="arg"),
    )

    @classmethod
    def layout(cls, r, h):
        make_tree(h)


SPACE_HOME = "Jo " + NFC_NAME + " 日本"


@folder_tests
class UnicodeHomeFolderTests(FolderTest):
    """A home whose name has spaces, an accent and CJK characters."""

    HOME_REL = SPACE_HOME
    CASES = (
        F("home", "{h}", True),
        F("ssh_child", "{h}/.ssh/k", True),
        F("downloads", "{h}/Downloads", True),
        F("project", "{h}/src/proj", False),
        F("sibling_with_a_suffix", "{r}/" + SPACE_HOME + "x", False),
        F("sibling_with_a_prefix_of_the_name", "{r}/Jo " + NFC_NAME, False),
        F("home_typed_decomposed", "{r}/" + unicodedata.normalize("NFD", SPACE_HOME), True,
          needs=["{r}/" + unicodedata.normalize("NFD", SPACE_HOME)]),
        F("ssh_child_typed_decomposed", "{r}/" + unicodedata.normalize("NFD", SPACE_HOME) + "/.ssh/k", True, needs=["{r}/" + unicodedata.normalize("NFD", SPACE_HOME) + "/.ssh/k"]),
        F("project_typed_decomposed", "{r}/" + unicodedata.normalize("NFD", SPACE_HOME) + "/src/proj", False,
          needs=["{r}/" + unicodedata.normalize("NFD", SPACE_HOME) + "/src/proj"]),
        F("arg_tilde_mobile_documents", "~/Library/Mobile Documents", True, mode="arg"),
    )

    @classmethod
    def layout(cls, r, h):
        make_tree(h)
        for rel in (SPACE_HOME + "x", "Jo " + NFC_NAME):
            (r / rel).mkdir()


@folder_tests
class EmptyListsFolderTests(FolderTest):
    """Without untrustedFolders (no runtime.env yet) only home and the folders
    above it are refused, by both."""

    LISTS = False
    CASES = (
        F("home", "{h}", True),
        F("parent_of_home", "{r}", True),
        F("root", "/", True),
        F("ssh_is_not_listed", "{h}/.ssh", False),
        F("ssh_child_is_not_listed", "{h}/.ssh/k", False),
        F("downloads_is_not_listed", "{h}/Downloads", False),
        F("etc_is_not_listed", "/etc", False, needs=["/etc"]),
        F("a_folder_under_slash_tmp", "{t}", False, needs=["{t}"]),
        F("arg_tilde_library", "~/Library", False, mode="arg"),
    )

    @classmethod
    def layout(cls, r, h):
        make_tree(h)


if __name__ == "__main__":
    unittest.main()
