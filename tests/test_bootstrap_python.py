"""The Python installer's decisions, run against the bash installer's.

bootstrap.sh is 1,767 lines, most of them the same file-writing and decision
work this package now does in Python. The two are compared the way the launcher
is: the same tree, the same stubs, the same inputs, and then the record and the
files they wrote side by side.

This module covers the half that decides *what an install is* - the flags and
the install-options record, the install environment and the interpreter, and
agent/ rendered from templates/. The download and npm phases (Node, pi, the
tools, uv, the PyPI index, the extension packages) and the entry point are the
next slice; there is deliberately no `python/bootstrap` yet, so nothing that
cannot install yet can be mistaken for the installer.
"""

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = (ROOT / "bootstrap.bash").read_text()
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")

sys.path.insert(0, str(ROOT / "python"))

from elmboot import agentconfig, console, installenv, options as elm_options  # noqa: E402
from elmboot import settings as elm_settings  # noqa: E402
from elmboot import usage  # noqa: E402


def block(text, start, end):
    """The source between two anchors; the start must be unambiguous."""
    if text.count(start) != 1:
        raise AssertionError("anchor is not unique: %r" % start)
    i = text.index(start)
    return text[i:text.index(end, i)]


def heredoc(text, opener):
    """The body of the one heredoc opened by `opener` (which ends <<'TAG'\\n)."""
    marker = re.search(r"<<'(\w+)'", opener).group(1)
    body = text.split(opener, 1)[1]
    return body.split("\n" + marker + "\n", 1)[0] + "\n"


class Notes:
    """A console stand-in: the lines the installer would print, in order."""

    def __init__(self):
        self.lines = []

    def say(self, heading):
        self.lines.append("\n\033[1m==> %s\033[0m" % heading)

    def note(self, *lines):
        self.lines += ["    " + line for line in lines]

    def warn(self, message):
        self.lines.append("\033[33m    %s\033[0m" % message)

    def text(self):
        return "".join(line + "\n" for line in self.lines)


class Captured:
    """Swap the module-level console functions for the duration of a call."""

    def __init__(self):
        self.notes = Notes()

    def __enter__(self):
        self.saved = {name: getattr(console, name) for name in ("say", "note", "warn", "die")}
        console.say, console.note, console.warn = self.notes.say, self.notes.note, self.notes.warn

        def die(message):
            raise AssertionError("unexpected refusal: %s" % message)

        console.die = die
        return self.notes

    def __exit__(self, *exception):
        for name, function in self.saved.items():
            setattr(console, name, function)
        return False


# --- texts and lists -----------------------------------------------------------------

class TextTests(unittest.TestCase):
    def test_the_help_text_is_the_bash_installers(self):
        self.assertEqual(heredoc(BOOTSTRAP, "  cat <<'EOU'\n"), usage.USAGE)

    def test_the_scrub_lists_are_lib_sandbox_s(self):
        sandbox = (ROOT / "lib" / "sandbox.sh").read_text()

        def words(name):
            line = next(l for l in sandbox.splitlines() if l.startswith(name + "="))
            return line.split("=", 1)[1].strip().strip('"').split()

        self.assertEqual(tuple(words("ELM_SCRUB_PREFIXES")), installenv.SCRUB_PREFIXES)
        self.assertEqual(tuple(words("ELM_SCRUB_NAMES")), installenv.SCRUB_NAMES)
        self.assertEqual(tuple(words("ELM_SCRUB_KEEP")), installenv.SCRUB_KEEP)

    def test_the_standalone_python_is_the_pinned_one(self):
        sandbox = (ROOT / "lib" / "sandbox.sh").read_text()
        release = re.search(r'^ELM_STANDALONE_PY_RELEASE="([^"]+)"', sandbox, re.M).group(1)
        version = re.search(r'^ELM_STANDALONE_PY_VERSION="([^"]+)"', sandbox, re.M).group(1)
        self.assertEqual(release, installenv.STANDALONE_RELEASE)
        self.assertEqual(version, installenv.STANDALONE_VERSION)
        for triple, digest in installenv.STANDALONE_DIGESTS.items():
            self.assertIn(digest, sandbox, triple)


# --- the flags and the record --------------------------------------------------------

