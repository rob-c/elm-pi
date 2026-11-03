"""The launcher's decisions, case by case: which flags it takes for itself and
what each one puts in front of pi's arguments, what the argument guard refuses,
where a session may start, and the smaller per-run switches (setup, update,
--with-all, the offline default, the session folder, the proxy environment,
matplotlib, the agent's Python on PATH, the busy-machine and inside-the-install
notes).

Each class cuts one block out of ./pi between two anchor strings and runs every
case in its own subshell of a single bash process, so a few hundred cases cost
a handful of process starts. Nothing here runs pi, the proxy or the network.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (ROOT / "pi").read_text()
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
# The launcher must run under macOS's bash 3.2 as well as a modern one; /bin/bash
# is the 3.2 one there, and the system one on Linux.
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")

ALWAYS = ",".join(CONFIG["excludedTools"]["always"])
WEB = ",".join(CONFIG["webTools"])
WF = ",".join(CONFIG["excludedTools"]["workflows"])
DEFAULT_XT = f"{ALWAYS},{WEB},{WF}"
LLAMA = "meta-llama/Llama-3.3-70B-Instruct"
QWEN = "Qwen/Qwen3.5-397B-A17B-FP8"


def block(text, start, end):
    """The source between two anchors; the start must be unambiguous."""
    if text.count(start) != 1:
        raise AssertionError(f"anchor is not unique: {start!r}")
    i = text.index(start)
    return text[i:text.index(end, i)]


# _v NAME... prints @@NAME=value, or @@NAME when unset; _a NAME values... prints
# one @@NAME[]=value line per element.
DUMP = r'''
_v() { local _n _s _x; for _n in "$@"; do eval "_s=\${$_n+x}"
  if [ -n "$_s" ]; then eval "_x=\${$_n}"; printf '@@%s=%s\n' "$_n" "$_x"; else printf '@@%s\n' "$_n"; fi; done; }
_a() { local _n="$1" _x; shift; for _x in "$@"; do printf '@@%s[]=%s\n' "$_n" "$_x"; done; }
'''


class Result:
    def __init__(self, rc, out, err):
        self.rc, self.out, self.err = rc, out, err
        self.vars, self.lists = {}, {}
        for line in out.splitlines():
            if not line.startswith("@@"):
                continue
            key, sep, value = line[2:].partition("=")
            if key.endswith("[]"):
                self.lists.setdefault(key[:-2], []).append(value)
            else:
                self.vars[key] = value if sep else None

    def list(self, name):
        return self.lists.get(name, [])


def run_batch(prelude, bodies, env, tmp):
    parts = ['T="$1"', DUMP, prelude]
    for i, body in enumerate(bodies):
        parts.append(f'(\n{body}\n) >"$T/.r{i}.out" 2>"$T/.r{i}.err" </dev/null\necho $? >"$T/.r{i}.rc"')
    subprocess.run([BASH, "-c", "\n".join(parts), "batch", str(tmp)], env=env, cwd=str(tmp),
                   check=True, capture_output=True, text=True, timeout=300)
    return [Result(int((tmp / f".r{i}.rc").read_text()), (tmp / f".r{i}.out").read_text(),
                   (tmp / f".r{i}.err").read_text()) for i in range(len(bodies))]


def q(value):
    return shlex.quote(str(value))


def exports(env):
    return "\n".join(f"unset {k}" if v is None else f"export {k}={q(v)}" for k, v in env.items())


def setargs(args):
    return "set -- " + " ".join(q(a) for a in args)


class Case:
    def __init__(self, name, args=(), env=None, bug=None, **kw):
        self.name, self.args, self.env, self.bug, self.kw = name, list(args), dict(env or {}), bug, kw


def as_list(value):
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


class BatchTest(unittest.TestCase):
    """Runs CASES once per class, in one bash process; one test method per case."""

    CASES = ()

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            cls.home = cls.tmp / "home"
            cls.home.mkdir()
            cls.prepare()
            env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(cls.home), "LANG": "C",
                   "TMPDIR": str(cls.tmp)}
            results = run_batch(cls.prelude(), [cls.body(c) for c in cls.CASES], env, cls.tmp)
            cls.results = {c.name: r for c, r in zip(cls.CASES, results)}
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def prepare(cls):
        pass

    @classmethod
    def prelude(cls):
        return ""

    @classmethod
    def body(cls, case):
        raise NotImplementedError

    def check(self, case, r):
        kw = case.kw
        self.assertEqual(kw.get("rc", 0), r.rc, f"stdout:\n{r.out}\nstderr:\n{r.err}")
        for key, want in kw.get("vars", {}).items():
            self.assertEqual(want, r.vars.get(key, "<not dumped>"), key)
        for text in as_list(kw.get("err_has")):
            self.assertIn(text, r.err)
        for text in as_list(kw.get("err_lacks")):
            self.assertNotIn(text, r.err)
        for text in as_list(kw.get("out_has")):
            self.assertIn(text, r.out)
        for text in as_list(kw.get("out_lacks")):
            self.assertNotIn(text, r.out)
        if kw.get("quiet"):
            self.assertEqual("", r.err)


def generate(cls):
    for case in cls.CASES:
        name = "test_" + re.sub(r"\W+", "_", case.name).strip("_").lower()
        if hasattr(cls, name):
            raise ValueError(f"duplicate case {name} in {cls.__name__}")

        def test(self, case=case):
            self.check(case, type(self).results[case.name])
        test.__name__ = name
        if case.bug:
            test = unittest.expectedFailure(test)
        setattr(cls, name, test)
    return cls


def touch(path, text="", mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)
    return path


# --- the launcher's own flags, and what goes in front of pi's arguments --------

POLICY = ("elm-only", "protected-paths", "trust-guard", "pinned-instructions", "command-guard")
GATE_REL = "agent/npm/node_modules/@gotgenes/pi-permission-system"
CU_REL = "agent/npm/node_modules/@injaneity/pi-computer-use/extensions/computer-use.ts"


def ext(h, *names):
    out = []
    for n in names:
        out += ["-e", f"{h}/agent/extensions/{n}.ts"]
    return out


def gate(h):
    return ["-e", f"{h}/{GATE_REL}/src/index.ts"]


def cu(h):
    return ["-e", f"{h}/{CU_REL}"]


def xt(*parts):
    return ["--exclude-tools", ",".join(parts)]


def fastpre(h):
    return ["--no-extensions"] + ext(h, *POLICY) + gate(h) + ext(h, "todo", "skill-router")


def fixed(value):
    return lambda h: value


C = Case
FLAG_CASES = (
    C("session_gets_the_default_exclusions", ["-p", "x"], pre=fixed(xt(DEFAULT_XT)), rest=["-p", "x"],
      vars={"FAST": "0", "LLAMA": "0", "REMOTE": "0", "WORKFLOWS": "0", "WITH_ALL": "0"}),
    C("no_arguments_still_exclude", [], pre=fixed(xt(DEFAULT_XT)), rest=[]),
    C("fast_loads_policy_gate_and_conveniences", ["--fast", "-p", "x"],
      pre=lambda h: fastpre(h) + xt(DEFAULT_XT), rest=["-p", "x"], vars={"FAST": "1"}),
    C("fast_on_an_install_without_packages", ["--fast"], variant="bare",
      pre=lambda h: ["--no-extensions"] + ext(h, *POLICY) + xt(DEFAULT_XT), rest=[]),
    C("fast_refuses_a_gate_without_its_entry_point", ["--fast"], variant="brokengate", rc=1,
      err_has="the permission gate is installed but"),
    C("fast_refuses_a_missing_policy_extension", ["--fast"], variant="nopolicy", rc=1,
      err_has="agent/extensions/trust-guard.ts is missing"),
    C("ne_loads_policy_and_gate_only", ["-ne", "-p", "x"],
      pre=lambda h: ext(h, *POLICY) + gate(h) + xt(DEFAULT_XT), rest=["-ne", "-p", "x"]),
    C("no_extensions_on_an_install_without_packages", ["--no-extensions"], variant="bare",
      pre=lambda h: ext(h, *POLICY) + xt(DEFAULT_XT), rest=["--no-extensions"]),
    C("fast_with_ne_loads_the_policy_once", ["--fast", "-ne"],
      pre=lambda h: fastpre(h) + xt(DEFAULT_XT), rest=["-ne"]),
    C("ne_after_double_dash_is_prompt_text", ["-p", "--", "-ne"], pre=fixed(xt(DEFAULT_XT)),
      rest=["-p", "--", "-ne"]),
    C("ne_refuses_a_missing_policy_extension", ["-ne"], variant="nopolicy", rc=1,
      err_has="agent/extensions/trust-guard.ts is missing"),
    C("ne_refuses_a_broken_gate", ["--no-extensions"], variant="brokengate", rc=1,
      err_has="Not starting without it"),
    C("llama_picks_the_shim_model", ["--llama", "-p", "x"],
      pre=fixed(["--model", f"elm-shim/{LLAMA}"] + xt(DEFAULT_XT)), rest=["-p", "x"], vars={"LLAMA": "1"}),
    C("llama_leaves_an_explicit_model", ["--llama", "--model", "elm/q"], pre=fixed(xt(DEFAULT_XT)),
      rest=["--model", "elm/q"]),
    C("llama_leaves_an_explicit_model_equals", ["--llama", "--model=elm/q"], pre=fixed(xt(DEFAULT_XT))),
    C("llama_leaves_an_explicit_provider", ["--llama", "--provider", "elm"], pre=fixed(xt(DEFAULT_XT))),
    C("fast_llama_loads_the_shim_extension", ["--fast", "--llama"],
      pre=lambda h: fastpre(h) + ext(h, "elm-shim") + ["--model", f"elm-shim/{LLAMA}"] + xt(DEFAULT_XT)),
    C("fast_with_a_shim_model_loads_the_shim_extension", ["--fast", "--model", "elm-shim/x"],
      pre=lambda h: fastpre(h) + ext(h, "elm-shim") + xt(DEFAULT_XT), rest=["--model", "elm-shim/x"]),
    C("fast_llama_without_the_shim_extension_file", ["--fast", "--llama"], variant="bare",
      pre=lambda h: ["--no-extensions"] + ext(h, *POLICY) + ["--model", f"elm-shim/{LLAMA}"] + xt(DEFAULT_XT)),
    # Prompt text that mentions --model is not the caller choosing a model.
    C("llama_model_kept_when_the_prompt_mentions_model", ["--llama", "-p", "what does --model do"],
      pre=fixed(["--model", f"elm-shim/{LLAMA}"] + xt(DEFAULT_XT))),
    C("remote_opens_the_web_and_loads_computer_use", ["--remote", "-p", "x"],
      pre=lambda h: cu(h) + xt(ALWAYS, WF), rest=["-p", "x"],
      vars={"REMOTE": "1", "PI_ELM_WEB": "1", "ELM_PI_PROXY_ALLOW": "*",
            "PI_COMPUTER_USE_CODESIGN_IDENTITY": "-"},
      err_has=["--remote - web tools on", "computer use is on"], err_lacks="pi-web-access is not installed"),
    C("remote_adds_to_a_given_allow_list", ["--remote"], env={"ELM_PI_PROXY_ALLOW": "api.exa.ai"},
      vars={"ELM_PI_PROXY_ALLOW": "api.exa.ai,*"}),
    C("remote_without_packages_says_there_are_no_web_tools", ["--remote"], variant="bare",
      pre=fixed(xt(ALWAYS, WF)), err_has="pi-web-access is not installed", err_lacks="computer use is on"),
    C("remote_in_a_child_has_no_computer_use", ["--remote"], env={"PI_ELM_CHILD": "1"},
      pre=fixed(xt(ALWAYS, WF)), vars={"PI_COMPUTER_USE_CODESIGN_IDENTITY": None}, err_lacks="computer use"),
    C("remote_merges_the_callers_exclusion", ["--remote", "-xt", "bash"],
      pre=lambda h: cu(h) + xt(ALWAYS, WF, "bash"), rest=[]),
    C("plain_session_does_not_load_computer_use", ["-p", "x"], vars={"PI_COMPUTER_USE_CODESIGN_IDENTITY": None},
      err_lacks="computer use"),
    C("workflows_flag_offers_the_workflow_tools", ["--workflows"], pre=fixed(xt(ALWAYS, WEB)),
      vars={"WORKFLOWS": "1"}, rest=[]),
    C("workflows_from_the_environment", [], env={"PI_ELM_WORKFLOWS": "1"}, pre=fixed(xt(ALWAYS, WEB)),
      vars={"WORKFLOWS": "1"}),
    C("web_env_with_workflows_leaves_only_the_always_list", ["--workflows"], env={"PI_ELM_WEB": "1"},
      pre=fixed(xt(ALWAYS))),
    C("with_all_and_remote_exclude_nothing", ["--with-all", "--remote", "-p", "x"], pre=cu, rest=["-p", "x"],
      vars={"WITH_ALL": "1", "WORKFLOWS": "1", "REMOTE": "1"}),
    C("with_all_and_remote_pass_the_callers_exclusion_through", ["--with-all", "--remote", "-xt", "bash"],
      pre=cu, rest=["-xt", "bash"]),
    C("with_all_and_web_env_exclude_nothing", ["--with-all"], env={"PI_ELM_WEB": "1"}, pre=fixed([]), rest=[]),
    C("two_caller_exclusions_are_both_merged", ["-xt", "a", "-xt", "b"], pre=fixed(xt(DEFAULT_XT, "a", "b")),
      rest=[]),
    C("long_exclusion_with_a_list", ["--exclude-tools", "a,b", "-p", "x"], pre=fixed(xt(DEFAULT_XT, "a,b")),
      rest=["-p", "x"]),
    # pi reads a "--" given as an option's value as that value and keeps parsing
    # options, so a -ne or -xt after it is a real option.
    C("ne_after_a_double_dash_name_still_loads_the_policy", ["--name", "--", "-ne"],
      pre=lambda h: ext(h, *POLICY) + gate(h) + xt(DEFAULT_XT), rest=["--name", "--", "-ne"]),
    C("exclusion_after_a_double_dash_name_is_merged", ["--name", "--", "-xt", "bash"],
      pre=fixed(xt(DEFAULT_XT, "bash")), rest=["--name", "--"]),
    C("dangling_exclusion_is_left_for_pi", ["-p", "x", "-xt"], pre=fixed(xt(DEFAULT_XT)),
      rest=["-p", "x", "--exclude-tools"]),
    C("short_tools_allowlist_is_left_alone", ["-t", "read"], pre=fixed([]), rest=["-t", "read"]),
    C("allowlist_keeps_the_callers_exclusion_as_given", ["--tools", "read", "-xt", "bash"], pre=fixed([]),
      rest=["--tools", "read", "-xt", "bash"]),
    # pi has no --exclude-tools=value form; it is an unknown flag to pi, passed on.
    C("equals_exclusion_is_not_pis_syntax", ["--exclude-tools=bash"], pre=fixed(xt(DEFAULT_XT)),
      rest=["--exclude-tools=bash"]),
    C("launcher_flags_anywhere_in_the_line", ["-p", "x", "--fast", "--workflows"],
      pre=lambda h: fastpre(h) + xt(ALWAYS, WEB), rest=["-p", "x"]),
    C("a_repeated_flag_counts_once", ["--fast", "--fast"], pre=lambda h: fastpre(h) + xt(DEFAULT_XT), rest=[]),
    C("flag_with_a_value_is_not_the_launchers", ["--fast=1"], vars={"FAST": "0"}, rest=["--fast=1"],
      pre=fixed(xt(DEFAULT_XT))),
    C("flag_with_different_case_is_not_the_launchers", ["--Remote"], vars={"REMOTE": "0"}, rest=["--Remote"]),
    C("install_after_a_launcher_flag_is_refused", ["--fast", "install", "npm:x"], rc=2,
      err_has="`pi install` is not available"),
    C("install_as_prompt_text_is_not_refused", ["-p", "install"], rest=["-p", "install"]),
    C("capitalised_install_is_not_the_subcommand", ["Install"], rest=["Install"]),
    C("older_runtime_env_without_the_always_list", [], env={"ELM_EXCLUDED_TOOLS": ""}, pre=fixed(xt(WEB, WF))),
    C("no_workflow_tools_listed_leaves_no_trailing_comma", [], env={"ELM_WORKFLOW_TOOLS": ""},
      pre=fixed(xt(ALWAYS, WEB))),
    # After --, the launcher's own flags are prompt text, kept in the prompt:
    # `pi -p -- --remote` must not open the network.
    C("remote_after_double_dash_is_prompt_text", ["-p", "--", "--remote"],
      vars={"REMOTE": "0"}, rest=["-p", "--", "--remote"]),
    C("fast_after_double_dash_is_prompt_text", ["--", "--fast"],
      vars={"FAST": "0"}, rest=["--", "--fast"]),
    C("with_all_after_double_dash_is_prompt_text", ["-p", "--", "--with-all"],
      vars={"WITH_ALL": "0"}, rest=["-p", "--", "--with-all"]),
)


@generate
class LauncherFlagTests(BatchTest):
    """--fast/--llama/--remote/--workflows/--with-all, -ne, -xt, and pi install."""

    CASES = FLAG_CASES
    PARSE = block(LAUNCHER, "FAST=0; LLAMA=0; REMOTE=0;", "# --- ELM-only policy")
    PRE = block(LAUNCHER, "# --- --remote: let this run", "# --- no update work at launch")

    @classmethod
    def prepare(cls):
        def install(name, policy=POLICY, extras=("todo", "skill-router", "elm-shim"), npm=True, gate_entry=True):
            h = cls.tmp / name
            for n in (*policy, *extras):
                touch(h / f"agent/extensions/{n}.ts", "export default () => {};\n")
            if npm:
                (h / GATE_REL).mkdir(parents=True)
                if gate_entry:
                    touch(h / GATE_REL / "src/index.ts")
                (h / "agent/npm/node_modules/pi-web-access").mkdir(parents=True)
                touch(h / CU_REL)
        install("full")
        install("bare", extras=(), npm=False)
        install("brokengate", gate_entry=False)
        install("nopolicy", policy=("elm-only", "protected-paths", "pinned-instructions"))

    @classmethod
    def prelude(cls):
        return f'. {q(ROOT / "lib/policy.sh")}\nELM_LLAMA_MODEL_ID={q(LLAMA)}'

    @classmethod
    def body(cls, case):
        env = {"ELM_EXCLUDED_TOOLS": ALWAYS, "ELM_WEB_TOOLS": WEB, "ELM_WORKFLOW_TOOLS": WF, **case.env}
        return "\n".join([
            "set -euo pipefail", f"HERE={q(cls.tmp / case.kw.get('variant', 'full'))}", exports(env),
            setargs(case.args), cls.PARSE, cls.PRE,
            "_v FAST LLAMA REMOTE WORKFLOWS WITH_ALL PI_ELM_WEB ELM_PI_PROXY_ALLOW PI_COMPUTER_USE_CODESIGN_IDENTITY",
            '_a PRE ${PRE[@]+"${PRE[@]}"}', '_a ARG "$@"'])

    def check(self, case, r):
        super().check(case, r)
        here = self.tmp / case.kw.get("variant", "full")
        if "pre" in case.kw:
            self.assertEqual(case.kw["pre"](here), r.list("PRE"))
        if "rest" in case.kw:
            self.assertEqual(case.kw["rest"], r.list("ARG"))


# --- --help / -h detection ------------------------------------------------------

@generate
class HelpDetectionTests(BatchTest):
    """Which argument lists count as asking for help."""

    CASES = (
        C("short_h_alone", ["-h"], vars={"WANTS_HELP": "1"}),
        C("help_after_other_arguments", ["-p", "x", "--help"], vars={"WANTS_HELP": "1"}),
        C("short_h_after_double_dash_is_text", ["--", "-h"], vars={"WANTS_HELP": "0"}),
        C("single_dash_help_is_not_help", ["-help"], vars={"WANTS_HELP": "0"}),
        C("help_with_a_suffix_is_not_help", ["--helpme"], vars={"WANTS_HELP": "0"}),
        C("bare_word_help_is_a_prompt", ["help"], vars={"WANTS_HELP": "0"}),
        C("help_before_double_dash_still_counts", ["--help", "--", "x"], vars={"WANTS_HELP": "1"}),
        # pi takes the "--" as --name's value and reads on, so --help is an option.
        C("help_after_a_double_dash_name_value", ["--name", "--", "--help"], vars={"WANTS_HELP": "1"}),
        C("help_as_an_option_value_is_not_help", ["--name", "--help"], vars={"WANTS_HELP": "0"}),
    )
    BLOCK = block(LAUNCHER, "WANTS_HELP=0", "# Telemetry is off")

    @classmethod
    def body(cls, case):
        return "\n".join(["set -euo pipefail", f". {q(ROOT / 'lib/policy.sh')}", setargs(case.args), cls.BLOCK,
                          "_v WANTS_HELP"])


# --- the argument guard (lib/policy.sh elm_policy_check_args) ----------------------

P = 'provider "{}" is not available.'
M = 'model "{}" is outside the allowed providers.'
MP = 'model pattern "{}" is outside the allowed providers.'
API = "--api-key is disabled: it can route a session to another provider."
EXT = "-e/--extension is disabled: \"{}\" would run unreviewed, with this install's access and its own network code."


def allow(name, args, **kw):
    return C(name, args, verdict="ALLOW", **kw)


def deny(name, args, message, **kw):
    return C(name, args, verdict="DENY:" + message, **kw)


@generate
class GuardTests(BatchTest):
    """Every --provider/--model/--models/--api-key form, allowed or refused, with the
    message the launcher prints."""

    CASES = (
        allow("no_arguments", []),
        allow("prompt_only", ["-p", "hello"]),
        allow("provider_elm_shim", ["--provider", "elm-shim"]),
        allow("provider_with_padding", ["--provider", "  elm  "]),
        allow("provider_equals_form", ["--provider=elm"]),
        allow("provider_equals_upper_case", ["--provider=ELM-SHIM"]),
        allow("model_on_elm", ["--model", "elm/anything"]),
        allow("model_with_padding", ["--model", " elm/x "]),
        allow("model_bare_llama_id", ["--model", LLAMA]),
        allow("model_bare_qwen_id_lower_case", ["--model", QWEN.lower()]),
        allow("short_m_with_a_value", ["-m", "elm/x"]),
        allow("short_m_attached_value", ["-melm/x"]),
        allow("short_m_equals_value", ["-m=elm-shim/x"]),
        allow("models_both_allowed_providers", ["--models", "elm/*,elm-shim/*"]),
        allow("models_equals_form", ["--models=elm/a"]),
        allow("models_under_a_one_provider_allowlist", ["--models", "elm/a,ELM/b"],
              env={"ELM_ALLOWED_PROVIDERS": "elm"}),
        allow("empty_model_is_pis_default", ["--model", ""]),
        allow("last_model_wins_allowed", ["--model", "openai/x", "--model", "elm/x"]),
        allow("last_models_wins_allowed", ["--models", "openai/*", "--models", "elm/*"]),
        allow("option_text_inside_one_argument", ["-p", "--model anthropic/x"]),
        allow("dangling_provider_is_pis_error", ["--provider"]),
        allow("dangling_short_m_is_pis_error", ["-m"]),
        allow("dangling_models_is_pis_error", ["--models"]),
        allow("models_with_empty_patterns", ["--models", "elm/a,,elm/b,"]),
        allow("dangling_api_key_is_pis_error", ["--api-key"]),
        allow("api_key_after_double_dash_is_text", ["--", "--api-key", "k"]),
        allow("remove_subcommand_is_not_a_session", ["remove", "--model", "openai/x"]),
        allow("default_allowlist_when_unset", ["--provider", "elm-shim"], env={"ELM_ALLOWED_PROVIDERS": None}),
        allow("allowlist_compared_case_insensitively", ["--provider", "elm"], env={"ELM_ALLOWED_PROVIDERS": "ELM"}),
        deny("narrowed_allowlist_refuses_the_shim", ["--provider", "elm-shim"], P.format("elm-shim"),
             env={"ELM_ALLOWED_PROVIDERS": "elm"}),
        deny("provider_openai", ["--provider", "openai"], P.format("openai")),
        deny("provider_equals_openai", ["--provider=openai"], P.format("openai")),
        deny("provider_lookalike_with_suffix", ["--provider", "elmx"], P.format("elmx")),
        deny("provider_prefix_of_elm", ["--provider", "el"], P.format("el")),
        deny("provider_two_words", ["--provider", "elm elm-shim"], P.format("elm elm-shim")),
        deny("provider_message_keeps_the_padding", ["--provider", " openai "], P.format(" openai ")),
        deny("model_without_a_provider", ["--model", "gpt-5"], M.format("gpt-5")),
        deny("model_equals_form", ["--model=openai/gpt-5"], M.format("openai/gpt-5")),
        deny("short_m_attached_refused", ["-manthropic/x"], M.format("anthropic/x")),
        deny("short_m_equals_refused", ["-m=anthropic/x"], M.format("anthropic/x")),
        deny("model_provider_lookalike", ["--model", "elmx/q"], M.format("elmx/q")),
        deny("model_shim_lookalike", ["--model", "elm-shim2/x"], M.format("elm-shim2/x")),
        deny("bare_id_must_match_exactly", ["--model", f"{LLAMA}:high"], M.format(f"{LLAMA}:high")),
        deny("bare_name_refused_even_with_provider_elm", ["--provider", "elm", "--model", "claude-opus"],
             M.format("claude-opus")),
        deny("last_model_wins_refused", ["--model", "elm/x", "--model", "openai/x"], M.format("openai/x")),
        deny("models_with_a_bare_name", ["--models", "gpt-4o"], MP.format("gpt-4o")),
        deny("models_names_the_first_refused_pattern", ["--models", "elm/a,openai/b,google/c"],
             MP.format("openai/b"), env={"ELM_ALLOWED_PROVIDERS": "elm"}),
        deny("models_equals_refused", ["--models=anthropic/*"], MP.format("anthropic/*")),
        # The pattern is matched as text, never expanded against files in the
        # working folder (where "*/*" could become "elm/x").
        deny("models_glob_is_not_expanded", ["--models", "*/*"], MP.format("*/*")),
        deny("models_message_is_trimmed", ["--models", "  google/x  "], MP.format("google/x")),
        deny("api_key_with_a_value", ["--api-key", "k"], API),
        deny("api_key_reported_before_provider", ["--provider", "openai", "--api-key", "k"], API),
        deny("extension_reported_before_api_key", ["--api-key", "k", "-e", "x.ts"], EXT.format("x.ts")),
        deny("provider_reported_before_model", ["--provider", "openai", "--model", "elm/x"], P.format("openai")),
        deny("model_refused_under_an_allowed_provider", ["--provider", "elm", "--model", "openai/x"],
             M.format("openai/x")),
        # pi takes the next argument as the value of these options whatever it
        # is, "--" included, and then reads the rest of the line as options.
        deny("append_system_prompt_value_hides_a_model", ["--append-system-prompt", "--", "--model",
             "anthropic/claude-opus-5"], M.format("anthropic/claude-opus-5")),
        deny("name_value_hides_a_provider", ["--name", "--", "--provider", "openai"], P.format("openai")),
        deny("theme_value_hides_an_extension", ["--theme", "--", "-e", "./ssh.ts"], EXT.format("./ssh.ts")),
    )

    @classmethod
    def prepare(cls):
        touch(cls.tmp / "elm/x")   # what "*/*" would expand to in this folder

    @classmethod
    def prelude(cls):
        return f". {q(ROOT / 'lib/policy.sh')}"

    @classmethod
    def body(cls, case):
        env = {"ELM_ALLOWED_PROVIDERS": "elm elm-shim", "ELM_QWEN_MODEL_ID": QWEN, "ELM_LLAMA_MODEL_ID": LLAMA,
               **case.env}
        return "\n".join([exports(env), setargs(case.args),
                          'if elm_policy_check_args "$@"; then V=ALLOW; else V="DENY:$ELM_POLICY_ERROR"; fi',
                          "_v V"])

    def check(self, case, r):
        self.assertEqual(0, r.rc, r.err)
        self.assertEqual(case.kw["verdict"], r.vars["V"])


# --- does this session need the key, and may it start here? ------------------------

EXACT = "\n".join(CONFIG["untrustedFolders"]["exact"])
TREE = "\n".join(CONFIG["untrustedFolders"]["tree"])


@generate
class SessionGateTests(BatchTest):
    """The key check and the untrusted-folder refusal, with the commands exempt from both."""

    CASES = (
        C("session_in_a_project", ["-p", "x"], cwd="project"),
        C("session_without_a_key", ["-p", "x"], cwd="project", env={"ELM_API_KEY": ""}, rc=1,
          err_has="ELM_API_KEY is not set"),
        C("update_without_a_key", ["update"], cwd="project", env={"ELM_API_KEY": ""},
          vars={"NEEDS_ELM_KEY": "0"}),
        C("setup_without_a_key", ["setup", "--python"], cwd="project", env={"ELM_API_KEY": ""}),
        C("list_models_without_a_key", ["--list-models"], cwd="project", env={"ELM_API_KEY": None}),
        C("version_without_a_key", ["--version"], cwd="project", env={"ELM_API_KEY": ""}),
        # -v is pi's own short --version.
        C("short_version_without_a_key", ["-v"], cwd="project", env={"ELM_API_KEY": ""},
          vars={"NEEDS_ELM_KEY": "0"}),
        C("session_in_home", ["-p", "x"], cwd="home", rc=2, home_msg="your home folder"),
        C("version_in_home", ["--version"], cwd="home"),
        C("list_models_in_home", ["--list-models", "qwen"], cwd="home"),
        C("update_in_home", ["update"], cwd="home"),
        C("forced_session_in_home", ["-p", "x"], cwd="home", env={"PI_FORCE": "1"}),
        C("child_session_in_home", ["-p", "x"], cwd="home", env={"PI_ELM_CHILD": "1"}),
        C("force_zero_is_not_force", ["-p", "x"], cwd="home", env={"PI_FORCE": "0"}, rc=2,
          home_msg="your home folder"),
        C("session_in_a_credential_folder", [], cwd="home/.aws", rc=2,
          home_msg="inside {home}/.aws, which holds credentials or system files"),
        C("session_in_downloads", [], cwd="home/Downloads", rc=2,
          home_msg="~/Downloads, which holds far more than one project"),
        C("prompt_named_update_still_a_session", ["-p", "update"], cwd="home", rc=2,
          home_msg="your home folder"),
    )
    BLOCK = block(LAUNCHER, "NEEDS_ELM_KEY=1", "# --- --remote: let this run")

    @classmethod
    def prepare(cls):
        (cls.tmp / "project").mkdir()
        for sub in (".aws", "Downloads"):
            (cls.home / sub).mkdir()

    @classmethod
    def prelude(cls):
        return f". {q(ROOT / 'lib/policy.sh')}"

    @classmethod
    def body(cls, case):
        env = {"ELM_API_KEY": "elm-test", "ELM_UNTRUSTED_EXACT": EXACT, "ELM_UNTRUSTED_TREE": TREE, **case.env}
        return "\n".join(["set -euo pipefail", f"cd {q(cls.tmp / case.kw['cwd'])}", f"HERE={q(cls.tmp / 'inst')}",
                          exports(env), setargs(case.args), cls.BLOCK, "_v NEEDS_ELM_KEY"])

    def check(self, case, r):
        super().check(case, r)
        if "home_msg" in case.kw:
            what = case.kw["home_msg"].format(home=self.home)
            self.assertIn(f"pi: not starting in {self.tmp / case.kw['cwd']} - {what}.", r.err)


# --- pi setup ----------------------------------------------------------------------

@generate
class SetupTests(BatchTest):
    """`pi setup` turns its own spellings into bootstrap.sh's flags, or prints the list."""

    CASES = (
        C("all_means_with_all", ["setup", "--all"], out_has="BOOT --non-interactive --with-all"),
        C("no_pypi_index_passes_through", ["setup", "--no-pypi-index"],
          out_has="BOOT --non-interactive --no-pypi-index"),
        C("no_python_passes_through", ["setup", "--no-python"], out_has="BOOT --non-interactive --no-python"),
        C("python_and_index_together", ["setup", "--python", "--pypi-index"],
          out_has="BOOT --non-interactive --with-python --with-pypi-index"),
        C("order_is_kept", ["setup", "--all", "--no-pypi-index"],
          out_has="BOOT --non-interactive --with-all --no-pypi-index"),
        C("nothing_to_set_up_prints_the_parts", ["setup"], rc=2,
          err_has=["Optional parts", "pi setup --all"], out_lacks="BOOT"),
        C("an_unknown_option_runs_nothing", ["setup", "--python", "--bogus"], rc=2,
          err_has="pi setup: unknown option: --bogus", out_lacks="BOOT"),
        C("a_word_without_dashes_is_unknown", ["setup", "python"], rc=2,
          err_has="pi setup: unknown option: python"),
        C("setup_runs_online", ["setup", "--python"], env={"PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1"},
          out_has="OFFLINE=unset/unset"),
        C("not_setup_falls_through", ["-p", "setup"], out_has="@@FELLTHROUGH", out_lacks="BOOT"),
    )
    USAGE = block(LAUNCHER, "elm_usage() {", "WANTS_HELP=0")
    BLOCK = block(LAUNCHER, 'if [ "${1:-}" = "setup" ]; then', "# --- --with-all: every optional extra, set up once")

    @classmethod
    def prepare(cls):
        touch(cls.tmp / "inst/bootstrap.sh",
              '#!/bin/sh\necho "BOOT $*"\necho "OFFLINE=${PI_OFFLINE-unset}/${PI_SKIP_VERSION_CHECK-unset}"\n', 0o755)

    @classmethod
    def body(cls, case):
        return "\n".join(["set -euo pipefail", f"HERE={q(cls.tmp / 'inst')}", exports(case.env), cls.USAGE,
                          setargs(case.args), cls.BLOCK, "printf '@@FELLTHROUGH\\n'"])


