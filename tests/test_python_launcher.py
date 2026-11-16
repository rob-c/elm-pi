"""The launcher, and the bash implementation it replaced.

`pi` is a hand-over to `python/pi`, which starts `python/elmpi` in a clean room;
the launcher's decisions are in that package, in modules that can be read and
changed one at a time. The implementation it replaced is `pi.bash`, kept beside
it - unchanged apart from naming itself - as the thing a change can be read
against. Two implementations of a thing this load-bearing are only worth having
if they cannot disagree, so this module is the agreement, in four parts:

* ReferenceTests subclass the functional suite in tests/test_install_fixes.py
  - the same test bodies, not a copy - and run it against `pi.bash`, while
    LauncherTests there runs it against the installed `pi`. Every case that
    holds one to its behaviour holds the other to the same behaviour.
* DifferentialTests run both launchers on the same install with the same
  arguments and compare what they decide - the exit code, the arguments pi
  receives, the environment it inherits, and everything they print.
* DriftTests read the lists and wordings back out of `pi.bash`: a change there
  that the Python launcher did not follow is a failing test, not a surprise.
* EntryPointTests, IsolationTests and the unit tests below hold each piece to
  what it promises: no policy in the shell, no import from outside the package
  and the stdlib, and a launch that a hostile PYTHONPATH or a project folder
  with a `json.py` in it cannot change.
"""

import json
import os
import re
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
# The installed command, and the two files it is made of: `pi` finds the
# install and hands over; `python/pi` chooses the interpreter and execs it
# isolated; `python/elmpi` is the launcher.
PYTHON_LAUNCHER = ROOT / "pi"
ENTRY = ROOT / "python" / "pi"
PACKAGE = ROOT / "python"
# The bash implementation `pi` used to be, kept as the reference.
BASH_LAUNCHER = ROOT / "pi.bash"

sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(PACKAGE))

import test_install_fixes as functional  # noqa: E402

from elmpi import argwalk, environ, extensions, flags, modes, paths, policy, tools  # noqa: E402
from elmpi.cli import NO_KEY_NEEDED, PACKAGE_COMMANDS_NAMES, SUBCOMMANDS  # noqa: E402
from elmpi import banner_text, usage  # noqa: E402


def read(path):
    return Path(path).read_text()


def heredoc(text, opener):
    """The text of a `cat <<'MARK'` heredoc, as the shell would print it.

    `opener` is the line that opens it, e.g. "cat <<'EOU'"; the heredoc runs
    from the next line to a line holding the marker alone.
    """
    marker = opener.split("<<'", 1)[1].rstrip("'")
    body = text.split(opener + "\n", 1)[1]
    return body.split("\n" + marker + "\n", 1)[0] + "\n"


class ReferenceTests(functional.LauncherTests):
    """The functional suite, unchanged, against the reference implementation.

    The same bodies run against the installed launcher in
    tests/test_install_fixes.py, so both implementations answer them.
    """

    LAUNCHER_UNDER_TEST = BASH_LAUNCHER


class ReferenceDeletedFolderTests(functional.DeletedFolderTests):
    """A shell in a deleted folder, against the reference implementation."""

    LAUNCHER_UNDER_TEST = BASH_LAUNCHER


# The environment a decision can show up in. Everything here has one correct
# value, and it is the one the bash launcher sets.
RECORDED = (
    "ANTHROPIC_API_KEY", "ELM_PI_PYTHON", "ELM_PI_PROXY_ALLOW", "ELM_SHIM_PATH",
    "MATPLOTLIBRC", "PATH", "PI_CLIPBOARD_OSC52", "PI_CODING_AGENT_DIR",
    "PI_ELM_ALLOWED_PROVIDERS", "PI_ELM_APPROVED_AGENTS", "PI_ELM_CHILD",
    "PI_ELM_COMPUTER_USE", "PI_ELM_MANUAL_ALLOW", "PI_ELM_PERMISSION_DEFAULT",
    "PI_ELM_PERMISSION_MODE", "PI_ELM_READ_AUTO", "PI_ELM_REMOTE", "PI_ELM_WEB",
    "PI_HASHLINE_DIR", "PI_OFFLINE", "PI_RADIUS_GATEWAY", "PI_SKIP_VERSION_CHECK",
    "PI_SUBAGENT_PI_BINARY", "PI_TELEMETRY", "PYTHONDONTWRITEBYTECODE",
)

# Vars whose value is the launcher itself: each points at the one it is, which
# is `pi` for the installed launcher and `pi.bash` for the reference.
SELF_REFERENTIAL = ("PI_SUBAGENT_PI_BINARY",)


