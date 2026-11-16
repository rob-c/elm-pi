"""The Python-port treadmill found a blank .env reported as a broken Qwen config.

Run bootstrap's actual verification block with a local listing command, preserving
the distinction between unavailable credentials, a refused launch and a bad model.
"""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VerificationDiagnosticsTests(unittest.TestCase):
    def verify(self, listing, status=0, error=""):
        source = (ROOT / "bootstrap.bash").read_text()
        start = source.index('say "verifying the ELM-only policy"')
        end = source.index("# The same files against the schemas", start)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            launcher = path / "pi"
            launcher.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_LISTING"\n'
                                'printf "%s\\n" "$TEST_ERROR" >&2\nexit "$TEST_STATUS"\n')
            launcher.chmod(0o755)
            script = 'set -euo pipefail\nHERE="$PWD"\nCONFIG_TOOL=unused\n'
            script += 'say() { :; }; die() { echo "ERROR: $*" >&2; exit 1; }; elm_py() { echo Qwen/Test; }\n'
            script += source[start:end]
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "TEST_LISTING": listing,
                   "TEST_STATUS": str(status), "TEST_ERROR": error}
            return subprocess.run(["/bin/bash", "-c", script], cwd=tmp, env=env,
                                  capture_output=True, text=True, timeout=10)

    def test_no_available_models_keeps_stdout_and_names_the_missing_key_possibility(self):
        run = self.verify("No models available. Configure authentication.")
        self.assertEqual(1, run.returncode)
        self.assertIn("No models available. Configure authentication.", run.stderr)
        self.assertIn("check that .env supplies ELM_API_KEY", run.stderr)

    def test_refused_launch_keeps_exit_status_and_error(self):
        run = self.verify("", status=23, error="pi: no usable Python")
        self.assertEqual(1, run.returncode)
        self.assertIn("pi --list-models failed (exit 23)", run.stderr)
        self.assertIn("pi: no usable Python", run.stderr)
        self.assertNotIn("did not list elm", run.stderr)

    def test_listing_and_policy_checks_still_run(self):
        good = self.verify("provider model\nelm Qwen/Test 262K")
        self.assertEqual(0, good.returncode, good.stderr)
        commercial = self.verify("elm Qwen/Test 262K\nopenai forbidden 128K")
        self.assertEqual(1, commercial.returncode)
        self.assertIn("commercial providers are still visible", commercial.stderr)
        bad_schema = self.verify("elm Qwen/Test 262K", error="errors loading models.json")
        self.assertEqual(1, bad_schema.returncode)
        self.assertIn("pi reported errors in agent/models.json", bad_schema.stderr)