# --- pi update -----------------------------------------------------------------------

@generate
class UpdateTests(BatchTest):
    """Which `pi update` forms are taken over, and how the installer is called."""

    CASES = (
        C("update_models_is_pis_own", ["update", "--models"], out_has="@@FELLTHROUGH", out_lacks="INSTALL"),
        C("extensions_and_models_together_are_refused", ["update", "--extensions", "--models"], rc=2,
          err_has="must be run separately"),
        C("models_and_extensions_in_either_order", ["update", "--models", "--extensions"], rc=2,
          err_has="must be run separately"),
        C("update_with_other_flags_still_runs_the_installer", ["update", "--force"],
          out_has="INSTALL --update --no-path --no-link"),
        C("installer_runs_against_this_install_unlinked_and_online", ["update"],
          env={"PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1"},
          out_has="ENV prefix={here} nopath=1 nolink=1 offline=unset/unset"),
        C("installer_success_exits_zero", ["update"], err_has="pi: updating this install.",
          out_lacks="@@FELLTHROUGH"),
        C("extensions_exit_status_is_bootstraps", ["update", "--extensions"], env={"STUB_EXIT": "3"}, rc=3,
          out_has="BOOT --force-packages --non-interactive"),
        C("extensions_says_what_it_reinstalls", ["update", "--extensions"],
          err_has="reinstalling the extension packages at the tested versions"),
        C("extensions_runs_online", ["update", "--extensions"], env={"PI_OFFLINE": "1"},
          out_has="ENV offline=unset"),
        C("update_as_prompt_text_falls_through", ["-p", "update"], out_has="@@FELLTHROUGH", out_lacks="INSTALL"),
    )
    BLOCK = block(LAUNCHER, 'if [ "${1:-}" = "update" ]; then', "# --- 'pi setup'")

    @classmethod
    def prepare(cls):
        here = cls.tmp / "inst"
        touch(here / "install.sh", '#!/bin/sh\necho "INSTALL $*"\n'
              'echo "ENV prefix=$ELM_PI_PREFIX nopath=$ELM_PI_NO_PATH nolink=$ELM_PI_NO_LINK '
              'offline=${PI_OFFLINE-unset}/${PI_SKIP_VERSION_CHECK-unset}"\nexit "${STUB_EXIT:-0}"\n', 0o755)
        touch(here / "bootstrap.sh", '#!/bin/sh\necho "BOOT $*"\necho "ENV offline=${PI_OFFLINE-unset}"\n'
              'exit "${STUB_EXIT:-0}"\n', 0o755)

    @classmethod
    def body(cls, case):
        return "\n".join(["set -euo pipefail", f"HERE={q(cls.tmp / 'inst')}", exports(case.env),
                          setargs(case.args), cls.BLOCK, "printf '@@FELLTHROUGH\\n'"])

    def check(self, case, r):
        out_has = [t.format(here=self.tmp / "inst") for t in as_list(case.kw.get("out_has"))]
        super().check(Case(case.name, **{**case.kw, "out_has": out_has}), r)