class DifferentialTests(unittest.TestCase):
    """Both launchers, same install, same arguments: same decisions."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def pair(self):
        """Two fresh installs, one per launcher, in their own folders."""
        self.serial = getattr(self, "serial", 0) + 1
        base = self.base / str(self.serial)
        return (functional.Fixture(base / "bash", launcher=BASH_LAUNCHER),
                functional.Fixture(base / "python", launcher=PYTHON_LAUNCHER))

    def verdict(self, fixture, args, env):
        """What the launcher decided, with its own folder written as <install>."""
        result = fixture.run(*args, env=env, record=RECORDED)
        root = str(fixture.root)

        def clean(value):
            return str(value).replace(root, "<install>")

        self_path = clean(fixture.launcher)
        entry_path = clean(os.path.join(fixture.root, "python", "pi"))
        recorded = {}
        for name, value in result.env_seen.items():
            cleaned = clean(value)
            if name in SELF_REFERENTIAL and cleaned in (self_path, entry_path):
                cleaned = "<launcher>"
            recorded[name] = cleaned
        return {
            "code": result.returncode,
            "args": [clean(argument) for argument in result.args_seen],
            "env": recorded,
            # The ENV lines the recorder prints are compared as `env` above;
            # in the stream they would only repeat that comparison.
            "stdout": clean("\n".join(line for line in result.stdout.splitlines()
                                      if not line.startswith("ENV:"))),
            "stderr": clean(result.stderr),
        }

    def check(self, args, env=None):
        self.check_after(None, args, env)

    def check_after(self, prepare, args, env=None):
        """Compare both launchers on installs `prepare` has changed the same way."""
        bash, python = self.pair()
        if prepare is not None:
            for fixture in (bash, python):
                prepare(fixture)
        expected = self.verdict(bash, args, dict(env or {}))
        actual = self.verdict(python, args, dict(env or {}))
        for part in ("code", "args", "env", "stdout", "stderr"):
            self.assertEqual(expected[part], actual[part],
                             "%s differs for %r\nbash:   %r\npython: %r"
                             % (part, args, expected[part], actual[part]))

    # --- what a session is handed -------------------------------------------

    def test_the_reference_still_runs_without_the_python_launcher_package(self):
        # Fixture's default changed during the port and made both arms Python;
        # removing the port from the reference arm proves it is independent.
        bash, _ = self.pair()
        shutil.rmtree(bash.root / "python")
        result = self.verdict(bash, ["-p", "x"], {})
        self.assertEqual(0, result["code"], result["stderr"])
        self.assertIn("x", result["args"])

    def test_a_plain_run(self):
        self.check(["-p", "x"])

    def test_help_before_the_key_and_the_install_are_ready(self):
        self.check(["--help"])
        self.check(["-h"], {"ANTHROPIC_API_KEY": "sk-x"})

    def test_help_after_the_prompt_separator_is_text(self):
        self.check(["-p", "--", "--help"])

    def test_catalogue_commands_need_no_key(self):
        self.check(["--version"])
        self.check(["--list-models"])

    # --- the provider guard --------------------------------------------------

    def test_a_commercial_model_is_refused(self):
        self.check(["--model", "anthropic/claude-opus-5", "-p", "x"])
        self.check(["-m", "gpt-5"], {})
        self.check(["--provider=openai", "-p", "x"])

    def test_api_keys_and_extensions_are_refused(self):
        self.check(["--api-key", "k", "-p", "x"])
        self.check(["-e", "x.ts", "-p", "x"])
        self.check(["--extension=", "-p", "x"])

    def test_model_patterns_are_checked_one_by_one(self):
        self.check(["--models", "elm/Qwen/Qwen3.5-397B-A17B-FP8,anthropic/x", "-p", "x"])
        self.check(["--models", "Qwen/Qwen3.5-397B-A17B-FP8", "-p", "x"])

    def test_the_unlock_lifts_the_guard_and_the_scrub(self):
        self.check(["--model", "anthropic/claude-opus-5", "-p", "x"], {"PI_ELM_UNLOCK": "1"})

    # --- subcommands ---------------------------------------------------------

    def test_subcommands_are_refused_with_the_same_words(self):
        for command in ("auth", "mcp", "config", "list", "install", "remove", "uninstall"):
            with self.subTest(command=command):
                self.check([command, "x"])

    def test_update_and_setup(self):
        self.check(["update"])
        self.check(["update", "--extensions"])
        self.check(["update", "--models"])
        self.check(["setup"])
        self.check(["setup", "--bogus"])
        self.check(["setup", "--all"])

    def test_with_all_and_remote_keep_subcommands_available(self):
        # With every tool enabled the exclusion list is empty; update/setup
        # must still be intercepted instead of sent to the model as a prompt.
        for command in (["update", "--extensions"], ["setup", "--no-python"]):
            with self.subTest(command=command):
                self.check(["--with-all", "--remote"] + command, {"PI_ELM_CHILD": "1"})

    # --- this launcher's own flags ------------------------------------------

    def test_fast_and_no_extensions_load_the_policy(self):
        self.check(["--fast", "-p", "x"])
        self.check(["-ne", "-p", "x"])
        self.check(["--no-extensions", "-p", "x"])

    def test_model_shortcuts(self):
        self.check(["--llama", "-p", "x"])
        self.check(["--mistral", "-p", "x"])
        self.check(["--fast", "--llama", "-p", "x"])
        self.check(["--llama", "--model", "elm/Qwen/Qwen3.5-397B-A17B-FP8", "-p", "x"])

    def test_exclusions_are_merged_not_replaced(self):
        self.check(["-xt", "bash", "--exclude-tools", "edit", "-p", "x"])
        self.check(["--tools", "read", "-p", "x"])
        self.check(["-xt", "bash", "-p", "x"], {"PI_ELM_WEB": "1"})
        self.check(["--no-workflows", "-p", "x"])
        self.check(["--workflows", "-p", "x"], {"PI_ELM_WORKFLOWS": "0"})
        self.check(["--with-all", "-p", "x"])
        self.check(["-p", "--", "-xt", "bash"])
        self.check(["-xt"])

    def test_remote_and_computer_use(self):
        self.check(["--remote", "-p", "x"])
        self.check(["--remote", "--no-computer-use", "-p", "x"])

    def test_permission_modes(self):
        for flag in ("--manual", "--read-only-auto", "--auto", "--yolo"):
            with self.subTest(flag=flag):
                self.check([flag, "-p", "x"])
        self.check(["-p", "x"], {"PI_ELM_PERMISSION_MODE": "manual"})
        self.check(["--auto", "-p", "x"], {"PI_ELM_PERMISSION_MODE": "manual"})
        self.check(["--yolo", "-p", "x"], {"PI_ELM_PERMISSION_MODE": "manual"})

    def test_with_all_is_not_set_up_by_a_sub_agent_child(self):
        """A child must not install into the install its parent runs from."""
        self.check(["--with-all", "-p", "x"], {"PI_ELM_CHILD": "1"})

    def test_a_child_inherits_its_session_mode(self):
        self.check(["-p", "x"], {"PI_ELM_CHILD": "1", "PI_ELM_PERMISSION_MODE": "read-only-auto"})
        self.check(["-p", "x"], {"PI_ELM_CHILD": "1", "PI_ELM_PERMISSION_MODE": "yolo"})

    # --- where the launch may start -----------------------------------------

    def test_home_is_not_a_project(self):
        bash, python = self.pair()
        expected = self.in_folder(bash, bash.home)
        actual = self.in_folder(python, python.home)
        self.assertEqual(expected["code"], actual["code"])
        self.assertEqual(2, actual["code"], actual)
        self.assertEqual(expected["stderr"].replace(str(bash.home), "<home>"),
                         actual["stderr"].replace(str(python.home), "<home>"))

    def in_folder(self, fixture, folder, env=None):
        environ_ = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(fixture.home),
                    "TMPDIR": tempfile.gettempdir(), "ELM_PI_NO_PROXY": "1"}
        environ_.update(env or {})
        result = subprocess.run([str(fixture.launcher), "-p", "x"], cwd=str(folder),
                                env=environ_, capture_output=True, text=True)
        return {"code": result.returncode,
                "stdout": result.stdout.replace(str(fixture.root), "<install>"),
                "stderr": result.stderr.replace(str(fixture.root), "<install>")}

    def test_every_reason_for_refusing_a_folder_is_the_same(self):
        """The four reasons: home, its container, a listed container, a listed tree."""
        bash, python = self.pair()
        for fixture in (bash, python):
            (fixture.home / "Desktop").mkdir()
            (fixture.home / ".ssh" / "keys").mkdir(parents=True)
        for folder in (lambda f: f.home, lambda f: f.home / "Desktop",
                       lambda f: f.home / ".ssh" / "keys"):
            with self.subTest(folder=folder):
                expected = self.in_folder(bash, folder(bash))
                actual = self.in_folder(python, folder(python))
                self.assertEqual(2, actual["code"])
                for part in ("stdout", "stderr"):
                    self.assertEqual(expected[part].replace(str(bash.home), "<home>"),
                                     actual[part].replace(str(python.home), "<home>"))

    def test_a_session_started_in_the_install_is_noted(self):
        bash, python = self.pair()
        expected = self.in_folder(bash, bash.root)
        actual = self.in_folder(python, python.root)
        self.assertEqual(expected["code"], actual["code"])
        self.assertIn("starting inside the elm-pi install", actual["stderr"])
        self.assertEqual(expected["stderr"], actual["stderr"])

    def test_a_missing_pi_orig_says_what_to_run(self):
        self.check_after(lambda fixture: (fixture.root / "pi.orig").unlink(), ["-p", "x"])

    def test_llama_and_mistral_together_are_a_question(self):
        self.check(["--llama", "--mistral", "-p", "x"])

    def test_mistral_without_a_model_id_says_which_file_names_it(self):
        def forget(fixture):
            path = fixture.root / "agent" / "runtime.env"
            path.write_text("\n".join(line for line in path.read_text().splitlines()
                                      if "ELM_MISTRAL_MODEL_ID" not in line) + "\n")
        self.check_after(forget, ["--mistral", "-p", "x"])

    def test_pythondontwritebytecode_zero_is_passed_on_as_unset(self):
        """The one change pi has over HEAD: Python 3.9 treats "0" as don't-write."""
        self.check(["-p", "x"], {"PYTHONDONTWRITEBYTECODE": "0"})
        self.check(["-p", "x"], {"PYTHONDONTWRITEBYTECODE": "1"})
        self.check(["-p", "x"], {"PYTHONDONTWRITEBYTECODE": "anything"})

    def test_a_credential_folder_is_not_a_project(self):
        bash, python = self.pair()
        for fixture in (bash, python):
            (fixture.home / ".ssh").mkdir()
        expected = self.in_folder(bash, bash.home / ".ssh")
        actual = self.in_folder(python, python.home / ".ssh")
        self.assertEqual(2, actual["code"])
        self.assertEqual(expected["stderr"].replace(str(bash.home), "<home>"),
                         actual["stderr"].replace(str(python.home), "<home>"))


