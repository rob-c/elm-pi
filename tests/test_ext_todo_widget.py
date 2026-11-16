"""todo.ts's live plan panel: the list above the editor, capped, never sent to the model.

The plan otherwise lives in scrollback and is lost at the next tool result (the plan's item 12).
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

HELPERS = """
const todo = registered.tools.todo;
const add = async (text) => todo.execute("c", { action: "add", text }, undefined, undefined, ctx);
const toggle = async (id) => todo.execute("c", { action: "toggle", id }, undefined, undefined, ctx);
const clear = async () => todo.execute("c", { action: "clear" }, undefined, undefined, ctx);
const afterToolCall = async () => await registered.handlers.tool_result[0]({ toolName: "todo", isError: false }, ctx);
"""


def widget(test, extra):
    return run_extension(test, "todo", HELPERS + extra + '''
        const value = registered.widgets.todos;
        out({ todos: typeof value === "function" ? value({}, {}).render(1000) : value });
    ''')


class TodoWidgetTests(unittest.TestCase):
    def test_the_list_appears_above_the_editor_after_a_todo_call(self):
        got = widget(self, """
            await add("read the data");
            await afterToolCall();
        """)
        self.assertEqual(["plan 0/1", "☐ read the data"], got["todos"])

    def test_a_completed_item_is_ticked_and_counted(self):
        got = widget(self, """
            await add("one"); await add("two"); await toggle(1); await afterToolCall();
        """)
        self.assertEqual(["plan 1/2", "☑ one", "☐ two"], got["todos"])

    def test_the_panel_is_capped_and_counts_the_rest(self):
        got = widget(self, """
            for (const t of ["a","b","c","d","e","f","g"]) await add(t);
            await afterToolCall();
        """)
        self.assertEqual(5, len(got["todos"]), "the panel never takes more than five lines")
        self.assertEqual("… and 4 more", got["todos"][-1], "three shown, four hidden")

    def test_an_empty_list_hides_the_panel(self):
        got = widget(self, """
            await add("gone"); await clear(); await afterToolCall();
        """)
        self.assertEqual([], got["todos"])

    def test_another_tool_does_not_repaint_it(self):
        got = widget(self, """
            await add("one"); await afterToolCall();
            await registered.handlers.tool_result[0]({ toolName: "bash", isError: false }, ctx);
        """)
        self.assertEqual(["plan 0/1", "☐ one"], got["todos"])

    def test_a_resumed_session_shows_the_list_it_reconstructed(self):
        # session_start rebuilds from the branch; the panel must show that, not an empty list.
        got = widget(self, """
            await add("survived"); await afterToolCall();
            ctx.sessionManager.getBranch = () => [{ type: "message", message: { role: "toolResult",
                toolName: "todo", details: { action: "add", todos: [{ id: 1, text: "survived", done: false }], nextId: 2 } } }];
            await registered.handlers.session_start[0]({}, ctx);
        """)
        self.assertEqual(["plan 0/1", "☐ survived"], got["todos"])

    def test_the_actual_terminal_widget_keeps_its_cap_after_wrapping(self):
        got = run_extension(self, "todo", HELPERS + r'''
            const { InteractiveMode } = await import("@earendil-works/pi-coding-agent");
            const { visibleWidth } = await import("@earendil-works/pi-tui");
            for (let i = 0; i < 7; i++) await add("Long task: " + "測定 🧪 ".repeat(30) + "\nnext line\nthird line");
            await afterToolCall();
            const mode = Object.create(InteractiveMode.prototype);
            mode.extensionWidgetsAbove = new Map(); mode.extensionWidgetsBelow = new Map();
            mode.ui = {}; mode.renderWidgets = () => {};
            mode.setExtensionWidget("todos", registered.widgets.todos);
            const panel = mode.extensionWidgetsAbove.get("todos");
            out([10, 40, 80].map(width => {
                const lines = panel.render(width);
                return { width, lines: lines.length, widths: lines.map(visibleWidth), multiline: lines.some(l => l.includes("\n")) };
            }));
        ''')
        for result in got:
            self.assertEqual(5, result["lines"], result)
            self.assertFalse(result["multiline"], result)
            self.assertLessEqual(max(result["widths"]), result["width"], result)

    def test_multiline_text_is_compact_on_screen_and_unchanged_in_the_list(self):
        got = run_extension(self, "todo", HELPERS + r'''
            await add("first\nsecond\tthird"); await afterToolCall();
            const value = registered.widgets.todos;
            const lines = typeof value === "function" ? value({}, {}).render(1000) : value;
            const list = await todo.execute("c", { action: "list" }, undefined, undefined, ctx);
            out({ lines, text: list.details.todos[0].text });
        ''')
        self.assertEqual(["plan 0/1", "☐ first second third"], got["lines"])
        self.assertEqual("first\nsecond\tthird", got["text"])

    def test_the_todos_dialog_keeps_multiline_items_on_one_terminal_row(self):
        got = run_extension(self, "todo", HELPERS + r'''
            await add("first\nsecond\tthird");
            ctx.ui.custom = async factory => {
                const theme = { fg: (_kind, text) => text };
                const dialog = factory({}, theme, {}, () => {});
                out(dialog.render(30));
            };
            await registered.commands.todos.handler("", ctx);
        ''')
        self.assertTrue(all("\n" not in row and "\t" not in row for row in got), got)
        self.assertIn("  ○ #1 first second third", got)

    def test_a_streaming_call_without_an_action_has_no_undefined_label(self):
        got = run_extension(self, "todo", HELPERS + '''
            const theme = { fg: (_kind, text) => String(text), bold: text => text };
            out(todo.renderCall({}, theme, {}).render(30).map(line => line.trimEnd()));
        ''')
        self.assertEqual(["todo"], got)


if __name__ == "__main__":
    unittest.main()
