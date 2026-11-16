"""The installer in Python (python/elmboot), held to the cases the bash one is.

bootstrap.sh is now a hand-over to python/elmboot; bootstrap.bash is the
installer it replaced, kept as the reference. tests/test_bootstrap_internals.py
cuts that reference into blocks and runs each against a table of cases. This
file runs the same tables - the same set-up, the same stub curl, the same checks
- through the Python phases, so that what the reference is held to, its
replacement is held to as well:

* install_tool: pinned and published checksums, the cache, the archive forms
* the Node download: nodejs.org, SHASUMS256.txt, each platform's build
* when pi is rebuilt, and what is said about why

and then what only the replacement has: the hand-over itself, the run's
rollback, and the exit status of a command that was killed.

Nothing is downloaded: curl is a stub that serves files from a folder.
"""

import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "python"))

import test_bootstrap_internals as reference  # noqa: E402

from elmboot import console, pirelease, tools  # noqa: E402
from elmboot import run as runs  # noqa: E402

BASH = reference.BASH

# curl as an executable: what the reference's shell function does. Serves files
# from $HERE/srv by the URL's last path part, logs every URL, and fails like
# `curl -f` for one it does not have.
CURL = r'''#!/bin/bash
out=""; url=""
echo "$*" >> "$HERE/curl.args"
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift 2; continue ;; --retry|--retry-max-time|-m|-H|-d) shift 2; continue ;;
               -*) shift; continue ;; esac
  url="$1"; shift
done
echo "$url" >> "$HERE/curl.log"
f="$HERE/srv/${url##*/}"
[ -f "$f" ] || exit 22
if [ -n "$out" ]; then ln "$f" "$out" 2>/dev/null || cp "$f" "$out"; else cat "$f"; fi
'''
RETRY = ["--retry", "5", "--retry-connrefused", "--retry-max-time", "120", "--retry-all-errors"]

# The phase under test, with the installer's say/warn/die written the way the
# reference's stubs write them, so one check reads both.
DRIVER = r'''
import json, os, sys
job = json.loads(sys.argv[1])
sys.path.insert(0, job["python"])
from types import SimpleNamespace
from elmboot import console, nodejs, tools
from elmboot.run import Run

console.say = lambda heading: print("== " + heading)
console.warn = lambda message: print("WARN " + message)
def die(message):
    print("DIE " + message)
    sys.stdout.flush()
    os._exit(1)
console.die = die

here = os.getcwd()
options = SimpleNamespace(force=bool(job.get("force")), update=False)
run = Run(here, os.environ, options)
run.retry = job["retry"]
if job.get("uname"):
    system, machine = job["uname"]
    os.uname = lambda: SimpleNamespace(sysname=system, machine=machine)
if job["phase"] == "tool":
    scratch = os.path.join(here, "tt")
    os.makedirs(scratch)
    tools.install_tool(run, job["toolset"].split(","), os.path.join(here, "cache"), scratch, *job["args"])
else:
    nodejs.fetch(run, "v9.8.7")
print("@@DONE")
'''


def run_case(d, job, pre="", shared=None, stubs=()):
    """One case in its own interpreter, in folder `d`; returns what the reference's runner does."""
    tools_dir = d / ".stubs"
    tools_dir.mkdir()
    curl = tools_dir / "curl"
    curl.write_text(CURL)
    curl.chmod(0o755)
    for name, status in stubs:
        stub = tools_dir / name
        stub.write_text("#!/bin/sh\nexit %d\n" % status)
        stub.chmod(0o755)
    env = {"PATH": "%s:/usr/bin:/bin:/usr/sbin:/sbin" % tools_dir, "HOME": str(d / "home"), "LANG": "C",
           "TMPDIR": str(d), "HERE": str(d), "ELM_PI_PYTHON": sys.executable}
    if pre:
        subprocess.run([BASH, "-c", pre], cwd=str(d), check=True,
                       env=dict(env, SHARED=str(shared) if shared else ""))
    import json
    job = dict(job, python=str(ROOT / "python"), retry=RETRY)
    done = subprocess.run([sys.executable, "-E", "-S", "-c", DRIVER, json.dumps(job)], cwd=str(d), env=env,
                          capture_output=True, text=True, timeout=120)
    return reference.ShRun(done.returncode, done.stdout, done.stderr)


