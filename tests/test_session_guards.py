"""server-reaper.ts, report-guard.ts and date-note.ts, run under node with a stub pi.

server-reaper: a web server a bash command starts in the background is stopped when the
session ends (test4, test5 and test7 each left one running); any other background job is
left alone. The server here is a real `python3 -m http.server`.

report-guard: a new README, summary or report file nobody asked for is refused (test6 and
test7 wrote README.md and LINK_VERIFICATION.md unasked).

date-note: the system prompt has today's date, as a section (test7's pages said "© 2024").
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAPER = ROOT / "templates/extensions/server-reaper.ts"
REPORT = ROOT / "templates/extensions/report-guard.ts"
DATE = ROOT / "templates/extensions/date-note.ts"
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
LAUNCHER = (ROOT / "pi").read_text()


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def run_node(test, script, *args, env=None):
    binary = node()
    if not binary:
        test.skipTest("needs node")
    run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, *map(str, args)],
                         capture_output=True, text=True, timeout=60, cwd=ROOT, env={**os.environ, **(env or {})})
    if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
        test.skipTest("this node cannot load TypeScript")
    test.assertEqual(0, run.returncode, run.stderr[-2000:])
    return json.loads(run.stdout.strip().splitlines()[-1]), run.stderr


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def listening(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


# Runs a bash command as pi's bash tool does (its own process group), between the
# extension's tool_call and tool_result, then ends the session for the given reason.
REAPER_DRIVER = r"""
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";
const m = await import(pathToFileURL(process.argv[1]).href);
const [command, reason] = [process.argv[2], process.argv[3]];
const h = {};
m.default({ on: (e, f) => { h[e] = f; } });
const input = { command };
await h.tool_call({ type: "tool_call", toolCallId: "b1", toolName: "bash", input }, {});
await new Promise((done) => spawn("bash", ["-c", command], { detached: true, stdio: "ignore" }).on("exit", done));
const r = await h.tool_result({ type: "tool_result", toolCallId: "b1", toolName: "bash", input,
  content: [{ type: "text", text: "(no output)" }], isError: false }, {});