# --- --with-all: set up once, then start again ------------------------------------

@generate
class WithAllSetupTests(BatchTest):
    """When --with-all runs bootstrap.sh, and what it starts afterwards."""

    CASES = (
        C("a_child_never_sets_up", with_all=1, env={"PI_ELM_CHILD": "1"}, built="", continued=True, calls=None),
        C("both_parts_present_starts_straight_away", with_all=1, built="python index", continued=True, calls=None),
        C("an_empty_index_counts_as_missing", with_all=1, built="python emptyindex", continued=False,
          calls="--non-interactive --with-all", out_has="RELAUNCH 1 --with-all -p x"),
        C("a_missing_python_alone_sets_up", with_all=1, built="index", continued=False,
          calls="--non-interactive --with-all", out_has="RELAUNCH 1 --with-all -p x"),
        C("after_one_attempt_starts_without_them", with_all=1, built="", env={"ELM_PI_WITH_ALL_SET_UP": "1"},
          continued=True, calls=None, err_has="some optional parts did not build"),
        C("a_failed_setup_stops", with_all=1, built="", env={"STUB_EXIT": "1"}, continued=False, rc=1,
          calls="--non-interactive --with-all", err_has="setting up the optional parts failed",
          out_lacks="RELAUNCH"),
        C("without_with_all_nothing_is_set_up", with_all=0, built="", continued=True, calls=None),
        C("setup_runs_online", with_all=1, built="", env={"PI_OFFLINE": "1"}, continued=False,
          calls="--non-interactive --with-all", offline="unset"),
    )
    BLOCK = block(LAUNCHER, 'if [ "$WITH_ALL" = "1" ] && [ -z "${PI_ELM_CHILD:-}" ]',
                  "# --- keep .pi out of the repository")

    @classmethod
    def prepare(cls):
        for i, case in enumerate(cls.CASES):
            h = cls.tmp / f"w{i}"
            built = case.kw["built"].split()
            if "python" in built:
                touch(h / "agent/python/env/bin/python", "#!/bin/sh\n", 0o755)
            if "index" in built:
                touch(h / "agent/pypi-index.db", "x")
            if "emptyindex" in built:
                touch(h / "agent/pypi-index.db", "")
            touch(h / "bootstrap.sh", '#!/bin/sh\necho "$*" >> "$(dirname "$0")/calls"\n'
                  'echo "${PI_OFFLINE-unset}" >> "$(dirname "$0")/offline"\nexit "${STUB_EXIT:-0}"\n', 0o755)
            touch(h / "pi", '#!/bin/sh\necho "RELAUNCH ${ELM_PI_WITH_ALL_SET_UP-} $*"\n', 0o755)

    @classmethod
    def body(cls, case):
        i = cls.CASES.index(case)
        return "\n".join(["set -euo pipefail", f"HERE={q(cls.tmp / f'w{i}')}", exports(case.env),
                          f"WITH_ALL={case.kw['with_all']}", "ORIG_ARGS=(--with-all -p x)",
                          cls.BLOCK, "printf '@@CONTINUED\\n'"])

    def check(self, case, r):
        super().check(case, r)
        h = self.tmp / f"w{self.CASES.index(case)}"
        self.assertEqual(case.kw["continued"], "@@CONTINUED" in r.out)
        calls = h / "calls"
        self.assertEqual(case.kw["calls"], calls.read_text().strip() if calls.exists() else None)
        if "offline" in case.kw:
            self.assertEqual(case.kw["offline"], (h / "offline").read_text().strip())


