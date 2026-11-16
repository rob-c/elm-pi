"""The Python-port treadmill must report failed installs and dead sessions as failures.

These run the actual driver and batch wrapper with small local stand-ins: no ELM
requests, downloaded dependencies or credentials are needed.
"""
import json
import os
from pathlib import Path
import shlex
import signal
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "docs/tuning/harness/treadmill"
NODE = str(ROOT / ".node/bin/node") if (ROOT / ".node/bin/node").exists() else shutil.which("node")


def executable(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)
    return path


@unittest.skipUnless(NODE, "needs Node for the real RPC driver")
class DriverTests(unittest.TestCase):
    def run_driver(self, script=None, max_seconds=20):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            launcher = project / "pi"
            if script is not None:
                executable(launcher, "#!" + NODE + "\n" + script)
            log = project / "rpc.jsonl"
            run = subprocess.run([NODE, str(HARNESS / "drive.mjs"), str(launcher), tmp,
                                  str(log), "[]", '["Say OK"]', str(max_seconds)],
                                 capture_output=True, text=True, timeout=15)
            rows = [json.loads(line) for line in log.read_text().splitlines()]
        return run, rows

    def test_missing_launcher_has_a_finish_and_nonzero_status(self):
        run, rows = self.run_driver()
        self.assertNotEqual(0, run.returncode)
        self.assertEqual("launcher error", next(r["finish"] for r in rows if "finish" in r))
        self.assertTrue(any("ENOENT" in r.get("error", "") for r in rows))

    def test_clean_and_failed_premature_exits_are_never_success(self):
        for status in (0, 7):
            with self.subTest(status=status):
                run, rows = self.run_driver(f'process.stderr.write("startup refused\\n"); process.exit({status});')
                self.assertEqual(status or 1, run.returncode)
                self.assertEqual("launcher exited before completion", next(r["finish"] for r in rows if "finish" in r))
                self.assertTrue(any("startup refused" in r.get("stderr", "") for r in rows))

    def test_timeout_is_a_failure(self):
        run, rows = self.run_driver("setInterval(() => {}, 1000);", max_seconds=0.01)
        self.assertNotEqual(0, run.returncode)
        self.assertEqual("time limit", next(r["finish"] for r in rows if "finish" in r))

    def test_wall_clock_jump_does_not_expire_a_monotonic_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            preload = project / "jump-clock.mjs"
            preload.write_text('''
const wallNow = Date.now;
const interval = globalThis.setInterval;
const timeout = globalThis.setTimeout;
let jump = 0;
Date.now = () => wallNow() + jump;
globalThis.setInterval = (fn, ms, ...args) => interval(() => { jump += 3600000; fn(...args); }, 5);
globalThis.setTimeout = (fn, ms, ...args) => timeout(fn, ms === 5000 ? 5 : ms, ...args);
''')
            launcher = executable(project / "pi", "#!" + NODE + '''
const {writeFileSync} = require("node:fs");
setTimeout(() => writeFileSync("still-running", "yes"), 100);
setInterval(() => {}, 1000);
''')
            log = project / "rpc.jsonl"
            run = subprocess.run([NODE, "--import", str(preload), str(HARNESS / "drive.mjs"),
                                  str(launcher), tmp, str(log), "[]", '["Say OK"]', "1"],
                                 capture_output=True, text=True, timeout=10)
            rows = [json.loads(line) for line in log.read_text().splitlines()]
            finished = next(r for r in rows if "finish" in r)
            self.assertNotEqual(0, run.returncode)
            self.assertEqual("time limit", finished["finish"])
            self.assertEqual(1, finished["secs"])
            self.assertEqual("yes", (project / "still-running").read_text())

    def test_completed_turn_uses_configurable_settle_period(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            launcher = executable(project / "pi", "#!" + NODE + r'''
process.stdin.setEncoding("utf8");
process.stdin.on("data", data => {
  if (!data.includes('"type":"prompt"')) return;
  process.stdout.write('{"type":"agent_start"}\n');
  process.stdout.write('{"type":"agent_end"}\n');
});
process.on("SIGTERM", () => process.exit(0));
setInterval(() => {}, 1000);
''')
            log = project / "rpc.jsonl"
            env = {**os.environ, "TREADMILL_SETTLE_SECONDS": "0.02"}
            run = subprocess.run([NODE, str(HARNESS / "drive.mjs"),
                                  str(launcher), tmp, str(log), "[]", '["Say OK"]', "10"],
                                 capture_output=True, text=True, timeout=5, env=env)
            rows = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(0, run.returncode, f"{run.stderr}\n{rows}")
            self.assertEqual("done", next(r["finish"] for r in rows if "finish" in r))

    def test_fragmented_unicode_and_extension_errors_survive_the_log(self):
        script = r'''
const text = JSON.stringify({type: "extension_ui_request", method: "notify", message: "Qwen: λ 中文 🐢"}) + "\n";
const bytes = Buffer.from(text);
const split = bytes.indexOf(Buffer.from("λ")) + 1;
process.stdout.write(bytes.subarray(0, split));
setTimeout(() => {
  process.stdout.write(bytes.subarray(split));
  process.stdout.write(JSON.stringify({type: "extension_error", extensionPath: "broken.ts", event: "agent_end", error: "render failed"}) + "\n");
  setTimeout(() => process.exit(8), 20);
}, 20);
'''
        run, rows = self.run_driver(script)
        self.assertEqual(8, run.returncode)
        self.assertEqual(["Qwen: λ 中文 🐢"], [r["notify"] for r in rows if "notify" in r])
        self.assertEqual(["extension broken.ts (agent_end): render failed"], [r["error"] for r in rows if "error" in r])

    @unittest.skipIf(os.name == "nt", "POSIX process groups")
    def test_crashed_launcher_does_not_leave_a_tool_holding_its_pipes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            launcher = executable(project / "pi", "#!" + NODE + r'''
const {spawn} = require("node:child_process");
const {writeFileSync} = require("node:fs");
const script = "process.on('SIGTERM', () => { require('node:fs').writeFileSync('tool-stopped', 'yes'); process.exit(0); }); process.send('ready'); setInterval(() => {}, 1000);";
const tool = spawn(process.execPath, ["-e", script], {stdio: ["ignore", "inherit", "inherit", "ipc"]});
writeFileSync("tool.pid", String(tool.pid));
tool.once("message", () => process.exit(7));
''')
            try:
                run = subprocess.run([NODE, str(HARNESS / "drive.mjs"), str(launcher), tmp,
                                      str(project / "rpc.jsonl"), "[]", '["Say OK"]', "20"],
                                     capture_output=True, text=True, timeout=10)
                self.assertEqual(7, run.returncode, run.stderr)
                self.assertEqual("yes", (project / "tool-stopped").read_text())
            finally:
                if (project / "tool.pid").exists():
                    try:
                        os.kill(int((project / "tool.pid").read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass


@unittest.skipUnless(NODE and shutil.which("git"), "needs Node and git")
class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.repo = self.base / "repo"
        self.harness = self.repo / "docs/tuning/harness/treadmill"
        self.harness.mkdir(parents=True)
        shutil.copy2(HARNESS / "batch.sh", self.harness / "batch.sh")
        self.work = self.base / "work"
        self.envfile = self.base / "empty.env"
        self.envfile.write_text("")
        self.runs = self.base / "runs.json"
        self.runs.write_text('[{"id":"one", "prompts":["Say OK"]}]')
        self.env = {**os.environ, "ELM_PI_ENV_FILE": str(self.envfile), "TREADMILL_WORK": str(self.work),
                    "TREADMILL_OUT": str(self.base / "out")}
        self.env.pop("TREADMILL_FROM", None)
        self.env.pop("TREADMILL_EXTENSION", None)
        self.env.pop("PI_CODING_AGENT_DIR", None)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                        "commit", "--allow-empty", "-qm", "fixture"], cwd=self.repo, check=True)

    def run_batch(self):
        return subprocess.run(["bash", str(self.harness / "batch.sh"), "trial", str(self.runs), "1"],
                              cwd=self.repo, env=self.env, capture_output=True, text=True, timeout=20)

    def test_bootstrap_failure_stops_before_running_sessions(self):
        executable(self.repo / "bootstrap.sh", "#!/bin/sh\necho fixture-bootstrap-failed\nexit 23\n")
        run = self.run_batch()
        self.assertEqual(23, run.returncode, run.stderr)
        self.assertIn("bootstrap failed (exit 23)", run.stderr)
        self.assertFalse((self.work / "btrial-one").exists())
        self.assertIn("fixture-bootstrap-failed", (self.base / "out/btrial/bootstrap.txt").read_text())

    def test_empty_batch_works_with_bash_3_nounset(self):
        executable(self.repo / "bootstrap.sh", "#!/bin/sh\nexit 0\n")
        (self.harness / "summary.py").write_text('print("EMPTY SUMMARY")\n')
        self.runs.write_text("[]")
        run = self.run_batch()
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertIn("EMPTY SUMMARY", (self.base / "out/btrial/summary.md").read_text())

    def test_offline_install_and_driver_failure_are_preserved(self):
        executable(self.repo / "bootstrap.sh", "#!/bin/sh\nexit 99\n")
        executable(self.repo / "scripts/dev-setup.sh", '#!/bin/sh\n[ "$1" = --from ] || exit 88\n'
                   'printf "%s\\n" "$2" > copied-from\nmkdir -p .node/bin\n'
                   + 'ln -s ' + shlex.quote(NODE) + ' .node/bin/node\n')
        self.env["TREADMILL_FROM"] = str(self.base / "source install")
        (self.harness / "drive.mjs").write_text(
            'import {writeFileSync} from "node:fs";\n'
            'writeFileSync(process.argv[4], JSON.stringify({finish:"launcher exited before completion"}) + "\\n");\n'
            'process.exit(7);\n')
        (self.harness / "analyze.py").write_text('print("ANALYZED FAILED SESSION")\n')
        (self.harness / "summary.py").write_text('print("SUMMARY PRESERVED")\n')
        run = self.run_batch()
        self.assertEqual(1, run.returncode, run.stderr)
        self.assertEqual(self.env["TREADMILL_FROM"], (self.work / "elm-pi-btrial/copied-from").read_text().strip())
        out = self.base / "out/btrial"
        self.assertIn("ANALYZED FAILED SESSION", (out / "one/report.md").read_text())
        self.assertIn("SUMMARY PRESERVED", (out / "summary.md").read_text())
        self.assertIn("one driver=7 analyzer=0", (out / "steps.txt").read_text())

    def test_empty_and_already_committed_seeds_reach_the_driver(self):
        executable(self.repo / "bootstrap.sh", '#!/bin/sh\nmkdir -p .node/bin\n'
                   + 'ln -s ' + shlex.quote(NODE) + ' .node/bin/node\n')
        (self.harness / "drive.mjs").write_text(
            'import {writeFileSync} from "node:fs";\n'
            'writeFileSync(process.argv[4], JSON.stringify({finish:"done"}) + "\\n");\n')
        (self.harness / "analyze.py").write_text('print("SESSION ANALYZED")\n')
        (self.harness / "summary.py").write_text('print("SUMMARY")\n')
        for kind in ("empty", "committed"):
            with self.subTest(seed=kind):
                seed = self.base / (kind + "-seed")
                seed.mkdir()
                if kind == "committed":
                    (seed / "seed.txt").write_text("already committed\n")
                    subprocess.run(["git", "init", "-q"], cwd=seed, check=True)
                    subprocess.run(["git", "add", "-A"], cwd=seed, check=True)
                    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                                    "commit", "-qm", "original seed"], cwd=seed, check=True)
                self.work = self.base / (kind + "-work")
                out = self.base / (kind + "-out")
                self.env.update(TREADMILL_WORK=str(self.work), TREADMILL_OUT=str(out))
                self.runs.write_text(json.dumps([{"id": "one", "prompts": ["Say OK"], "seed": str(seed)}]))
                run = self.run_batch()
                self.assertEqual(0, run.returncode, run.stdout + run.stderr)
                self.assertIn('"finish":"done"', (out / "btrial/one/rpc.jsonl").read_text().replace(" ", ""))
                self.assertIn("one driver=0 analyzer=0", (out / "btrial/steps.txt").read_text())


