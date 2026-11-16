"""templates/extensions/verify-guard.ts: a turn that wrote code and ran nothing is sent back once.

The session: the 200-problem batch of 2026-11-14 (ten sessions of twenty stock coding problems).
c20.6 and c20.7 wrote all twenty files and executed none, replying "Done." after each; the other
eight ran one python3 -c check per file. Nothing failed, so it is the only defect the batch showed
in sessions that passed.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

# One run: the calls given, then the settle that ends it. `step` is a helper inside the snippet.
HELPERS = """
const start = async () => { await registered.handlers.agent_start[0]({}, ctx); };
const call = async (tool, path, ok) => {
  const handlers = registered.handlers;
  await handlers.tool_call[0]({ toolName: tool, toolCallId: "c", input: { path, anchor: "abcde" } }, ctx);
  await handlers.tool_result[0]({ toolName: tool, isError: !ok }, ctx);
};
const settle = async () => await registered.handlers.agent_before_settle[0]({}, ctx);
"""


class VerifyGuardTests(unittest.TestCase):
    def settle(self, *calls):
        body = [HELPERS, "await start();"]
        for tool, path, ok in calls:
            body.append(f'await call("{tool}", "{path}", {str(ok).lower()});')
        body.append("out((await settle()) ?? null);")
        return run_extension(self, "verify-guard", "\n".join(body))

    def test_a_python_file_written_and_never_run_is_sent_back(self):
        got = self.settle(("write", "solutions/p07.py", True))
        self.assertTrue(got["continue"])
        self.assertEqual("verify-guard", got["entries"][0]["customType"])
        content = got["entries"][0]["content"]
        self.assertIn("wrote 1 code file and ran nothing", content)
        self.assertIn("report what it printed", content)

    def test_a_file_written_then_run_is_left_alone(self):
        self.assertIsNone(self.settle(("write", "solutions/p07.py", True), ("bash", "", True)))

    def test_a_run_that_failed_is_a_run_that_tried(self):
        # A failing command is evidence, not silence: the note would be wrong and the reply can be true.
        self.assertIsNone(self.settle(("write", "solutions/p07.py", True), ("bash", "", False)))

    def test_writing_prose_or_data_is_not_this_guards_business(self):
        self.assertIsNone(self.settle(("write", "README.md", True), ("write", "counts.csv", True)))

    def test_a_refused_or_failed_write_changes_nothing(self):
        self.assertIsNone(self.settle(("write", "solutions/p07.py", False)))

    def test_a_launched_child_may_run_it(self):
        self.assertIsNone(self.settle(("write", "solutions/p07.py", True), ("subagent", "", True)))

    def test_every_writer_this_install_has_counts(self):
        # The editor here is replace/replace_match/insert, not pi's builtin edit.
        for tool in ("write", "replace", "replace_match", "insert"):
            with self.subTest(tool=tool):
                self.assertIsNotNone(self.settle((tool, "src/thing.ts", True)), f"{tool} of a .ts file")

    def test_at_most_two_notes_a_session(self):
        body = [HELPERS, "const seen = [];"]
        for _ in range(3):
            body += ["await start();", 'await call("write", "a.py", true);',
                     "seen.push((await settle()) ? 1 : 0);"]
        body.append("out(seen);")
        self.assertEqual([1, 1, 0], run_extension(self, "verify-guard", "\n".join(body)))


if __name__ == "__main__":
    unittest.main()