# --- drift: the lists and words the two launchers must agree about -----------------

class DriftTests(unittest.TestCase):
    """Every list the Python package mirrors is read back out of the bash launcher.

    Two implementations only stay equivalent if a change to one is a failing
    test for the other. The behaviour is compared by DifferentialTests; these
    are the constants behind it - the ones an edit to `pi` would move without
    changing any single case's output shape.
    """

    def setUp(self):
        self.launcher = read(BASH_LAUNCHER)
        self.policy = read(ROOT / "lib" / "policy.sh")

    def test_the_fast_run_loads_the_same_conveniences(self):
        line = next(line for line in self.launcher.splitlines()
                    if "for e in todo " in line)
        listed = line.split("for e in ", 1)[1].split(";", 1)[0].split()
        self.assertEqual(listed, list(extensions.FAST_CONVENIENCES))

    def test_the_same_commands_need_no_key(self):
        line = next(line for line in self.launcher.splitlines() if "NEEDS_ELM_KEY=0" in line)
        listed = line.split('case "${1:-}" in ', 1)[1].split(")", 1)[0].split("|")
        self.assertEqual(listed, list(NO_KEY_NEEDED))

    def test_the_permission_modes_and_their_strictness_are_the_same(self):
        line = next(line for line in self.launcher.splitlines() if line.startswith("elm_mode_rank()"))
        ranked = {mode: int(rank)
                  for mode, rank in re.findall(r"([a-z*-]+)\) echo (-?\d+)", line)}
        self.assertEqual(-1, ranked.pop("*"))
        self.assertEqual(ranked, modes.RANK)
        saved = next(line for line in self.launcher.splitlines() if 'case "$SAVED_MODE" in' in line)
        listed = saved.split('case "$SAVED_MODE" in ', 1)[1].split(")", 1)[0].split("|")
        self.assertEqual(list(modes.SAVABLE), listed)

    def test_the_launchers_own_flags_are_the_same(self):
        block = self.launcher.split("flag_prev=\"\"\nfor a in \"$@\"; do", 1)[1].split("esac", 1)[0]
        listed = {line.strip().split(")", 1)[0] for line in block.splitlines()
                  if line.strip().startswith("--") and ")" in line}
        listed.discard("--")
        self.assertEqual(listed, set(flags.CONSUMED))

    def test_pis_refused_subcommands_are_the_same(self):
        block = self.launcher.split("# --- pi's own subcommands", 1)[1].split("esac", 1)[0]
        listed = set()
        for line in block.splitlines():
            if re.fullmatch(r"[a-z|-]+\)", line.strip()):
                listed |= set(line.strip()[:-1].split("|"))
        self.assertEqual(set(SUBCOMMANDS) | set(PACKAGE_COMMANDS_NAMES), listed)

    def test_the_folder_refusals_use_the_same_words(self):
        from elmpi import untrusted
        self.assertIn('ELM_UNTRUSTED_WHAT="%s"' % untrusted.HOME_ITSELF, self.policy)
        self.assertIn('ELM_UNTRUSTED_WHAT="%s"' % untrusted.HOME_CONTAINER, self.policy)
        self.assertIn('ELM_UNTRUSTED_WHAT="$entry, which holds far more than one project"',
                      self.policy)
        self.assertEqual("inside %s, which holds credentials or system files", untrusted.TREE)
        self.assertEqual("%s, which holds far more than one project", untrusted.CONTAINER)

    def test_the_help_section_pi_setup_prints_is_the_same_text(self):
        text = self.launcher
        section = text.split("elm_usage() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("/^Optional parts/,/^$/p", "\n".join(
            line for line in text.splitlines() if "sed -n" in line))
        self.assertIn("  pi setup --all", "\n".join(usage.optional_parts_section()))
        self.assertTrue(section)


# --- the pieces, on their own ----------------------------------------------------


class ArgumentGrammarTests(unittest.TestCase):
    """One list decides which options take a value, and it is the bash one."""

    def test_the_value_options_are_the_bash_launchers(self):
        text = read(ROOT / "lib" / "policy.sh")
        block = text.split("elm_policy_takes_value() {", 1)[1].split("esac", 1)[0]
        listed = set()
        for line in block.splitlines():
            line = line.strip().rstrip("\\").split(")")[0].strip()
            if line.startswith("--") or line.startswith("-"):
                listed |= {part.strip() for part in line.split("|")
                           if part.strip() and not part.strip().startswith("return")}
        self.assertEqual(listed, set(argwalk.VALUE_OPTIONS))

    def test_classify_knows_values_prompt_text_and_stop(self):
        got = [(argument, kind) for _, argument, kind in argwalk.classify(
            ["--model", "--", "--fast", "--", "-p", "x"])]
        self.assertEqual([
            ("--model", argwalk.OPTION),
            ("--", argwalk.VALUE),       # pi takes "--" as the value here
            ("--fast", argwalk.OPTION),
            ("--", argwalk.OPTION),
            ("-p", argwalk.TEXT),
            ("x", argwalk.TEXT),
        ], got)

    def test_joined_value_takes_pis_last_one(self):
        self.assertIsNone(argwalk.joined_value(["-p", "x"], "--session-dir"))
        self.assertEqual("a", argwalk.joined_value(["--session-dir", "a"], "--session-dir"))
        self.assertEqual("b", argwalk.joined_value(
            ["--session-dir", "a", "--session-dir=b"], "--session-dir"))
        self.assertEqual("--", argwalk.joined_value(["--session-dir", "--"], "--session-dir"))
        self.assertIsNone(argwalk.joined_value(["--", "--session-dir", "a"], "--session-dir"))


