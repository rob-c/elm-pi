from __future__ import annotations

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

    def test_package_subcommands_do_not_treat_models_as_a_value(self):
        self.assertTrue(policy("update", "--models", "--force")[0])
        self.assertTrue(policy("install", "--models")[0])


if __name__ == "__main__":
    unittest.main()
