"""Command output is drawn for a person: an exit line, head and tail, colour - and reaches the model plain.

command-output.ts is run under node beside the installed pi packages, with a
theme stub that wraps each run of text in <colour>...</> so the colour of every
line can be read off. The tests skip on a checkout that has not been
bootstrapped.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "templates/extensions/command-output.ts"
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
COLOUR_NOTE = re.search(r'COLOUR_NOTE = "([^"]+)"', SOURCE.read_text()).group(1)


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


# Loads the extension against a stub pi and runs each case, printing the
# results as one JSON object.
RUNNER = r"""
const [source, casesJson] = process.argv.slice(1);
const mod = await import(source);
const { initTheme } = await import("@earendil-works/pi-coding-agent");
initTheme("dark");
const theme = { fg: (c, s) => `<${c}>${s}</>`, bold: (s) => s };
const cases = JSON.parse(casesJson);
const out = { classify: {}, renders: {} };

for (const line of cases.lines) out.classify[line] = mod.classify(line, false);
out.diff = cases.diff.map((line) => mod.classify(line, mod.isDiff(cases.diff)));
out.located = mod.paintLine(cases.located, "plain", theme);

let resolver;
const registered = [];
const handlers = {};
mod.default({
  registerToolRenderer: (f) => { resolver = f; },
  on: (event, handler) => { registered.push(event); handlers[event] = handler; },
  registerTool: () => registered.push("tool"),
});
out.registered = registered;
out.note = mod.COLOUR_NOTE;
out.handled = {};
for (const [name, event] of Object.entries(cases.events)) out.handled[name] = (await handlers.tool_result(event)) ?? null;
const base = { renderCall() { return "base call"; }, renderResult() { return "base live view"; } };
out.otherTool = resolver("read", () => "next renderers") === "next renderers";
const bash = resolver("bash", () => base);
out.keepsCall = bash.renderCall === base.renderCall;
out.partial = bash.renderResult({ content: [] }, { expanded: false, isPartial: true }, theme, {});