class ProviderGuardTests(unittest.TestCase):
    ENV = {
        "ELM_ALLOWED_PROVIDERS": "elm elm-shim",
        "ELM_QWEN_MODEL_ID": "Qwen/Qwen3.5-397B-A17B-FP8",
        "ELM_LLAMA_MODEL_ID": "meta-llama/Llama-3.3-70B-Instruct",
        "ELM_MISTRAL_MODEL_ID": "mistralai/Mistral-Small-4-119B-2603",
    }

    def env(self, **overrides):
        return environ.Environment(dict(self.ENV, **overrides))

    def test_allowed(self):
        for argv in ([], ["-p", "x"], ["--model", "elm/Qwen/Qwen3.5-397B-A17B-FP8"],
                     ["--model", "Qwen/Qwen3.5-397B-A17B-FP8"], ["-mQwen/Qwen3.5-397B-A17B-FP8"],
                     ["--provider=ELM"], ["--models", "elm/a, elm-shim/b"],
                     ["--model"], ["-p", "--", "--model", "anthropic/x"],
                     ["update", "--models"], ["--extension="]):
            with self.subTest(argv=argv):
                self.assertIsNone(policy.check_args(argv, self.env()))

    def test_refused(self):
        cases = {
            ("--model", "anthropic/claude-opus-5"): policy.MODEL_REFUSED % "anthropic/claude-opus-5",
            ("--model", "gpt-5"): policy.MODEL_REFUSED % "gpt-5",
            ("--model", ""): None,          # an empty value is no model, as in bash
            ("--models", "elm/a,anthropic/b"): policy.MODEL_PATTERN_REFUSED % "anthropic/b",
            ("--provider", "openai"): policy.PROVIDER_ALLOWED % "openai",
            ("--api-key=k",): policy.API_KEY_REFUSED,
            ("-e", ""): policy.EXTENSION_REFUSED % "",
        }
        for argv, expected in cases.items():
            with self.subTest(argv=argv):
                self.assertEqual(expected, policy.check_args(list(argv), self.env()))

    def test_the_last_repeated_option_is_the_one_checked(self):
        self.assertIsNone(policy.check_args(
            ["--model", "anthropic/x", "--model", "elm/Qwen/Qwen3.5-397B-A17B-FP8"], self.env()))
        self.assertEqual(policy.MODEL_REFUSED % "anthropic/x",
                         policy.check_args(["--model", "elm/Qwen/Qwen3.5-397B-A17B-FP8",
                                            "--model", "anthropic/x"], self.env()))

    def test_an_unset_model_id_is_not_a_model(self):
        # A blank --model is no model at all: it must not match "" in the list.
        self.assertIsNone(policy.check_args(["--model", ""], self.env(ELM_QWEN_MODEL_ID="")))
        self.assertEqual(policy.MODEL_REFUSED % "Qwen/Qwen3.5-397B-A17B-FP8",
                         policy.check_args(["--model", "Qwen/Qwen3.5-397B-A17B-FP8"],
                                           self.env(ELM_QWEN_MODEL_ID="")))


class ExclusionTests(unittest.TestCase):
    ENV = {
        "ELM_EXCLUDED_TOOLS": "notebook_move",
        "ELM_WEB_TOOLS": "web_search,fetch_content",
        "ELM_WORKFLOW_TOOLS": "workflow,workflow_control",
    }

    def env(self, **overrides):
        return environ.Environment(dict(self.ENV, **overrides))

    def test_no_exclusions_preserves_the_arguments_for_later_launcher_steps(self):
        switches = flags.Switches(with_all=True, rest=["--session-dir", "transcripts", "-p", "x"])
        rest, flags_out = tools.plan(self.env(PI_ELM_WEB="1"), switches, switches.rest, False)
        self.assertEqual(switches.rest, rest)
        self.assertEqual([], flags_out)

    def test_web_tools_go_out_unless_asked_for(self):
        switches = flags.Switches(rest=["-p", "x"])
        self.assertEqual(["notebook_move,web_search,fetch_content"],
                         tools.plan(self.env(), switches, switches.rest, False)[1][1:])
        switches = flags.Switches(rest=["-p", "x"])
        self.assertEqual(["notebook_move"],
                         tools.plan(self.env(PI_ELM_WEB="1"), switches, switches.rest, False)[1][1:])

    def test_bg_wait_is_offered_only_where_nothing_else_wakes_the_session(self):
        interactive = flags.Switches(rest=[])
        self.assertEqual("notebook_move,bg_wait",
                         tools.plan(self.env(PI_ELM_WEB="1"), interactive, [], False)[1][1])
        printing = flags.Switches(rest=["-p", "x"])
        self.assertEqual("notebook_move",
                         tools.plan(self.env(PI_ELM_WEB="1"), printing, printing.rest, False)[1][1])
        # A sub-agent child gets no bg_wait either: the bash launcher's
        # condition skips the addition for PI_SUBAGENT_CHILD, whatever the
        # comment above it says.
        child = flags.Switches(rest=[])
        self.assertEqual("notebook_move",
                         tools.plan(self.env(PI_ELM_WEB="1"), child, [], True)[1][1])

    def test_the_callers_lists_are_folded_in(self):
        switches = flags.Switches(rest=["-xt", "bash", "--exclude-tools", "edit", "-p", "x"])
        rest, flags_out = tools.plan(self.env(PI_ELM_WEB="1"), switches, switches.rest, False)
        self.assertEqual(["--exclude-tools", "notebook_move,bash,edit"], flags_out)
        self.assertEqual(["-p", "x"], rest)

    def test_an_allowlist_is_left_alone(self):
        switches = flags.Switches(rest=["--tools", "read", "-xt", "bash", "-p", "x"])
        rest, flags_out = tools.plan(self.env(PI_ELM_WEB="1"), switches, switches.rest, False)
        self.assertEqual([], flags_out)
        self.assertEqual(["--tools", "read", "-xt", "bash", "-p", "x"], rest)


class ModeTests(unittest.TestCase):
    def resolve(self, flag="", env=None, saved="", child=False, problem=""):
        return modes.resolve(flag, environ.Environment(dict(env or {})), saved, child,
                             problem, ["-p"])

    def test_the_default_is_manual_and_the_saved_mode_wins(self):
        self.assertEqual("manual", self.resolve().mode)
        self.assertEqual("auto", self.resolve(saved="auto").mode)
        self.assertEqual("manual", self.resolve(saved="yolo").mode)

    def test_a_flag_is_for_one_run_only(self):
        resolution = self.resolve("yolo")
        self.assertEqual(("yolo", "manual"), (resolution.mode, resolution.default))

    def test_the_environment_can_only_tighten_a_run(self):
        self.assertEqual("manual", self.resolve("yolo", {"PI_ELM_PERMISSION_MODE": "manual"}).mode)
        self.assertEqual("manual", self.resolve("", {"PI_ELM_PERMISSION_MODE": "manual"},
                                                saved="auto").mode)
        resolution = self.resolve("", {"PI_ELM_PERMISSION_MODE": "auto"})
        self.assertEqual("manual", resolution.mode)
        self.assertTrue(any("cannot loosen" in note for note in resolution.notes), resolution.notes)

    def test_a_child_inherits_and_never_gets_yolo(self):
        self.assertEqual("auto", self.resolve(env={"PI_ELM_PERMISSION_MODE": "yolo"},
                                              child=True).mode)
        self.assertEqual("read-only-auto",
                         self.resolve(env={"PI_ELM_PERMISSION_MODE": "read-only-auto"},
                                      child=True).mode)

    def test_a_gate_that_cannot_apply_a_mode(self):
        self.assertEqual("auto", self.resolve(problem=modes.NO_GATE).mode)
        with self.assertRaises(Exception):
            self.resolve("manual", problem=modes.UNPATCHED_GATE)

    def test_apply_keeps_read_only_auto_as_manual_plus_the_flag(self):
        env = environ.Environment({})
        modes.apply(env, modes.Resolution("read-only-auto", "manual", []))
        self.assertEqual("manual", env.get("PI_ELM_PERMISSION_MODE"))
        self.assertEqual("1", env.get("PI_ELM_READ_AUTO"))
        modes.apply(env, modes.Resolution("auto", "manual", []))
        self.assertEqual("auto", env.get("PI_ELM_PERMISSION_MODE"))
        self.assertEqual("", env.get("PI_ELM_READ_AUTO"))


