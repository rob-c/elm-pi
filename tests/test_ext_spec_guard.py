"""templates/extensions/spec-guard.ts: code to be written from a document has its tests written first, by a sub-agent.

The sessions: the treadmill of 2026-11-16, "write the parser FORMAT.md describes", 36 runs of which
26 passed their hidden check. Each read FORMAT.md once, wrote the parser and checked it with cases
from the same reading. Two guards that acted after the code existed made no difference; refusing the
first write until a sub-agent had written test_spec.py from the document alone did.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

REQUEST = ("Write the parser FORMAT.md describes in runlog.py: parse_line(line) returning (seconds, level, fields), "
           "and parse_lines(lines) returning (records, n_invalid) where records is the list of those tuples.")

HELPERS = """
const say = async (text, source = "rpc") => { for (const h of registered.handlers.input) await h({ type: "input", text, source }, ctx); };
const call = async (tool, path) =>
  (await registered.handlers.tool_call[0]({ toolName: tool, toolCallId: "c", input: { path } }, ctx)) ?? null;
"""


class SpecGuardTests(unittest.TestCase):
    def run_session(self, body, files=None, env=None):
        return run_extension(self, "spec-guard", HELPERS + body, files=files, env=env)

    def calls(self, request, *calls, files=None, env=None):
        """What each tool call got back: None when it went ahead."""
        body = ["await say(%r);" % request, "const got = [];"]
        body += ['got.push(await call("%s", "%s"));' % call for call in calls]
        body.append("out(got);")
        return self.run_session("\n".join(body), files=files, env=env)

    def test_the_first_write_from_a_named_document_is_refused_with_what_to_do_first(self):
        read, seed, write = self.calls(REQUEST, ("read", "FORMAT.md"), ("read", "runlog.py"), ("write", "runlog.py"))
        self.assertIsNone(read)
        self.assertIsNone(seed)
        self.assertTrue(write["block"])
        reason = write["reason"]
        self.assertTrue(reason.startswith("Not written yet: runlog.py is to come from FORMAT.md"), reason)
        self.assertIn("Launch one `subagent` (agent qwen)", reason)
        self.assertIn("read FORMAT.md and nothing else", reason)
        self.assertIn("write test_spec.py with unittest", reason)
        # 2026-11-17: asked for tests of broken forms as well, 25 of 30 passed against 28 of 30 without -
        # the parsers began refusing what the document allows. The brief stays at what each sentence says.
        self.assertNotIn("breaks", reason)
        self.assertNotIn("refuse", reason)
        self.assertIn("write runlog.py and run test_spec.py", reason)
        self.assertIn("decide from its words which is wrong, the code or the test", reason)

    def test_it_says_how_to_work_and_gives_no_answer(self):
        # Nothing of the hidden check's cases: no blank lines, comments, clocks or function names.
        reason = self.calls(REQUEST, ("read", "FORMAT.md"), ("write", "runlog.py"))[1]["reason"].lower()
        for word in ("blank", "comment", "#", "invalid", "25", "clock", "parse_", "quote "):
            self.assertNotIn(word, reason)

    def test_refused_once_and_the_next_write_goes_ahead(self):
        # A session that goes on without the tests is not held: the refusal is advice it was given once.
        got = self.calls(REQUEST, ("read", "FORMAT.md"), ("write", "runlog.py"), ("write", "runlog.py"),
                         ("replace", "runlog.py"))
        self.assertEqual([None, True, None, None], [g and g["block"] for g in got])

    def test_with_the_tests_already_there_the_code_is_written(self):
        got = self.calls(REQUEST, ("read", "FORMAT.md"), ("write", "runlog.py"), files={"test_spec.py": "import unittest\n"})
        self.assertEqual([None, None], got)

    def test_writing_the_tests_themselves_is_never_refused(self):
        got = self.calls(REQUEST, ("read", "FORMAT.md"), ("write", "test_spec.py"), ("write", "runlog.py"))
        self.assertEqual([None, None, True], [g and g["block"] for g in got])

    def test_a_document_the_request_does_not_name_is_not_a_specification(self):
        # A README read while fixing a bug is context, not what the code is written from.
        fix = "example.py should print about 2.449 but it prints 0.0. Fix spread()."
        self.assertEqual([None, None], self.calls(fix, ("read", "README.md"), ("replace", "stats.py")))
        self.assertEqual([None, None], self.calls("Tidy the format of runlog.py", ("read", "FORMAT.md"),
                                                  ("write", "runlog.py")))

    def test_the_document_has_to_have_been_read_and_the_file_be_code(self):
        self.assertEqual([None], self.calls(REQUEST, ("write", "runlog.py")))                       # never read it
        self.assertEqual([None, None], self.calls(REQUEST, ("read", "FORMAT.md"), ("write", "NOTES.md")))
        self.assertEqual([None, None], self.calls(REQUEST, ("read", "FORMAT.md"), ("bash", "")))

    def test_the_name_is_matched_as_a_file_name_whatever_its_case_or_folder(self):
        for request, path, refused in (
                ("Implement what docs/spec.txt says in tool.py", "docs/spec.txt", True),
                ("Implement what SPEC.TXT says", "docs/spec.txt", True),
                ("write the parser format.md describes", "FORMAT.md", True),
                ("Implement myformat.md", "format.md", False),             # another file's name
                ("Implement format.mdx", "format.md", False),
                ("Follow the protocol in PROTOCOL.rst.", "PROTOCOL.rst", True)):
            with self.subTest(request=request, path=path):
                got = self.calls(request, ("read", path), ("write", "tool.py"))[1]
                self.assertEqual(refused, got is not None)

    def test_several_documents_are_named(self):
        got = self.calls("Write client.py from API.md and WIRE.md", ("read", "API.md"), ("read", "WIRE.md"),
                         ("write", "client.py"))[2]
        self.assertIn("client.py is to come from API.md and WIRE.md", got["reason"])

    def test_every_writer_this_install_has_is_covered(self):
        # The editor here is replace/replace_match/insert, not pi's builtin edit.
        for tool in ("write", "replace", "replace_match", "insert"):
            with self.subTest(tool=tool):
                self.assertTrue(self.calls(REQUEST, ("read", "FORMAT.md"), (tool, "src/thing.ts"))[1]["block"])

    def test_a_new_request_is_a_new_piece_of_work_and_twice_is_the_most(self):
        got = self.run_session("""
            const seen = [];
            for (let n = 0; n < 3; n++) {
              await say(%r);
              await call("read", "FORMAT.md");
              seen.push((await call("write", "runlog.py")) ? 1 : 0);
            }
            out(seen);
        """ % REQUEST)
        self.assertEqual([1, 1, 0], got)

    def test_a_new_request_forgets_what_the_last_one_read(self):
        got = self.run_session("""
            await say("What does FORMAT.md say about times?");
            await call("read", "FORMAT.md");
            await say("Write runlog.py as FORMAT.md describes");
            out(await call("write", "runlog.py"));
        """)
        self.assertIsNone(got)

    def test_a_notice_from_an_extension_is_not_a_new_request(self):
        # The sub-agent's own completion notice starts a run: the request is still the user's.
        got = self.run_session("""
            await say(%r);
            await call("read", "FORMAT.md");
            await say("a child has finished", "extension");
            out((await call("write", "runlog.py")) !== null);
        """ % REQUEST)
        self.assertTrue(got)

    def test_a_sub_agent_is_given_a_brief_not_the_request(self):
        self.assertEqual([None, None], self.calls(REQUEST, ("read", "FORMAT.md"), ("write", "runlog.py"),
                                                  env={"PI_SUBAGENT_CHILD": "1"}))


if __name__ == "__main__":
    unittest.main()