class Table(unittest.TestCase):
    """A table of the reference's cases, run through Python once for the class."""

    CASES = ()
    BASH_ONLY = {}

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            cls.dirs, cls.results = {}, {}
            cls.shared(cls.tmp / "shared")
            for i, case in enumerate(cls.CASES):
                if case.name in cls.BASH_ONLY:
                    continue
                d = cls.tmp / f"c{i}"
                d.mkdir()
                cls.dirs[case.name] = d
                cls.prepare(case, d)
                cls.results[case.name] = cls.run_one(case, d)
        except BaseException:
            reference.cleanup_tree(cls.tmp)
            raise

    @classmethod
    def tearDownClass(cls):
        reference.cleanup_tree(cls.tmp)

    @classmethod
    def shared(cls, path):
        pass


def generate(cls):
    for case in cls.CASES:
        def test(self, case=case):
            why = type(self).BASH_ONLY.get(case.name) or case.kw.get("skip")
            if why:
                raise unittest.SkipTest(why)
            case.kw["check"](self, type(self).results[case.name], type(self).dirs[case.name])
        test.__name__ = "test_" + reference.slug(case.name)
        if case.bug:
            test = unittest.expectedFailure(test)
        setattr(cls, test.__name__, test)
    return cls


@generate
class ToolInstallTests(Table):
    """elmboot.tools.install_tool against the reference's forty cases."""

    CASES = reference.TOOL_CASES
    BASH_ONLY = {
        "without_a_sha256_tool_the_install_stops_saying_why":
            "the Python installer hashes with hashlib: there is no tool to be without",
    }
    # A shell function standing in for a program the machine lacks or that
    # fails: here, a program of that name first on PATH.
    PROGRAMS = {"tar() { return 2; }": (("tar", 2),),
                "unzip() { return 127; }; tar() { return 2; }": (("unzip", 127), ("tar", 2))}

    shared = classmethod(reference.InstallToolTests.shared.__func__)
    prepare = classmethod(reference.InstallToolTests.prepare.__func__)

    @classmethod
    def run_one(cls, case, d):
        kw = case.kw
        pre = kw["pre"]
        stubs = cls.PROGRAMS.get(pre, ())
        return run_case(d, {"phase": "tool", "toolset": kw["toolset"], "args": list(kw["args"]),
                            "force": kw.get("force", 0)},
                        pre="" if stubs else pre, shared=cls.shared_dir, stubs=stubs)


@generate
class NodeFetchTests(Table):
    """elmboot.nodejs.fetch against the reference's cases for step 1."""

    CASES = reference.NODE_CASES
    prepare = classmethod(reference.NodeDownloadTests.prepare.__func__)

    @classmethod
    def run_one(cls, case, d):
        return run_case(d, {"phase": "node", "uname": list(case.kw["uname"])}, pre=case.kw["pre"])


class NeedPiTests(unittest.TestCase):
    """When step 2 rebuilds pi, by the reference's table."""

    def test_every_case_of_the_reference(self):
        for case in reference.NEED_PI_CASES:
            env = case.kw["env"]
            if "FAIL" in (env["DIGEST"], env["TESTED"]):
                continue                    # the two commands that fail: below
            with self.subTest(case=case.name):
                options = SimpleNamespace(force=env["FORCE"] == "1", update=env["UPDATE"] == "1",
                                          force_packages=env["FORCE_PACKAGES"] == "1")
                need, why = pirelease.need_pi(options, env["PI_INSTALLED"], env["PI_VERSION"],
                                              env["TESTED"], env["STAMP"], env["DIGEST"])
                out = ("    " + why + "\n") if why else ""
                result = reference.ShRun(0, out + "@@NEED_PI=%d\n" % need, "")
                case.kw["check"](self, result, None)

    def test_a_manifest_or_a_versions_file_that_cannot_be_read_stops_the_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = runs.Run(tmp, dict(os.environ, ELM_PI_PYTHON=sys.executable),
                           SimpleNamespace(force=False, update=False, force_packages=False, patch=True))
            with mock.patch.object(run, "capture", return_value=(1, "")), \
                    mock.patch.object(console, "say"):
                with self.assertRaises(console.Failure) as caught:
                    pirelease.install_pi(run)
            self.assertEqual("cannot hash package.json", str(caught.exception))
            answers = iter([(0, "d1"), (1, "")])
            with mock.patch.object(run, "capture", side_effect=lambda *a, **k: next(answers)), \
                    mock.patch.object(console, "say"):
                with self.assertRaises(console.Failure) as caught:
                    pirelease.install_pi(run)
            self.assertEqual("cannot read config/versions.json", str(caught.exception))