class PathTests(unittest.TestCase):
    def test_lexical_resolution(self):
        self.assertEqual("/work/a/b", paths.lexical("a/./b/../b", "/work"))
        self.assertEqual("/", paths.lexical("..", "/work"))
        self.assertEqual("/x", paths.lexical("/x/", "/work"))

    def test_canonical_follows_symlinks_and_needs_the_folder_to_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir()
            link = Path(tmp) / "link"
            link.symlink_to(real)
            # The kernel's spelling, as /bin/pwd -P gives it: on macOS the temp
            # directory is /private/var/folders, whatever /var says.
            resolved = os.path.realpath(str(real))
            self.assertEqual(resolved, paths.canonical(str(link)))
            self.assertEqual(os.path.join(resolved, "missing", "deeper"),
                             paths.canonical(str(link) + "/missing/deeper"))

    def test_is_inside_follows_symlinks_and_matches_the_folder_itself(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            (project / "sub").mkdir(parents=True)
            link = Path(tmp) / "link"
            link.symlink_to(project)
            self.assertTrue(paths.is_inside(project, project))
            self.assertTrue(paths.is_inside(project / "sub", project))
            self.assertTrue(paths.is_inside(link / "sub", project))
            self.assertFalse(paths.is_inside(Path(tmp), project))
            self.assertFalse(paths.is_inside(Path(str(project) + "-elsewhere"), project))

    def test_session_directories_resolve_as_pi_reads_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(os.path.join(tmp, "sessions"),
                             paths.normalize_session_dir("sessions", tmp))
            self.assertEqual(os.path.join(os.path.expanduser("~"), "s"),
                             paths.normalize_session_dir("~/s", tmp))
            self.assertEqual(os.path.join(tmp, "a b"),
                             paths.normalize_session_dir("file://" + tmp + "/a%20b", tmp))
            with self.assertRaises(ValueError):
                paths.normalize_session_dir("file://example.org/x", tmp)


class EnvironmentTests(unittest.TestCase):
    def test_clean_path_drops_what_a_repository_could_supply(self):
        self.assertEqual("/usr/bin:/bin",
                         environ.clean_path(".:/usr/bin:relative::/bin:/usr/bin:"))
        with tempfile.TemporaryDirectory() as tmp:
            env_dir = Path(tmp) / "env" / "bin"
            env_dir.mkdir(parents=True)
            (Path(tmp) / "env" / "pyvenv.cfg").write_text("")
            self.assertEqual("/usr/bin", environ.clean_path("%s:/usr/bin" % env_dir))
            self.assertEqual("%s:/usr/bin" % env_dir,
                             environ.clean_path("%s:/usr/bin" % env_dir, relative_only=True))

    def test_dotenv_is_data(self):
        class Notes:
            def __init__(self):
                self.lines = []

            def note(self, *lines):
                self.lines += lines

        env, notes = environ.Environment({}), Notes()
        with tempfile.TemporaryDirectory() as tmp:
            dotenv = Path(tmp) / ".env"
            dotenv.write_text("ELM_API_KEY='k'\nexport ELM_BASE_URL=https://x\n"
                              "PATH=/evil\n$(touch pwned)\n")
            environ.load_dotenv(dotenv, env, notes)
        self.assertEqual("k", env.get("ELM_API_KEY"))
        self.assertEqual("https://x", env.get("ELM_BASE_URL"))
        self.assertEqual("", env.get("PATH"))
        self.assertEqual(2, len(notes.lines))


class UntrustedFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.project = Path(self.tmp.name) / "src" / "project"
        for folder in (self.home, self.home / ".ssh", self.project):
            folder.mkdir(parents=True)
        self.env = environ.Environment({
            "ELM_UNTRUSTED_EXACT": "/\n~",
            "ELM_UNTRUSTED_TREE": "~/.ssh\n/etc",
        })

    def tearDown(self):
        self.tmp.cleanup()

    def reason(self, folder):
        from elmpi import untrusted
        return untrusted.untrusted_folder(str(folder), self.env, home=str(self.home))

    def test_home_is_refused(self):
        self.assertEqual("your home folder", self.reason(self.home))

    def test_a_folder_containing_home_is_refused(self):
        self.assertEqual("a folder that contains your home folder", self.reason(Path(self.tmp.name)))

    def test_a_credential_folder_and_what_is_under_it(self):
        self.assertTrue(self.reason(self.home / ".ssh").startswith("inside "))
        self.assertTrue(self.reason(self.home / ".ssh" / "keys").startswith("inside "))

    def test_an_ordinary_project_is_allowed(self):
        self.assertIsNone(self.reason(self.project))
        self.assertIsNone(self.reason(self.project / "sub"))


class TranscriptModeTests(unittest.TestCase):
    """A transcript is a copy of everything the agent read, wherever it sits."""

    def test_nested_transcripts_are_tightened_too(self):
        from elmpi import state
        with tempfile.TemporaryDirectory() as tmp:
            deep = Path(tmp) / "a" / "b"
            deep.mkdir(parents=True)
            transcript = deep / "s.jsonl"
            transcript.write_text("{}")
            other = deep / "notes.txt"
            other.write_text("x")
            for path in (transcript, other):
                os.chmod(path, 0o644)
            state.secure(tmp, tmp, environ.Environment({}))
            self.assertEqual(0o600, transcript.stat().st_mode & 0o777)
            # Only transcripts: a mistaken --session-dir . must not rewrite a
            # project's own files.
            self.assertEqual(0o644, other.stat().st_mode & 0o777)


class PreflightTests(unittest.TestCase):
    def test_a_forced_start_and_a_child_are_silent(self):
        from elmpi import preflight
        self.assertEqual([], preflight.note(environ.Environment({"PI_FORCE": "1"})))
        self.assertEqual([], preflight.note(environ.Environment({"PI_ELM_CHILD": "1"})))


class LauncherTextTests(unittest.TestCase):
    """The texts and lists two implementations must not disagree about."""

    def test_the_help_text_is_the_bash_launchers(self):
        self.assertEqual(heredoc(read(BASH_LAUNCHER), "  cat <<'EOU'"), usage.USAGE)

    def test_the_banner_is_the_bash_launchers(self):
        self.assertEqual(heredoc(read(BASH_LAUNCHER), "done >&2 <<'ELM_BANNER'"),
                         banner_text.BANNER)

    def test_the_policy_extensions_are_the_bash_launchers(self):
        text = read(BASH_LAUNCHER)
        listed = text.split('POLICY_EXTENSIONS="', 1)[1].split('"', 1)[0]
        self.assertEqual(listed.split(), list(extensions.POLICY_EXTENSIONS))

    def test_the_gate_is_named_by_the_same_path(self):
        text = read(BASH_LAUNCHER)
        self.assertIn('GATE_PKG="$HERE/%s"' % extensions.GATE_PACKAGE, text)
        self.assertIn('GATE="$GATE_PKG/src/index.ts"', text)


class ProxyTests(unittest.TestCase):
    """The egress proxy: which host is allowed, and how one is found or refused."""

    def test_the_gateway_comes_from_the_base_url(self):
        from elmpi import proxy
        cases = {
            "": "elm.edina.ac.uk",
            "https://elm.edina.ac.uk/api/v1": "elm.edina.ac.uk",
            "http://gateway.example.org:8443/v1": "gateway.example.org",
            "https://[fd00::1234]:8443/v1": "fd00::1234",
        }
        for value, host in cases.items():
            env = environ.Environment({"ELM_BASE_URL": value} if value else {})
            self.assertEqual(host, proxy.elm_host(env))

    def test_the_allow_list_keeps_the_installs_hosts(self):
        from elmpi import proxy
        env = environ.Environment({"ELM_PROXY_ALLOW": "pypi.org,files.pythonhosted.org"})
        self.assertEqual("elm.edina.ac.uk,pypi.org,files.pythonhosted.org",
                         proxy.allow_list(env, "elm.edina.ac.uk"))
        env = environ.Environment({"ELM_PROXY_ALLOW": "pypi.org", "ELM_PI_PROXY_ALLOW": "*"})
        self.assertEqual("elm.edina.ac.uk,pypi.org,*", proxy.allow_list(env, "elm.edina.ac.uk"))

    def test_only_a_loopback_proxy_with_a_port_is_one_of_ours(self):
        from elmpi import proxy
        self.assertEqual(8080, proxy.loopback_port("http://127.0.0.1:8080"))
        self.assertEqual(80, proxy.loopback_port("http://localhost:80/"))
        self.assertEqual(3128, proxy.loopback_port("http://[::1]:3128"))
        for url in ("", "http://proxy.example.org:8080", "socks5://127.0.0.1:1080",
                    "http://127.0.0.1", "127.0.0.1:8080", "http://localhost:0",
                    "http://localhost:65536"):
            self.assertIsNone(proxy.loopback_port(url), url)

    def test_an_invalid_published_port_is_not_used(self):
        from elmpi import proxy
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(proxy, "STARTUP_POLLS", 1), \
                patch.object(proxy, "STARTUP_INTERVAL", 0):
            port_file = Path(tmp) / "proxy.port"
            for value in ("0", "65536", "not-a-port"):
                port_file.write_text(value)
                self.assertIsNone(proxy._wait_for_port(str(port_file)), value)

    def test_the_health_check_asks_who_replies(self):
        from elmpi import proxy
        with _HealthServer(_health_reply(["elm.edina.ac.uk"])) as port:
            self.assertTrue(proxy.alive(port))
        with _HealthServer(b"HTTP/1.1 200 OK\r\n\r\n"
                           b'{"error":"elm-pi-egress is unavailable"}') as port:
            self.assertFalse(proxy.alive(port))
        with _HealthServer(b"HTTP/1.1 200 OK\r\n\r\n" + b"x" * 140000) as port:
            self.assertFalse(proxy.alive(port))
        with _HealthServer(b"HTTP/1.0 404 Not Found\r\n\r\nsomeone else") as port:
            self.assertFalse(proxy.alive(port))

    def test_a_loopback_service_that_never_answers_cannot_stall_startup(self):
        from elmpi import proxy
        with _HangingHealthServer() as port:
            started = time.monotonic()
            self.assertFalse(proxy.alive(port, timeout=0.05))
            self.assertLess(time.monotonic() - started, 0.5)

    def test_an_inherited_loopback_proxy_is_adopted_not_duplicated(self):
        from elmpi import proxy
        with _HealthServer(_health_reply(["elm.edina.ac.uk"])) as port:
            env = environ.Environment({"HTTPS_PROXY": "http://127.0.0.1:%d" % port})
            proxy.ensure(str(ROOT), env)
            self.assertEqual("http://127.0.0.1:%d" % port, env.get("HTTPS_PROXY"))
            self.assertEqual("http://127.0.0.1:%d" % port, env.get("http_proxy"))
            self.assertEqual("127.0.0.1,localhost,::1", env.get("NO_PROXY"))
            self.assertEqual("", env.get("ELM_PI_UPSTREAM_PROXY"))

    def test_offline_child_does_not_adopt_a_broader_parent_proxy(self):
        from elmpi import network, proxy
        reply = _health_reply(["elm.edina.ac.uk", "pypi.org"])
        with _HealthServer(reply) as port, \
                mock.patch.object(proxy, "_start_own", return_value=54321) as start:
            env = environ.Environment({
                "HTTPS_PROXY": "http://127.0.0.1:%d" % port,
                "ELM_PROXY_ALLOW": "pypi.org",
            })
            got = proxy.ensure(str(ROOT), env, network.resolve("offline", env))
        self.assertEqual(54321, got)
        self.assertEqual("elm.edina.ac.uk", start.call_args.args[3])

    def test_a_rescoped_child_keeps_the_sites_upstream_proxy(self):
        from elmpi import network, proxy
        reply = _health_reply(["elm.edina.ac.uk", "pypi.org"], upstream=True)
        campus = "http://campus-proxy.example:3128"
        with _HealthServer(reply) as port, \
                mock.patch.object(proxy, "_start_own", return_value=54321) as start:
            env = environ.Environment({
                "HTTPS_PROXY": "http://127.0.0.1:%d" % port,
                "ELM_PI_UPSTREAM_PROXY": campus,
                "ELM_PROXY_ALLOW": "pypi.org",
            })
            proxy.ensure(str(ROOT), env, network.resolve("offline", env))
        self.assertEqual(campus, start.call_args.args[4])

    def test_a_missing_proxy_script_fails_closed(self):
        from elmpi import proxy
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception) as caught:
                proxy.ensure(tmp, environ.Environment({}))
        self.assertEqual(1, caught.exception.code)
        self.assertIn("refuses to run unproxied", "\n".join(caught.exception.lines))

    def test_a_watchdog_does_not_hold_a_completed_sessions_output_open(self):
        # A still-running heartbeat must not keep a runner waiting for EOF
        # after its session has finished, even while a health check is stalled.
        script = """import os, sys, time
sys.path.insert(0, %r)
from elmpi import proxy
proxy._heartbeat = lambda *args: time.sleep(60)
proxy._watchdog(os.getpid(), 9, lambda port: None)
print('session finished', flush=True)
print('session diagnostic', file=sys.stderr, flush=True)
""" % str(PACKAGE)
        process = subprocess.Popen([sys.executable, "-E", "-S", "-c", script],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(0, process.returncode)
            self.assertEqual("session finished\n", stdout)
            self.assertEqual("session diagnostic\n", stderr)
        finally:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            process.communicate(timeout=5)


class _HealthServer:
    """A loopback server that answers one request as the egress proxy does."""

    def __init__(self, reply):
        self.reply = reply
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]

    def __enter__(self):
        threading.Thread(target=self._serve, daemon=True).start()
        return self.port

    def _serve(self):
        try:
            connection, _ = self.server.accept()
        except OSError:
            return
        with connection:
            connection.recv(65536)
            connection.sendall(self.reply)

    def __exit__(self, *exception):
        self.server.close()
        return False


