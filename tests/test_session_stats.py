"""scripts/session-stats: the numbers a batch is judged on, read from the session files pi writes.

The tool exists because the figures in docs/tuning/README.md were pulled by throwaway scripts three
times in one day; a number nobody can reproduce is a number nobody can check.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts/session-stats"


def entry(**kw):
    return json.dumps(kw)


def message(role, usage=None, stop=None, error=False):
    m = {"role": role}
    if usage:
        m["usage"] = usage
    if stop:
        m["stopReason"] = stop
    if error:
        m["isError"] = True
    return entry(type="message", message=m)


class SessionStatsTests(unittest.TestCase):
    def run_tool(self, *paths):
        return subprocess.run([sys.executable, str(TOOL), *map(str, paths)], capture_output=True, text=True)

    def project(self, lines, name="s1"):
        folder = Path(tempfile.mkdtemp()) / "proj"
        (folder / ".pi/sessions").mkdir(parents=True)
        (folder / ".pi/sessions" / f"{name}.jsonl").write_text("\n".join(lines) + "\n")
        return folder

    def test_it_counts_requests_tokens_and_the_largest_request(self):
        folder = self.project([
            entry(type="session"),
            message("user"),
            message("assistant", {"input": 100, "output": 10}, stop="tool_use"),
            message("assistant", {"input": 900, "output": 20}, stop="stop"),
        ])
        out = self.run_tool(folder)
        self.assertEqual(0, out.returncode, out.stderr)
        self.assertIn("| s1 | 2 | 1,000 | 900 |", out.stdout)
        self.assertIn("every session ended stop", out.stdout)

    def test_a_session_that_did_not_finish_is_named(self):
        # The bug this is here for: `last turn: aborted` went unnoticed for a day.
        folder = self.project([message("assistant", {"input": 50, "output": 5}, stop="aborted")])
        out = self.run_tool(folder)
        self.assertIn("did not end on stop: s1", out.stdout)

    def test_compactions_tool_errors_and_cache_share_come_out(self):
        folder = self.project([
            message("assistant", {"input": 200, "output": 5, "cacheRead": 150}, stop="tool_use"),
            message("toolResult", error=True),
            entry(type="compaction", summary="..." * 10),
        ])
        out = self.run_tool(folder)
        self.assertIn("| 75% |", out.stdout)
        self.assertIn("| 1 | 1 |", out.stdout)

    def test_it_takes_a_sessions_folder_or_a_folder_of_projects(self):
        one = self.project([message("assistant", {"input": 10, "output": 1}, stop="stop")])
        out = self.run_tool(one / ".pi/sessions")
        self.assertIn("| s1 | 1 | 10 |", out.stdout)

    def test_a_folder_with_no_sessions_says_so_and_fails(self):
        empty = Path(tempfile.mkdtemp())
        out = self.run_tool(empty)
        self.assertEqual(1, out.returncode)
        self.assertIn("no .pi/sessions", out.stderr)

    def test_a_truncated_line_does_not_lose_the_rest(self):
        folder = self.project([message("assistant", {"input": 30, "output": 3}, stop="stop"), "{not json"])
        out = self.run_tool(folder)
        self.assertEqual(0, out.returncode, out.stderr)
        self.assertIn("| 30 |", out.stdout)

    def test_it_is_python39_and_reads_only(self):
        source = TOOL.read_text()
        self.assertNotIn("match ", source)          # 3.10 syntax
        self.assertNotIn("Path.readlink", source)
        self.assertIn("Path", source)


if __name__ == "__main__":
    unittest.main()
