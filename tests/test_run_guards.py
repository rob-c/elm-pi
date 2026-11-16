"""repeat-guard.ts and ultracode-note.ts, run under node with a stub pi.

repeat-guard: a turn whose tool calls all fail, the same calls with the same
errors as the turn before, counts one more; at WARN_AT the model gets one note,
at STOP_AT the run is aborted. Anything else starts the count again, and a turn
that ended on a gateway error is passed over.

ultracode-note: while `workflow` is not an active tool, the block pi-dynamic-
workflows appends to a user message is replaced in what the model is sent; with
the tool active nothing changes.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.extension_harness import run_extension

ROOT = Path(__file__).resolve().parents[1]
REPEAT = ROOT / "templates/extensions/repeat-guard.ts"
ULTRA = ROOT / "templates/extensions/ultracode-note.ts"
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def package_source(name):
    """A file of an installed package, from an elm-pi install next to this checkout or the default prefix."""
    for root in (ROOT, Path.home() / ".local/share/elm-pi", Path.home() / "sandbox/elm-pi-test"):
        path = root / "agent/npm/node_modules" / name
        if path.is_file():
            return path.read_text()
    return None


RUNNER = r"""
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
const [repeatPath, ultraPath, casesPath] = process.argv.slice(1);
const cases = JSON.parse(readFileSync(casesPath, "utf8"));
const repeat = await import(pathToFileURL(repeatPath).href);
const ultra = await import(pathToFileURL(ultraPath).href);

function load(mod, active = []) {
  const h = {};
  mod.default({ on: (name, fn) => { h[name] = fn; }, getActiveTools: () => active });
  return h;
}