OPTIONS_FILE = "agent/install-options"
APPLY_FLAG = block(BOOTSTRAP, "apply_flag() {", "\n}\n") + "\n}\n"
PARSE_BLOCK = block(BOOTSTRAP, 'for arg in "$@"; do\n  case "$arg" in\n'
                               '    --no-shim|--no-packages', 'apply_flag() {')
OPTIONS_BLOCK = block(BOOTSTRAP, "# --- the options this install was made with", "# Not NODE_VERSION:")


class OptionsTests(unittest.TestCase):
    """Every case the bash installer's own tests run, on both implementations."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def tree(self, name):
        root = self.base / name
        if root.exists():
            shutil.rmtree(root)
        (root / "agent").mkdir(parents=True)
        return root

    def bash(self, root, flags, reset, env):
        script = (
            "set -euo pipefail\n"
            "say() { printf '\\n\\033[1m==> %s\\033[0m\\n' \"$*\"; }\n"
            "warn() { printf 'WARN %s\\n' \"$*\"; }\n"
            "WITH_SHIM=1; WITH_PACKAGES=1; INTERACTIVE=1; UPDATE=0; AUTH_LOCK=1; FORCE=0\n"
            "WITH_TOOLS=1; WITH_PATCH=1; WITH_PYTHON=1; WITH_PYPI_INDEX=0; FORCE_PACKAGES=0\n"
            "DROPPED_FLAGS=\"\"; GIVEN_FLAGS=\"\"\n"
            "RESET_OPTIONS=\"$2\"; HERE=\"$PWD\"; CONFIG_TOOL=/nonexistent\n"
            "elm_py() { :; }\n"
            "set -- $1\n" + PARSE_BLOCK +
            "\n" + APPLY_FLAG + OPTIONS_BLOCK +
            'echo "RESULT $WITH_SHIM $WITH_PACKAGES $AUTH_LOCK $WITH_TOOLS $WITH_PATCH '
            '$WITH_PYTHON $WITH_PYPI_INDEX|${ELM_PI_TOOLS:-}|$OPT_BRANCH|$OPT_REPO"\n')
        result = subprocess.run([BASH, "-c", script, "options", flags, "1" if reset else "0"],
                                cwd=str(root), env={"PATH": "/usr/bin:/bin", **env},
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout

    def python(self, root, argv, reset, env):
        environment = dict(env)
        with Captured() as notes:
            parsed = elm_options.parse(list(argv))
            parsed.reset_options = reset
            elm_options.inherit(str(root), parsed, environment)
            elm_options.write(str(root), parsed, environment)
        result = "RESULT %d %d %d %d %d %d %d|%s|%s|%s\n" % (
            parsed.shim, parsed.packages, parsed.auth_lock, parsed.with_tools,
            parsed.patch, parsed.python, parsed.pypi_index, parsed.tools,
            parsed.branch, parsed.repo)
        return notes.text() + result

    def record(self, root):
        path = root / OPTIONS_FILE
        return path.read_text() if path.exists() else ""

    def compare(self, argv=(), reset=False, start=None, **env):
        expected_root, actual_root = self.tree("bash"), self.tree("python")
        for root in (expected_root, actual_root):
            if start is not None:
                start(root)
        expected = self.bash(expected_root, " ".join(argv), reset, env)
        expected_record = self.record(expected_root)
        actual = self.python(actual_root, argv, reset, env)
        self.assertEqual(expected_record, self.record(actual_root))
        # The tree paths in the output are the only thing that may differ.
        normalise = lambda text, root: text.replace(str(root), "<root>")
        self.assertEqual(normalise(expected, expected_root), normalise(actual, actual_root))

    def test_defaults(self):
        self.compare()
        self.assertIn("flags=\n", self.record(self.base / "python") + "\n")

    def test_flags_are_recorded_and_repeated(self):
        self.compare(["--no-shim"], ELM_PI_TOOLS="fd,rg", ELM_PI_BRANCH="dev",
                     ELM_PI_REPO="https://x/y.git")
        self.compare(["--no-packages", "--no-shim"])
        self.compare(["--no-python"])
        self.compare(["--with-pypi-index"])

    def test_a_recorded_install_is_repeated_without_the_environment(self):
        record = ("flags=--no-shim\ntools=fd,rg\nbranch=dev\nrepo=https://x/y.git\n")

        def existing(root):
            (root / OPTIONS_FILE).write_text(record)

        self.compare([], start=existing)

    def test_reset_takes_the_record_back(self):
        def existing(root):
            (root / OPTIONS_FILE).write_text("flags=--no-shim\ntools=\nbranch=\nrepo=\n")

        self.compare(["--no-auth-lock"], reset=True, start=existing)

    def test_an_install_from_before_the_record(self):
        def old(root):
            (root / "agent" / "settings.json").write_text('{"packages": []}')
            (root / "agent" / "extensions").mkdir()
            (root / "agent" / "auth.json").write_text("{}")
            os.chmod(root / "agent" / "auth.json", 0o600)
            (root / "agent" / "bin").mkdir()

        self.compare([], start=old)

    def test_a_with_flag_takes_its_opposite_back(self):
        def no_python(root):
            (root / OPTIONS_FILE).write_text("flags=--no-python\ntools=\nbranch=\nrepo=\n")

        self.compare(["--with-python"], start=no_python)
        self.compare(["--no-pypi-index"],
                     start=lambda root: (root / OPTIONS_FILE).write_text(
                         "flags=--with-pypi-index\ntools=\nbranch=\nrepo=\n"))


class RecordFileTests(unittest.TestCase):
    """What lands in agent/install-options, written and read back."""

    def test_the_record_is_five_lines_and_reads_as_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agent").mkdir()
            env = {}
            with Captured():
                parsed = elm_options.parse(["--no-packages", "--with-pypi-index"])
                elm_options.inherit(tmp, parsed, env)
                elm_options.write(tmp, parsed, env)
            text = (Path(tmp) / "agent" / "install-options").read_text()
        self.assertTrue(text.startswith("# The options this install was made with."))
        self.assertIn("flags=--no-packages --with-pypi-index\n", text)
        self.assertIn("tools=\n", text)
        self.assertEqual(7, len(text.splitlines()))   # three comments, then the four keys

    def test_a_value_with_whitespace_is_not_a_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agent").mkdir()
            env = {"ELM_PI_BRANCH": "two words", "ELM_PI_REPO": "https://x/y.git"}
            with Captured():
                parsed = elm_options.parse([])
                elm_options.inherit(tmp, parsed, env)
                elm_options.write(tmp, parsed, env)
            text = (Path(tmp) / "agent" / "install-options").read_text()
        self.assertIn("branch=\n", text)
        self.assertIn("repo=https://x/y.git\n", text)


# --- the values this repo owns inside agent/, both installers ------------------------

MERGE_BLOCK = heredoc(BOOTSTRAP, 'HERE="$HERE" elm_py - <<\'PYX\'\n')
HASHLINE_BLOCK = heredoc(BOOTSTRAP, 'HERE="$HERE" elm_py - <<\'PYHL\'\n')
WORKFLOW_BLOCK = heredoc(BOOTSTRAP, 'HERE="$HERE" elm_py - <<\'PYWF\'\n')
PACKAGES_BLOCK = heredoc(BOOTSTRAP, '  elm_py - <<\'PYX\'\n')


class OwnedSettingsTests(unittest.TestCase):
    """The installer-owned merge, models.json and the package list: same output,
    same files, run from the bash heredocs the installer uses."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        # Equal-length names, deliberately: a failure prints brief() previews
        # cut at 57 characters of the raw JSON, and a preview cut inside the
        # tree's path would differ between two roots of different lengths.
        self.trees = {"aa": self.make("aa"), "bb": self.make("bb")}

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, name):
        root = self.base / name
        for part in ("templates", "config"):
            shutil.copytree(ROOT / part, root / part)
        (root / "agent").mkdir()
        return root

    def run_bash(self, root, body):
        result = subprocess.run([sys.executable, "-E", "-S", "-"], input=body,
                                cwd=str(root), capture_output=True, text=True,
                                env={"PATH": "/usr/bin:/bin", "HOME": str(self.base),
                                     "HERE": str(root)})
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout

    def with_models(self, root):
        """The files the merge and models rules read, in a state they change."""
        (root / "agent" / "model-ids.json").write_text(json.dumps(
            {"qwen": "Qwen/Qwen-Test", "llama": "meta-llama/Llama-Test",
             "mistral": "mistralai/Mistral-Test"}))
        for name in ("settings.json", "models.json"):
            shutil.copy2(root / "templates" / name, root / "agent" / name)
        for relative in ("extensions/subagent/config.json",
                         "extensions/pi-permission-system/config.json",
                         "config/pi-task-models/config.json",
                         "config/pi-auto-compact/config.json", "web-search.json"):
            (root / "agent" / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / "templates" / relative, root / "agent" / relative)

    def settled(self, root):
        """The files both implementations touched, as text, with the tree as <root>."""
        found = {}
        for path in sorted((root / "agent").rglob("*.json")):
            found[path.relative_to(root / "agent").as_posix()] = path.read_text().replace(
                str(root), "<root>")
        return found

    def compare(self, prepare):
        for tree, root in self.trees.items():
            self.make_fresh(tree)
            self.with_models(root)
            if prepare is not None:
                prepare(root)
        expected = self.run_bash(self.trees["aa"], MERGE_BLOCK)
        actual = self.capture(elm_settings.merge_owned, self.trees["bb"])
        self.assertEqual(self.normal(expected, self.trees["aa"]),
                         self.normal(actual, self.trees["bb"]))
        self.assertEqual(self.settled(self.trees["aa"]), self.settled(self.trees["bb"]))

    def capture(self, function, root):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            result = function(str(root))
        return buffer.getvalue(), result

    def normal(self, text, root):
        return text.replace(str(root), "<root>") if isinstance(text, str) else text[0].replace(
            str(root), "<root>")

    def make_fresh(self, name):
        root = self.trees[name]
        shutil.rmtree(root / "agent", ignore_errors=True)
        (root / "agent").mkdir()

    def test_everything_already_matches(self):
        self.compare(None)

    def test_an_edited_key_is_reported_and_reapplied(self):
        def edit(root):
            path = root / "agent" / "settings.json"
            data = json.loads(path.read_text())
            data["httpIdleTimeoutMs"] = 5
            data["theme"] = "mine"
            path.write_text(json.dumps(data, indent=2))
        self.compare(edit)

    def test_a_zero_is_not_a_false(self):
        def edit(root):
            path = root / "agent" / "config" / "pi-auto-compact" / "config.json"
            data = json.loads(path.read_text())
            data["autoCompactThreshold"] = False
            path.write_text(json.dumps(data))
        self.compare(edit)

    def test_a_stray_llama_is_removed_and_mistral_is_added(self):
        def edit(root):
            path = root / "agent" / "models.json"
            data = json.loads(path.read_text().replace("@QWEN_MODEL@", "Qwen/Qwen-Test")
                              .replace("@LLAMA_MODEL@", "meta-llama/Llama-Test")
                              .replace("@MISTRAL_MODEL@", "mistralai/Mistral-Test"))
            data["providers"]["elm"]["models"].append(
                {"id": "meta-llama/Llama-Test", "name": "Llama"})
            path.write_text(json.dumps(data, indent=2))
        self.compare(edit)

    def test_the_old_max_tokens_is_moved_to_the_measured_one(self):
        def edit(root):
            path = root / "agent" / "models.json"
            data = json.loads(path.read_text().replace("@QWEN_MODEL@", "Qwen/Qwen-Test")
                              .replace("@LLAMA_MODEL@", "meta-llama/Llama-Test")
                              .replace("@MISTRAL_MODEL@", "mistralai/Mistral-Test"))
            for model in data["providers"]["elm"]["models"]:
                model["maxTokens"] = 32768
            path.write_text(json.dumps(data, indent=2))
        self.compare(edit)

    def test_a_key_the_repo_does_not_own_is_never_lost(self):
        def edit(root):
            path = root / "agent" / "settings.json"
            data = json.loads(path.read_text())
            data["myOwnKey"] = {"a": [1, 2, 3]}
            path.write_text(json.dumps(data, indent=2))
        self.compare(edit)
        self.assertIn("myOwnKey", (self.trees["bb"] / "agent/settings.json").read_text())

    def test_edits_to_every_owned_key_converge_and_stay_put(self):
        """The property the bash suite has: any edit of an owned key is replaced,
        nothing else is touched, and the second run changes nothing."""
        def edit(root):
            for relative, keys in elm_settings.OWNED.items():
                path = root / "agent" / relative
                if not path.exists():
                    continue
                data = json.loads(path.read_text())
                for key in keys:
                    data[key] = "edited"
                data["unowned"] = {"keep": [1, 2]}
                path.write_text(json.dumps(data, indent=2))
        self.compare(edit)
        # Again, on the tree the first run left: both must agree, and both must
        # find nothing left to change on the third.
        for _ in range(2):
            expected = self.run_bash(self.trees["aa"], MERGE_BLOCK)
            actual = self.capture(elm_settings.merge_owned, self.trees["bb"])[0]
            self.assertEqual(self.normal(expected, self.trees["aa"]),
                             self.normal(actual, self.trees["bb"]))
            self.assertEqual(self.settled(self.trees["aa"]),
                             self.settled(self.trees["bb"]))
        self.assertIn("unowned", (self.trees["bb"] / "agent/settings.json").read_text())

    def test_a_malformed_live_file_stops_both(self):
        for root in self.trees.values():
            self.make_fresh(root.name)
            self.with_models(root)
            (root / "agent" / "settings.json").write_text("{not json")
        result = subprocess.run([sys.executable, "-E", "-S", "-"], input=MERGE_BLOCK,
                                cwd=str(self.trees["aa"]), capture_output=True, text=True,
                                env={"PATH": "/usr/bin:/bin", "HERE": str(self.trees["aa"])})
        self.assertNotEqual(0, result.returncode)
        with self.assertRaises(ValueError):
            with contextlib.redirect_stdout(io.StringIO()):
                elm_settings.merge_owned(str(self.trees["bb"]))

    def test_hashline_and_workflow_settings(self):
        for tag, body, call in (("hashline", HASHLINE_BLOCK, elm_settings.hashline),
                                ("workflow", WORKFLOW_BLOCK, elm_settings.workflow)):
            with self.subTest(tag=tag):
                for name, root in self.trees.items():
                    self.make_fresh(name)
                    (root / "agent" / ("hashline" if tag == "hashline" else "workflows")).mkdir(
                        parents=True, exist_ok=True)
                expected = self.run_bash(self.trees["aa"], body)
                actual = self.capture(call, self.trees["bb"])[0]
                self.assertEqual(self.normal(expected, self.trees["aa"]),
                                 self.normal(actual, self.trees["bb"]))
                self.assertEqual(self.settled(self.trees["aa"]), self.settled(self.trees["bb"]))

    def test_the_package_list_is_derived_and_named(self):
        for name, root in self.trees.items():
            self.make_fresh(name)
            shutil.copy2(root / "templates/settings.json", root / "agent/settings.json")
            path = root / "agent/settings.json"
            data = json.loads(path.read_text())
            data["packages"] = ["npm:added-by-hand"]
            path.write_text(json.dumps(data, indent=2))
        expected = self.run_bash(self.trees["aa"], PACKAGES_BLOCK)
        actual, chosen = self.capture(elm_settings.package_list, self.trees["bb"])
        self.assertEqual(self.normal(expected, self.trees["aa"]),
                         self.normal(actual, self.trees["bb"]))
        self.assertEqual(self.settled(self.trees["aa"]), self.settled(self.trees["bb"]))
        self.assertNotIn("added-by-hand", chosen)
        self.assertIn("not in templates/: added-by-hand - removed.", actual)