await h.session_shutdown({ type: "session_shutdown", reason }, {});
await new Promise((done) => setTimeout(done, 500));
console.log(JSON.stringify({ note: r ? r.content[r.content.length - 1].text : null }));
"""


class ServerReaperTests(unittest.TestCase):
    def setUp(self):
        if not (shutil.which("lsof") or shutil.which("ss")):
            self.skipTest("needs lsof or ss")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def serve(self, port, background=True):
        python = Path(sys.executable).resolve()
        return f'cd "{self.tmp}" && "{python}" -m http.server --bind 127.0.0.1 {port} > /dev/null 2>&1 {"&" if background else ""}'

    def leave_nothing(self, port):
        self.addCleanup(lambda: subprocess.run(["pkill", "-f", f"http.server --bind 127.0.0.1 {port}"], capture_output=True))

    def test_a_server_started_in_the_background_stops_when_the_session_ends(self):
        port = free_port()
        self.leave_nothing(port)
        out, stderr = run_node(self, REAPER_DRIVER, REAPER, self.serve(port), "quit")
        self.assertIn(f"127.0.0.1:{port}", out["note"])
        self.assertIn("elm-pi stops this server", out["note"])
        self.assertIn("`view` its .html file - no server is needed", out["note"])
        self.assertIn("elm-pi: stopped the server this session started", stderr)
        self.assertFalse(listening(port))

    def test_a_reload_keeps_the_server(self):
        port = free_port()
        self.leave_nothing(port)
        out, _ = run_node(self, REAPER_DRIVER, REAPER, self.serve(port), "reload")
        self.assertIsNotNone(out["note"])
        self.assertTrue(listening(port))

    def test_other_background_jobs_are_left_alone(self):
        marker = self.tmp / "still-running"
        command = f'(sleep 2; touch "{marker}") &'
        out, _ = run_node(self, REAPER_DRIVER, REAPER, command, "quit")
        self.assertIsNone(out["note"])
        time.sleep(2.5)
        self.assertTrue(marker.exists())     # a computation the user asked for outlives the session

    def test_which_commands_start_a_server(self):
        cases = {
            "python3 -m http.server --bind 127.0.0.1 8080 &": True,
            "cd site && python3 -m http.server 8000 > /dev/null 2>&1 & echo $!": True,
            "nohup npx serve -s dist": True,
            "python3 -m http.server --bind 127.0.0.1 8080": False,        # foreground: ends with its command
            "python3 build.py > out.log 2>&1 && ls": False,
            "sleep 30 &": False,
            '"/usr/local/bin/python3" -m http.server 9000 &': True,
        }
        out, _ = run_node(self, "import { pathToFileURL } from 'node:url';"
                                "const m = await import(pathToFileURL(process.argv[1]).href);"
                                "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(m.startsServer)));",
                          REAPER, json.dumps(list(cases)))
        self.assertEqual(list(cases.values()), out)

    def test_listeners_are_read_from_lsof_or_ss(self):
        lsof = "p55870\nf3\nn127.0.0.1:8080\np901\nf5\nn*:5000\n"
        ss = 'LISTEN 0 5 127.0.0.1:8080 0.0.0.0:* users:(("python3",pid=55870,fd=3))\n'
        out, _ = run_node(self, "import { pathToFileURL } from 'node:url';"
                                "const m = await import(pathToFileURL(process.argv[1]).href);"
                                "console.log(JSON.stringify([m.parseLsof(process.argv[2]), m.parseSs(process.argv[3]),"
                                " ['05:07', '1:02:03', '2-00:00:01'].map(m.parseEtime)]));",
                          REAPER, lsof, ss)
        self.assertEqual([{"pid": 55870, "addr": "127.0.0.1:8080"}, {"pid": 901, "addr": "*:5000"}], out[0])
        self.assertEqual([{"pid": 55870, "addr": "127.0.0.1:8080"}], out[1])
        self.assertEqual([307, 3723, 172801], out[2])

    def test_it_is_loaded_and_in_fast_mode(self):
        self.assertIn("server-reaper.ts", CONFIG["requiredExtensions"])
        self.assertRegex(LAUNCHER, r"for e in [^;\n]*\bserver-reaper\b")


REPORT_DRIVER = r"""
import { pathToFileURL } from "node:url";
const m = await import(pathToFileURL(process.argv[1]).href);
const h = {};
m.default({ on: (e, f) => { h[e] = f; } });
const out = [];
for (const c of JSON.parse(process.argv[2])) {
  const branch = c.asked.map((text) => ({ type: "message", message: { role: "user", content: [{ type: "text", text }] } }));
  const ctx = { cwd: process.env.SITE, sessionManager: { getBranch: () => branch } };
  const r = await h.tool_call({ type: "tool_call", toolCallId: "t", toolName: c.tool, input: c.input }, ctx);
  out.push(r?.block ? r.reason : null);
}
console.log(JSON.stringify(out));
"""
FORK = ("You are a delegated subagent running from a fork of the parent session. Treat the inherited conversation "
        "as reference-only context.\n\nTask:\n")


class ReportGuardTests(unittest.TestCase):
    def run_cases(self, cases, child=False):
        with tempfile.TemporaryDirectory() as site:
            (Path(site) / "README.md").write_text("# existing\n")
            (Path(site) / "docs").mkdir()
            out, _ = run_node(self, REPORT_DRIVER, REPORT, json.dumps(cases),
                              env={"SITE": site, "PI_SUBAGENT_CHILD": "1" if child else ""})
        return out

    def test_a_report_nobody_asked_for_is_refused(self):
        site = "make me a website about alpacas and make sure everything is 100% self-consistent"
        cases = [
            {"tool": "write", "input": {"path": "docs/SUMMARY.md", "content": "x"}, "asked": [site]},
            {"tool": "bash", "input": {"command": "cat > LINK_VERIFICATION.md << 'EOF'\n# ok\nEOF"},
             "asked": ["Can you verify all the links between pages work correctly?"]},          # test6
            {"tool": "write", "input": {"path": "README.md", "content": "x"}, "asked": [site]},   # exists: an edit
            {"tool": "write", "input": {"path": "docs/SUMMARY.md", "content": "x"}, "asked": ["write up a summary of the run"]},
            {"tool": "write", "input": {"path": "NOTES.md", "content": "x"}, "asked": ["keep NOTES.md as you go"]},
            {"tool": "write", "input": {"path": ".pi/tmp/plan-notes.md", "content": "x"}, "asked": [site]},
            {"tool": "write", "input": {"path": "index.html", "content": "x"}, "asked": [site]},
            {"tool": "bash", "input": {"command": "python3 run.py > results.csv 2>&1"}, "asked": [site]},
        ]
        out = self.run_cases(cases)
        self.assertIn("Nobody asked for SUMMARY.md: a report or summary goes in your reply", out[0])
        self.assertIn("Nobody asked for LINK_VERIFICATION.md", out[1])
        self.assertEqual([None] * 6, out[2:])

    def test_a_sub_agent_goes_by_its_own_task(self):
        """test7: a child wrote README.md, its task named only gallery.html."""
        user = "make me a website and document it in a README"          # the parent's request, not the child's
        cases = [
            {"tool": "write", "input": {"path": "CHANGES_README.md", "content": "x"},
             "asked": [user, FORK + "Create gallery.html. Write it to gallery.html."]},
            {"tool": "write", "input": {"path": "SITE_README.md", "content": "x"},
             "asked": [user, FORK + "Write SITE_README.md describing the pages."]},
        ]
        refused, named = self.run_cases(cases, child=True)
        self.assertIn("Create it only when your task names it", refused)
        self.assertIsNone(named)

    def test_it_is_loaded_and_in_fast_mode(self):
        self.assertIn("report-guard.ts", CONFIG["requiredExtensions"])
        self.assertRegex(LAUNCHER, r"for e in [^;\n]*\breport-guard\b")


class DateNoteTests(unittest.TestCase):
    def test_the_system_prompt_has_todays_date_as_a_section(self):
        out, _ = run_node(self, "import { pathToFileURL } from 'node:url';"
                                "const m = await import(pathToFileURL(process.argv[1]).href); const h = {};"
                                "m.default({ on: (e, f) => { h[e] = f; } });"
                                "const event = { type: 'before_agent_start', messageType: 'user', prompt: 'x',"
                                " systemPrompt: 'You are pi.', systemPromptOptions: { sections: { cwd: '/x' } } };"
                                "const r = await h.before_agent_start(event, {});"
                                "console.log(JSON.stringify([m.today(new Date(2026, 10, 12, 23, 59)), r ?? null,"
                                " event.systemPromptOptions.sections]));",
                          DATE)
        fixed, returned, sections = out
        self.assertEqual("Today's date is Thursday 2026-11-12.", fixed)
        self.assertIsNone(returned)          # no replacement prompt: see the test below
        self.assertEqual("/x", sections["cwd"])
        self.assertRegex(sections["date"], r"^Today's date is \w+day \d{4}-\d{2}-\d{2}\.$")

    def test_no_extension_replaces_the_system_prompt(self):
        """A returned `systemPrompt` is sent in place of the sections, rendered when its handler
        runs: date-note's first version did that, and the sections pinned-instructions and
        remote-research add after it (extensions load in name order) never reached the model."""
        for source in sorted((ROOT / "templates/extensions").glob("*.ts")):
            with self.subTest(source.name):
                self.assertNotRegex(source.read_text(), r"\bsystemPrompt\s*:", "use event.systemPromptOptions.sections")

    def test_it_is_loaded_and_in_fast_mode(self):
        self.assertIn("date-note.ts", CONFIG["requiredExtensions"])
        self.assertRegex(LAUNCHER, r"for e in [^;\n]*\bdate-note\b")


if __name__ == "__main__":
    unittest.main()
