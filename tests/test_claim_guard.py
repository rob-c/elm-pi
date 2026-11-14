"""claim-guard.ts: a reply that claims work, from a run with no tool call, is sent back once.

The decision (needsNote) case by case, then the extension's handlers end to end
under node with a stub pi: the note goes in at agent_before_settle with
continue, once per run, and never for Qwen, for a run that called a tool, or for
a reply that claims nothing.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "templates/extensions/claim-guard.ts"
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
MISTRAL, LLAMA, QWEN = CONFIG["models"]["mistral"], CONFIG["models"]["llama"], CONFIG["models"]["qwen"]


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


CLAIMS = ["I added the function `weighted_mean` to src/stats.py.", "Fixed.", "Created results/summary.json",
          "I ran the tests and they pass.", "Renamed kmh to km_per_hour.", "Task completed: updated the README.",
          "The file was modified as asked.", "ANNOTATED all three functions",
          # the form reported on Mistral's own API: "Task completed" and nothing done
          "Task completed.", "Change complete."]
NOT_CLAIMS = ["", "parse_stamp", "477.00", "Which file should I change?", "The module report imports kmh.",
              "I can add that if you want.", "This can be done with grep."]

# Every word the guard counts as a claim, read back from the extension itself.
CLAIM_WORDS = re.search(r"\\b\(([a-z|?]+)\)\\b/i;", EXTENSION.read_text()).group(1).replace("?", "").split("|")
# Each in a sentence, capitalised, and after other words.
WORD_CLAIMS = {f"word_{w}_{i}": text for w in CLAIM_WORDS
               for i, text in enumerate((f"I {w} it.", f"{w.capitalize()} the file as asked.", f"All done: {w} 3 functions"))}
# Not claims: plans, offers, questions and words that only contain a claim word.
NOT_CLAIM_FORMS = {
    "future": "I will add the function next.", "offer": "Shall I fix the test?", "suggestion": "You could rename it.",
    "imperative": "Add a docstring to every function.", "unchanged": "The file is unchanged.",
    "prefixed": "The ids are prefixed with call_.", "readded": "a readded flag", "addendum": "See the addendum.",
    "fixedpoint": "a fixedpoint iteration", "runtime": "The runtime is 3 s.", "changelog": "Read the changelog.",
    "answer": "The mean is 477.00.", "path": "src/stats.py:mean", "plan": "Next: read the file, then edit it.",
    "question": "Which file should I change?", "doneish": "This can be done with grep.",
}

# id -> (model id, tool calls, final text, expected)
DECISIONS = {}
for _id, _text in WORD_CLAIMS.items():
    DECISIONS[f"mistral_{_id}"] = (MISTRAL, 0, _text, True)
for _id, _text in NOT_CLAIM_FORMS.items():
    DECISIONS[f"mistral_not_a_claim_{_id}"] = (MISTRAL, 0, _text, False)
    DECISIONS[f"llama_not_a_claim_{_id}"] = (LLAMA, 0, _text, False)
for i, text in enumerate(CLAIMS):
    DECISIONS[f"mistral_claim_{i}"] = (MISTRAL, 0, text, True)
    DECISIONS[f"llama_claim_{i}"] = (LLAMA, 0, text, True)
    DECISIONS[f"qwen_claim_{i}_is_left_alone"] = (QWEN, 0, text, False)
    DECISIONS[f"mistral_claim_{i}_after_a_tool_call"] = (MISTRAL, 1, text, False)
for i, text in enumerate(NOT_CLAIMS):
    DECISIONS[f"mistral_no_claim_{i}"] = (MISTRAL, 0, text, False)
# Qwen as a sub-agent (test5: "Created new file" with no tool call), and only there.
for i, text in enumerate(CLAIMS):
    DECISIONS[f"qwen_child_claim_{i}"] = (QWEN, 0, text, True, True)
    DECISIONS[f"qwen_child_claim_{i}_after_a_tool_call"] = (QWEN, 1, text, False, True)
for i, text in enumerate(NOT_CLAIMS):
    DECISIONS[f"qwen_child_no_claim_{i}"] = (QWEN, 0, text, False, True)
# A sub-agent's task said to use a tool, and the run made no call: whatever it replies is made up
# (live probes, 2026-11-13: a workflow agent replied "started" to "Use the bash tool to run: ...
# echo started"; another wrote six results for six steps it never ran).
TOOL_TASKS = {
    "use_the_bash_tool": "Use the bash tool to run: python3 -m http.server --bind 127.0.0.1 8768 & sleep 1; echo started",
    "steps": "Do these steps in order.\n1. bash: python3 -m http.server 8767 &\n3. write tool: create the file .env",
    "use_view": "Use the view tool on probe.png and say what colour it is.",
    "run_the_command": "Run the command `pytest -q` and report the result.",
    "with_the_tool": "Count the lines with the `grep` tool.",
}
NOT_TOOL_TASKS = {
    "question": "What is the mean of 3, 4 and 5?",
    "about_tools": "Which tools would you use to find a file?",
    "explain": "Explain what this bash script does: echo hi",
    "write_prose": "Write a paragraph about worms for the home page.",
}
for _id, _task in TOOL_TASKS.items():
    DECISIONS[f"qwen_child_task_{_id}_no_call"] = (QWEN, 0, "started", True, True, _task)
    DECISIONS[f"qwen_child_task_{_id}_after_a_call"] = (QWEN, 1, "started", False, True, _task)
    DECISIONS[f"qwen_top_level_task_{_id}"] = (QWEN, 0, "started", False, False, _task)
    DECISIONS[f"mistral_child_task_{_id}_no_call"] = (MISTRAL, 0, "started", True, True, _task)
for _id, _task in NOT_TOOL_TASKS.items():
    DECISIONS[f"qwen_child_answers_{_id}"] = (QWEN, 0, "4", False, True, _task)
DECISIONS.update({
    "mistral_id_in_another_case": (MISTRAL.upper(), 0, CLAIMS[0], True),
    "no_model": (None, 0, CLAIMS[0], False),
    "an_unknown_model": ("someone/else", 0, CLAIMS[0], False),
    "a_word_inside_another_is_not_a_claim": (MISTRAL, 0, "the readded flag", False),
})

# A run through the handlers: model, tool calls during it, the final reply, and
# how many times pi asks before settling (it asks again after a continue).
RUNS = {
    "mistral_claim_without_tools_gets_one_note_and_continues": (MISTRAL, 0, CLAIMS[0], 2),
    "a_second_settle_in_the_same_run_gets_nothing": (MISTRAL, 0, CLAIMS[0], 2),
    "qwen_claim_without_tools_settles": (QWEN, 0, CLAIMS[0], 1),
    "mistral_with_a_tool_call_settles": (MISTRAL, 2, CLAIMS[0], 1),
    "mistral_plain_answer_settles": (MISTRAL, 0, "parse_stamp", 1),
    "qwen_child_claim_without_tools_gets_one_note_and_continues": (QWEN, 0, CLAIMS[0], 2, True),
    "a_workflow_agent_that_made_up_a_tool_result_is_sent_back": (QWEN, 0, "started", 2, True, TOOL_TASKS["use_the_bash_tool"]),
    # test13: every write refused (manual), and the reply said the stylesheet "has been created"
    "every_call_refused_and_a_claim_is_sent_back": (QWEN, -3, "The stylesheet file has been created.", 2, True),
}

RUNNER = r"""
import { pathToFileURL } from "node:url";
import { readFileSync } from "node:fs";
const [file, casesPath] = process.argv.slice(1);
const mod = await import(pathToFileURL(file).href);
const { decisions, runs } = JSON.parse(readFileSync(casesPath, "utf8"));
const out = { decisions: {}, runs: {}, note: mod.NOTE };
for (const [id, [model, calls, text, child, task]] of Object.entries(decisions)) out.decisions[id] = mod.needsNote(model ?? undefined, calls, text, child ?? false, task ?? "");
for (const [id, [model, calls, text, settles, child, task]] of Object.entries(runs)) {
  const h = {};
  // a top-level session has the subagent tool; pi-subagents takes it from a child
  const tools = child ? ["read", "bash"] : ["read", "bash", "subagent"];
  mod.default({ on: (e, f) => { h[e] = f; }, getActiveTools: () => tools });
  await h.agent_start({ type: "agent_start" }, {});
  // a negative count: that many calls, every one refused
  for (let i = 0; i < Math.abs(calls); i++)
    await h.tool_result({ type: "tool_result", toolName: "write", input: {}, content: [], isError: calls < 0 }, {});
  const event = { type: "agent_before_settle", entries: [], continue: false, outcome: {},
    context: { canContinue: false, contextMessages: [{ role: "user", content: [{ type: "text", text: task ?? "do it" }] },
      { role: "assistant", content: [{ type: "text", text }] }], contextEntries: [], llmMessages: [], pendingMessages: [] } };
  const results = [];
  for (let i = 0; i < settles; i++) results.push((await h.agent_before_settle(event, { model: { id: model } })) ?? null);
  // A new run starts clean.
  await h.agent_start({ type: "agent_start" }, {});
  results.push((await h.agent_before_settle(event, { model: { id: model } })) ?? null);
  out.runs[id] = results;
}
console.log(JSON.stringify(out));
"""


class ClaimGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binary = node()
        if not binary:
            raise unittest.SkipTest("needs node")
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            (cls.tmp / "claim-guard.ts").write_text(EXTENSION.read_text())
            (cls.tmp / "cases.json").write_text(json.dumps({
                "decisions": {k: [v[0], v[1], v[2], v[4] if len(v) > 4 else False, v[5] if len(v) > 5 else ""]
                              for k, v in DECISIONS.items()},
                "runs": RUNS}))
            env = {"PATH": "/usr/bin:/bin", "HOME": str(cls.tmp), "ELM_MISTRAL_MODEL_ID": MISTRAL,
                   "ELM_LLAMA_MODEL_ID": LLAMA, "ELM_QWEN_MODEL_ID": QWEN}
            run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", RUNNER,
                                  str(cls.tmp / "claim-guard.ts"), str(cls.tmp / "cases.json")],
                                 capture_output=True, text=True, env=env, cwd=cls.tmp, timeout=120)
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

    def note(self):
        return {"entries": [{"type": "custom_message", "customType": "claim-guard", "content": self.out["note"],
                             "display": True}], "continue": True}

    def test_the_note_says_what_to_do_and_how_to_be_honest_without_tools(self):
        self.assertIn("this run made no tool call", self.out["note"])
        self.assertIn("Do the work now with tool calls", self.out["note"])
        self.assertIn("only describing earlier work", self.out["note"])

    def test_a_claim_once_noted_settles_and_a_new_run_is_checked_again(self):
        self.assertEqual([self.note(), None, self.note()],
                         self.out["runs"]["a_second_settle_in_the_same_run_gets_nothing"])

    def test_runs_that_need_no_note_settle(self):
        for name in ("qwen_claim_without_tools_settles", "mistral_with_a_tool_call_settles",
                     "mistral_plain_answer_settles"):
            with self.subTest(name=name):
                self.assertTrue(all(r is None for r in self.out["runs"][name][:-1]))

    def test_a_qwen_child_claiming_work_without_a_call_is_sent_back(self):
        # test5: "CHANGED - index.html: Created new file" from a child that made no tool call
        self.assertEqual(self.note(), self.out["runs"]["qwen_child_claim_without_tools_gets_one_note_and_continues"][0])
        self.assertIsNone(self.out["runs"]["qwen_claim_without_tools_settles"][0])   # top level: left alone

    def test_a_sub_agent_told_to_use_a_tool_that_used_none_is_sent_back(self):
        self.assertEqual(self.note(), self.out["runs"]["a_workflow_agent_that_made_up_a_tool_result_is_sent_back"][0])

    def test_a_run_whose_calls_were_all_refused_counts_as_making_none(self):
        self.assertEqual(self.note(), self.out["runs"]["every_call_refused_and_a_claim_is_sent_back"][0])

    def test_the_noted_run_continues(self):
        first = self.out["runs"]["mistral_claim_without_tools_gets_one_note_and_continues"][0]
        self.assertEqual(self.note(), first)

    def test_the_claim_words_were_read_from_the_extension(self):
        self.assertIn("added", CLAIM_WORDS)
        self.assertIn("completed", CLAIM_WORDS)
        self.assertNotIn("done", CLAIM_WORDS)

    def test_the_guard_is_loaded_everywhere_mistral_can_run(self):
        self.assertIn("claim-guard.ts", CONFIG["requiredExtensions"])
        self.assertIn("permission-mode claim-guard repeat-guard server-reaper report-guard date-note; do", (ROOT / "pi").read_text())


for _id, (_model, _calls, _text, _want, *_child) in DECISIONS.items():
    setattr(ClaimGuardTests, f"test_decision_{_id}",
            lambda self, i=_id, w=_want: self.assertEqual(w, self.out["decisions"][i], i))


if __name__ == "__main__":
    unittest.main()
