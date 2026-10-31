from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def policy(*args: str) -> tuple[bool, str]:
    script = r'''
source "$1/lib/policy.sh"
shift
export ELM_ALLOWED_PROVIDERS="elm elm-shim"
export ELM_QWEN_MODEL_ID="Qwen/Qwen3.5-397B-A17B-FP8"
export ELM_LLAMA_MODEL_ID="meta-llama/Llama-3.3-70B-Instruct"
if elm_policy_check_args "$@"; then
  printf 'ALLOW'
else
  printf 'DENY:%s' "$ELM_POLICY_ERROR"
fi
'''
    result = subprocess.run(
        ["bash", "-c", script, "policy-test", str(ROOT), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    return result == "ALLOW", result


def extensions_disabled(*args: str) -> bool:
    script = r'''
source "$1/lib/policy.sh"
shift
elm_policy_extensions_disabled "$@"
'''
    return subprocess.run(
        ["bash", "-c", script, "policy-test", str(ROOT), *args],
        check=False,
    ).returncode == 0


class PolicyTests(unittest.TestCase):
    def test_allowed_models_and_provider(self):
        self.assertTrue(policy("--provider", "ELM", "--model", "elm/Qwen/x")[0])
        self.assertTrue(policy("--model", "Qwen/Qwen3.5-397B-A17B-FP8")[0])
        self.assertTrue(policy("--model=elm-shim/meta-llama/Llama-3.3-70B-Instruct")[0])

    def test_unknown_and_case_variant_providers_are_denied(self):
        for args in (
            ("--provider", "ANTHROPIC"),
            ("--model", "Anthropic/claude"),
            ("--model", "meta/muse-spark-1.3"),
            ("--models", " elm/*, OPENAI/*"),
        ):
            with self.subTest(args=args):
                allowed, message = policy(*args)
                self.assertFalse(allowed, message)

    def test_api_key_is_denied(self):
        self.assertFalse(policy("--api-key=secret")[0])

    def test_last_repeated_option_matches_upstream(self):
        self.assertTrue(policy("--provider", "anthropic", "--provider", "elm")[0])
        self.assertFalse(policy("--provider", "elm", "--provider", "anthropic")[0])

    def test_double_dash_ends_option_parsing(self):
        self.assertTrue(policy("--", "--model", "anthropic/claude")[0])

    def test_extension_disable_aliases_are_detected_before_double_dash(self):
        self.assertTrue(extensions_disabled("--no-extensions"))
        self.assertTrue(extensions_disabled("-ne"))
        self.assertFalse(extensions_disabled("--", "-ne"))

    def test_extensions_of_the_callers_choosing_are_refused(self):
        for args in (
            ("-e", "./ssh.ts", "--ssh", "host"),
            ("--extension", "npm:@llblab/pi-telegram"),
            ("--extension=./bridge.ts",),
            ("-p", "hi", "-e", "builtin:mcp"),
        ):
            with self.subTest(args=args):
                allowed, message = policy(*args)
                self.assertFalse(allowed, message)
                self.assertIn("--extension is disabled", message)
        # After -- it is prompt text, and a dangling -e is pi's error to report.
        self.assertTrue(policy("--", "-e", "./ssh.ts")[0])
        self.assertTrue(policy("-e")[0])

    def test_launcher_checks_the_callers_arguments_not_its_own(self):
        launcher = (ROOT / "pi").read_text()
        # Its own -e arguments (--fast, -ne) go into PRE, which the guard never sees.
        self.assertIn('elm_policy_check_args "$@"', launcher)
        self.assertNotIn('elm_policy_check_args "${PRE', launcher)

    def test_tools_that_move_data_past_the_proxy_are_denied(self):
        config = json.loads((ROOT / "templates/extensions/pi-permission-system/config.json").read_text())
        bash = config["permission"]["bash"]
        for pattern in ("ssh *", "scp *", "sftp *", "rsync *:*", "sshfs *", "mosh *",
                        "nc *", "socat *", "ngrok *", "cloudflared *", "tailscale funnel*"):
            with self.subTest(pattern=pattern):
                rule = bash[pattern]
                self.assertEqual("deny", rule["action"])
                self.assertIn("LOCKDOWN.md", rule["reason"])
        # Last match wins: the denials must come after the catch-all.
        self.assertEqual("*", next(iter(bash)))
        self.assertNotIn("rsync *", bash)  # a local rsync is an ordinary copy

    def test_package_subcommands_do_not_treat_models_as_a_value(self):
        self.assertTrue(policy("update", "--models", "--force")[0])
        self.assertTrue(policy("install", "--models")[0])


if __name__ == "__main__":
    unittest.main()