# --- the offline default -------------------------------------------------------------

@generate
class OfflineDefaultTests(BatchTest):
    """pi's startup network work is off for sessions, on for update and setup."""

    CASES = (
        C("session_starts_offline", ["-p", "x"], vars={"PI_OFFLINE": "1", "PI_SKIP_VERSION_CHECK": "1"}),
        C("update_is_left_online", ["update"], vars={"PI_OFFLINE": None, "PI_SKIP_VERSION_CHECK": None}),
        C("setup_is_left_online", ["setup", "--all"], vars={"PI_OFFLINE": None}),
        C("startup_checks_restored_on_request", ["-p", "x"], env={"PI_ELM_STARTUP_CHECKS": "1"},
          vars={"PI_OFFLINE": None, "PI_SKIP_VERSION_CHECK": None}),
        C("a_callers_own_setting_is_kept", [], env={"PI_OFFLINE": "0"},
          vars={"PI_OFFLINE": "0", "PI_SKIP_VERSION_CHECK": "1"}),
    )
    BLOCK = block(LAUNCHER, 'case "${1:-}" in\n  update|setup) ;;', "# --- intercept 'pi update'")

    @classmethod
    def body(cls, case):
        return "\n".join(["set -euo pipefail", "unset PI_OFFLINE PI_SKIP_VERSION_CHECK", exports(case.env),
                          setargs(case.args), cls.BLOCK, "_v PI_OFFLINE PI_SKIP_VERSION_CHECK"])


