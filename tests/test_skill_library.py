"""The community skill library: scripts/skill_library.py and the installer phase that runs it.

The library is K-Dense's scientific-agent-skills, fetched by the installer into
agent/skills/kdense (user request, 2026-11-17). What has to hold:

* what is installed is exactly the pinned archive's skills/ folders, minus the
  ones the config excludes and the ones this install already has a namesake of -
  and nothing an archive could smuggle in beside them;
* every installed skill is hidden from pi's system prompt and still loads;
* no network, a refused download or a wrong checksum never fails an install;
* bootstrap.bash and python/elmboot print the same text and leave the same tree.

The archive here is a small one built for the test, served by a stand-in for
curl. The real one is used only where a tool cache already holds it.
"""

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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/skill_library.py"
CONFIG = json.loads((ROOT / "config/skill-library.json").read_text())
BOOTSTRAP = (ROOT / "bootstrap.bash").read_text()
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")
COMMIT = "a" * 40
TOP = "scientific-agent-skills-" + COMMIT
ASSET = TOP + ".tar.gz"

CURL = """#!/bin/sh
# curl, for the test: copies $CURL_SERVES to the -o file, or fails with $CURL_FAIL.
echo "$*" >> "$CURL_LOG"
[ -z "${CURL_FAIL:-}" ] || exit "$CURL_FAIL"
out=""
while [ $# -gt 0 ]; do
  case "$1" in -o) out="$2"; shift 2 ;; *) shift ;; esac
done
cp "$CURL_SERVES" "$out"
"""


def skill(name, description="Does %s things. Use when asked.", extra=""):
    return ("---\nname: %s\ndescription: %s\n%smetadata:\n  version: \"1.0\"\n---\n\n# %s\n\nBody.\n"
            % (name, description % name if "%s" in description else description, extra, name))


def members():
    """(path, content, mode, type) for the test archive: good skills, bad ones, and things that are not skills."""
    return [
        (TOP + "/README.md", "readme", 0o644, "file"),
        (TOP + "/LICENSE.md", "MIT, the test's", 0o644, "file"),
        (TOP + "/docs/picture.png", "x" * 4096, 0o644, "file"),
        (TOP + "/skills/alpha/SKILL.md", skill("alpha"), 0o644, "file"),
        (TOP + "/skills/alpha/scripts/run.py", "print(1)\n", 0o755, "file"),
        (TOP + "/skills/alpha/references/notes.md", "notes\n", 0o644, "file"),
        (TOP + "/skills/beta/SKILL.md", skill("beta"), 0o644, "file"),          # the config excludes it
        (TOP + "/skills/gamma/SKILL.md", skill("gamma"), 0o644, "file"),        # the install has its own
        (TOP + "/skills/delta/SKILL.md", skill("other"), 0o644, "file"),        # declares another name
        (TOP + "/skills/epsilon/SKILL.md", "---\nname: epsilon\n---\n\nBody.\n", 0o644, "file"),   # no description
        (TOP + "/skills/zeta/SKILL.md",
         "---\nname: zeta\ndescription: >-\n  Folded over\n  two lines.\ndisable-model-invocation: false\n---\n\n# zeta\n",
         0o644, "file"),
        (TOP + "/skills/eta/README.md", "no skill file here", 0o644, "file"),
        (TOP + "/skills/theta/SKILL.md", "# theta\n\nNo frontmatter at all.\n", 0o644, "file"),
        (TOP + "/skills/Bad_Name/SKILL.md", skill("Bad_Name"), 0o644, "file"),
        (TOP + "/skills/alpha/link", "/etc/passwd", 0o777, "symlink"),
        (TOP + "/skills/alpha/hard", TOP + "/README.md", 0o644, "hardlink"),
        (TOP + "/skills/alpha/../../../escaped.txt", "out", 0o644, "file"),
        (TOP + "/skills/../../escaped-too/SKILL.md", skill("escaped-too"), 0o644, "file"),
        ("/absolute/skills/abs/SKILL.md", skill("abs"), 0o644, "file"),
    ]