class ReportTests(unittest.TestCase):
    def test_missing_session_keeps_startup_errors_and_fails_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            out = base / "btrial/one"
            out.mkdir(parents=True)
            (out / "rpc.jsonl").write_text('\n'.join(json.dumps(r, separators=(",", ":")) for r in [
                {"t": "01:02:03", "stderr": "pi: no usable Python"},
                {"t": "01:02:03", "error": "launcher refused"},
                {"t": "01:02:03", "finish": "launcher exited before completion", "dialogs": 0}]))
            run = subprocess.run([sys.executable, str(HARNESS / "analyze.py"), tmp, tmp, str(out)],
                                 capture_output=True, text=True)
            self.assertNotEqual(0, run.returncode)
            self.assertIn("NO SESSION FILE", run.stdout)
            self.assertIn("pi: no usable Python", run.stdout)
            self.assertIn("DRIVER ERROR: launcher refused", run.stdout)
            (out / "report.md").write_text(run.stdout)
            summary = subprocess.run([sys.executable, str(HARNESS / "summary.py"), str(out.parent)],
                                     capture_output=True, text=True, env={**os.environ, "TREADMILL_WORK": tmp})
            self.assertEqual(0, summary.returncode, summary.stderr)
            self.assertIn("launcher exited before completion", summary.stdout)
            self.assertIn("| 0 | 1 | 0 |", summary.stdout)

    def test_score_uses_recorded_python_and_explains_when_none_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            agent = base / "elm-pi-btrial/agent"
            agent.mkdir(parents=True)
            out = base / "treadmill-out/btrial/one.1"
            out.mkdir(parents=True)
            (out / "rpc.jsonl").write_text("")
            (base / "btrial-one.1").mkdir()
            checks = base / "checks"
            checks.mkdir()
            (checks / "one.py").write_text("assert 1 + 1 == 2\n")
            env = {**os.environ, "TREADMILL_WORK": tmp, "TREADMILL_OUT": str(base / "treadmill-out")}
            command = [sys.executable, str(HARNESS / "score.py"), "trial", tmp]
            missing = subprocess.run(command, capture_output=True, text=True, env=env)
            self.assertNotEqual(0, missing.returncode)
            self.assertIn("score: no runnable Python", missing.stderr)
            self.assertNotIn("Traceback", missing.stderr)
            (agent / "python-path").write_text(sys.executable + "\n")
            scored = subprocess.run(command, capture_output=True, text=True, env=env)
            self.assertEqual(0, scored.returncode, scored.stderr)
            self.assertIn("1/1 passed", scored.stdout)