# --- which session folder gets secured -------------------------------------------------

@generate
class SessionDirTests(BatchTest):
    """The session folder the launcher locks down is the one pi will write to."""

    CASES = (
        C("settings_value_by_default", [], vars={"SESSION_DIR": ".pi/sessions"}),
        C("environment_overrides_settings", [], env={"PI_CODING_AGENT_SESSION_DIR": "/s/env"},
          vars={"SESSION_DIR": "/s/env"}),
        C("argument_with_a_value", ["--session-dir", "/s/a"], vars={"SESSION_DIR": "/s/a"}),
        C("argument_equals_form", ["--session-dir=/s/b"], vars={"SESSION_DIR": "/s/b"}),
        C("argument_beats_the_environment", ["--session-dir", "/s/a"],
          env={"PI_CODING_AGENT_SESSION_DIR": "/s/env"}, vars={"SESSION_DIR": "/s/a"}),
        C("last_argument_wins", ["--session-dir", "/s/a", "--session-dir=/s/b"], vars={"SESSION_DIR": "/s/b"}),
        C("after_double_dash_is_prompt_text", ["-p", "--", "--session-dir", "/s/a"],
          vars={"SESSION_DIR": ".pi/sessions"}),
        C("dangling_flag_keeps_the_default", ["-p", "x", "--session-dir"], vars={"SESSION_DIR": ".pi/sessions"}),
        C("empty_environment_value_is_ignored", [], env={"PI_CODING_AGENT_SESSION_DIR": ""},
          vars={"SESSION_DIR": ".pi/sessions"}),
    )
    BLOCK = block(LAUNCHER, '[ -z "${PI_CODING_AGENT_SESSION_DIR:-}" ]', "type elm_secure_runtime_state")

    @classmethod
    def body(cls, case):
        return "\n".join(["set -euo pipefail", "SESSION_DIR=.pi/sessions", exports(case.env),
                          setargs(case.args), cls.BLOCK, "_v SESSION_DIR"])