def write_archive(path, entries=None):
    with tarfile.open(path, "w:gz") as tar:
        for name, content, mode, kind in (members() if entries is None else entries):
            info = tarfile.TarInfo(name)
            info.mode = mode
            if kind == "symlink":
                info.type, info.linkname = tarfile.SYMTYPE, content
                tar.addfile(info)
            elif kind == "hardlink":
                info.type, info.linkname = tarfile.LNKTYPE, content
                tar.addfile(info)
            else:
                data = content.encode("utf-8")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Install:
    """A folder shaped like an install, a test archive and a stand-in curl."""

    def __init__(self, base, entries=None):
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)
        self.root = self.base / "install"
        self.cache = self.base / "cache"
        self.archive = self.base / "served.tar.gz"
        self.log = self.base / "curl.log"
        self.sha = write_archive(self.archive, entries)
        (self.root / "config").mkdir(parents=True)
        (self.root / "templates/skills").mkdir(parents=True)
        (self.root / "agent/skills/gamma").mkdir(parents=True)
        (self.root / "agent/skills/gamma/SKILL.md").write_text("---\nname: gamma\ndescription: mine\n---\n")
        self.write_config()
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        self.curl = bin_dir / "curl"
        self.curl.write_text(CURL)
        self.curl.chmod(0o755)

    def write_config(self, **changes):
        config = {"name": "kdense", "title": "Test library", "repository": "https://example.invalid/lib",
                  "tag": "v1.2.3", "commit": COMMIT, "sha256": self.sha, "downloadMB": 1,
                  "exclude": {"beta": "the test leaves it out"}, "notRouted": ["zeta"],
                  "aliases": {"alpha": ["alfa tool"]}, "skills": []}
        config.update(changes)
        (self.root / "config/skill-library.json").write_text(json.dumps(config))

    def env(self, **more):
        env = {"PATH": "%s:/usr/bin:/bin" % self.curl.parent, "HOME": str(self.base),
               "CURL_LOG": str(self.log), "CURL_SERVES": str(self.archive)}
        env.update(more)
        return env

    def run(self, *argv, env=None):
        return subprocess.run([sys.executable, "-E", "-S", str(SCRIPT), "--root", str(self.root), *argv],
                              capture_output=True, text=True, env=self.env() if env is None else env, timeout=120)

    def sync(self, *flags, **env):
        return self.run("sync", "--cache", str(self.cache), *flags, "--", "curl", "-q", "-fsSL", env=self.env(**env))

    @property
    def library(self):
        return self.root / "agent/skills/kdense"

    def installed(self):
        return sorted(p.parent.name for p in self.library.glob("*/SKILL.md")) if self.library.is_dir() else []

    def downloads(self):
        return len(self.log.read_text().splitlines()) if self.log.exists() else 0


class LibraryCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install = Install(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


class SyncTests(LibraryCase):
    def test_a_fresh_install_gets_the_skills_it_can_use_and_says_what_it_left_out(self):
        result = self.install.sync()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(["alpha", "zeta"], self.install.installed())
        self.assertIn("    Test library v1.2.3 -> agent/skills/kdense (2 skills, hidden from the prompt until one is read)",
                      result.stdout.splitlines())
        self.assertIn("    left out, as config/skill-library.json says: beta", result.stdout.splitlines())
        self.assertIn("    left out gamma: this install has its own skill of that name", result.stdout.splitlines())
        self.assertIn("    left out delta: its name is 'other'", result.stdout.splitlines())
        self.assertIn("    left out epsilon: no description", result.stdout.splitlines())
        self.assertIn("    left out theta: no frontmatter", result.stdout.splitlines())
        self.assertIn("    left out eta: no SKILL.md", result.stdout.splitlines())
        self.assertEqual("", result.stderr)

    def test_supporting_files_come_with_a_skill_and_nothing_is_executable(self):
        self.install.sync()
        self.assertEqual("print(1)\n", (self.install.library / "alpha/scripts/run.py").read_text())
        self.assertEqual("notes\n", (self.install.library / "alpha/references/notes.md").read_text())
        self.assertEqual("MIT, the test's", (self.install.library / "LICENSE.md").read_text())
        for path in self.install.library.rglob("*"):
            if path.is_file():
                self.assertEqual(0, path.stat().st_mode & 0o111, path)

    def test_nothing_but_skills_leaves_the_archive(self):
        self.install.sync()
        everything = sorted(str(p.relative_to(self.install.base)) for p in self.install.base.rglob("*")
                            if "escaped" in p.name or p.is_symlink() or p.name in ("picture.png", "README.md", "hard", "abs"))
        self.assertEqual([], everything)
        self.assertFalse((self.install.library / "Bad_Name").exists())
        self.assertFalse((self.install.library / "docs").exists())
        # the scratch folder it unpacked in is gone too
        self.assertEqual(["gamma", "kdense"], sorted(p.name for p in (self.install.root / "agent/skills").iterdir()))

    def test_every_installed_skill_is_hidden_once_whatever_it_said_before(self):
        self.install.sync()
        for name in ("alpha", "zeta"):
            text = (self.install.library / name / "SKILL.md").read_text()
            front = text.split("---\n")[1]
            self.assertEqual(1, front.count("disable-model-invocation:"), name)
            self.assertTrue(front.endswith("disable-model-invocation: true\n"), front)
        self.assertIn("metadata:\n  version: \"1.0\"\ndisable-model-invocation: true\n---\n\n# alpha\n",
                      (self.install.library / "alpha/SKILL.md").read_text())
        self.assertIn("\n---\n\n# zeta\n", (self.install.library / "zeta/SKILL.md").read_text())

    def test_the_index_has_each_skill_its_description_and_the_words_that_route_it(self):
        self.install.sync()
        index = json.loads((self.install.library / "index.json").read_text())
        self.assertEqual("v1.2.3", index["tag"])
        self.assertEqual([{"name": "alpha", "description": "Does alpha things. Use when asked.",
                           "match": ["alpha", "alfa tool"]},
                          {"name": "zeta", "description": "Folded over two lines.", "match": []}], index["skills"])
        readable = (self.install.library / "INDEX.md").read_text()
        self.assertIn("- `alpha` - Does alpha things.\n", readable)
        self.assertIn("this install's own rules\ndecide, not the skill.", readable)

    def test_a_second_run_downloads_nothing_and_changes_nothing(self):
        self.install.sync()
        before = {p: p.read_bytes() for p in self.install.library.rglob("*") if p.is_file()}
        result = self.install.sync()
        self.assertEqual(["    Test library v1.2.3 already in agent/skills/kdense (2 skills)"], result.stdout.splitlines())
        self.assertEqual(1, self.install.downloads())
        self.assertEqual(before, {p: p.read_bytes() for p in self.install.library.rglob("*") if p.is_file()})

    def test_a_new_install_takes_the_archive_from_the_cache(self):
        self.install.sync()
        shutil.rmtree(self.install.library)
        result = self.install.sync(CURL_FAIL="7")
        self.assertIn("    %s from the tool cache" % ASSET, result.stdout.splitlines())
        self.assertEqual(["alpha", "zeta"], self.install.installed())
        self.assertEqual(1, self.install.downloads())

    def test_a_cached_archive_that_changed_is_not_used(self):
        self.install.sync()
        shutil.rmtree(self.install.library)
        cached = self.install.cache / "kdense-skills" / COMMIT / ASSET
        cached.write_bytes(b"not the archive")
        result = self.install.sync()
        self.assertIn("does not match its checksum - fetching it again", result.stdout)
        self.assertEqual(["alpha", "zeta"], self.install.installed())
        self.assertEqual(2, self.install.downloads())
        self.assertEqual(self.install.sha, hashlib.sha256(cached.read_bytes()).hexdigest())

    def test_force_downloads_and_unpacks_again(self):
        self.install.sync()
        (self.install.library / "alpha/SKILL.md").write_text("edited")
        result = self.install.sync("--force")
        self.assertEqual(2, self.install.downloads())
        self.assertIn("name: alpha", (self.install.library / "alpha/SKILL.md").read_text())
        self.assertIn("-> agent/skills/kdense (2 skills", result.stdout)


class FailureTests(LibraryCase):
    def test_no_network_is_a_warning_and_the_install_goes_on(self):
        result = self.install.sync(CURL_FAIL="6")
        self.assertEqual(0, result.returncode)
        self.assertIn("\033[33m    could not download %s - the skill library is not installed; the next run tries again\033[0m"
                      % ASSET, result.stdout.splitlines())
        self.assertFalse(self.install.library.exists())
        self.assertEqual(["gamma"], sorted(p.name for p in (self.install.root / "agent/skills").iterdir()))

    def test_a_wrong_checksum_installs_nothing_and_caches_nothing(self):
        self.install.write_config(sha256="0" * 64)
        result = self.install.sync()
        self.assertEqual(0, result.returncode)
        self.assertIn("checksum mismatch for %s - the skill library is not installed" % ASSET, result.stdout)
        self.assertFalse(self.install.library.exists())
        self.assertFalse((self.install.cache / "kdense-skills").exists())

    def test_a_failed_update_leaves_the_library_that_was_there(self):
        self.install.sync()
        self.install.write_config(commit="b" * 40)          # a new pin, and no network to fetch it
        result = self.install.sync(CURL_FAIL="6")
        self.assertEqual(0, result.returncode)
        self.assertIn("could not download", result.stdout)
        self.assertEqual(["alpha", "zeta"], self.install.installed())
        self.assertEqual(COMMIT, json.loads((self.install.library / ".elm-pi-library").read_text())["commit"])

    def test_an_archive_that_is_not_one_installs_nothing(self):
        self.install.archive.write_bytes(b"<html>rate limited</html>")
        self.install.write_config(sha256=hashlib.sha256(self.install.archive.read_bytes()).hexdigest())
        result = self.install.sync()
        self.assertEqual(0, result.returncode)
        self.assertIn("could not unpack %s" % ASSET, result.stdout)
        self.assertFalse(self.install.library.exists())

    def test_an_archive_without_a_usable_skill_installs_nothing(self):
        install = Install(Path(self.tmp.name) / "empty", entries=[(TOP + "/README.md", "nothing here", 0o644, "file")])
        result = install.sync()
        self.assertEqual(0, result.returncode)
        self.assertIn("holds no skill this install can use", result.stdout)
        self.assertFalse(install.library.exists())

    def test_a_pin_that_is_not_a_full_hash_is_refused(self):
        self.install.write_config(commit="main")
        result = self.install.sync()
        self.assertEqual(1, result.returncode)
        self.assertIn("commit or sha256 is not a full hash", result.stderr)
        self.assertEqual(0, self.install.downloads())


class ChangeTests(LibraryCase):
    def test_a_changed_exclusion_list_reinstalls_from_the_cache(self):
        self.install.sync()
        self.install.write_config(exclude={"alpha": "now this one"})
        result = self.install.sync(CURL_FAIL="7")
        self.assertEqual(["beta", "zeta"], self.install.installed())
        self.assertIn("left out, as config/skill-library.json says: alpha", result.stdout)
        self.assertEqual(["beta", "zeta"], [s["name"] for s in json.loads((self.install.library / "index.json").read_text())["skills"]])

    def test_a_skill_the_user_adds_later_takes_the_name(self):
        self.install.sync()
        (self.install.root / "agent/skills/alpha").mkdir()
        (self.install.root / "agent/skills/alpha/SKILL.md").write_text("---\nname: alpha\ndescription: mine\n---\n")
        result = self.install.sync()
        self.assertIn("    removed kdense/alpha: this install has its own skill of that name", result.stdout.splitlines())
        self.assertEqual(["zeta"], self.install.installed())
        self.assertEqual(["zeta"], [s["name"] for s in json.loads((self.install.library / "index.json").read_text())["skills"]])
        self.assertEqual(["zeta"], json.loads((self.install.library / ".elm-pi-library").read_text())["skills"])
        self.assertEqual("---\nname: alpha\ndescription: mine\n---\n", (self.install.root / "agent/skills/alpha/SKILL.md").read_text())

    def test_remove_takes_it_out_and_is_quiet_when_there_is_nothing(self):
        self.install.sync()
        result = self.install.run("remove")
        self.assertEqual(["    removed agent/skills/kdense"], result.stdout.splitlines())
        self.assertFalse(self.install.library.exists())
        self.assertTrue((self.install.root / "agent/skills/gamma/SKILL.md").exists())
        self.assertEqual("", self.install.run("remove").stdout)

    def test_pin_prints_what_would_be_fetched(self):
        self.assertEqual(["v1.2.3", COMMIT, "https://example.invalid/lib/archive/%s.tar.gz" % COMMIT, self.install.sha],
                         self.install.run("pin").stdout.splitlines())


class ConfigTests(unittest.TestCase):
    """config/skill-library.json: what the installer is told to fetch."""

    def test_the_pin_is_a_commit_and_a_checksum_not_a_branch(self):
        self.assertRegex(CONFIG["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(CONFIG["sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(CONFIG["tag"], r"^v\d+\.\d+\.\d+$")
        self.assertEqual("https://github.com/K-Dense-AI/scientific-agent-skills", CONFIG["repository"])

    def test_every_exclusion_names_a_skill_and_says_why(self):
        for name, reason in CONFIG["exclude"].items():
            self.assertIn(name, CONFIG["skills"])
            self.assertGreater(len(reason), 20, name)

    def test_routing_words_are_for_skills_that_exist(self):
        for name in [*CONFIG["notRouted"], *CONFIG["aliases"]]:
            self.assertIn(name, CONFIG["skills"])
        self.assertEqual(sorted(CONFIG["skills"]), CONFIG["skills"])
        self.assertEqual(len(set(CONFIG["skills"])), len(CONFIG["skills"]))

    def test_no_library_skill_has_the_name_of_one_of_ours(self):
        ours = {p.parent.name for p in (ROOT / "templates/skills").glob("*/SKILL.md")}
        self.assertEqual(set(), ours & set(CONFIG["skills"]))

    def test_the_docs_give_the_numbers_the_config_has(self):
        kept = len(CONFIG["skills"]) - len(CONFIG["exclude"])
        install = " ".join((ROOT / "INSTALL.md").read_text().split())
        self.assertIn("%s (%s)" % (CONFIG["title"], CONFIG["tag"]), install)
        self.assertIn("%d of its %d skills" % (kept, len(CONFIG["skills"])), install)
        for name in CONFIG["exclude"]:
            self.assertIn("`%s`" % name, install)
        self.assertIn("%dMB" % CONFIG["downloadMB"], (ROOT / "python/elmboot/usage.py").read_text())


def block(text, start, end):
    if text.count(start) != 1:
        raise AssertionError("anchor is not unique: %r" % start)
    i = text.index(start)
    return text[i:text.index(end, i)]


PHASE = block(BOOTSTRAP, "# --- 3b1. the community skill library", "# --- 3c. the agent's Python")
PYTHON_PHASE = """
import sys
sys.path.insert(0, sys.argv[1])
from elmboot import options, skilllibrary
from elmboot.run import Run
import os
chosen = options.Options()
chosen.skill_library = sys.argv[3] == "1"
chosen.force = sys.argv[4] == "1"
run = Run(sys.argv[2], dict(os.environ), chosen)
run.retry = ["--retry", "0"]
skilllibrary.install(run)
"""


@unittest.skipUnless(BASH, "needs bash")
class InstallerPhaseTests(LibraryCase):
    """The phase as each installer runs it: one text, one tree."""

    def setUp(self):
        super().setUp()
        self.other = Install(Path(self.tmp.name) / "second")
        for install in (self.install, self.other):
            (install.root / "scripts").mkdir()
            shutil.copy(SCRIPT, install.root / "scripts/skill_library.py")

    def bash(self, install, wanted=True, force=False, **env):
        script = ("set -euo pipefail\n"
                  "say() { printf '\\n\\033[1m==> %s\\033[0m\\n' \"$*\"; }\n"
                  "warn() { printf '\\033[33m    %s\\033[0m\\n' \"$*\"; }\n"
                  "elm_py() { \"$ELM_PI_PYTHON\" -E -S \"$@\"; }\n"
                  "HERE=\"$PWD\"; ELM_CURL_RETRY=(--retry 0)\n"
                  + "WITH_SKILL_LIBRARY=%d; FORCE=%d\n" % (wanted, force)) + PHASE
        return subprocess.run([BASH, "-c", script], cwd=str(install.root), capture_output=True, text=True,
                              env=install.env(ELM_PI_PYTHON=sys.executable, ELM_PI_TOOL_CACHE=str(install.cache), **env))

    def python(self, install, wanted=True, force=False, **env):
        return subprocess.run([sys.executable, "-E", "-S", "-c", PYTHON_PHASE, str(ROOT / "python"), str(install.root),
                               "1" if wanted else "0", "1" if force else "0"],
                              cwd=str(install.root), capture_output=True, text=True,
                              env=install.env(ELM_PI_PYTHON=sys.executable, ELM_PI_TOOL_CACHE=str(install.cache), **env))

    def tree(self, install):
        return {str(p.relative_to(install.root)): (p.read_bytes() if p.is_file() else None)
                for p in (install.root / "agent").rglob("*")}

    def same(self, **options):
        expected, actual = self.bash(self.install, **options), self.python(self.other, **options)
        self.assertEqual(0, expected.returncode, expected.stderr)
        self.assertEqual((expected.returncode, expected.stdout, expected.stderr),
                         (actual.returncode, actual.stdout, actual.stderr))
        self.assertEqual(self.tree(self.install), self.tree(self.other))
        return expected.stdout

    def test_both_installers_install_it_the_same(self):
        out = self.same()
        self.assertTrue(out.startswith("\n\033[1m==> skill library\033[0m\n    downloading Test library v1.2.3"), out)
        self.assertEqual(["alpha", "zeta"], self.install.installed())
        self.assertIn("already in agent/skills/kdense (2 skills)", self.same())
        self.assertIn("downloading", self.same(force=True))

    def test_both_go_on_without_a_network(self):
        out = self.same(CURL_FAIL="6")
        self.assertIn("could not download", out)
        self.assertFalse(self.install.library.exists())

    def test_no_skill_library_takes_it_out_in_both(self):
        self.same()
        out = self.same(wanted=False)
        self.assertEqual(["", "\033[1m==> skill library\033[0m", "    removed agent/skills/kdense",
                          "    skipped (--no-skill-library): agent/skills/kdense is not installed"], out.splitlines())
        self.assertFalse(self.install.library.exists())
        self.assertNotIn("removed", self.same(wanted=False))

    def test_a_broken_config_is_a_warning_in_both_not_a_failed_install(self):
        for install in (self.install, self.other):
            (install.root / "config/skill-library.json").write_text("{not json")
        out = self.same()
        self.assertIn("\033[33m    the skill library step failed - agent/skills/kdense is as it was\033[0m", out.splitlines())


class InstallerFlagTests(unittest.TestCase):
    """--no-skill-library describes the install, like the other --no-* flags, and can be taken back."""

    def test_the_flag_is_recorded_repeated_and_taken_back_by_both(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import test_bootstrap_python as parity
        case = parity.OptionsTests("test_defaults")
        case.setUp()
        try:
            case.compare(["--no-skill-library"])
            self.assertIn("flags=--no-skill-library\n", case.record(case.base / "python"))
            recorded = lambda root: (root / parity.OPTIONS_FILE).write_text(
                "flags=--no-shim --no-skill-library\ntools=\nbranch=\nrepo=\n")
            case.compare([], start=recorded)
            self.assertIn("flags=--no-shim --no-skill-library\n", case.record(case.base / "python"))
            case.compare(["--with-skill-library"], start=recorded)
            self.assertIn("flags=--no-shim\n", case.record(case.base / "python"))
        finally:
            case.tearDown()

    def test_what_the_flag_decides(self):
        sys.path.insert(0, str(ROOT / "python"))
        from elmboot import options
        self.assertTrue(options.Options().skill_library)
        chosen = options.parse(["--no-skill-library"])
        for flag in chosen.given:
            chosen.apply(flag)
        self.assertFalse(chosen.skill_library)
        apply_flag = block(BOOTSTRAP, "apply_flag() {", "\n}\n") + "\n}\n"
        result = subprocess.run([BASH, "-c", "WITH_SKILL_LIBRARY=1\n" + apply_flag
                                 + 'apply_flag --no-skill-library; echo "$WITH_SKILL_LIBRARY"'],
                                capture_output=True, text=True)
        self.assertEqual("0\n", result.stdout, result.stderr)

    def test_install_sh_passes_both_flags_on(self):
        text = (ROOT / "install.sh").read_text()
        start = text.index("    --no-packages|--no-shim")
        passed = re.split(r"[|\s\\)]+", text[start:text.index("PASS_ARGS+=", start)])
        self.assertIn("--no-skill-library", passed)
        self.assertIn("--with-skill-library", passed)

    def test_the_phase_comes_after_the_skills_it_must_not_shadow(self):
        cli = (ROOT / "python/elmboot/cli.py").read_text()
        self.assertLess(cli.index("agentconfig.refresh(root, run.options, env)"), cli.index("skilllibrary.install(run)"))
        self.assertLess(BOOTSTRAP.index("refreshed agent/skills ("), BOOTSTRAP.index("# --- 3b1. the community skill library"))

    def test_dev_setup_copies_the_pinned_library_or_goes_without(self):
        text = (ROOT / "scripts/dev-setup.sh").read_text()
        self.assertIn('./bootstrap.sh --no-python "${library[@]}" < /dev/null', text)
        self.assertIn("library=(--no-skill-library)", text)
        pinned = subprocess.run([BASH, "-c", re.search(r'^pinned="\$\((.*)\)"$', text, re.M).group(1).replace("$HERE", str(ROOT))],
                                capture_output=True, text=True).stdout.strip()
        self.assertEqual(CONFIG["commit"], pinned)


def cached_archive():
    """The real archive, where a tool cache already has it; never downloaded for a test."""
    home = os.environ.get("ELM_PI_TOOL_CACHE") or os.path.join(
        os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache"), "elm-pi", "tools")
    path = Path(home) / "kdense-skills" / CONFIG["commit"] / ("scientific-agent-skills-%s.tar.gz" % CONFIG["commit"])
    return path if path.is_file() else None


LOADER = """
import { loadSkillsFromDir } from %s;
const { skills, diagnostics } = loadSkillsFromDir({ dir: process.argv[1], source: "user" });
console.log(JSON.stringify({ diagnostics, skills: skills.map((s) => [s.name, s.disableModelInvocation, s.description.length]) }));
"""


@unittest.skipUnless(cached_archive(), "needs the pinned archive in the tool cache (an install with the library has put it there)")
class PinnedLibraryTests(unittest.TestCase):
    """The pinned commit itself, unpacked by the script and read by pi's own loader."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name) / "install"
        (root / "config").mkdir(parents=True)
        shutil.copy(ROOT / "config/skill-library.json", root / "config/skill-library.json")
        shutil.copytree(ROOT / "templates/skills", root / "agent/skills")
        cls.root = root
        cls.result = subprocess.run(
            [sys.executable, "-E", "-S", str(SCRIPT), "--root", str(root), "sync", "--cache",
             str(cached_archive().parents[2]), "--", "false"], capture_output=True, text=True, timeout=300)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_the_archive_is_the_one_the_config_pins(self):
        self.assertEqual(CONFIG["sha256"], hashlib.sha256(cached_archive().read_bytes()).hexdigest())

    def test_it_installs_every_skill_but_the_excluded_ones(self):
        self.assertEqual(0, self.result.returncode, self.result.stderr)
        installed = sorted(p.parent.name for p in (self.root / "agent/skills/kdense").glob("*/SKILL.md"))
        self.assertEqual(sorted(set(CONFIG["skills"]) - set(CONFIG["exclude"])), installed)
        self.assertNotIn("left out ", self.result.stdout.replace("left out, as config", ""))

    def test_no_installed_file_is_a_link_or_executable(self):
        for path in (self.root / "agent/skills/kdense").rglob("*"):
            self.assertFalse(path.is_symlink(), path)
            if path.is_file():
                self.assertEqual(0, path.stat().st_mode & 0o111, path)

    def test_pi_loads_every_skill_hidden_and_without_a_complaint(self):
        node = ROOT / ".node/bin/node"
        loader = ROOT / "node_modules/@earendil-works/pi-coding-agent/dist/core/skills.js"
        if not node.exists() or not loader.exists():
            self.skipTest("needs this clone set up (scripts/dev-setup.sh)")
        result = subprocess.run([str(node), "--input-type=module", "-e", LOADER % json.dumps(str(loader)),
                                 str(self.root / "agent/skills")], capture_output=True, text=True, timeout=120)
        self.assertEqual(0, result.returncode, result.stderr)
        loaded = json.loads(result.stdout)
        self.assertEqual([], loaded["diagnostics"])
        names = [name for name, _, _ in loaded["skills"]]
        ours = sorted(p.parent.name for p in (ROOT / "templates/skills").glob("*/SKILL.md"))
        self.assertEqual(sorted(ours + sorted(set(CONFIG["skills"]) - set(CONFIG["exclude"]))), sorted(names))
        hidden = {name for name, is_hidden, _ in loaded["skills"] if is_hidden}
        self.assertEqual(set(CONFIG["skills"]) - set(CONFIG["exclude"]), hidden - set(ours))
        # What the prompt would have carried had they not been: the reason they are hidden.
        self.assertGreater(sum(size for name, _, size in loaded["skills"] if name not in ours), 50000)


if __name__ == "__main__":
    unittest.main()
