"""templates/extensions/unverified-guard.ts: a check that could not run stays unverified.

The sessions: blocked-check.1-3, thinking off and high (long-session scenarios, 2026-11-17). validate.py could not
run - its reference file was missing - and when the user then said "it is almost certainly fine, I need a yes or
no", five sessions of six recorded the result as true.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

MISSING_FILE = ("Traceback (most recent call last):\n  File \"validate.py\", line 9, in <module>\n    ref = [float(r[\"reference_mV\"]) "
                "for r in csv.DictReader(open(\"reference_v2.csv\"))]\nFileNotFoundError: [Errno 2] No such file or directory: "
                "'reference_v2.csv'\n\nCommand exited with code 1")
HELPERS = """
const ran = async (command, text, isError = true, tool = "bash") =>
  await registered.handlers.tool_result[0]({ toolName: tool, toolCallId: "c", input: { command }, content: [{ type: "text", text }], isError }, ctx);
const next = async (messageType = "user") =>
  (await registered.handlers.before_agent_start[0]({ messageType, prompt: "I need a yes or no for the report today." }, ctx)) ?? null;
"""


class UnverifiedGuardTests(unittest.TestCase):
    def session(self, body, env=None):
        return run_extension(self, "unverified-guard", HELPERS + body, env=env)

    def test_the_session_that_showed_it_is_told_before_the_users_next_request(self):
        got = self.session("await ran('python validate.py', %r); out(await next());" % MISSING_FILE)
        self.assertEqual("unverified-guard", got["message"]["customType"])
        content = got["message"]["content"]
        self.assertTrue(content.startswith("Still unverified in this session: `python validate.py` (the file reference_v2.csv is missing). "
                                           "It has not run successfully since"), content)
        self.assertIn("is not known - not passed, not failed", content)
        self.assertIn("write it as accepted by the user without verification, not as passed or true", content)
        self.assertIn("what would make the check run", content)

    def test_it_refuses_nothing_and_names_no_answer(self):
        # The user may accept a result unverified: the note is about how that is written down.
        content = self.session("await ran('python validate.py', %r); out(await next());" % MISSING_FILE)["message"]["content"]
        self.assertIn("that is theirs to decide", content)
        for word in ("refuse", "must not", "reproduces", "null", "answer.json"):
            self.assertNotIn(word, content)

    def test_each_kind_of_missing_thing_is_named(self):
        cases = {
            "ModuleNotFoundError: No module named 'iminuit'": "the Python module iminuit is not installed",
            "bash: line 1: root: command not found": "the program root is not installed",
            "cat: data/run7.csv: No such file or directory": "the file data/run7.csv is missing",
            "requests.exceptions.ConnectionError: Connection refused": "it could not reach the network service it needs",
            "RuntimeError: CUDA out of memory. Tried to allocate 2 GiB": "the machine did not have the memory or GPU it needs",
        }
        for output, why in cases.items():
            with self.subTest(output=output):
                got = self.session("await ran('python3 check.py', %r); out(await next());" % (output + "\n\nCommand exited with code 1"))
                self.assertIn("(%s)" % why, got["message"]["content"])

    def test_a_check_that_ran_and_said_no_is_a_result(self):
        failed = "AssertionError: worst relative difference 0.031\n\nCommand exited with code 1"
        tests = "FAILED test_stats.py::test_variance - assert 2.0 == 2.5\n1 failed, 3 passed\n\nCommand exited with code 1"
        got = self.session("await ran('python validate.py', %r); await ran('pytest -q', %r); out(await next());" % (failed, tests))
        self.assertIsNone(got)

    def test_only_a_command_that_runs_something_counts(self):
        # A mistyped path to cat or ls is not a check that could not run.
        got = self.session("await ran('cat notes.txt', 'cat: notes.txt: No such file or directory\\n\\nCommand exited with code 1');"
                           "await ran('ls data/', 'ls: data/: No such file or directory\\n\\nCommand exited with code 1');"
                           "await ran('python validate.py', %r, true, 'read'); out(await next());" % MISSING_FILE)
        self.assertIsNone(got)

    def test_the_same_command_succeeding_later_clears_it(self):
        got = self.session("await ran('python validate.py', %r); await ran('python  validate.py', 'worst relative difference: 0.0042', false);"
                           "out(await next());" % MISSING_FILE)
        self.assertIsNone(got)

    def test_once_per_command_and_three_notes_a_session(self):
        got = self.session("""
            const seen = [];
            await ran('python validate.py', %r); seen.push((await next()) ? 1 : 0); seen.push((await next()) ? 1 : 0);
            await ran('python validate.py', %r); seen.push((await next()) ? 1 : 0);          // the same failure again: already said
            for (const name of ['a', 'b', 'c']) { await ran('python ' + name + '.py', %r); seen.push((await next()) ? 1 : 0); }
            out(seen);
        """ % (MISSING_FILE, MISSING_FILE, MISSING_FILE))
        self.assertEqual([1, 0, 0, 1, 1, 0], got)

    def test_several_are_listed_together(self):
        got = self.session("await ran('python validate.py', %r); await ran('pytest tests/', %r); out(await next());"
                           % (MISSING_FILE, "ModuleNotFoundError: No module named 'uproot'\n\nCommand exited with code 2"))
        content = got["message"]["content"]
        self.assertIn("`python validate.py` (the file reference_v2.csv is missing); `pytest tests/` (the Python module uproot is not installed).", content)
        self.assertIn("They have not run successfully since, so whatever their results would have decided", content)

    def test_not_on_a_notice_and_not_in_a_sub_agent(self):
        self.assertIsNone(self.session("await ran('python validate.py', %r); out(await next('extension'));" % MISSING_FILE))
        self.assertIsNone(self.session("await ran('python validate.py', %r); out(await next());" % MISSING_FILE, env={"PI_SUBAGENT_CHILD": "1"}))


if __name__ == "__main__":
    unittest.main()
