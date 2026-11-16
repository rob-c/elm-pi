"""status-line.ts: --remote and a non-default model stay visible; ordinary sessions show nothing."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

QWEN = "Qwen/Qwen3.5-397B-A17B-FP8"
MISTRAL = "mistralai/Mistral-Small-4-119B-2603"


def status(test, model=QWEN, name="Qwen 3.5 397B", default=QWEN, tools=("read", "bash")):
    """The footer line after one session_start, with a throwaway agent/settings.json as the install's."""
    agent = Path(tempfile.mkdtemp()) / "agent"
    agent.mkdir()
    (agent / "settings.json").write_text(json.dumps({"defaultModel": default}))
    out = run_extension(test, "status-line", f"""
        process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
        globalThis.__active = {json.dumps(list(tools))};
        ctx.model = {{ id: {json.dumps(model)}, name: {json.dumps(name)} }};
        await registered.handlers.session_start[0]({{}}, ctx);
        out(registered.statuses["elm-pi"] ?? null);
    """)
    return out


class StatusLineTests(unittest.TestCase):
    def test_the_ordinary_session_shows_nothing(self):
        self.assertEqual("", status(self))

    def test_remote_is_named(self):
        self.assertEqual("web", status(self, tools=("read", "bash", "web_search")))

    def test_a_model_that_is_not_the_default_is_named(self):
        self.assertEqual("Mistral Small 4 119B", status(self, model=MISTRAL, name="Mistral Small 4 119B"))

    def test_both_together_are_one_line(self):
        self.assertEqual("Mistral Small 4 119B · web",
                         status(self, model=MISTRAL, name="Mistral Small 4 119B", tools=("web_search",)))

    def test_a_session_with_no_settings_file_still_paints(self):
        agent = Path(tempfile.mkdtemp()) / "agent"
        agent.mkdir()
        got = run_extension(self, "status-line", f"""
            process.env.PI_CODING_AGENT_DIR = {json.dumps(str(agent))};
            globalThis.__active = ["read"];
            ctx.model = {{ id: "x", name: "Something" }};
            await registered.handlers.session_start[0]({{}}, ctx);
            out(registered.statuses["elm-pi"] ?? null);
        """)
        self.assertEqual("Something", got)   # no known default, so any model is worth naming

    def test_it_repaints_each_turn_so_a_model_change_shows(self):
        out = run_extension(self, "status-line", f"""
            globalThis.__active = ["read"];
            ctx.model = {{ id: "a", name: "First" }};
            await registered.handlers.agent_start[0]({{}}, ctx);
            ctx.model = {{ id: "b", name: "Second" }};
            await registered.handlers.agent_start[0]({{}}, ctx);
            out(registered.statuses["elm-pi"]);
        """)
        self.assertEqual("Second", out)

    def test_a_model_selected_between_turns_is_visible_immediately(self):
        out = run_extension(self, "status-line", '''
            globalThis.__active = ["read"];
            ctx.model = { id: "a", name: "First" };
            await registered.handlers.session_start[0]({}, ctx);
            ctx.model = { id: "b", name: "Second" };
            for (const handler of registered.handlers.model_select ?? [])
                await handler({ type: "model_select", model: ctx.model, source: "cycle" }, ctx);
            out(registered.statuses["elm-pi"]);
        ''')
        self.assertEqual("Second", out)


if __name__ == "__main__":
    unittest.main()