# --- the environment and the interpreter --------------------------------------------

class EnvironmentTests(unittest.TestCase):
    def test_the_scrub_drops_what_redirects_a_toolchain(self):
        env = {"PYTHONPATH": "/x", "CONDA_DEFAULT_ENV": "base", "NODE_OPTIONS": "--x",
               "npm_config_registry": "http://x", "BASH_ENV": "/x", "CDPATH": ".",
               "LD_PRELOAD": "/x", "NODE_EXTRA_CA_CERTS": "/missing", "AWS_PROFILE": "p",
               "GITHUB_TOKEN": "t", "PATH": "/usr/bin"}
        installenv.scrub(env)
        self.assertEqual({"AWS_PROFILE": "p", "GITHUB_TOKEN": "t", "PATH": "/usr/bin"}, env)

    def test_a_ca_bundle_that_exists_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "ca.pem"
            bundle.write_text("")
            env = {"SSL_CERT_FILE": str(bundle), "CURL_CA_BUNDLE": "/gone"}
            installenv.scrub(env)
        self.assertEqual({"SSL_CERT_FILE": str(bundle)}, env)

    def test_clean_path_drops_environments_unless_asked_not_to(self):
        with tempfile.TemporaryDirectory() as tmp:
            conda = Path(tmp) / "conda" / "bin"
            conda.mkdir(parents=True)
            (Path(tmp) / "conda" / "conda-meta").mkdir()
            value = "%s:.:/usr/bin:/usr/bin" % conda
            self.assertEqual("/usr/bin", installenv.clean_path(value))
            self.assertEqual("%s:/usr/bin" % conda,
                             installenv.clean_path(value, keep_environments=True))

    def test_the_install_environment_confines_npm(self):
        env = {"PATH": "/custom/bin:/usr/bin", "npm_config_registry": "http://x",
               "NODE_OPTIONS": "--require x"}
        installenv.install_environment("/install", env)
        self.assertEqual("/install/.npm-cache", env["NPM_CONFIG_CACHE"])
        self.assertEqual("/install/.node", env["NPM_CONFIG_PREFIX"])
        self.assertEqual("/dev/null", env["NPM_CONFIG_GLOBALCONFIG"])
        self.assertEqual("/custom/bin:/usr/bin", env["ELM_PI_USER_PATH"])
        self.assertTrue(env["PATH"].startswith("/install/.node/bin:/usr/bin:/bin:"))
        self.assertNotIn("npm_config_registry", env)
        self.assertNotIn("NODE_OPTIONS", env)

    def test_disk_space_is_only_for_what_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            parsed = elm_options.Options()
            parsed.pypi_index = True
            keep, temporary, parts = installenv.disk_plan(tmp, parsed)
            self.assertEqual((2400, 1000), (keep, temporary))
            (Path(tmp) / "agent" / "python" / "env" / "bin").mkdir(parents=True)
            (Path(tmp) / "agent" / "python" / "env" / "bin" / "python").write_text("")
            os.chmod(Path(tmp) / "agent" / "python" / "env" / "bin" / "python", 0o755)
            (Path(tmp) / "agent" / "pypi-index.db").write_text("x")

    def test_no_space_stops_before_the_first_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            parsed = elm_options.Options()
            with Captured() as notes:
                installenv.check_disk(tmp, parsed, {"ELM_PI_DISK_NOTED": "1"})
            self.assertEqual("", notes.text())
            saved = os.statvfs
            os.statvfs = lambda path: type("S", (), {"f_bavail": 1, "f_frsize": 4096})
            try:
                with self.assertRaises(console.Failure):
                    installenv.check_disk(tmp, parsed, {"ELM_PI_DISK_NOTED": "1"})
            finally:
                os.statvfs = saved

    def test_the_python_choice_prefers_what_was_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "agent").mkdir()
            (Path(tmp) / "agent" / "python-path").write_text(sys.executable + "\n")
            env = {}
            self.assertEqual(sys.executable, installenv.select_python(tmp, env))
            self.assertEqual(sys.executable, env["ELM_PI_PYTHON"])

    def test_a_named_interpreter_that_is_too_old_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "python3.7"
            fake.write_text("#!/bin/sh\nexit 10\n")
            fake.chmod(0o755)
            self.assertEqual(10, installenv.python_check(str(fake)))
            with self.assertRaises(console.Failure) as caught:
                installenv.select_python(tmp, {"ELM_PI_PYTHON": str(fake)})
        self.assertIn("older than Python 3.8", str(caught.exception))

    def test_a_tmpdir_only_this_account_can_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o777)
            env = {"TMPDIR": tmp}
            installenv.private_tmpdir(env)
            self.assertEqual(os.path.join(tmp, "elm-pi-%d" % os.geteuid()), env["TMPDIR"])
            self.assertFalse(os.lstat(env["TMPDIR"]).st_mode & 0o077)