class _HangingHealthServer(_HealthServer):
    def __init__(self):
        super().__init__(b"")

    def _serve(self):
        try:
            connection, _ = self.server.accept()
        except OSError:
            return
        with connection:
            connection.recv(65536)
            time.sleep(0.5)


def _health_reply(allow, upstream=False):
    body = json.dumps({"proxy": "elm-pi-egress", "pid": 1, "port": 1,
                       "allow": allow, "upstream": upstream}).encode()
    return (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body)


class RuntimeFileTests(unittest.TestCase):
    """agent/runtime.env is read as data; the values are what sourcing gives."""

    def test_multi_line_values_survive_and_nothing_executes(self):
        from elmpi import runtime
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agent").mkdir()
            (Path(tmp) / "agent" / "runtime.env").write_text(
                "export ELM_ALLOWED_PROVIDERS='elm elm-shim'\n"
                "export ELM_UNTRUSTED_EXACT='/\n~\n~/Desktop'\n"
                "export ELM_QWEN_MODEL_ID=Qwen/Qwen3.5\n"
                "touch " + tmp + "/pwned\n")
            env = environ.Environment({})
            runtime.load(tmp, env)
        self.assertEqual("/\n~\n~/Desktop", env.get("ELM_UNTRUSTED_EXACT"))
        self.assertEqual("Qwen/Qwen3.5", env.get("ELM_QWEN_MODEL_ID"))
        self.assertFalse(os.path.exists(os.path.join(tmp, "pwned")))

    def test_a_missing_file_says_which_step_puts_it_back(self):
        from elmpi import runtime
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception) as caught:
                runtime.load(tmp, environ.Environment({}))
        self.assertEqual(1, caught.exception.code)
        self.assertIn("runtime configuration is missing", caught.exception.lines[0])

    def test_the_help_fallback_reads_the_credentials_from_the_config(self):
        from elmpi import runtime
        names = runtime.credential_names(str(ROOT))
        self.assertIn("ANTHROPIC_API_KEY", names)
        self.assertIn("HF_TOKEN", names)


