"""Commands colour their output when it goes straight back to pi, and nowhere else.

Each test runs bash the way pi's bash tool does - `bash -c "<prefix>\\n<command>"`
with stdout a pipe - using the shellCommandPrefix from templates/settings.json
and templates/shell/colour.sh as the agent's copy.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "templates/settings.json").read_text())
ESC = "\x1b["


class ColourShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which("git"):     # AlmaLinux and Ubuntu as installed have none
            raise unittest.SkipTest("needs git: the cases colour git's own output")
        cls.dir = Path(tempfile.mkdtemp())
        cls.agent = cls.dir / "agent"
        (cls.agent / "shell").mkdir(parents=True)
        shutil.copy(ROOT / "templates/shell/colour.sh", cls.agent / "shell/colour.sh")
        cls.repo = cls.dir / "repo"
        cls.repo.mkdir()
        (cls.repo / "sub").mkdir()
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.org"]
        subprocess.run(["git", "init", "-q"], cwd=cls.repo, check=True)
        (cls.repo / "fit.py").write_text("slope = 2.4\n")
        subprocess.run(["git", "add", "fit.py"], cwd=cls.repo, check=True)
        subprocess.run([*git, "commit", "-qm", "first"], cwd=cls.repo, check=True)
        (cls.repo / "fit.py").write_text("slope = 2.5\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_bash(self, command, **env):
        script = f"{SETTINGS['shellCommandPrefix']}\n{command}"
        environ = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        # pi's bash inherits the terminal's TERM. GNU ls with no LS_COLORS colours only for a TERM
        # its colour database knows, --color=always included, and a test run may have none or "dumb".
        environ.update({"PI_CODING_AGENT_DIR": str(self.agent), "TERM": "xterm-256color", **env})
        return subprocess.run(["bash", "-c", script], cwd=self.repo, capture_output=True, text=True, env=environ)

    def test_output_straight_to_pi_is_coloured(self):
        for command in ["git diff", "git log -1", "git status", "ls", "grep -n slope fit.py",
                        "diff <(echo a) <(echo b)"]:
            with self.subTest(command=command):
                # The wrappers leave a missing tool alone, and a diff without --color (macOS's,
                # minimal images have none) plain - nothing to colour there.
                if command.startswith("diff") and subprocess.run(
                        "diff --color=always /dev/null /dev/null", shell=True, capture_output=True).returncode:
                    self.skipTest("this diff has no --color")
                self.assertIn(ESC, self.run_bash(command).stdout)

    def test_the_added_flag_is_taken_out_of_a_recursive_diffs_headers_quoted_or_not(self):
        """GNU diffutils 3.10 and later quote an argument holding "=": the header is
        `diff '--color=always' -ruN a/x b/x` on Ubuntu 24.04 and 26.04 (2026-11-16), and the flag
        stayed in what the model read. A stand-in diff prints each spelling, whatever this
        machine's own does."""
        tools = self.dir / "fake-diff"
        tools.mkdir(exist_ok=True)
        for folder in ("a", "b"):
            (self.repo / folder).mkdir(exist_ok=True)
        self.addCleanup(shutil.rmtree, self.repo / "a", True)
        self.addCleanup(shutil.rmtree, self.repo / "b", True)
        for flag in ("'--color=always'", "--color=always"):
            with self.subTest(flag=flag):
                fake = tools / "diff"
                fake.write_text("#!/bin/sh\n"
                                "[ \"$2\" = /dev/null ] && exit 0\n"            # the wrapper's probe
                                "printf '%s\\n' \"diff " + flag + " -ruN a/one.txt b/one.txt\"\n"
                                "printf '\\033[1m--- a/one.txt\\033[0m\\n'\n"
                                "printf '%s\\n' \"+keep " + flag + " in a changed line\"\n"
                                "exit 1\n")
                fake.chmod(0o755)
                run = self.run_bash("diff -ruN a b; echo \"status $?\"",
                                    PATH=f"{tools}{os.pathsep}{os.environ['PATH']}")
                lines = run.stdout.splitlines()
                self.assertEqual("diff -ruN a/one.txt b/one.txt", lines[0], run.stderr)
                self.assertIn(ESC, lines[1])                                     # still coloured
                self.assertEqual(f"+keep {flag} in a changed line", lines[2])    # only diff's own line
                self.assertEqual("status 1", lines[3])                           # and diff's own status

    def test_a_list_of_files_from_grep_is_never_coloured(self):
        """GNU grep colours the names `grep -l` prints; macOS's does not. A stand-in grep that
        colours whenever it is asked to shows what the wrapper asked for."""
        tools = self.dir / "fake-grep"
        tools.mkdir(exist_ok=True)
        fake = tools / "grep"
        fake.write_text("#!/bin/sh\ncase \"$1\" in --color=always) printf '\\033[35mASKED\\033[m\\n' ;; "
                        "*) echo plain ;; esac\n")
        fake.chmod(0o755)
        path = f"{tools}{os.pathsep}{os.environ['PATH']}"
        for command in ("grep -rl slope .", "grep -l slope fit.py", "grep -L slope fit.py", "grep -rIl slope .",
                        "grep --files-with-matches slope fit.py", "grep --files-without-match slope fit.py"):
            with self.subTest(command=command):
                self.assertEqual("plain\n", self.run_bash(command, PATH=path).stdout)
        for command in ("grep -n slope fit.py", "grep -rn slope .", "grep --line-number slope fit.py",
                        "grep slope -- -l", "grep -n -- -l fit.py"):
            with self.subTest(command=command):
                self.assertIn("ASKED", self.run_bash(command, PATH=path).stdout)

    def test_pipes_files_and_substitutions_stay_plain(self):
        run = self.run_bash("git diff > patch; cat patch; git diff | cat; x=$(git diff); echo \"$x\"; "
                            "ls | cat; grep slope fit.py | cat; { git diff; } 2>&1 | cat")
        self.assertIn("+slope = 2.5", run.stdout)
        self.assertNotIn(ESC, run.stdout)
        self.assertNotIn(ESC, (self.repo / "patch").read_text())
        (self.repo / "patch").unlink()

    def test_a_pipe_still_matches_what_it_matched_before(self):
        run = self.run_bash("git diff | grep -c '^+slope'")
        self.assertEqual("1", run.stdout.strip())

    def test_exit_status_and_explicit_flags_are_kept(self):
        self.assertEqual(1, self.run_bash("grep nothing-here fit.py").returncode)
        self.assertEqual(3, self.run_bash("git diff >/dev/null; exit 3").returncode)
        self.assertNotIn(ESC, self.run_bash("grep --color=never slope fit.py").stdout)

    def test_git_that_runs_hooks_gets_no_colour(self):
        # -c settings reach hooks through GIT_CONFIG_PARAMETERS; a hook parsing git must see none.
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\necho \"params=[$GIT_CONFIG_PARAMETERS]\"\n")
        hook.chmod(0o755)
        try:
            run = self.run_bash("git -c user.name=t -c user.email=t@example.org commit -qam second && git reset -q HEAD~1")
            self.assertIn("params=[", run.stderr)          # git sends a hook's output to stderr
            self.assertNotIn("color", run.stderr)
        finally:
            hook.unlink()

    def test_scripts_do_not_see_the_wrappers(self):
        run = self.run_bash("bash -c 'git diff'; type -t git")
        self.assertNotIn(ESC, run.stdout.split("function")[0])
        self.assertTrue(run.stdout.strip().endswith("function"))

    def test_missing_tools_get_no_wrapper_and_no_color_turns_it_off(self):
        run = self.run_bash("type -t no-such-tool-xyz || echo absent")
        self.assertEqual("absent", run.stdout.strip())
        self.assertNotIn(ESC, self.run_bash("git diff; ls", NO_COLOR="1").stdout)

    def test_the_prefix_is_quiet_and_harmless_without_the_file(self):
        self.assertEqual(("ok\n", ""), (lambda r: (r.stdout, r.stderr))(self.run_bash("echo ok")))
        run = self.run_bash("echo ok; git diff", PI_CODING_AGENT_DIR=str(self.dir / "missing"))
        self.assertEqual("", run.stderr)
        self.assertNotIn(ESC, run.stdout)

    def test_bootstrap_installs_it_and_owns_the_setting(self):
        bootstrap = (ROOT / "bootstrap.bash").read_text()
        self.assertIn("cp templates/shell/colour.sh agent/shell/colour.sh", bootstrap)
        self.assertIn('"shellCommandPrefix",', bootstrap)
        self.assertIn("$PI_CODING_AGENT_DIR/shell/colour.sh", SETTINGS["shellCommandPrefix"])


if __name__ == "__main__":
    unittest.main()