class ToolCatalogueTests(unittest.TestCase):
    """The tools the Python installer would fetch are the ones the reference would."""

    @staticmethod
    def reference_rows(system, machine):
        """What the reference's own platform logic and install_tool lines ask for:
        (binary, version, asset, url, checksum url), with install_tool stubbed."""
        text = reference.BOOTSTRAP
        start = text.index('  case "$(uname -s)" in', text.index('  TOOLSET="'))
        end = text.index("\n", text.index('  RUFF_VERSION="${RUFF_VERSION:-'))
        platform = text[start:end].replace("$(uname -s)", system).replace("$(uname -m)", machine)
        calls = text[text.index("  GH=https://github.com"):text.index('  echo "    agent/bin is')]
        script = ('die() { echo "DIE $*" >&2; exit 9; }\n'
                  "install_tool() { printf '%s|%s|%s|%s|%s\\n' \"$1\" \"$2\" \"$3\" \"$4\" \"$5\"; }\n"
                  + platform + "\n" + calls)
        out = subprocess.run([BASH, "-c", script], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
        if out.returncode != 0:
            raise AssertionError("the reference's tool block did not run: " + out.stderr)
        return [tuple(line.split("|")) for line in out.stdout.splitlines()]

    def test_names_versions_and_urls_match_the_reference_on_every_platform(self):
        for system, machine in (("Darwin", "arm64"), ("Darwin", "x86_64"), ("Linux", "x86_64"),
                                ("Linux", "aarch64"), ("Linux", "amd64")):
            with self.subTest(system=system, machine=machine):
                with mock.patch.object(tools.os, "uname",
                                       return_value=SimpleNamespace(sysname=system, machine=machine)):
                    ours = tools.catalogue({}, tools.names_for_machine())
                self.assertEqual(self.reference_rows(system, machine), ours)
                self.assertEqual(11, len(ours))

    def test_the_default_set_is_the_references(self):
        self.assertIn('TOOLSET="${ELM_PI_TOOLS:-%s}"' % tools.DEFAULT_SET, reference.BOOTSTRAP)
        self.assertEqual(tools.DEFAULT_SET.split(","), [row[0] for row in tools.catalogue(
            {}, {"triple": "t", "gnu_triple": "g", "go_os": "o", "go_arch": "a", "rust_arch": "r",
                 "jq_os": "j", "resvg_os": "v", "resvg_ext": "zip"})])

    def test_a_version_is_matched_as_a_whole_word(self):
        self.assertTrue(tools.is_version("ruff 0.17.1", "0.17.1"))
        self.assertTrue(tools.is_version("x 0.17.1.\nbuilt later", "0.17.1"))
        self.assertTrue(tools.is_version("fd 10.5.2 (rev abc)", "10.5.2"))
        self.assertFalse(tools.is_version("ruff 0.17.10", "0.17.1"))
        self.assertFalse(tools.is_version("ruff 10.17.1", "0.17.1"))
        self.assertFalse(tools.is_version("ruff 0.17.1.2", "0.17.1"))
        self.assertFalse(tools.is_version("", "0.17.1"))

    def test_an_environment_pin_wins_and_fd_is_older_on_an_intel_mac(self):
        self.assertEqual("10.3.0", tools.versions({}, "x86_64-apple-darwin")["FD_VERSION"])
        self.assertEqual("10.5.2", tools.versions({}, "aarch64-apple-darwin")["FD_VERSION"])
        self.assertEqual("9.9.9", tools.versions({"FD_VERSION": "9.9.9"}, "x86_64-apple-darwin")["FD_VERSION"])
        self.assertEqual("1.1.1", tools.versions({"RG_VERSION": "1.1.1"}, "x")["RG_VERSION"])
        # set and empty is unset, as ${RG_VERSION:-...} has it
        self.assertEqual(dict(tools.VERSIONS)["RG_VERSION"], tools.versions({"RG_VERSION": ""}, "x")["RG_VERSION"])


EXAMPLE = (ROOT / ".env.example").read_text()
KEY_BLOCK = reference.block(reference.BOOTSTRAP, 'say "ELM API key"\n', "# --- 7. verify the lockdown")
KEY_DRIVER = r"""
import os, sys
sys.path.insert(0, sys.argv[1])
from types import SimpleNamespace
from elmboot import cli, console
from elmboot.run import Run
console.say = lambda heading: print("== " + heading)
console.warn = lambda message: print("WARN " + message)
def die(message):
    print("DIE " + message)
    sys.stdout.flush()
    os._exit(1)
console.die = die
run = Run(os.getcwd(), os.environ, SimpleNamespace(interactive=sys.argv[2] == "1"))
cli.key(run)
cli.resolve_model(run)
print("@@DONE")
"""


class KeyTests(unittest.TestCase):
    """Step 5, by both installers: a .env without a key is not a key.

    A folder copied from a clone carries .env.example's empty `ELM_API_KEY=`
    line. Both installers said "keeping existing .env", never asked, and ended
    at the lockdown check with pi's advice to /login (2026-11-16).
    """

    def folder(self, env_file):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name).resolve()
        (d / ".env.example").write_text(EXAMPLE)
        configure = d / "configure.sh"
        configure.write_text("#!/bin/sh\necho ran > configured\n")
        configure.chmod(0o755)
        if env_file is not None:
            (d / ".env").write_text(env_file)
            (d / ".env").chmod(0o644)
        return d

    def outcome(self, d, done):
        env = d / ".env"
        return {"rc": done.returncode, "out": done.stdout.replace(str(d), "<here>"),
                "env": env.read_text() if env.exists() else None,
                "mode": oct(env.stat().st_mode & 0o777) if env.exists() else None,
                "configured": (d / "configured").exists(),
                "left": sorted(p.name for p in d.iterdir() if p.name.startswith(".env.") and p.name != ".env.example")}

    def bash(self, env_file, key="", interactive="1"):
        d = self.folder(env_file)
        script = "\n".join(["set -euo pipefail", 'HERE="$PWD"', reference.STUBS, "INTERACTIVE=" + interactive,
                            KEY_BLOCK, 'echo "@@DONE"'])
        env = {"PATH": "/usr/bin:/bin", "HOME": str(d)}
        if key:
            env["ELM_API_KEY"] = key
        return self.outcome(d, subprocess.run([BASH, "-c", script], cwd=str(d), env=env, capture_output=True,
                                              text=True, stdin=subprocess.DEVNULL))

    def python(self, env_file, key="", interactive="1"):
        d = self.folder(env_file)
        env = {"PATH": "/usr/bin:/bin", "HOME": str(d)}
        if key:
            env["ELM_API_KEY"] = key
        return self.outcome(d, subprocess.run([sys.executable, "-E", "-S", "-c", KEY_DRIVER, str(ROOT / "python"),
                                               interactive], cwd=str(d), env=env, capture_output=True, text=True,
                                              stdin=subprocess.DEVNULL))

    def both(self, env_file, key="", interactive="1"):
        ours, theirs = self.python(env_file, key, interactive), self.bash(env_file, key, interactive)
        self.assertEqual(theirs, ours)
        return ours

    def test_a_copied_example_is_given_the_key_in_place_of_its_empty_line(self):
        got = self.both(EXAMPLE, key="elm-abc123")
        self.assertEqual(EXAMPLE.replace("ELM_API_KEY=\n", "ELM_API_KEY=elm-abc123\n", 1), got["env"])
        self.assertIn("# Optional overrides", got["env"])                    # the rest of the file is kept
        self.assertEqual(1, got["env"].count("ELM_API_KEY=elm-abc123"))
        self.assertIn("    .env had no key: added ELM_API_KEY from the environment\n", got["out"])
        self.assertNotIn("keeping existing .env", got["out"])
        self.assertEqual((0, "0o600", True, []), (got["rc"], got["mode"], got["configured"], got["left"]))

    def test_a_copied_example_with_no_key_to_be_had_stops_saying_exactly_that(self):
        got = self.both(EXAMPLE)
        self.assertEqual(1, got["rc"])
        self.assertIn("WARN .env has no ELM_API_KEY - add it there before running ./pi\n", got["out"])
        self.assertIn("DIE this install has no ELM key yet, so the ELM-only policy cannot be verified. "
                      "Everything else is installed: put ELM_API_KEY=elm-... in <here>/.env and run "
                      "<here>/bootstrap.sh again (nothing is downloaded twice)\n", got["out"])
        self.assertEqual((EXAMPLE, False), (got["env"], got["configured"]))   # untouched, and nothing asked of ELM
        self.assertNotIn("@@DONE", got["out"])                               # the lockdown check is never reached

    def test_a_env_that_has_a_key_is_kept_as_it_is(self):
        for text in ("ELM_API_KEY=elm-mine\n", "# mine\nexport ELM_API_KEY=elm-mine\nELM_BASE_URL=https://x/v1\n"):
            with self.subTest(text=text):
                got = self.both(text, key="elm-from-the-shell")
                self.assertEqual((0, text, True), (got["rc"], got["env"], got["configured"]))
                self.assertIn("    keeping existing .env\n", got["out"])
                self.assertEqual("0o644", got["mode"])                       # yours: not touched at all

    def test_a_env_with_other_settings_and_no_key_line_gets_one_at_the_end(self):
        for text in ("ELM_BASE_URL=https://x/v1\n", "ELM_BASE_URL=https://x/v1", ""):
            with self.subTest(text=text):
                got = self.both(text, key="elm-abc123")
                before = text if text.endswith("\n") or not text else text + "\n"
                self.assertEqual(before + "ELM_API_KEY=elm-abc123\n", got["env"])
                self.assertEqual((0, "0o600", True), (got["rc"], got["mode"], got["configured"]))

    def test_an_exported_empty_key_line_is_replaced_too(self):
        got = self.both("# note\nexport ELM_API_KEY=\nELM_SHIM_PORT=8812\n", key="elm-abc123")
        self.assertEqual("# note\nELM_API_KEY=elm-abc123\nELM_SHIM_PORT=8812\n", got["env"])

    def test_a_key_with_characters_awk_and_sed_would_read_is_written_as_typed(self):
        key = r"elm-a\tb&c/d\\e"
        got = self.both(EXAMPLE, key=key)
        self.assertIn("ELM_API_KEY=" + key + "\n", got["env"])

    def test_no_env_at_all_is_as_it_was(self):
        made = self.both(None, key="elm-abc123")
        self.assertEqual((0, "ELM_API_KEY=elm-abc123\n", "0o600", True),
                         (made["rc"], made["env"], made["mode"], made["configured"]))
        self.assertIn("    wrote .env from the environment\n", made["out"])
        none = self.both(None, interactive="0")
        self.assertEqual((1, EXAMPLE, "0o600", False), (none["rc"], none["env"], none["mode"], none["configured"]))
        self.assertIn("WARN no key available - edit .env before running ./pi\n", none["out"])
        self.assertIn("DIE this install has no ELM key yet", none["out"])

    def test_at_a_terminal_it_asks_for_the_key_the_env_lacks(self):
        from elmboot import cli
        d = self.folder(EXAMPLE)
        run = runs.Run(str(d), {}, SimpleNamespace(interactive=True))
        typed = mock.Mock(readline=mock.Mock(return_value="elm-typed\n"), isatty=mock.Mock(return_value=True))
        said = []
        with mock.patch.object(cli.sys, "stdin", typed), \
                mock.patch.object(cli.sys, "stdout", mock.Mock(write=said.append)), \
                mock.patch.object(console, "say"), mock.patch.object(console, "note") as noted:
            cli.key(run)
        self.assertEqual(["    .env has no key - paste your ELM API key (elm-...): "], said)
        noted.assert_called_once_with("added the key to .env (mode 600)")
        self.assertIn("ELM_API_KEY=elm-typed\n", (d / ".env").read_text())
        self.assertTrue(cli.has_key(run))

    def test_at_a_terminal_an_empty_answer_stops_and_non_interactive_never_asks(self):
        from elmboot import cli
        d = self.folder(EXAMPLE)
        empty = mock.Mock(readline=mock.Mock(return_value="\n"), isatty=mock.Mock(return_value=True))
        with mock.patch.object(cli.sys, "stdin", empty), mock.patch.object(cli.sys, "stdout", mock.Mock()), \
                mock.patch.object(console, "say"):
            with self.assertRaises(console.Failure) as caught:
                cli.key(runs.Run(str(d), {}, SimpleNamespace(interactive=True)))
            self.assertEqual("no key given", str(caught.exception))
            with mock.patch.object(console, "warn") as warned:
                cli.key(runs.Run(str(d), {}, SimpleNamespace(interactive=False)))      # --non-interactive
            warned.assert_called_once_with(".env has no ELM_API_KEY - add it there before running ./pi")
        self.assertEqual(1, empty.readline.call_count)
        self.assertEqual(EXAMPLE, (d / ".env").read_text())


