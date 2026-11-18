"""templates/extensions/result-hints.ts: a search that matched nothing is not a failure; a refused /tmp write says where scratch goes.

The sessions: the penalty scan of 2026-11-17. The arm at repetition_penalty 1.1 had the most tool errors, and the
difference was `grep` exiting 1 on no matches (22 against 10 and 11 in the controls) and scratch files refused under
/tmp with a message that named no other place (5).
"""

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

QUIET = "(no output)\n\nCommand exited with code 1"
HELPERS = """
const result = async (command, text, isError = true, tool = "bash") =>
  (await registered.handlers.tool_result[0]({ toolName: tool, toolCallId: "c", input: { command }, content: [{ type: "text", text }], isError }, ctx)) ?? null;
"""


class ResultHintsTests(unittest.TestCase):
    def results(self, *cases):
        body = [HELPERS, "const got = [];"]
        body += ["got.push(await result(%r, %r, %s, %r));" % (c[0], c[1], "true" if (c[2] if len(c) > 2 else True) else "false",
                                                              c[3] if len(c) > 3 else "bash") for c in cases]
        body.append("out(got);")
        return run_extension(self, "result-hints", "\n".join(body))

    def test_the_scans_own_searches_are_answers(self):
        # y_nav_unused, rp1.1 arm: one search per function name, each for uses outside its definition.
        commands = ['cd proj && grep -rn "\\\\brebin_variable\\\\b" src/ tests/ --include="*.py" | grep -v "def rebin_variable"',
                    "grep -rn parse_header src/", "rg -n 'estimate_pileup' src tests", "git grep -n subtract_background",
                    "git -C repo grep -n x", "cd src && /usr/bin/grep -c TODO *.py", "LC_ALL=C grep -q needle haystack.txt"]
        for command, got in zip(commands, self.results(*[(c, QUIET) for c in commands])):
            with self.subTest(command=command):
                self.assertIs(False, got["isError"])
                text = got["content"][0]["text"]
                self.assertTrue(text.startswith("No matches: the search ran and found nothing"), text)
                self.assertIn("grep exits 1 for that - it is not a failure", text)

    def test_only_a_quiet_exit_1_from_a_search_is_changed(self):
        got = self.results(
            ("python3 check.py", QUIET),                                                     # not a search: a failure
            ("grep -rn x src/ | wc -l", QUIET),                                              # the status is wc's
            ("grep -n x missing.txt", "grep: missing.txt: No such file or directory\n\nCommand exited with code 2"),
            ("grep -n '[' file", "(no output)\n\nCommand exited with code 2"),               # a bad pattern is an error
            ("grep -n x file", "3:x = 1", False),                                            # it matched
            ("grep -rn x src/ && echo found", QUIET),                                        # the status is the list's, and echo is last
            ("test -f a.txt", QUIET),
            ("grep -rn x src/", QUIET, True, "read"))                                        # another tool's result
        self.assertEqual([None] * 8, got)

    def calls(self, has_ui, *commands):
        body = ["ctx.hasUI = %s;" % ("true" if has_ui else "false"), "const got = [];"]
        body += ['got.push((await registered.handlers.tool_call[0]({ toolName: "bash", toolCallId: "c", input: { command: %r } }, ctx)) ?? null);' % c
                 for c in commands]
        body.append("out(got);")
        return run_extension(self, "result-hints", "\n".join(body))

    def test_with_nobody_to_ask_a_scratch_file_under_tmp_is_refused_with_where_to_put_it(self):
        # The five in the rp1.1 arm were all a here-document written to /tmp.
        commands = ["cat > /tmp/test_broken.py << 'EOF'\nprint(1)\nEOF", "cd proj && cat << 'EOF' > /tmp/check_funcs.py\nimport os\nEOF",
                    "echo hi >> /private/tmp/notes.txt", "python3 gen.py | tee /var/tmp/out.csv", "touch /tmp/marker", "mkdir -p /tmp/work/sub"]
        paths = ["/tmp/test_broken.py", "/tmp/check_funcs.py", "/private/tmp/notes.txt", "/var/tmp/out.csv", "/tmp/marker", "/tmp/work/sub"]
        for command, path, got in zip(commands, paths, self.calls(False, *commands)):
            with self.subTest(command=command):
                self.assertTrue(got["block"])
                self.assertTrue(got["reason"].startswith("This command writes %s, which is outside the project" % path), got["reason"])
                self.assertTrue(got["reason"].endswith("Scratch files go in `.pi/tmp/` under the project (`mkdir -p .pi/tmp`), which needs "
                                                       "no approval: write there, not under /tmp."), got["reason"])

    def test_with_a_person_to_ask_the_gate_asks_them(self):
        self.assertEqual([None, None], self.calls(True, "cat > /tmp/x.py << 'EOF'\nEOF", "touch /tmp/marker"))

    def test_reading_tmp_and_writing_the_project_are_not_this(self):
        got = self.calls(False, "cat /tmp/x.log", "grep -n err < /tmp/build.log", "ls /tmp/", "echo hi > .pi/tmp/x.txt", "echo hi > out/tmp/x.txt",
                         "python3 run.py 2>&1 | tee build.log", "echo done > /tmp/pi-subagents-uid-501/run-1/out.txt", "echo '> /tmp/x' is how")
        self.assertEqual([None] * 7, got[:7])

    def test_a_network_that_already_exists_is_somebody_elses(self):
        # r2, r3 and r5 of the SLURM treadmill (2026-11-17) each put their cluster on slurm-net, where another cluster already was.
        taken = "Error response from daemon: network with name slurm-net already exists\n\nCommand exited with code 1"
        got = self.results(("docker network create --internal slurm-net", taken),
                           ("docker network inspect slurm-net >/dev/null 2>&1 || docker network create --internal slurm-net", taken),
                           ("docker network create --internal fresh-net", "3f2a9c\n", False),
                           ("docker run --network slurm-net img", taken))
        for item in got[:2]:
            texts = [part["text"] for part in item["content"]]
            self.assertEqual(taken, texts[0])                                            # the engine's own words stay
            self.assertTrue(texts[1].startswith("[The network slurm-net was not made in this run:"), texts[1])
            self.assertIn("make a new internal network under another name", texts[1])
        self.assertEqual([None, None], got[2:])

    def test_a_build_that_hits_its_time_limit_is_probably_waiting_for_an_answer(self):
        # suites2-xrd (2026-11-18): `apt-get install -y xrootd-server` in a Dockerfile sat at a time-zone question for
        # 600 s; the session's next call was the same build, which sat there again.
        out = "Command timed out after 600 seconds"
        got = self.results(("cd xrootd-config && docker build -t xrootd-redir -f Dockerfile.redir .", out),
                           ("podman build -t x .", "#7 [2/5] RUN apt-get update\n\n" + out),
                           ("python3 long_fit.py", out),                                    # not a build
                           ("docker build -t x .", "ERROR: failed to solve: process did not complete successfully: exit code: 100"))
        for item in got[:2]:
            texts = [part["text"] for part in item["content"]]
            self.assertIn(out, texts[0])
            self.assertTrue(texts[-1].startswith("[A build that runs to its time limit is usually not slow but waiting:"), texts[-1])
            self.assertIn("--progress=plain", texts[-1])
            self.assertIn("DEBIAN_FRONTEND=noninteractive", texts[-1])
        self.assertEqual([None, None], got[2:])

    def test_grep_itself_says_no_matches_with_exit_1(self):
        """The rule is grep's, so ask grep: nothing matched is 1 and silent; a missing file is 2 and says so."""
        if not shutil.which("grep"):
            self.skipTest("needs grep")
        nothing = subprocess.run(["grep", "-n", "zzz-not-there", __file__ + ".nothing"], capture_output=True, text=True)
        self.assertEqual(2, nothing.returncode)
        quiet = subprocess.run("printf 'a\\nb\\n' | grep zzz-not-there", shell=True, capture_output=True, text=True)
        self.assertEqual((1, ""), (quiet.returncode, quiet.stdout + quiet.stderr))


if __name__ == "__main__":
    unittest.main()