const out = { warnAt: repeat.WARN_AT, stopAt: repeat.STOP_AT, runs: {}, ultra: {}, note: ultra.NOTE };
const call = (name, args) => ({ type: "toolCall", id: "c", name, arguments: args });
const result = (name, text, isError) => ({ role: "toolResult", toolName: name, isError, content: [{ type: "text", text }] });
// a turn: [kind, tool, args, error-text]; kind "fail", "ok", "error" (gateway), "text" (no calls)
for (const [id, turns] of Object.entries(cases.repeat)) {
  const h = load(repeat);
  await h.agent_start({ type: "agent_start" }, {});
  const log = [];
  for (const [kind, tool, args, text] of turns) {
    let aborted = false;
    const ctx = { abort: () => { aborted = true; }, hasUI: true };
    const message = kind === "error"
      ? { role: "assistant", stopReason: "error", content: [] }
      : kind === "text"
        ? { role: "assistant", stopReason: "stop", content: [{ type: "text", text: "done" }] }
        : { role: "assistant", stopReason: "toolUse", content: [call(tool, args)] };
    const results = kind === "fail" ? [result(tool, text, true)] : kind === "ok" ? [result(tool, text, false)] : [];
    const r = (await h.turn_end({ type: "turn_end", message, toolResults: results }, ctx)) ?? null;
    log.push({ note: r ? r.entries[0].content : null, aborted });
  }
  out.runs[id] = log;
}
for (const [id, [active, messages]] of Object.entries(cases.ultra)) {
  const h = load(ultra, active);
  const r = h.context({ type: "context", messages });
  out.ultra[id] = r ? r.messages : null;
}
console.log(JSON.stringify(out));
"""

NOT_FOUND = "Tool subagent not found"
STATUS = ("subagent", {"action": "status", "id": "fe891a35"})


# An ordinary failing command: the same-call-in-a-row rule. A tool the session lacks is counted apart.
RUN = ("bash", {"command": "node x.mjs"}, "Error: Cannot find module 'x'\n\nCommand exited with code 1")


def fails(n, tool=RUN[0], args=RUN[1], text=RUN[2]):
    return [["fail", tool, args, text]] * n


REPEAT_CASES = {
    # test4's loop, as it was: the same status call, the same "not found"
    "the_test4_loop": fails(10, *STATUS, NOT_FOUND),
    "two_failures_say_nothing": fails(2),
    "a_success_between_starts_again": fails(2) + [["ok", "bash", {"command": "ls"}, "a.txt"]] + fails(2),
    "a_different_call_starts_again": fails(2) + fails(1, args={"command": "node y.mjs"}) + fails(2),
    "a_different_error_starts_again": fails(2) + fails(1, text="Error: out of memory") + fails(2),
    "a_reply_without_calls_starts_again": fails(2) + [["text", None, None, None]] + fails(2),
    # a 429 that outlasted the retries made no call: it neither counts nor resets
    "a_gateway_error_is_passed_over": fails(2) + [["error", None, None, None]] + fails(1),
    "a_failing_test_between_edits_is_not_a_repeat": [
        ["fail", "bash", {"command": "pytest"}, "1 failed"], ["ok", "replace", {"path": "a.py"}, "ok"],
        ["fail", "bash", {"command": "pytest"}, "1 failed"], ["ok", "replace", {"path": "a.py"}, "ok"],
        ["fail", "bash", {"command": "pytest"}, "1 failed"], ["ok", "replace", {"path": "a.py"}, "ok"],
        ["fail", "bash", {"command": "pytest"}, "1 failed"],
    ],
    # test5: a child alternated two different calls to the tool it did not have
    "a_missing_tool_with_changing_arguments": [
        ["fail", "subagent", {"action": "status", "id": "r"}, NOT_FOUND],
        ["fail", "subagent", {"action": "status", "id": "r"}, NOT_FOUND],
        ["fail", "subagent", {"action": "children.list"}, NOT_FOUND],
        ["ok", "bash", {"command": "ls"}, "a.txt"],
        ["fail", "subagent", {"action": "children.list"}, NOT_FOUND],
        ["fail", "subagent", {"action": "status", "id": "r"}, NOT_FOUND],
        ["fail", "subagent", {"action": "status", "id": "r"}, NOT_FOUND],
        ["fail", "subagent", {"action": "status", "id": "r"}, NOT_FOUND],
        ["fail", "subagent", {"action": "status", "id": "r"}, NOT_FOUND],
    ],
    "a_failing_bash_command_repeated": fails(8, tool="bash", args={"command": "node x.mjs"},
                                           text="Error: Cannot find module 'x'\n\nCommand exited with code 1"),
}

ARMED_TAIL = ("\n\n---\n[workflows mode armed. Decide first: if this message is a question ...\n"
              "handle it by calling the `workflow` tool: write a script\n...]\n\n"
              "Effort: ULTRA. Be exhaustive — fan out widely ... skip the workflow and just respond directly.")
ASK = "I want to use 5 workers in parallel to make a small framework"
ULTRA_CASES = {
    "string_content_without_the_tool": [[], [{"role": "user", "content": ASK + ARMED_TAIL}]],
    "part_content_without_the_tool": [["read", "subagent"],
                                      [{"role": "user", "content": [{"type": "text", "text": ASK + ARMED_TAIL}]}]],
    "with_the_tool_nothing_changes": [["read", "workflow"], [{"role": "user", "content": ASK + ARMED_TAIL}]],
    "an_unarmed_message_is_left_alone": [[], [{"role": "user", "content": ASK}]],
    "only_user_messages_are_touched": [[], [{"role": "assistant", "content": [{"type": "text", "text": ASK + ARMED_TAIL}]}]],
    "every_armed_message_and_only_those": [[], [{"role": "user", "content": ASK + ARMED_TAIL},
                                                {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
                                                {"role": "user", "content": "thanks"},
                                                {"role": "user", "content": "now the docs" + ARMED_TAIL}]],
}


class RunGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binary = node()
        if not binary:
            raise unittest.SkipTest("needs node")
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            for src in (REPEAT, ULTRA):
                (cls.tmp / src.name).write_text(src.read_text())
            (cls.tmp / "cases.json").write_text(json.dumps({"repeat": REPEAT_CASES, "ultra": ULTRA_CASES}))
            run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", RUNNER,
                                  str(cls.tmp / REPEAT.name), str(cls.tmp / ULTRA.name), str(cls.tmp / "cases.json")],
                                 capture_output=True, text=True, cwd=cls.tmp, timeout=120,
                                 env={"PATH": "/usr/bin:/bin", "HOME": str(cls.tmp)})
            if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
                raise unittest.SkipTest("this node cannot load TypeScript")
            if run.returncode != 0:
                raise AssertionError(run.stderr[-3000:])
            cls.out = json.loads(run.stdout)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def notes(self, case):
        return [i + 1 for i, turn in enumerate(self.out["runs"][case]) if turn["note"]]

    def aborts(self, case):
        return [i + 1 for i, turn in enumerate(self.out["runs"][case]) if turn["aborted"]]

    # --- repeat-guard ---------------------------------------------------------------

    def test_the_test4_loop_is_warned_once_then_stopped(self):
        warn, stop = self.out["warnAt"], self.out["stopAt"]
        self.assertEqual((3, 8), (warn, stop))
        self.assertEqual([warn, stop, stop + 1, stop + 2], self.notes("the_test4_loop"))
        self.assertEqual([stop, stop + 1, stop + 2], self.aborts("the_test4_loop"))

    def test_the_warning_says_what_failed_and_whose_the_call_is(self):
        note = self.out["runs"]["the_test4_loop"][2]["note"]
        self.assertIn("The same `subagent` call has now failed 3 times in a row", note)
        self.assertIn(NOT_FOUND, note)
        self.assertIn("not in this session", note)
        self.assertIn("belongs to whoever made it, not to you", note)
        self.assertIn("give your final report now", note)

    def test_the_stop_says_why(self):
        note = self.out["runs"]["the_test4_loop"][7]["note"]
        self.assertIn("elm-pi stopped this run: the same `subagent` call failed 8 times in a row", note)

    def test_anything_else_starts_the_count_again(self):
        for case in ("two_failures_say_nothing", "a_success_between_starts_again", "a_different_call_starts_again",
                     "a_different_error_starts_again", "a_reply_without_calls_starts_again",
                     "a_failing_test_between_edits_is_not_a_repeat"):
            with self.subTest(case=case):
                self.assertEqual([], self.notes(case))
                self.assertEqual([], self.aborts(case))

    def test_a_gateway_error_neither_counts_nor_resets(self):
        self.assertEqual([4], self.notes("a_gateway_error_is_passed_over"))

    def test_a_missing_tool_is_counted_by_name_through_anything_between(self):
        # 3rd and 8th call to the missing tool: turns 3 and 9 (a successful ls came between)
        self.assertEqual([3, 9], self.notes("a_missing_tool_with_changing_arguments"))
        self.assertEqual([9], self.aborts("a_missing_tool_with_changing_arguments"))
        self.assertIn("not in this session", self.out["runs"]["a_missing_tool_with_changing_arguments"][2]["note"])

    def test_a_failing_command_repeated_is_caught_too(self):
        self.assertEqual([3, 8], self.notes("a_failing_bash_command_repeated"))
        note = self.out["runs"]["a_failing_bash_command_repeated"][2]["note"]
        self.assertIn("Cannot find module 'x'", note)
        self.assertNotIn("not in this session", note)

    # --- ultracode-note ---------------------------------------------------------------

    def content(self, case, i=0):
        message = self.out["ultra"][case][i]
        c = message["content"]
        return c if isinstance(c, str) else c[0]["text"]

    def test_without_the_tool_the_block_becomes_one_line(self):
        for case in ("string_content_without_the_tool", "part_content_without_the_tool"):
            with self.subTest(case=case):
                text = self.content(case)
                self.assertEqual(f"{ASK}\n\n{self.out['note']}", text)
                self.assertNotIn("workflows mode armed", text)
                self.assertNotIn("Effort: ULTRA", text)

    def test_the_line_says_what_to_do_instead(self):
        note = self.out["note"]
        self.assertIn("no `workflow` tool", note)
        self.assertIn("`pi --no-workflows`", note)
        self.assertIn('`subagent({ workflow: "parallel", args: { tasks } })`', note)
        self.assertIn("no `workflow-check`", note)

    def test_nothing_changes_with_the_tool_or_without_the_block(self):
        for case in ("with_the_tool_nothing_changes", "an_unarmed_message_is_left_alone", "only_user_messages_are_touched"):
            with self.subTest(case=case):
                self.assertIsNone(self.out["ultra"][case])

    def test_every_armed_user_message_and_only_those(self):
        messages = self.out["ultra"]["every_armed_message_and_only_those"]
        self.assertEqual([f"{ASK}\n\n{self.out['note']}", "ok", "thanks", f"now the docs\n\n{self.out['note']}"],
                         [m["content"] if isinstance(m["content"], str) else m["content"][0]["text"] for m in messages])

    # --- both loaded everywhere --------------------------------------------------------

    def test_both_are_required_and_the_guard_is_in_fast(self):
        self.assertIn("repeat-guard.ts", CONFIG["requiredExtensions"])
        self.assertIn("ultracode-note.ts", CONFIG["requiredExtensions"])
        self.assertIn(" claim-guard repeat-guard server-reaper report-guard date-note; do", (ROOT / "pi.bash").read_text())


class PackageTextTests(unittest.TestCase):
    """The pi-dynamic-workflows text the extensions and docs rely on, against the installed package:
    an update that rewords it fails here instead of quietly leaving the note in place."""

    def setUp(self):
        self.editor = package_source("@quintinshaw/pi-dynamic-workflows/dist/workflow-editor.js")
        self.effort = package_source("@quintinshaw/pi-dynamic-workflows/dist/effort-command.js")
        if not (self.editor and self.effort):
            self.skipTest("pi-dynamic-workflows is not installed next to this checkout")

    def test_the_armed_block_starts_where_ultracode_note_cuts(self):
        anchor = re.search(r'export const ARMED = "(.*)";', ULTRA.read_text()).group(1)
        self.assertEqual("\\n\\n---\\n[workflows mode armed", anchor)
        # the block's own lines: a "---" rule, then the note; appended after a blank line (the session)
        self.assertRegex(self.editor, r'"---",\s*"\[workflows mode armed\. Decide first')

    def test_the_effort_directives_and_threshold_the_docs_quote(self):
        self.assertIn("Effort: ULTRA.", self.effort)
        self.assertIn("Effort: HIGH.", self.effort)
        self.assertRegex(self.effort, r"length >= 16")


if __name__ == "__main__":
    unittest.main()


class WaitGuardTests(unittest.TestCase):
    """wait-guard.ts: bg_wait is refused with a UI (the run wakes the session) and left alone without one."""

    def test_bg_wait_is_refused_only_in_an_interactive_session(self):
        binary = node()
        if not binary:
            self.skipTest("needs node")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "wait-guard.ts"
            source.write_text((ROOT / "templates/extensions/wait-guard.ts").read_text())
            script = (
                "import { pathToFileURL } from 'node:url';"
                "const m = await import(pathToFileURL(process.argv[1]).href); const h = {};"
                "m.default({ on: (e, f) => { h[e] = f; } });"
                "const cases = [['bg_wait', true], ['bg_wait', false], ['read', true]];"
                "const out = []; for (const [toolName, hasUI] of cases)"
                " out.push((await h.tool_call({ type: 'tool_call', toolName, input: { all: true } }, { hasUI })) ?? null);"
                "console.log(JSON.stringify({ out, reason: m.REASON }));")
            run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, str(source)],
                                 capture_output=True, text=True, timeout=60, cwd=tmp)
            if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
                self.skipTest("this node cannot load TypeScript")
            self.assertEqual(0, run.returncode, run.stderr)
            result = json.loads(run.stdout)
        interactive, print_mode, other = result["out"]
        self.assertEqual({"block": True, "reason": result["reason"]}, interactive)
        self.assertIsNone(print_mode)       # pi -p and sub-agents keep bg_wait
        self.assertIsNone(other)
        self.assertIn("End your turn now", result["reason"])
        self.assertIn("Background task completed", result["reason"])

    def test_the_same_command_over_and_over_is_a_wait(self):
        """batch 4, gannets-manual: `ls -lh .../*.html` 91 times while the children wrote the pages."""
        binary = node()
        if not binary:
            self.skipTest("needs node")
        ls = ["bash", {"command": "ls -lh /p/site/*.html"}]
        calls = [ls, ls, ls, "agent_start", ls,                      # the third is refused; a new run does not reset it
                 ["read", {"path": "a.html"}], ls, ls,               # anything else between starts the count again
                 ["bash", {"command": "pytest -q"}], ["bash", {"command": "pytest -q"}]]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "wait-guard.ts"
            source.write_text((ROOT / "templates/extensions/wait-guard.ts").read_text())
            script = (
                "import { pathToFileURL } from 'node:url';"
                "const m = await import(pathToFileURL(process.argv[1]).href); const h = {};"
                "m.setHoldMs(5);"
                "m.default({ on: (e, f) => { h[e] = f; } });"
                "const out = []; for (const c of JSON.parse(process.argv[2])) {"
                " if (c === 'agent_start') { await h.agent_start({ type: 'agent_start' }); continue; }"
                " const r = await h.tool_call({ type: 'tool_call', toolName: c[0], input: c[1] }, { hasUI: true });"
                " out.push(r ? 'refused' : null); }"
                "console.log(JSON.stringify(out));")
            run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, str(source), json.dumps(calls)],
                                 capture_output=True, text=True, timeout=60, cwd=tmp)
            if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
                self.skipTest("this node cannot load TypeScript")
            self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual([None, None, "refused", "refused", None, None, None, None, None], json.loads(run.stdout))

    def test_a_third_refused_wait_in_a_turn_is_held_and_never_aborts(self):
        """auto11: eight waits refused in 45 s, each one a turn - so the third was made to end the turn with
        ctx.abort(). pi-subagents takes an abort for the user's Esc and stops waking the session: in three
        driven sessions of three (2026-11-14) the children finished and no turn ever started. Now the third
        wait is held in the handler until a notice is queued, or the hold runs out."""
        binary = node()
        if not binary:
            self.skipTest("needs node")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "wait-guard.ts"
            source.write_text((ROOT / "templates/extensions/wait-guard.ts").read_text())
            script = (
                "import { pathToFileURL } from 'node:url';"
                "const m = await import(pathToFileURL(process.argv[1]).href); const h = {};"
                "m.setHoldMs(1200);"
                "m.default({ on: (e, f) => { h[e] = f; }, getActiveTools: () => [], setActiveTools: () => {} });"
                "let aborted = 0; let pending = false;"
                "const ctx = { hasUI: true, abort: () => { aborted++; }, hasPendingMessages: () => pending, ui: { notify: () => {} } };"
                "const out = [];"
                "const call = async (c) => { const t0 = Date.now(); const r = await h.tool_call({ toolName: c[0], input: c[1] }, ctx);"
                " out.push([r ? r.reason : null, Date.now() - t0]); };"
                "await call(['subagent', { action: 'status', id: 'x' }]);"       # the one check
                "await call(['subagent', { action: 'status', id: 'x' }]);"       # refused (1)
                "await call(['bash', { command: 'sleep 30' }]);"                 # refused (2)
                "await call(['bash', { command: 'sleep 60 && ls' }]);"           # refused (3): held, quiet
                "setTimeout(() => { pending = true; }, 150);"
                "await call(['bash', { command: 'sleep 60 && ls' }]);"           # held until the notice is queued
                "console.log(JSON.stringify({ out, aborted, quiet: m.HELD_QUIET, notice: m.HELD_NOTICE, again: m.AGAIN, hold: m.HOLD_MS }));")
            run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, str(source)],
                                 capture_output=True, text=True, timeout=60, cwd=tmp,
                                 env={"PATH": "/usr/bin:/bin"})
            if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
                self.skipTest("this node cannot load TypeScript")
            self.assertEqual(0, run.returncode, run.stderr)
            got = json.loads(run.stdout)
        reasons = [r for r, _ in got["out"]]
        took = [ms for _, ms in got["out"]]
        self.assertEqual(0, got["aborted"])                       # never: an abort stops pi-subagents waking the session
        self.assertEqual(120_000, got["hold"])
        self.assertIsNone(reasons[0])
        self.assertEqual(got["again"], reasons[2])
        self.assertEqual(got["quiet"], reasons[3])
        self.assertGreaterEqual(took[3], 1100)                    # held for the whole (shortened) hold
        self.assertLess(max(took[:3]), 300)                       # the first refusals answer at once
        self.assertEqual(got["notice"], reasons[4])
        self.assertLess(took[4], 1000)                            # and a queued notice ends the hold early

    def test_once_refused_the_other_ways_of_waiting_are_refused_too(self):
        """test9: after bg_wait was refused, two status checks, sleep 5, sleep 10 and the run's log."""
        binary = node()
        if not binary:
            self.skipTest("needs node")
        log = "cat /var/folders/x/T/pi-subagents-uid-504/async-subagent-runs/75f83005/output-0.log | tail -100"
        calls = [
            ["bash", {"command": "sleep 2"}],                              # before any check or refusal: allowed
            ["subagent", {"action": "status", "id": "75f8"}],             # the one check: allowed
            ["bg_wait", {"id": "75f8"}],
            ["subagent", {"action": "status", "id": "75f8"}],
            ["bash", {"command": "sleep 5 && echo \"Checking status...\""}],
            ["bash", {"command": log}],
            ["bash", {"command": "sleep 10"}],
            ["bg_wait", {"id": "75f8"}],
            ["bash", {"command": "sleep 2 && python3 build.py"}],          # real work after a pause
            ["bash", {"command": "ls site/"}],
            ["subagent", {"agent": "qwen", "task": "x"}],
            "agent_start",                                                 # the next turn starts clean
            ["bash", {"command": "sleep 5"}],
        ]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "wait-guard.ts"
            source.write_text((ROOT / "templates/extensions/wait-guard.ts").read_text())
            script = (
                "import { pathToFileURL } from 'node:url';"
                "const m = await import(pathToFileURL(process.argv[1]).href); const h = {};"
                "m.setHoldMs(5);"                                           # the third wait on is held: briefly here
                "m.default({ on: (e, f) => { h[e] = f; } });"
                "const out = []; for (const c of JSON.parse(process.argv[2])) {"
                " if (c === 'agent_start') { await h.agent_start({ type: 'agent_start' }); continue; }"
                " const r = await h.tool_call({ type: 'tool_call', toolName: c[0], input: c[1] }, { hasUI: true });"
                " out.push(r ? r.reason.slice(0, 40) : null); }"
                "console.log(JSON.stringify(out));")
            run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, str(source), json.dumps(calls)],
                                 capture_output=True, text=True, timeout=60, cwd=tmp)
            if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
                self.skipTest("this node cannot load TypeScript")
            self.assertEqual(0, run.returncode, run.stderr)
            out = json.loads(run.stdout)
        first, again = "bg_wait is not used in an interactive se", "Still waiting is still not needed: nothi"
        held = "Two minutes on and no notice yet: the ru"
        self.assertEqual([None, None, first, again, held, held, held, held, None, None, None, None], out)

    def test_without_bg_wait_a_second_status_check_is_the_refused_wait(self):
        """auto01: the launcher no longer offers bg_wait to an interactive session, so the launch result's one
        status check is allowed and the next in that turn is refused, then everything else that waits."""
        binary = node()
        if not binary:
            self.skipTest("needs node")
        calls = [
            ["subagent", {"action": "status", "id": "b8ce"}],   # the one-shot check the launch result offers
            ["subagent", {"action": "status", "id": "b8ce"}],   # auto01: checked again
            ["bash", {"command": "sleep 10"}],
            "agent_start",
            ["subagent", {"action": "status", "id": "8b39"}],   # a new turn: one check again
            ["bash", {"command": "sleep 10 && cat /var/x/async-subagent-runs/8b39/output-0.log"}],  # auto02, next
            "agent_start",
            ["bash", {"command": "tail -100 /var/x/async-subagent-runs/d638/output-0.log"}],       # auto02: no check first
            "agent_start",
            ["subagent", {"action": "status", "id": "dc07"}],
            ["bash", {"command": "sleep 30 && ls -lh site/*.html | wc -l"}],                        # auto03: a poll
            ["bash", {"command": "sleep 2 && python3 build.py"}],                                    # a pause before work
        ]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "wait-guard.ts"
            source.write_text((ROOT / "templates/extensions/wait-guard.ts").read_text())
            script = (
                "import { pathToFileURL } from 'node:url';"
                "const m = await import(pathToFileURL(process.argv[1]).href); const h = {};"
                "m.default({ on: (e, f) => { h[e] = f; } });"
                "const out = []; for (const c of JSON.parse(process.argv[2])) {"
                " if (c === 'agent_start') { await h.agent_start({ type: 'agent_start' }); continue; }"
                " const r = await h.tool_call({ type: 'tool_call', toolName: c[0], input: c[1] }, { hasUI: true });"
                " out.push(r ? r.reason.slice(0, 40) : null); }"
                "console.log(JSON.stringify(out));")
            run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, str(source), json.dumps(calls)],
                                 capture_output=True, text=True, timeout=60, cwd=tmp)
            if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
                self.skipTest("this node cannot load TypeScript")
            self.assertEqual(0, run.returncode, run.stderr)
            out = json.loads(run.stdout)
        first, again = "bg_wait is not used in an interactive se", "Still waiting is still not needed: nothi"
        self.assertEqual([None, first, again, None, first, first, None, first, None], out)
        launcher = (ROOT / "pi.bash").read_text()
        self.assertIn('XT_LIST="${XT_LIST:+$XT_LIST,}bg_wait"', launcher)

    def test_it_is_loaded(self):
        self.assertIn("wait-guard.ts", CONFIG["requiredExtensions"])

    def test_async_launch_arms_the_wait_guard_without_a_valid_status_check(self):
        """python-before parallel.1: invalid alternate status calls, then sleep/list polls while children wrote."""
        got = run_extension(self, "wait-guard", '''
            const call = async (toolName, input) =>
                (await registered.handlers.tool_call[0]({ toolName, input }, ctx)) ?? null;
            const result = { toolName: "subagent", isError: false, content: [{ type: "text",
                text: "Run fan-out: 0/64 used\\nAsync workflow [1ffbbbcd-29ec-4f7a-ab9e-826a67ff2231]\\nDetached. Return control now." }] };
            await registered.handlers.agent_start[0]({}, ctx);
            for (const handler of registered.handlers.tool_result ?? []) await handler(result, ctx);
            await call("subagent_supervisor", { action: "status", id: "1ffbbbcd" });
            await call("workflow_control", { action: "status", runId: "1ffbbbcd" });
            const poll = await call("bash", { command: 'sleep 5 && ls -la *.py' });
            const work = await call("bash", { command: 'python3 check_independent_file.py' });
            const read = await call("read", { path: "README.md" });
            await registered.handlers.agent_start[0]({}, ctx);
            const nextTurn = await call("bash", { command: "sleep 5" });
            out({ poll, work, read, nextTurn });
        ''')
        self.assertIsNotNone(got["poll"])
        self.assertTrue(got["poll"]["block"])
        self.assertIn("End your turn now", got["poll"]["reason"])
        self.assertEqual([None, None, None], [got["work"], got["read"], got["nextTurn"]])

    def test_async_launch_keeps_one_status_check_and_holds_without_aborting(self):
        got = run_extension(self, "wait-guard", '''
            let aborted = 0;
            ctx.abort = () => { aborted++; };
            ctx.hasPendingMessages = () => true;
            const result = { toolName: "subagent", isError: false, content: [{ type: "text",
                text: "Async workflow [1ffbbbcd-29ec-4f7a-ab9e-826a67ff2231]" }] };
            for (const handler of registered.handlers.tool_result ?? []) await handler(result, ctx);
            const call = async (toolName, input) =>
                (await registered.handlers.tool_call[0]({ toolName, input }, ctx)) ?? null;
            const status = await call("subagent", { action: "status", id: "1ffbbbcd" });
            const waits = [];
            for (const seconds of [5, 10, 15]) waits.push(await call("bash", { command: `sleep ${seconds} && ls *.py` }));
            out({ status, waits, aborted, notice: ext.HELD_NOTICE });
        ''')
        self.assertIsNone(got["status"])
        self.assertTrue(all(item["block"] for item in got["waits"]))
        self.assertEqual(got["notice"], got["waits"][-1]["reason"])
        self.assertEqual(0, got["aborted"])

    def test_only_a_successful_async_launch_with_a_ui_arms_waiting(self):
        got = run_extension(self, "wait-guard", '''
            const cases = [
                [true, true, "subagent", "Async workflow [1ffbbbcd-29ec-4f7a-ab9e-826a67ff2231]"],
                [true, false, "subagent", "Validation succeeded"],
                [true, false, "bash", "Async workflow [1ffbbbcd-29ec-4f7a-ab9e-826a67ff2231]"],
                [false, false, "subagent", "Async workflow [1ffbbbcd-29ec-4f7a-ab9e-826a67ff2231]"],
            ];
            const results = [];
            for (const [hasUI, isError, toolName, text] of cases) {
                ctx.hasUI = hasUI;
                await registered.handlers.agent_start[0]({}, ctx);
                for (const handler of registered.handlers.tool_result ?? [])
                    await handler({ toolName, isError, content: [{ type: "text", text }] }, ctx);
                results.push((await registered.handlers.tool_call[0]({ toolName: "bash",
                    input: { command: `sleep ${results.length + 5} && ls *.py` } }, ctx)) ?? null);
            }
            out(results);
        ''')
        self.assertEqual([None] * 4, got)