class SessionFolderTests(unittest.TestCase):
    def test_the_folder_comes_from_settings_then_environment_then_arguments(self):
        from elmpi import state
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agent").mkdir()
            settings = Path(tmp) / "agent" / "settings.json"
            settings.write_text('{"sessionDir": ".pi/sessions"}')
            env = environ.Environment({})
            self.assertEqual(os.path.join(tmp, ".pi/sessions"),
                             state.session_dir(tmp, env, ["-p", "x"], tmp))
            env = environ.Environment({"PI_CODING_AGENT_SESSION_DIR": "elsewhere"})
            self.assertEqual(os.path.join(tmp, "elsewhere"),
                             state.session_dir(tmp, env, [], tmp))
            self.assertEqual(os.path.join(tmp, "from-flag"),
                             state.session_dir(tmp, env, ["--session-dir", "from-flag"], tmp))
            self.assertEqual(os.path.join(tmp, "file-url"),
                             state.session_dir(tmp, env,
                                               ["--session-dir=file://" + tmp + "/file-url"], tmp))
            settings.write_text("{}")
            self.assertEqual(os.path.join(tmp, ".pi/sessions"),
                             state.session_dir(tmp, environ.Environment({}), [], tmp))


class InterpreterTests(unittest.TestCase):
    def test_a_broken_candidate_does_not_prevent_fallback_or_a_useful_refusal(self):
        from elmpi import interpreter
        from elmpi.errors import Refusal
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "python3"
            broken.write_text("#!/bin/sh\nexit 127\n")
            broken.chmod(0o755)
            with patch.object(interpreter, "candidates", return_value=[str(broken), sys.executable]):
                env = environ.Environment({})
                self.assertEqual(sys.executable, interpreter.select(tmp, env))
                self.assertEqual(sys.executable, env.get("ELM_PI_PYTHON"))
            with patch.object(interpreter, "candidates", return_value=[str(broken)]):
                with self.assertRaises(Refusal) as caught:
                    interpreter.select(tmp, environ.Environment({}))
                self.assertEqual(1, caught.exception.code)
                self.assertIn(str(broken) + " (does not run)", "\n".join(caught.exception.lines))

    def test_a_recorded_interpreter_is_trusted_and_exported(self):
        from elmpi import interpreter
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agent").mkdir()
            (Path(tmp) / "agent" / "python-path").write_text(sys.executable + "\n")
            env = environ.Environment({})
            self.assertEqual(sys.executable, interpreter.select(tmp, env, mode="fast"))
            self.assertEqual(sys.executable, env.get("ELM_PI_PYTHON"))

    def test_an_explicit_named_interpreter_must_be_runnable(self):
        from elmpi import interpreter
        env = environ.Environment({"ELM_PI_PYTHON": "python3"})
        with self.assertRaises(Exception) as caught:
            interpreter.select(str(ROOT), env)
        self.assertEqual(1, caught.exception.code)
        self.assertIn("must be an absolute path", caught.exception.lines[0])


class BannerTests(unittest.TestCase):
    def test_a_terminal_gets_the_banner_and_a_program_does_not(self):
        from elmpi import banner
        env = environ.Environment({})
        self.assertTrue(banner.wanted([], env, True, True))
        self.assertTrue(banner.wanted(["-h"], env, True, True))
        for argv in (["-p", "x"], ["--print"], ["--mode", "json"], ["--mode=json"],
                     ["--mode", "rpc"]):
            self.assertFalse(banner.wanted(argv, env, True, True), argv)
        self.assertFalse(banner.wanted([], env, False, True))
        self.assertFalse(banner.wanted([], env, True, False))
        self.assertFalse(banner.wanted([], environ.Environment({"PI_ELM_BANNER": "0"}), True, True))
        self.assertFalse(banner.wanted([], environ.Environment({"PI_ELM_CHILD": "1"}), True, True))

    def test_colour_needs_a_wide_terminal_that_wants_it(self):
        from elmpi import banner
        wide = environ.Environment({"TERM": "xterm-256color"})
        self.assertIn("\033[", banner.render(wide, 100)[1])
        for env, width in ((environ.Environment({}), 100),
                           (environ.Environment({"NO_COLOR": "1", "TERM": "xterm"}), 100),
                           (wide, 60)):
            self.assertFalse(any("\033[" in line for line in banner.render(env, width)), env.mapping)
        boxed = banner.render(wide, 100)
        self.assertIn("  Powered by ELM:", boxed[1])
        visible = boxed[1].replace(banner.COLOUR_ON, "").replace(banner.COLOUR_OFF, "")
        self.assertEqual(banner.WIDTH, len(visible), boxed[1])


