"""empty-state.ts: three lines on a first session, nothing on a resumed one or without a screen."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402


def agent_dir(templates=("explain", "fix", "plot", "review"), install="install"):
    """A throwaway agent/ directory with prompt templates in it, and its install folder."""
    root = Path(tempfile.mkdtemp()) / install
    (root / "agent/prompts").mkdir(parents=True)
    for name in templates:
        (root / "agent/prompts" / f"{name}.md").write_text("---\ndescription: x\n---\nbody\n")
    (root / "agent/reference").mkdir()
    (root / "INSTALL.md").write_text("x")
    return root / "agent"


class EmptyStateTests(unittest.TestCase):
    def lines(self, reason=None, has_ui=True, templates=("explain", "plot", "review"), extra=""):
        agent = agent_dir(templates)
        script = f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            ctx.hasUI = {str(has_ui).lower()};
            {extra}
            await registered.handlers.session_start[0]({json.dumps({"reason": reason})}, ctx);
            out(registered.notes);
        """
        return run_extension(self, "empty-state", script)

    def test_a_new_session_gets_three_lines_naming_what_exists(self):
        notes = self.lines()
        self.assertEqual(1, len(notes))
        text = notes[0][0]
        self.assertEqual(3, len(text.splitlines()))
        self.assertIn("`/help`", text)
        self.assertIn("`/explain`", text)
        self.assertIn("`/plot`", text)
        self.assertIn("INSTALL.md", text)

    def test_a_template_that_is_not_installed_is_not_named(self):
        text = self.lines(templates=("plot",))[0][0]
        self.assertIn("`/plot`", text)
        self.assertNotIn("/explain", text)

    def test_a_session_with_no_templates_names_only_help(self):
        text = self.lines(templates=())[0][0]
        self.assertIn("`/help`", text)
        self.assertNotIn("prompt templates", text)

    def test_a_resumed_or_forked_session_says_nothing(self):
        self.assertEqual([], self.lines(reason="resume"))
        self.assertEqual([], self.lines(reason="fork"))

    def test_a_session_resumed_from_the_cli_says_nothing(self):
        # pi emits startup for --continue/--resume as well: the loaded branch is the distinction.
        self.assertEqual([], self.lines(reason="startup", extra='''
            ctx.sessionManager.getBranch = () => [{ type: "message",
                message: { role: "user", content: "An earlier request" } }];
        '''))

    def test_startup_without_messages_still_shows_the_greeting(self):
        self.assertEqual(1, len(self.lines(reason="startup", extra='''
            ctx.sessionManager.getBranch = () => [{ type: "model_change", modelId: "qwen" }];
        ''')))

    def test_a_run_without_a_screen_says_nothing(self):
        self.assertEqual([], self.lines(has_ui=False))

    def test_it_never_asks_to_read_a_file_it_does_not_know_exists(self):
        # Three lines, no offer: the rules in APPEND_SYSTEM forbid offering to read the docs.
        text = self.lines()[0][0]
        for word in ("shall I", "would you like", "offer"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