class OpenServerTests(unittest.TestCase):
    """command-guard.ts: a python http.server not bound to this machine is refused, with how to bind and stop it."""

    CASES = {
        # test5's and test4's commands, as run
        "cd /Users/x/sandbox/test5 && python3 -m http.server 8080 &": True,
        "python3 -m http.server 8000 > /dev/null 2>&1 & echo $!": True,
        "python -m http.server": True,
        "python3.12 -u -m http.server 9000 --directory site": True,
        "python3 -m http.server --bind 0.0.0.0 8000": True,
        "python3 -m http.server --bind 127.0.0.1 8000 & echo $!": False,
        "python3 -m http.server -b localhost 8000": False,
        "python3 -m http.server 8000 --bind=127.0.0.1": False,
        "python3 -m http.client": False,
        "grep -n http.server notes.md": False,
    }

    def test_only_an_unbound_server_is_refused(self):
        binary = node()
        if not binary:
            self.skipTest("needs node")
        guard = ROOT / "templates/extensions/command-guard.ts"
        script = ("import { pathToFileURL } from 'node:url';"
                  "const m = await import(pathToFileURL(process.argv[1]).href);"
                  "const cases = JSON.parse(process.argv[2]);"
                  "console.log(JSON.stringify({ out: cases.map((c) => m.openServer(c) ?? null), reason: m.OPEN_SERVER }));")
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, str(guard),
                              json.dumps(list(self.CASES))], capture_output=True, text=True, timeout=60, cwd=ROOT)
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            self.skipTest("this node cannot load TypeScript")
        self.assertEqual(0, run.returncode, run.stderr[-2000:])
        result = json.loads(run.stdout)
        for (command, refused), denial in zip(self.CASES.items(), result["out"]):
            with self.subTest(command=command):
                self.assertEqual(refused, denial is not None)
        self.assertIn("--bind 127.0.0.1", result["reason"])
        self.assertIn("$ELM_PI_PREVIEW_PORT", result["reason"])
        self.assertIn("http://127.0.0.1:$ELM_PI_PREVIEW_PORT/", result["reason"])
        self.assertIn("kill <PID>", result["reason"])


