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
        environ.update({"PI_CODING_AGENT_DIR": str(self.agent), **env})
        return subprocess.run(["bash", "-c", script], cwd=self.repo, capture_output=True, text=True, env=environ)

    def test_output_straight_to_pi_is_coloured(self):
        for command in ["git diff", "git log -1", "git status", "ls", "grep -n slope fit.py",
                        "diff <(echo a) <(echo b)"]:
            with self.subTest(command=command):
                self.assertIn(ESC, self.run_bash(command).stdout)

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
        bootstrap = (ROOT / "bootstrap.sh").read_text()
        self.assertIn("cp templates/shell/colour.sh agent/shell/colour.sh", bootstrap)
        self.assertIn('"shellCommandPrefix",', bootstrap)
        self.assertIn("$PI_CODING_AGENT_DIR/shell/colour.sh", SETTINGS["shellCommandPrefix"])


if __name__ == "__main__":
    unittest.main()