# --- the proxy's allow list and upstream ----------------------------------------------

PYPI = "pypi.org,files.pythonhosted.org"


@generate
class ProxyEnvironmentTests(BatchTest):
    """The gateway host, the hosts the proxy allows, and which inherited proxy is chained to."""

    CASES = (
        C("default_gateway", [], vars={"ELM_HOST": "elm.edina.ac.uk", "PROXY_ALLOW": f"elm.edina.ac.uk,{PYPI}"}),
        C("gateway_with_a_port", [], env={"ELM_BASE_URL": "http://gw.example:8443/v1"},
          vars={"ELM_HOST": "gw.example"}),
        C("gateway_without_a_scheme", [], env={"ELM_BASE_URL": "gw.example/api"}, vars={"ELM_HOST": "gw.example"}),
        C("gateway_scheme_in_capitals", [], env={"ELM_BASE_URL": "HTTPS://Upper.Example/v1"},
          vars={"ELM_HOST": "Upper.Example"}),
        C("empty_base_url_means_the_default", [], env={"ELM_BASE_URL": ""}, vars={"ELM_HOST": "elm.edina.ac.uk"}),
        C("a_base_url_with_no_host_is_refused", [], env={"ELM_BASE_URL": "https:///v1"}, rc=1,
          err_has="REFUSED could not work out the ELM host"),
        C("run_hosts_come_last", [], env={"ELM_PI_PROXY_ALLOW": "a.example,b.example"},
          vars={"PROXY_ALLOW": f"elm.edina.ac.uk,{PYPI},a.example,b.example"}),
        C("no_session_hosts_listed", [], env={"ELM_PROXY_ALLOW": ""}, vars={"PROXY_ALLOW": "elm.edina.ac.uk"}),
        C("campus_proxy_is_chained", [], env={"HTTPS_PROXY": "http://campus.example:3128"},
          vars={"PROXY_UPSTREAM": "http://campus.example:3128",
                "ELM_PI_UPSTREAM_PROXY": "http://campus.example:3128"}),
        C("lower_case_proxy_variable_is_chained", [], env={"https_proxy": "http://campus.example:3128"},
          vars={"PROXY_UPSTREAM": "http://campus.example:3128"}),
        C("upper_case_proxy_variable_wins", [], env={"HTTPS_PROXY": "http://a.example:1",
                                                    "https_proxy": "http://b.example:2"},
          vars={"PROXY_UPSTREAM": "http://a.example:1"}),
        C("our_own_proxy_on_127_is_not_chained", [], env={"HTTPS_PROXY": "http://127.0.0.1:50000"},
          vars={"PROXY_UPSTREAM": "", "INHERITED_PROXY": "http://127.0.0.1:50000", "ELM_PI_UPSTREAM_PROXY": None}),
        C("our_own_proxy_on_localhost_is_not_chained", [], env={"HTTPS_PROXY": "http://localhost:50000"},
          vars={"PROXY_UPSTREAM": "", "ELM_PI_UPSTREAM_PROXY": None}),
        C("our_own_proxy_on_ipv6_loopback_is_not_chained", [], env={"HTTPS_PROXY": "http://[::1]:50000"},
          vars={"PROXY_UPSTREAM": ""}),
        C("another_loopback_address_is_chained", [], env={"HTTPS_PROXY": "http://127.0.0.2:3128"},
          vars={"PROXY_UPSTREAM": "http://127.0.0.2:3128"}),
        C("no_proxy_in_the_environment", [], vars={"PROXY_UPSTREAM": "", "ELM_PI_UPSTREAM_PROXY": None}),
    )
    BLOCK = block(LAUNCHER, 'ELM_HOST="$(printf', "# --- is a proxy of ours alive")

    @classmethod
    def body(cls, case):
        env = {"ELM_PROXY_ALLOW": PYPI, **case.env}
        return "\n".join(["set -euo pipefail", 'refuse_unproxied() { echo "REFUSED $1" >&2; exit 1; }',
                          "unset ELM_BASE_URL ELM_PI_PROXY_ALLOW HTTPS_PROXY https_proxy ELM_PI_UPSTREAM_PROXY",
                          exports(env), cls.BLOCK,
                          "_v ELM_HOST PROXY_ALLOW PROXY_UPSTREAM INHERITED_PROXY ELM_PI_UPSTREAM_PROXY"])