class ImageMentionTests(unittest.TestCase):
    """image-mentions.ts: the images a message names are attached to it, as a pasted one is."""

    CWD, HOME = "/work/proj", "/home/u"
    FILES = ["/work/proj/figures/fit.png", "/work/proj/a.png", "/work/proj/b.jpg", "/work/proj/plots/a.png",
             "/home/u/Desktop/Screenshot 2026-11-12 at 10.00.00.png", "/tmp/x y/shot.png", "/home/u/.ssh/key.png",
             "/work/proj/fit.png"] + [f"/work/proj/m{i}.png" for i in range(10)]
    CASES = {
        "what is wrong with figures/fit.png?": ["/work/proj/figures/fit.png"],
        "compare a.png and b.jpg.": ["/work/proj/a.png", "/work/proj/b.jpg"],
        "the screenshot is ~/Desktop/Screenshot 2026-11-12 at 10.00.00.png please look":
            ["/home/u/Desktop/Screenshot 2026-11-12 at 10.00.00.png"],
        "here: '/tmp/x y/shot.png'": ["/tmp/x y/shot.png"],
        "dropped: /tmp/x\\ y/shot.png": ["/tmp/x y/shot.png"],
        "see `plots/a.png`, then fix it": ["/work/proj/plots/a.png"],
        "@figures/fit.png is attached already": [],
        # `pi @fit.png -p "describe it"`: pi puts the file in the text this way and attaches it itself
        '<file name="/work/proj/fit.png"></file>\ndescribe it': [],
        '<file name="/work/proj/fit.png"></file>\nnow compare it with a.png': ["/work/proj/a.png"],
        "and ~/.ssh/key.png": [],
        "missing.png does not exist": [],
        "fit.png.bak is not an image": [],
        " ".join(f"m{i}.png" for i in range(10)): [f"/work/proj/m{i}.png" for i in range(8)],
    }

    def run_node(self, script, *args):
        binary = node()
        if not binary:
            self.skipTest("needs node")
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, *map(str, args)],
                             capture_output=True, text=True, timeout=60, cwd=ROOT)
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            self.skipTest("this node cannot load TypeScript")
        self.assertEqual(0, run.returncode, run.stderr[-2000:])
        return json.loads(run.stdout)

    def test_names_are_found_however_they_are_written(self):
        out = self.run_node(
            "import { pathToFileURL } from 'node:url';"
            "const m = await import(pathToFileURL(process.argv[1]).href);"
            "const files = new Set(JSON.parse(process.argv[2])); const cases = JSON.parse(process.argv[3]);"
            "console.log(JSON.stringify(cases.map((t) => m.mentionedImages(t, process.argv[4], (p) => files.has(p), process.argv[5]))));",
            ROOT / "templates/extensions/image-mentions.ts", json.dumps(self.FILES), json.dumps(list(self.CASES)),
            self.CWD, self.HOME)
        for (text, want), got in zip(self.CASES.items(), out):
            with self.subTest(text=text):
                self.assertEqual(want, got)

    def test_a_named_image_is_attached_for_a_model_that_sees_and_not_otherwise(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "fit.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
            out = self.run_node(
                "import { pathToFileURL } from 'node:url';"
                "const m = await import(pathToFileURL(process.argv[1]).href); const h = {};"
                "m.default({ on: (e, f) => { h[e] = f; } });"
                "const ev = (source) => ({ type: 'input', text: 'what is wrong with fit.png?', images: [], source });"
                "const sees = { cwd: process.argv[2], model: { input: ['text', 'image'] } };"
                "const blind = { cwd: process.argv[2], model: { input: ['text'] } };"
                "const r = [await h.input(ev('interactive'), sees), await h.input(ev('interactive'), blind),"
                " await h.input(ev('extension'), sees)];"
                "console.log(JSON.stringify(r.map((x) => ({ action: x.action, images: (x.images ?? []).map((i) => i.mimeType),"
                " text: x.text }))));",
                ROOT / "templates/extensions/image-mentions.ts", tmp)
        seen, blind, from_extension = out
        self.assertEqual({"action": "transform", "images": ["image/png"], "text": "what is wrong with fit.png?"}, seen)
        self.assertEqual("continue", blind["action"])          # Llama through the shim sees no images
        self.assertEqual("continue", from_extension["action"])

    def test_a_file_that_is_not_an_image_is_never_attached(self):
        """test9: seven '.jpg' downloads held "error code: 522", and the gateway refused every request with them."""
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "gallery1.jpg").write_bytes(b"error code: 522\n")
            (Path(tmp) / "shot.jpg").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)     # a PNG named .jpg
            out = self.run_node(
                "import { pathToFileURL } from 'node:url';"
                "const m = await import(pathToFileURL(process.argv[1]).href); const h = {};"
                "m.default({ on: (e, f) => { h[e] = f; } });"
                "const sees = { cwd: process.argv[2], model: { input: ['text', 'image'] } };"
                "const r = await h.input({ type: 'input', text: 'look at gallery1.jpg and shot.jpg', images: [],"
                " source: 'interactive' }, sees);"
                "console.log(JSON.stringify((r.images ?? []).map((i) => i.mimeType)));",
                ROOT / "templates/extensions/image-mentions.ts", tmp)
        self.assertEqual(["image/png"], out)                # the PNG, typed by its bytes; not the error text

    def test_it_is_loaded(self):
        self.assertIn("image-mentions.ts", CONFIG["requiredExtensions"])