class TerminalBannerTests(unittest.TestCase):
    """End to end at a terminal: the banner is drawn, and never where a program reads."""

    def output(self, *args, env=None):
        import pty
        with tempfile.TemporaryDirectory() as tmp:
            fixture = functional.Fixture(Path(tmp) / "install-base", launcher=PYTHON_LAUNCHER)
            environ_ = {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(fixture.home),
                "TMPDIR": tempfile.gettempdir(), "PI_FORCE": "1", "ELM_PI_NO_PROXY": "1",
                "TERM": "xterm-256color",
            }
            environ_.update(env or {})
            pid, descriptor = pty.fork()
            if pid == 0:
                try:
                    os.chdir(str(fixture.project))
                    os.execve(str(fixture.launcher), [str(fixture.launcher), *args], environ_)
                finally:
                    os._exit(1)
            captured = b""
            while True:
                try:
                    chunk = os.read(descriptor, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                captured += chunk
            os.close(descriptor)
            os.waitpid(pid, 0)
        return captured.decode("utf-8", "replace").replace("\r\n", "\n")

    def test_a_session_at_a_terminal_opens_with_the_banner(self):
        shown = self.output(env={"COLUMNS": "120"})
        self.assertIn("Powered by ELM:", shown)
        self.assertIn("   o_.--'--._o     EEEEEEE  LLLLLLL  MM     MM", shown)
        self.assertIn("Thank you to the ELM team at EDINA.", shown)
        self.assertTrue(any("\033[0;1;38;5;22;48;5;255m" in line for line in shown.splitlines()))

    def test_programs_children_and_the_switch_never_see_it(self):
        for args, env in ((["-p", "x"], {}),
                          (["--print", "x"], {}),
                          (["--mode", "rpc"], {}),
                          (["--mode=json"], {}),
                          ([], {"PI_ELM_CHILD": "1"}),
                          ([], {"PI_ELM_BANNER": "0"})):
            with self.subTest(args=args, env=env):
                self.assertNotIn("Powered by ELM", self.output(*args, env=env))

    def test_without_colour_or_room_it_is_plain_text(self):
        for env in ({"NO_COLOR": "1"}, {"TERM": "dumb"}, {"COLUMNS": "60"}):
            with self.subTest(env=env):
                shown = self.output(env=dict(env, COLUMNS=env.get("COLUMNS", "120")))
                self.assertIn("Powered by ELM:", shown)
                self.assertNotIn("\033[", shown)


class EntryPointTests(unittest.TestCase):
    """The shells' own choices: which interpreter, and what happens without one."""

    def test_a_bad_recorded_interpreter_falls_back_to_path(self):
        """A recorded interpreter that has gone must not stop the launch.

        The shell trusts agent/python-path without starting it (bash's `fast`
        mode does the same), so the fallback to `python3` on PATH is what has
        to work - and running the whole launcher under macOS's 3.9 says the
        package really is 3.8-compatible.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fixture = functional.Fixture(Path(tmp) / "install-base", launcher=PYTHON_LAUNCHER)
            (fixture.root / "agent" / "python-path").write_text("/nonexistent/python3\n")
            # The fallback is `command -v python3`, so that is what PATH must
            # have: a base image (Fedora's, say) has no python3 of its own.
            result = fixture.run("-p", "x", record=("ELM_PI_PYTHON",),
                                 env={"PATH": "%s:/usr/bin:/bin" % os.path.dirname(sys.executable)})
        self.assertEqual(0, result.returncode, result.stderr)
        chosen = result.env_seen["ELM_PI_PYTHON"]
        self.assertTrue(os.access(chosen, os.X_OK), chosen)
        self.assertNotEqual("/nonexistent/python3", chosen)

    def test_a_symlinked_entry_point_finds_its_install(self):
        """The installer links ~/.local/bin/pi, and that link may be a link."""
        with tempfile.TemporaryDirectory() as tmp:
            fixture = functional.Fixture(Path(tmp) / "install-base", launcher=PYTHON_LAUNCHER)
            link = Path(tmp) / "bin" / "pi"
            link.parent.mkdir()
            link.symlink_to(fixture.launcher)
            result = subprocess.run(
                [str(link), "--help"], cwd=str(fixture.project),
                env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(fixture.home),
                     "TMPDIR": tempfile.gettempdir(), "PI_FORCE": "1", "ELM_PI_NO_PROXY": "1"},
                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("Flags added by this launcher", result.stdout)

    def test_an_interpreter_that_says_it_is_too_old_is_refused(self):
        from elmpi import interpreter
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "python3.7"
            fake.write_text("#!/bin/sh\nexit 10\n")
            fake.chmod(0o755)
            self.assertEqual(interpreter.TOO_OLD, interpreter.check(str(fake)))
            env = environ.Environment({"ELM_PI_PYTHON": str(fake)})
            with self.assertRaises(Exception) as caught:
                interpreter.select(str(ROOT), env)
        self.assertEqual(1, caught.exception.code)
        self.assertIn("older than Python 3.8", caught.exception.lines[0])


# --- the shell, and what it must not do ------------------------------------------


POLICY_WORDS = ("--fast", "--remote", "--no-extensions", "--exclude-tools",
                "LOCKDOWN.md", "untrustedFolders", "permission-mode")


class IsolationTests(unittest.TestCase):
    """Two shell files, each doing one thing: hand over, then start Python."""

    def test_pi_only_finds_the_install_and_hands_over(self):
        text = read(PYTHON_LAUNCHER)
        self.assertTrue(os.access(PYTHON_LAUNCHER, os.X_OK))
        self.assertLessEqual(len(text.splitlines()), 45, "policy has leaked into `pi`")
        self.assertIn('exec "$HERE/python/pi" "$@"', text)
        for policy_word in POLICY_WORDS:
            self.assertNotIn(policy_word, text)
        self.assertEqual(set(), set(re.findall(r"\bELM_[A-Z0-9_]+\b", text)))

    def test_the_python_entry_resolves_a_path_and_starts_an_interpreter(self):
        text = read(ENTRY)
        self.assertTrue(os.access(ENTRY, os.X_OK))
        # Secure interpreter selection is necessarily longer than the old PATH
        # lookup; policy leakage is checked explicitly below.
        self.assertLessEqual(len(text.splitlines()), 110, "policy has leaked into the shell")
        self.assertIn('-E -s -S -B', text)
        self.assertIn('"$PACKAGE_DIR/elmpi/__main__.py"', text)
        for policy_word in POLICY_WORDS:
            self.assertNotIn(policy_word, text)
        # The one ELM_* name it may read is the interpreter it was told to use.
        self.assertEqual({"ELM_PI_PYTHON"}, set(re.findall(r"\bELM_[A-Z0-9_]+\b", text)))

    def test_both_shell_files_parse(self):
        result = subprocess.run(["bash", "-n", str(PYTHON_LAUNCHER), str(ENTRY)],
                                capture_output=True, text=True)
        for path in (PYTHON_LAUNCHER, ENTRY):
            one = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
            self.assertEqual(0, one.returncode, "%s: %s" % (path, one.stderr))

    def test_only_the_package_and_the_stdlib_are_imported(self):
        script = (
            "import importlib, os, sys, sysconfig\n"
            "sys.path.insert(0, %r)\n"
            "for name in sorted(os.listdir(%r)):\n"
            "    if name.endswith('.py') and name != '__main__.py':\n"
            "        importlib.import_module('elmpi.' + name[:-3])\n"
            "stdlib = os.path.realpath(sysconfig.get_paths()['stdlib'])\n"
            "outside = []\n"
            "for module in list(sys.modules.values()):\n"
            "    path = getattr(module, '__file__', None)\n"
            "    if not path:\n"
            "        continue\n"
            "    path = os.path.realpath(path)\n"
            "    if not path.startswith(stdlib) and not path.startswith(os.path.realpath(%r)):\n"
            "        outside.append(path)\n"
            "print('\\n'.join(outside))\n"
        ) % (str(PACKAGE), str(PACKAGE / "elmpi"), str(PACKAGE))
        result = subprocess.run([sys.executable, "-E", "-s", "-S", "-c", script],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("", result.stdout.strip())

    def test_a_hostile_pythonpath_and_project_change_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            # Startup hooks and a stdlib name in the project folder: the three
            # ways a Python launcher is normally redirected.
            (project / "sitecustomize.py").write_text("raise SystemExit('sitecustomize ran')\n")
            (project / "json.py").write_text("raise SystemExit('project json.py imported')\n")
            (project / "elmpi").mkdir()
            (project / "elmpi" / "__init__.py").write_text("raise SystemExit('project elmpi imported')\n")
            hostile = Path(tmp) / "hostile"
            hostile.mkdir()
            (hostile / "json.py").write_text("raise SystemExit('PYTHONPATH json.py imported')\n")
            fixture = functional.Fixture(Path(tmp) / "install-base", launcher=PYTHON_LAUNCHER)
            env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(fixture.home),
                   "TMPDIR": tempfile.gettempdir(), "PI_FORCE": "1", "ELM_PI_NO_PROXY": "1",
                   "PYTHONPATH": str(hostile), "PYTHONSTARTUP": str(hostile / "json.py"),
                   "PYTHONHOME": str(hostile)}
            result = subprocess.run([str(fixture.launcher), "--help"], cwd=str(project),
                                    env=env, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("Flags added by this launcher", result.stdout)
            self.assertNotIn("imported", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
