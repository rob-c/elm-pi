"""command-guard.ts: parallel children must not create or remove a shared scratch virtualenv.

In both python-before and python-after parallel.1 (2026-11-15), both Qwen children
chose .pi/tmp/venv. One child's cleanup deleted the environment under its sibling.
The second run reproduced the shared path despite the new unique-scratch prompt.
"""

import json
import unittest

from tests.extension_harness import run_extension


def verdicts(test, commands, child=True, files=None):
    return run_extension(test, "command-guard", """
        const results = [];
        for (const command of %s) {
            const input = command.replaceAll("{cwd}", ctx.cwd);
            const result = await registered.handlers.tool_call[0]({ toolName: "bash",
                toolCallId: "scratch", input: { command: input } }, ctx);
            results.push(result ?? null);
        }
        out(results);
    """ % json.dumps(commands), files=files, env={"PI_SUBAGENT_CHILD": "1" if child else "0"})


class ChildScratchTests(unittest.TestCase):
    def test_observed_shared_venv_creation_and_cleanup_are_refused(self):
        commands = [
            "python3 -m venv .pi/tmp/venv && source .pi/tmp/venv/bin/activate && pip install pytest",
            "mkdir -p .pi/tmp && python3 -m venv .pi/tmp/venv && source .pi/tmp/venv/bin/activate && pip install pytest -q",
            "rm -rf .pi/tmp/venv",
            "rm -rf .pi/tmp/venv .pytest_cache __pycache__",
        ]
        for command, got in zip(commands, verdicts(self, commands)):
            with self.subTest(command=command):
                self.assertIsNotNone(got)
                self.assertTrue(got["block"])
                self.assertIn("mktemp -d .pi/tmp/child.XXXXXX", got["reason"])

    def test_quoting_wrappers_absolute_paths_and_cd_keep_the_same_boundary(self):
        commands = [
            '/usr/bin/python3 -m venv "{cwd}/.pi/tmp/venv"',
            "env python3 -m venv './.pi/tmp/venv/'",
            "cd .pi/tmp && python3 -m venv venv",
            "bash -c 'python3 -m venv .pi/tmp/venv'",
            "python3 -mvenv .pi/tmp/venv",
            "python3 -m virtualenv .pi/tmp/venv",
            "virtualenv --python python3 .pi/tmp/venv",
            "uv venv --python python3 .pi/tmp/venv",
            "uv -q venv .pi/tmp/venv",
            "uv --no-managed-python venv .pi/tmp/venv",
            'rm -rf "{cwd}/.pi/tmp/venv/lib"',
            "mv .pi/tmp/venv .pi/tmp/old",
            "rm -rf .pi/tmp",
            "cd .pi && rm -rf tmp",
        ]
        for command, got in zip(commands, verdicts(self, commands)):
            with self.subTest(command=command):
                self.assertIsNotNone(got)
                self.assertTrue(got["block"])

    def test_private_envs_prepared_env_usage_and_unrelated_commands_remain_allowed(self):
        commands = [
            "mkdir -p .pi/tmp && mktemp -d .pi/tmp/child.XXXXXX",
            "python3 -m venv .pi/tmp/child.ABC123/venv",
            "rm -rf .pi/tmp/child.ABC123",
            "python3 -m venv .venv",
            "source .pi/tmp/venv/bin/activate && pytest test_words.py -v",
            "cat .pi/tmp/venv/pyvenv.cfg",
            "ls -la .pi/tmp/venv",
            "python3 -m venv --help .pi/tmp/venv",
            "python3 -m venv --prompt .pi/tmp/venv .pi/tmp/child.ABC123/env",
            "echo python3 -m venv .pi/tmp/venv",
            "echo rm -rf .pi/tmp/venv",
            "python3 -c 'print(1)' -m venv .pi/tmp/venv",
            "python3 runner.py -m venv .pi/tmp/venv",
            "rm -rf other/.pi/tmp/venv",
        ]
        got = verdicts(self, commands, files={".pi/tmp/venv/pyvenv.cfg": "home = /usr/bin\n"})
        self.assertEqual([None] * len(commands), got)

    def test_the_parent_can_prepare_or_clean_a_shared_environment(self):
        commands = ["python3 -m venv .pi/tmp/venv", "rm -rf .pi/tmp/venv", "rm -rf .pi/tmp"]
        self.assertEqual([None] * len(commands), verdicts(self, commands, child=False))


if __name__ == "__main__":
    unittest.main()