# --- matplotlib: files, not windows -----------------------------------------------------

@generate
class MatplotlibTests(BatchTest):
    """The install's matplotlibrc is used only where the researcher has no setup of their own."""

    CASES = (
        C("no_setup_of_their_own", [], vars={"MATPLOTLIBRC": "{here}/config/matplotlibrc"}),
        C("a_backend_in_the_environment", [], env={"MPLBACKEND": "TkAgg"}, vars={"MATPLOTLIBRC": None}),
        C("their_own_matplotlibrc_variable", [], env={"MATPLOTLIBRC": "/theirs"}, vars={"MATPLOTLIBRC": "/theirs"}),
        C("an_xdg_config_rc", [], env={"XDG_CONFIG_HOME": "{tmp}/xdg"}, vars={"MATPLOTLIBRC": None}),
        C("a_dot_config_rc_in_home", [], env={"HOME": "{tmp}/home_cfg"}, vars={"MATPLOTLIBRC": None}),
        C("a_dot_matplotlib_rc_in_home", [], env={"HOME": "{tmp}/home_dot"}, vars={"MATPLOTLIBRC": None}),
        C("an_mplconfigdir_with_an_rc", [], env={"MPLCONFIGDIR": "{tmp}/mpl"}, vars={"MATPLOTLIBRC": None}),
        C("an_mplconfigdir_without_an_rc", [], env={"MPLCONFIGDIR": "{tmp}/empty"},
          vars={"MATPLOTLIBRC": "{here}/config/matplotlibrc"}),
        C("an_install_without_the_file", [], variant="norc", vars={"MATPLOTLIBRC": None}),
    )
    BLOCK = block(LAUNCHER, "mpl_user_rc=0", "# pi's half of --help")

    @classmethod
    def prepare(cls):
        touch(cls.tmp / "inst/config/matplotlibrc", "backend: Agg\n")
        (cls.tmp / "norc").mkdir()
        touch(cls.tmp / "xdg/matplotlib/matplotlibrc")
        touch(cls.tmp / "home_cfg/.config/matplotlib/matplotlibrc")
        touch(cls.tmp / "home_dot/.matplotlib/matplotlibrc")
        touch(cls.tmp / "mpl/matplotlibrc")
        (cls.tmp / "empty").mkdir()

    @classmethod
    def fill(cls, value, case):
        here = cls.tmp / case.kw.get("variant", "inst")
        return None if value is None else value.format(tmp=cls.tmp, here=here)

    @classmethod
    def body(cls, case):
        env = {k: cls.fill(v, case) for k, v in case.env.items()}
        return "\n".join(["set -euo pipefail", "unset MPLBACKEND MATPLOTLIBRC MPLCONFIGDIR XDG_CONFIG_HOME",
                          f"HERE={q(cls.tmp / case.kw.get('variant', 'inst'))}", exports(env), cls.BLOCK,
                          "_v MATPLOTLIBRC"])

    def check(self, case, r):
        self.assertEqual(0, r.rc, r.err)
        self.assertEqual(self.fill(case.kw["vars"]["MATPLOTLIBRC"], case), r.vars["MATPLOTLIBRC"])


# --- the agent's Python and pixi on PATH -------------------------------------------------

BASE_PATH = "{h}/agent/bin:{h}/.node/bin:/usr/bin:/bin"