for (const [name, c] of Object.entries(cases.results)) {
  const context = { isError: c.isError, durationMs: c.durationMs, showImages: false, lastComponent: undefined };
  const component = bash.renderResult(c.result, { expanded: c.expanded, isPartial: false }, theme, context);
  out.renders[name] = component.render(200).map((line) => line.trimEnd()).filter(Boolean);
}
console.log(JSON.stringify(out));
"""


class CommandOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary = node()
        packages = ROOT / "node_modules/@earendil-works"
        if not cls.binary or not (packages / "pi-tui").exists():
            raise unittest.SkipTest("needs node and the installed pi packages (run bootstrap.sh)")
        cls.dir = Path(tempfile.mkdtemp())
        (cls.dir / "node_modules").mkdir()
        (cls.dir / "node_modules/@earendil-works").symlink_to(packages)
        shutil.copy(SOURCE, cls.dir / "command-output.ts")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run_cases(self, **cases):
        cases = {"lines": [], "diff": [], "located": "", "results": {}, "events": {}, **cases}
        run = subprocess.run([self.binary, "--no-warnings", "--input-type=module", "-e", RUNNER,
                              str(self.dir / "command-output.ts"), json.dumps(cases)],
                             cwd=self.dir, capture_output=True, text=True, env={**os.environ, "NO_COLOR": "1"})
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            self.skipTest("this node cannot load TypeScript")
        self.assertEqual(0, run.returncode, run.stderr)
        return json.loads(run.stdout)

    def test_lines_are_coloured_by_what_they_say(self):
        expected = {
            "FAILED tests/test_fit.py::test_slope - AssertionError": "error",
            "== 1 failed, 12 passed in 0.31s ==": "error",
            "E       assert 2.48 == 2.5": "error",
            "ValueError: x and y must have the same length": "error",
            "Traceback (most recent call last):": "error",
            "bash: gnuplot: command not found": "error",
            "npm ERR! code E404": "error",
            "== 12 passed, 2 warnings in 0.30s ==": "warning",
            "fit.py:3:8: F401 [*] `os` imported but unused": "warning",
            "DeprecationWarning: use numpy.trapezoid": "warning",
            "== 12 passed in 0.30s ==": "success",
            "All checks passed!": "success",
            "OK": "success",
            # A count of nothing is not a problem, and ordinary words are left alone.
            "Found 0 errors.": "plain",
            "no failures": "plain",
            "everything here is fine": "plain",
            "evaluating terms": "plain",
        }
        out = self.run_cases(lines=list(expected))
        self.assertEqual(expected, out["classify"])

    def test_plus_and_minus_are_changes_only_in_a_diff(self):
        diff = ["diff --git a/fit.py b/fit.py", "--- a/fit.py", "+++ b/fit.py", "@@ -1,2 +1,2 @@",
                " import numpy", "-slope = 2.4", "+slope = 2.5"]
        out = self.run_cases(diff=diff, lines=["- a list item", "+ a note"])
        self.assertEqual(["meta", "meta", "meta", "hunk", "plain", "removed", "added"], out["diff"])
        self.assertEqual("plain", out["classify"]["- a list item"])
        self.assertEqual("plain", out["classify"]["+ a note"])

    def test_locations_stand_out_without_breaking_the_line_colour(self):
        out = self.run_cases(located='  File "analysis/fit.py", line 42, in <module> see src/io.py:7:3')
        self.assertEqual('<toolOutput>  </><accent>File "analysis/fit.py", line 42</>'
                         '<toolOutput>, in <module> see </><accent>src/io.py:7:3</>', out["located"])

    def test_long_output_shows_head_and_tail_and_counts_hidden_errors(self):
        lines = [f"step {i}" for i in range(40)]
        lines[20] = "error: missing } in fit.cpp"
        lines[21] = "warning: unused variable"
        text = "\n".join(lines) + "\n\nCommand exited with code 2"
        result = {"content": [{"type": "text", "text": text}]}
        out = self.run_cases(results={
            "collapsed": {"result": result, "isError": True, "durationMs": 2400, "expanded": False},
            "expanded": {"result": result, "isError": True, "durationMs": 2400, "expanded": True},
        })
        collapsed = out["renders"]["collapsed"]
        self.assertEqual("<error>✗ exit 2 · 2.4s · 40 lines</>", collapsed[0])
        self.assertEqual([f"<toolOutput>step {i}</>" for i in range(4)], collapsed[1:5])
        self.assertIn("… 24 lines hidden", collapsed[5])
        self.assertIn("1 error and 1 warning lines among them", collapsed[5])
        self.assertEqual([f"<toolOutput>step {i}</>" for i in range(28, 40)], collapsed[6:])
        expanded = out["renders"]["expanded"]
        self.assertEqual(41, len(expanded))
        self.assertIn("<error>error: missing } in fit.cpp</>", expanded)
        self.assertFalse(any("Command exited" in line for line in expanded))

    def test_status_footers_and_notes(self):
        out = self.run_cases(results={
            "ok": {"result": {"content": [{"type": "text", "text": "fitted"}, {"type": "text", "text": "Installed lmfit into agent/python"}],
                              "structuredContent": {"exit_code": 0}},
                   "isError": False, "durationMs": 830, "expanded": False},
            "timeout": {"result": {"content": [{"type": "text", "text": "running\n\nCommand timed out after 30 seconds"}]},
                        "isError": True, "durationMs": 30000, "expanded": False},
            "truncated": {"result": {"content": [{"type": "text", "text": "last line\n\n[Showing lines 4001-4001 of 4001. Full output: /tmp/pi-bash-1.log]"},
                                                 {"type": "image", "data": "", "mimeType": "image/png"}],
                                     "details": {"truncation": {"truncated": True, "totalLines": 4001}, "fullOutputPath": "/tmp/pi-bash-1.log"}},
                          "isError": False, "expanded": False},
        })
        ok = out["renders"]["ok"]
        self.assertEqual(["<success>✓ exit 0 · 830ms · 1 line</>", "<toolOutput>fitted</>",
                          "<muted>Installed lmfit into agent/python</>"], ok)
        timeout = out["renders"]["timeout"]
        self.assertEqual("<error>✗ timed out after 30s · 30.0s · 1 line</>", timeout[0])
        self.assertEqual(["<toolOutput>running</>"], timeout[1:])
        truncated = out["renders"]["truncated"]
        self.assertEqual("<success>✓ exit 0 · 4001 lines</>", truncated[0])
        self.assertEqual("<toolOutput>last line</>", truncated[1])
        self.assertIn("full output (4001 lines): /tmp/pi-bash-1.log", truncated[2])
        self.assertIn("1 image attached", truncated[3])

    def test_the_model_gets_plain_text_and_the_display_keeps_the_colour(self):
        raw = "\x1b[31mred\x1b[0m plain\n\x1b]0;title\x07loading 10%\rloading 100%\n\x1b[2Kdone\n\nCommand exited with code 1"
        event = {"toolName": "bash", "isError": True, "details": {"fullOutputPath": "/tmp/x.log"},
                 "content": [{"type": "text", "text": raw}, {"type": "image", "data": "", "mimeType": "image/png"}],
                 "structuredContent": {"output": raw, "exit_code": 1}}
        plain_event = {"toolName": "bash", "isError": False, "details": None,
                       "content": [{"type": "text", "text": "no escapes here"}]}
        progress = {"toolName": "bash", "isError": False, "details": None,
                    "content": [{"type": "text", "text": "10%\rdone"}]}
        other_tool = {**event, "toolName": "read"}
        out = self.run_cases(events={"coloured": event, "plain": plain_event, "progress": progress, "other": other_tool})
        handled = out["handled"]["coloured"]
        plain = "red plain\nloading 100%\ndone\n\nCommand exited with code 1"
        self.assertEqual(plain, handled["content"][0]["text"])
        self.assertEqual(out["note"], handled["content"][1]["text"])   # the model is told the user saw colour
        self.assertEqual("image", handled["content"][2]["type"])
        self.assertEqual({"output": plain, "exit_code": 1}, handled["structuredContent"])
        self.assertEqual("\x1b[31mred\x1b[0m plain\nloading 100%\ndone\n\nCommand exited with code 1",
                         handled["details"]["colour"])
        self.assertEqual("/tmp/x.log", handled["details"]["fullOutputPath"])
        self.assertIsNone(out["handled"]["plain"])     # output without escape codes reaches the model unchanged
        no_colour = out["handled"]["progress"]          # only redraws: the copy is cleaned, but no colour is claimed
        self.assertEqual(["done"], [part["text"] for part in no_colour["content"]])
        self.assertNotIn("colour", no_colour["details"] or {})
        self.assertIsNone(out["handled"]["other"])

    def test_a_commands_own_colour_is_shown_as_printed(self):
        rainbow = "".join(f"\x1b[38;5;{196 + i}m{c}" for i, c in enumerate("rainbow"))
        lines = ["\x1b[1;32mbuild ok", "still green", "\x1b[0mfine.log is not an error", rainbow]
        result = {"content": [{"type": "text", "text": "build ok\nstill green\nfine.log is not an error\nrainbow"},
                              {"type": "text", "text": COLOUR_NOTE}],
                  "details": {"colour": "\n".join(lines)}}
        out = self.run_cases(results={"own": {"result": result, "isError": False, "expanded": False}})
        own = out["renders"]["own"]
        self.assertEqual("<success>✓ exit 0 · 4 lines</>", own[0])
        self.assertEqual("\x1b[1;32mbuild ok\x1b[0m", own[1])
        self.assertEqual("\x1b[1;32mstill green\x1b[0m", own[2])        # the colour carries over, and is reset
        self.assertEqual("\x1b[1;32m\x1b[0mfine.log is not an error\x1b[0m", own[3])   # its plain line is not re-coloured red
        self.assertEqual(rainbow + "\x1b[0m", own[4])
        self.assertEqual(5, len(own))                                   # the note to the model is not drawn

    def test_display_only_and_only_for_bash(self):
        out = self.run_cases()
        self.assertEqual(["tool_result"], out["registered"])   # no tool is replaced and nothing is added to the context
        self.assertTrue(out["otherTool"])
        self.assertTrue(out["keepsCall"])
        self.assertEqual("base live view", out["partial"])   # a running command keeps pi's live tail and timer

    def test_loaded_with_the_other_required_extensions(self):
        self.assertIn("command-output.ts", CONFIG["requiredExtensions"])


if __name__ == "__main__":
    unittest.main()