class HandOverTests(unittest.TestCase):
    """bootstrap.sh: find an interpreter, start python/elmboot isolated, nothing else."""

    WRAPPER = (ROOT / "bootstrap.sh").read_text()

    def test_it_is_a_hand_over_and_not_an_installer(self):
        code = [line for line in self.WRAPPER.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        self.assertLess(len(code), 30, "bootstrap.sh is growing back into an installer")
        for phase in ("curl ", "npm", "node_modules", "agent/", "templates/", "mktemp", "elm_py "):
            self.assertNotIn(phase, "\n".join(code), phase)
        self.assertIn('exec "$ELM_PI_PYTHON" -E -s -S -B -u -X utf8 "$HERE/python/elmboot/__main__.py" "$@"',
                      self.WRAPPER)

    def test_help_is_the_references_help_byte_for_byte(self):
        ours = subprocess.run([str(ROOT / "bootstrap.sh"), "--help"], capture_output=True, text=True)
        theirs = subprocess.run([str(ROOT / "bootstrap.bash"), "--help"], capture_output=True, text=True)
        self.assertEqual((0, ""), (ours.returncode, ours.stderr))
        self.assertEqual(theirs.stdout, ours.stdout)
        self.assertIn("--non-interactive", ours.stdout)

    def test_help_wins_over_a_mistyped_flag_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.copy_installer(Path(tmp))
            before = sorted(p.name for p in Path(tmp).iterdir())
            done = subprocess.run([str(Path(tmp) / "bootstrap.sh"), "--nope", "-h"], capture_output=True, text=True)
            self.assertEqual(0, done.returncode, done.stderr)
            self.assertIn("elm-pi installer.", done.stdout)
            self.assertEqual(before, sorted(p.name for p in Path(tmp).iterdir()))     # no agent/, no .node

    def test_a_mistyped_flag_is_refused_as_the_reference_refuses_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.copy_installer(Path(tmp))
            said = []
            for name in ("bootstrap.sh", "bootstrap.bash"):
                done = subprocess.run(["./" + name, "--no-such-flag"], cwd=tmp, capture_output=True, text=True)
                said.append((done.returncode, done.stdout, done.stderr.replace(name, "bootstrap.sh")))
            self.assertEqual(said[1], said[0])
            self.assertEqual((2, "", "unknown option: --no-such-flag\ntry: ./bootstrap.sh --help\n"), said[0])
            self.assertFalse((Path(tmp) / "agent").exists())

    def test_a_named_interpreter_that_does_not_run_is_an_error_not_a_download(self):
        done = subprocess.run([str(ROOT / "bootstrap.sh"), "--help"], capture_output=True, text=True,
                              env=dict(os.environ, ELM_PI_PYTHON="/nonexistent/python3"))
        self.assertEqual(1, done.returncode)
        self.assertIn("ELM_PI_PYTHON=/nonexistent/python3 is not a runnable Python", done.stderr)
        self.assertNotIn("downloading", done.stdout + done.stderr)

    def test_the_installer_imports_nothing_from_the_folder_it_is_started_in(self):
        # A json.py beside the caller must not be the json the installer uses.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "json.py").write_text("raise SystemExit('a project file was imported')\n")
            done = subprocess.run([str(ROOT / "bootstrap.sh"), "--help"], cwd=tmp, capture_output=True, text=True,
                                  env=dict(os.environ, PYTHONPATH=tmp))
            self.assertEqual(0, done.returncode, done.stderr)
            self.assertIn("elm-pi installer.", done.stdout)

    def test_the_package_is_standard_library_only(self):
        import ast
        allowed = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
        for path in sorted((ROOT / "python/elmboot").glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) and node.level == 0 else [])
                for name in names:
                    top = name.split(".")[0]
                    if top in ("elmboot", "elmpi") or allowed is None:
                        continue
                    self.assertIn(top, allowed, "%s imports %s" % (path.name, name))

    @staticmethod
    def copy_installer(root):
        import shutil
        for name in ("bootstrap.sh", "bootstrap.bash"):
            shutil.copy2(ROOT / name, root / name)
        shutil.copytree(ROOT / "lib", root / "lib")
        shutil.copytree(ROOT / "python", root / "python", ignore=shutil.ignore_patterns("__pycache__"))