@generate
class AgentPathTests(BatchTest):
    """Where the agent's Python and pixi go on PATH, and when the researcher's own env stays first."""

    CASES = (
        C("no_agent_python", [], variant="none", path=BASE_PATH, vars={"ELM_PI_AGENT_PYTHON": None}),
        C("agent_python_after_agent_bin", [], variant="py",
          path="{h}/agent/bin:{h}/agent/python/env/bin:{h}/.node/bin:/usr/bin:/bin",
          vars={"ELM_PI_AGENT_PYTHON": "{h}/agent/python/env/bin/python",
                "UV_PYTHON_INSTALL_DIR": "{h}/agent/python/interpreters", "UV_CACHE_DIR": "{h}/agent/python/cache"}),
        C("an_active_virtualenv_stays_first", [], variant="py", env={"VIRTUAL_ENV": "/venv"}, path=BASE_PATH,
          vars={"ELM_PI_AGENT_PYTHON": "{h}/agent/python/env/bin/python"}),
        C("conda_base_does_not_count", [], variant="py", env={"CONDA_DEFAULT_ENV": "base"},
          path="{h}/agent/bin:{h}/agent/python/env/bin:{h}/.node/bin:/usr/bin:/bin"),
        C("a_named_conda_env_stays_first", [], variant="py", env={"CONDA_DEFAULT_ENV": "analysis"},
          path=BASE_PATH),
        C("a_child_already_has_it", [], variant="py",
          start="{h}/agent/bin:{h}/agent/python/env/bin:/usr/bin:/bin",
          path="{h}/agent/bin:{h}/agent/python/env/bin:/usr/bin:/bin"),
        C("pixi_tools_after_agent_bin", [], variant="pixi",
          path="{h}/agent/bin:{h}/agent/pixi/bin:{h}/.node/bin:/usr/bin:/bin",
          vars={"PIXI_HOME": "{h}/agent/pixi", "PIXI_CACHE_DIR": "{h}/agent/pixi/cache"}),
        C("pixi_before_the_agent_python", [], variant="both",
          path="{h}/agent/bin:{h}/agent/pixi/bin:{h}/agent/python/env/bin:{h}/.node/bin:/usr/bin:/bin"),
        C("no_pixi_no_pixi_home", [], variant="py", vars={"PIXI_HOME": None}),
    )
    BLOCK = block(LAUNCHER, 'AGENT_PY_ENV="$HERE/agent/python/env"', "# --- where jiti keeps")

    @classmethod
    def prepare(cls):
        for name in ("py", "both"):
            touch(cls.tmp / name / "agent/python/env/bin/python", "#!/bin/sh\n", 0o755)
        for name in ("pixi", "both"):
            touch(cls.tmp / name / "agent/bin/pixi", "#!/bin/sh\n", 0o755)
        (cls.tmp / "none").mkdir()

    @classmethod
    def body(cls, case):
        h = cls.tmp / case.kw["variant"]
        start = case.kw.get("start", BASE_PATH).format(h=h)
        return "\n".join(["set -euo pipefail", "unset VIRTUAL_ENV CONDA_DEFAULT_ENV", f"HERE={q(h)}",
                          f"PATH={q(start)}", exports(case.env), cls.BLOCK,
                          "_v PATH ELM_PI_AGENT_PYTHON UV_PYTHON_INSTALL_DIR UV_CACHE_DIR PIXI_HOME PIXI_CACHE_DIR"])

    def check(self, case, r):
        self.assertEqual(0, r.rc, r.err)
        h = self.tmp / case.kw["variant"]
        if "path" in case.kw:
            self.assertEqual(case.kw["path"].format(h=h), r.vars["PATH"])
        for key, want in case.kw.get("vars", {}).items():
            self.assertEqual(None if want is None else want.format(h=h), r.vars[key], key)


# --- a busy machine ------------------------------------------------------------------------

def busy(load, cores, runners=0):
    return f"pi: this machine is busy - load {load} across {cores} threads, {runners} sub-agent runner(s) live."


@generate
class BusyMachineTests(BatchTest):
    """The load notice: when it shows, what it says, and when it refuses."""

    CASES = (
        C("an_idle_machine_says_nothing", load="1.20", cores=4, quiet=True),
        C("over_one_and_a_half_times_warns_and_starts", load="6.50", cores=4,
          err_has=[busy("6.50", 4), "Starting anyway"]),
        C("exactly_one_and_a_half_times_is_not_busy", load="6.00", cores=4, quiet=True),
        C("strict_load_refuses_when_busy", load="9.00", cores=4, env={"PI_STRICT_LOAD": "1"}, rc=1,
          err_has="PI_STRICT_LOAD=1 is set, so not starting"),
        C("strict_load_starts_when_idle", load="1.00", cores=4, env={"PI_STRICT_LOAD": "1"}, quiet=True),
        C("force_silences_the_warning", load="9.00", cores=4, env={"PI_FORCE": "1"}, quiet=True),
        C("a_child_is_never_warned", load="9.00", cores=4, env={"PI_ELM_CHILD": "1"}, quiet=True),
        C("live_runners_are_noted_when_idle", load="1.00", cores=4, runners=2,
          err_has="pi: note - 2 sub-agent runner(s) already running (load 1.00/4)."),
        C("the_busy_warning_counts_runners", load="9.00", cores=4, runners=3, err_has=busy("9.00", 4, 3)),
        C("no_load_reading_says_nothing", load=None, cores=4, runners=2, quiet=True),
        C("cores_from_nproc_when_sysctl_has_none", load="3.50", cores=None, nproc=2, err_has=busy("3.50", 2)),
    )
    BLOCK = block(LAUNCHER, 'CORES="$(sysctl -n hw.ncpu', "# --- note a session started inside the install")

    @classmethod
    def body(cls, case):
        i = cls.CASES.index(case)
        kw = case.kw
        loadavg = cls.tmp / f"loadavg{i}"
        if kw["load"] is not None:
            loadavg.write_text(f"{kw['load']} 1.00 1.00 1/100 1000\n")
        cores = "" if kw["cores"] is None else f"echo {kw['cores']}"
        snippet = cls.BLOCK.replace("/proc/loadavg", q(loadavg))
        return "\n".join([
            "set -euo pipefail", "unset PI_FORCE PI_ELM_CHILD PI_STRICT_LOAD", exports(case.env),
            f"sysctl() {{ case \"$2\" in hw.ncpu) {cores or 'return 1'} ;; *) return 1 ;; esac; }}",
            f"nproc() {{ echo {kw.get('nproc', 8)}; }}",
            f"pgrep() {{ local n=0; while [ $n -lt {kw.get('runners', 0)} ]; do echo $((100 + n)); n=$((n + 1)); done; }}",
            snippet, "printf '@@STARTED\\n'"])

    def check(self, case, r):
        super().check(case, r)
        self.assertEqual(case.kw.get("rc", 0) == 0, "@@STARTED" in r.out)


# --- a session started inside the install --------------------------------------------------

@generate
class InsideInstallTests(BatchTest):
    """The note for a session whose project folder is the install itself."""

    NOTE = "this session is starting inside the elm-pi install"
    CASES = (
        C("in_the_install_root", cwd="inst", err_has=NOTE),
        C("in_a_folder_of_the_install", cwd="inst/agent", err_has=NOTE),
        C("in_a_sibling_whose_name_starts_the_same", cwd="inst-work", quiet=True),
        C("through_a_symlink_to_the_install", cwd="instlink", err_has=NOTE),
        C("not_a_session", cwd="inst", needs_key=0, quiet=True),
        C("forced", cwd="inst", env={"PI_FORCE": "1"}, quiet=True),
        C("a_child", cwd="inst", env={"PI_ELM_CHILD": "1"}, quiet=True),
    )
    BLOCK = block(LAUNCHER, "# --- note a session started inside the install", "# --- stdin guard")

    @classmethod
    def prepare(cls):
        (cls.tmp / "inst/agent").mkdir(parents=True)
        (cls.tmp / "inst-work").mkdir()
        (cls.tmp / "instlink").symlink_to(cls.tmp / "inst")

    @classmethod
    def body(cls, case):
        return "\n".join(["set -euo pipefail", "unset PI_FORCE PI_ELM_CHILD", exports(case.env),
                          f"cd {q(cls.tmp / case.kw['cwd'])}", f"HERE={q(cls.tmp / 'inst')}",
                          f"NEEDS_ELM_KEY={case.kw.get('needs_key', 1)}", cls.BLOCK])


if __name__ == "__main__":
    unittest.main()