class ArchiveTests(unittest.TestCase):
    def test_tar_and_zip_unpack_without_tar_or_unzip(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = b"#!/bin/sh\n"
            bundle = Path(tmp) / "x.tar.gz"
            with tarfile.open(str(bundle), "w:gz") as archive:
                info = tarfile.TarInfo("dir/tool")
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            self.assertTrue(installenv.extract(str(bundle), str(Path(tmp) / "out")))
            self.assertEqual(data, (Path(tmp) / "out" / "dir" / "tool").read_bytes())
            self.assertTrue(installenv.extract(str(bundle), str(Path(tmp) / "again")))

            as_zip = Path(tmp) / "x.zip"
            with zipfile.ZipFile(str(as_zip), "w") as archive:
                archive.writestr("tool", data)
            self.assertTrue(installenv.extract(str(as_zip), str(Path(tmp) / "z")))
            self.assertEqual(data, (Path(tmp) / "z" / "tool").read_bytes())

    def test_an_archive_cannot_write_outside_its_destination(self):
        """An archive is a remote file: its members may not escape the target,
        on the interpreter this installer records as well as this one."""
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "evil.tar.gz"
            with tarfile.open(str(archive), "w:gz") as bundle:
                for name in ("../escaped", "/absolute-escaped", "good/tool"):
                    data = name.encode()
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    bundle.addfile(info, io.BytesIO(data))
                link = tarfile.TarInfo("good/out")
                link.type = tarfile.SYMTYPE
                link.linkname = "../../elsewhere"
                bundle.addfile(link)
            destination = Path(tmp) / "out"
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                self.assertTrue(installenv.extract(str(archive), str(destination)))
            self.assertEqual("good/tool", (destination / "good" / "tool").read_text())
            self.assertFalse((Path(tmp) / "escaped").exists())
            self.assertFalse(Path("/absolute-escaped").exists())
            self.assertFalse((destination / "good" / "out").exists())
            self.assertIn("outside the destination", buffer.getvalue())

            # And the same under an older interpreter, which has no tarfile
            # data filter: the check cannot be the standard library's.
            code = ("import sys; sys.path.insert(0, %r); from elmboot import installenv;"
                    "installenv.extract(sys.argv[1], sys.argv[2])"
                    % str(ROOT / "python"))
            for interpreter in ("/usr/bin/python3", sys.executable):
                if not os.access(interpreter, os.X_OK):
                    continue
                fresh = Path(tmp) / ("out-" + interpreter.split("/")[-1])
                result = subprocess.run([interpreter, "-E", "-S", "-c", code,
                                         str(archive), str(fresh)],
                                        capture_output=True, text=True)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertFalse((Path(tmp) / "escaped").exists(), interpreter)
                self.assertTrue((fresh / "good" / "tool").is_file(), interpreter)

    def test_a_binary_is_found_wherever_it_unpacked(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a" / "b").mkdir(parents=True)
            (Path(tmp) / "a" / "b" / "tool").write_text("")
            self.assertEqual(os.path.join(tmp, "a", "b", "tool"),
                             installenv.find_binary(tmp, "tool"))
            self.assertEqual("", installenv.find_binary(tmp, "absent"))

    def test_sha256_matches_hashlib(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "f"
            path.write_bytes(b"hello")
            self.assertEqual(hashlib.sha256(b"hello").hexdigest(),
                             installenv.sha256_of(str(path)))


# --- agent/ rendered from templates/, both installers -------------------------------

AGENT_BLOCK = block(BOOTSTRAP, 'chmod +x pi python/pi pi.orig configure.sh 2>/dev/null || true',
                    "# --- 3b. command-line tools")
PRELUDE = r'''
set -euo pipefail
HERE="$1"; ELM_PI_PYTHON="$2"; ELM_PI_USER_PATH="/usr/bin:/bin"; export ELM_PI_PYTHON ELM_PI_USER_PATH
AUTH_LOCK=1
PATH="/usr/bin:/bin"
CONFIG_TOOL="$HERE/scripts/elm_config.py"
. "$HERE/lib/sandbox.sh"
. "$HERE/lib/state.sh"
ELM_PI_ROOT="$HERE"
ELM_PI_PYTHON_PATH="$(command -v python3)"
say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m    %s\033[0m\n' "$*"; }
die() { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
elm_py() { ( cd "${ELM_PI_ROOT:-/}" && exec "$ELM_PI_PYTHON" -E -S "$@" ); }
'''


class AgentConfigurationTests(unittest.TestCase):
    """The same templates and config, rendered by both installers."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.sources = ("templates", "config", "lib", "scripts")
        self.bash_tree = self.install("bash")
        self.python_tree = self.install("python")

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, name):
        """A tree with what the phase reads, and the files it chmods."""
        root = self.base / name
        root.mkdir()
        for part in self.sources:
            shutil.copytree(ROOT / part, root / part)
        for program in ("pi", "pi.orig", "configure.sh"):
            (root / program).write_text("#!/bin/sh\n")
        (root / "agent").mkdir()
        return root

    def run_bash(self, root, shim="1"):
        script = PRELUDE.replace("HERE=\"$1\"", "HERE=\"$1\"; WITH_SHIM=" + shim) + "\n" + AGENT_BLOCK
        result = subprocess.run([BASH, "-c", script, "installer", str(root), sys.executable],
                                cwd=str(root), capture_output=True, text=True,
                                env={"PATH": "/usr/bin:/bin", "HOME": str(self.base),
                                     "TMPDIR": tempfile.gettempdir()})
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout

    def run_python(self, root):
        env = {"ELM_PI_PYTHON": sys.executable, "ELM_PI_USER_PATH": "/usr/bin:/bin",
               "PATH": "/usr/bin:/bin", "TMPDIR": tempfile.gettempdir()}
        parsed = elm_options.Options()
        with Captured() as notes:
            agentconfig.refresh(str(root), parsed, env)
        return notes.text()

    def tree(self, root):
        """Every path under agent/, with its content, mode and symlink target."""
        found = {}
        base = root / "agent"
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(base).as_posix()
            if path.is_symlink():
                found[relative] = ("link", os.readlink(str(path)).replace(str(root), "<root>"))
            elif path.is_dir():
                found[relative] = ("dir", None)
            else:
                found[relative] = ("file", path.read_text(errors="replace").replace(
                    str(root), "<root>"))
        return found

    def test_the_same_tree_is_rendered(self):
        expected = self.run_bash(self.bash_tree)
        actual = self.run_python(self.python_tree)
        self.maxDiff = None
        self.assertEqual(expected.replace(str(self.bash_tree), "<root>"),
                         actual.replace(str(self.python_tree), "<root>"))
        self.assertEqual(self.tree(self.bash_tree), self.tree(self.python_tree))

    def test_no_shim_removes_the_extension_from_the_set(self):
        expected = self.run_bash(self.bash_tree, shim="0")
        self.assertIn("no shim", expected)
        env = {"ELM_PI_PYTHON": sys.executable, "ELM_PI_USER_PATH": "/usr/bin:/bin",
               "PATH": "/usr/bin:/bin", "TMPDIR": tempfile.gettempdir()}
        parsed = elm_options.Options()
        parsed.shim = False
        with Captured() as notes:
            agentconfig.refresh(str(self.python_tree), parsed, env)
        self.assertIn("no shim", notes.text())
        self.assertFalse((self.python_tree / "agent" / "extensions" / "elm-shim.ts").exists())
        bash_line = next(l for l in expected.splitlines() if "extensions (" in l)
        self.assertEqual(bash_line, [l for l in notes.text().splitlines()
                                     if "extensions (" in l][0])

    def test_a_tuned_config_is_kept(self):
        """Both leave an edited settings.json exactly as it was."""
        for root in (self.bash_tree, self.python_tree):
            (root / "agent").mkdir(exist_ok=True)
            (root / "agent" / "settings.json").write_text('{"mine": true}\n')
        self.run_bash(self.bash_tree)
        self.run_python(self.python_tree)
        for root in (self.bash_tree, self.python_tree):
            self.assertEqual('{"mine": true}\n', (root / "agent" / "settings.json").read_text())


if __name__ == "__main__":
    unittest.main()