class RunTests(unittest.TestCase):
    """What a run undoes, and how it reports a command."""

    def tree(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def run_in(self, root):
        return runs.Run(str(root), dict(os.environ), SimpleNamespace())

    def test_a_failed_run_gets_its_previous_pi_and_packages_back(self):
        root = self.tree()
        for live, kept, mark in (("node_modules", ".elm-pi-old-core.1", "old pi"),
                                 ("agent/npm/node_modules", ".elm-pi-old-packages.1", "old packages")):
            (root / live).mkdir(parents=True)
            (root / live / "new").write_text("half-built")
            (root / kept).mkdir()
            (root / kept / "mark").write_text(mark)
        run = self.run_in(root)
        run.core_old, run.packages_old = str(root / ".elm-pi-old-core.1"), str(root / ".elm-pi-old-packages.1")
        stage = root / ".elm-pi-stage-core.abc"
        stage.mkdir()
        run.temp(str(stage))
        with mock.patch.object(runs.sys, "stderr") as said:
            run.finish(failed=True)
        self.assertEqual("old pi", (root / "node_modules/mark").read_text())
        self.assertEqual("old packages", (root / "agent/npm/node_modules/mark").read_text())
        self.assertFalse((root / "node_modules/new").exists())
        self.assertEqual(["agent", "node_modules"], sorted(p.name for p in root.iterdir()))   # nothing left over
        written = "".join(call.args[0] for call in said.write.call_args_list)
        self.assertIn("    put back the previous node_modules\n", written)
        self.assertIn("    put back the previous agent/npm/node_modules\n", written)

    def test_a_run_that_worked_keeps_the_new_trees_and_drops_the_old(self):
        root = self.tree()
        (root / "node_modules").mkdir()
        (root / "node_modules/new").write_text("new pi")
        (root / ".elm-pi-old-core.1").mkdir()
        run = self.run_in(root)
        run.core_old = str(root / ".elm-pi-old-core.1")
        run.finish(failed=False)
        self.assertEqual("new pi", (root / "node_modules/new").read_text())
        self.assertEqual(["node_modules"], [p.name for p in root.iterdir()])

    def test_a_fresh_install_that_fails_has_nothing_to_put_back(self):
        root = self.tree()
        (root / "node_modules").mkdir()
        run = self.run_in(root)
        run.core_old = str(root / ".elm-pi-old-core.1")           # named, never made: there was no pi before
        run.finish(failed=True)
        self.assertTrue((root / "node_modules").is_dir())

    def test_a_command_that_fails_ends_the_run_with_its_status(self):
        run = self.run_in(self.tree())
        with self.assertRaises(runs.Stop) as caught:
            run.must(["/bin/sh", "-c", "exit 7"])
        self.assertEqual(7, caught.exception.code)
        run.must(["/bin/sh", "-c", "exit 0"])

    def test_a_command_that_was_killed_is_128_plus_the_signal(self):
        # npm stopped with SIGTERM left the installer exiting 241 (-15 as a byte).
        run = self.run_in(self.tree())
        self.assertEqual(128 + signal.SIGTERM, run.call(["/bin/sh", "-c", "kill -TERM $$"]))
        self.assertEqual(128 + signal.SIGKILL, run.call(["/bin/sh", "-c", "kill -KILL $$"]))

    def test_a_program_that_is_not_there_is_127_and_says_which(self):
        run = self.run_in(self.tree())
        with mock.patch.object(runs.sys, "stderr") as said:
            self.assertEqual(127, run.call(["/nonexistent/elm-pi-test-program"]))
        self.assertIn("/nonexistent/elm-pi-test-program", said.write.call_args[0][0])

    def test_capture_is_the_text_without_its_last_newlines(self):
        run = self.run_in(self.tree())
        self.assertEqual((0, "a\n b"), run.capture(["/bin/sh", "-c", "printf 'a\\n b\\n\\n'"]))
        self.assertEqual((3, "out\nerr"), run.capture(["/bin/sh", "-c", "echo out; echo err >&2; exit 3"],
                                                      merge=True))


if __name__ == "__main__":
    unittest.main()
