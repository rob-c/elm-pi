"""help.ts: the session's own commands, skills and tools, read from what pi reports."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

FIXTURE = """
globalThis.__commands = [
  { name: "mode", description: "change the permission mode", source: "extension" },
  { name: "todos", description: "the session's plan", source: "extension" },
  { name: "review", description: "Review work for correctness", source: "prompt" },
  { name: "plot", description: "Plot data properly", source: "prompt" },
  { name: "skill:data-fitting", source: "skill" },
  { name: "skill:changing-code", source: "skill" },
  { name: "skill:astropy", description: "astronomy", source: "skill", sourceInfo: { path: "/i/agent/skills/kdense/astropy/SKILL.md" } },
  { name: "skill:sympy", description: "symbolic maths", source: "skill", sourceInfo: { path: "/i/agent/skills/kdense/sympy/SKILL.md" } },
];
globalThis.__tools = [
  { name: "bash", description: "Execute a shell command" },
  { name: "write" }, { name: "view" }, { name: "web_search" }
];
globalThis.__active = ["bash", "write", "view"];
"""


def help_text(test, args=""):
    out = run_extension(test, "help", FIXTURE + f"""
        const command = registered.commands["help"];
        command.handler({args!r}, ctx);
        out(registered.notes[0][0]);
    """)
    return out


class HelpTests(unittest.TestCase):
    def test_it_lists_the_commands_the_session_has_with_their_own_descriptions(self):
        text = help_text(self)
        self.assertIn("/mode - change the permission mode", text)
        self.assertIn("/review - Review work for correctness", text)

    def test_skills_are_named_without_the_skill_prefix(self):
        text = help_text(self)
        self.assertIn("data-fitting, changing-code", text)
        self.assertNotIn("skill:data-fitting", text)

    def test_the_library_is_a_count_and_its_index_not_167_names(self):
        text = help_text(self)
        self.assertIn("  data-fitting, changing-code\n", text)
        self.assertIn("  K-Dense library: 2 more, named when a request mentions one or loaded with /skill:<name> - "
                      "/i/agent/skills/kdense/INDEX.md", text)
        self.assertNotIn("astropy,", text)

    def test_a_filter_finds_a_library_skill_by_name(self):
        self.assertEqual("Skills (loaded automatically when a request needs them)\n  K-Dense library: astropy",
                         help_text(self, "astro").strip())

    def test_the_tools_offered_are_the_ones_pi_reports(self):
        text = help_text(self)
        self.assertIn("Tools offered now: bash, write, view", text)
        self.assertNotIn("web_search", text)

    def test_a_filter_matches_tool_names_and_descriptions(self):
        self.assertEqual("Tools offered now: bash", help_text(self, "bash").strip())
        self.assertEqual("Tools offered now: bash", help_text(self, "shell").strip())

    def test_a_disabled_tool_is_not_a_match(self):
        self.assertEqual('Nothing here matches "web_search".', help_text(self, "web_search"))

    def test_it_says_where_to_read_more(self):
        self.assertIn("INSTALL.md", help_text(self))

    def test_an_argument_filters_on_name_and_description(self):
        text = help_text(self, "permission")
        self.assertIn("/mode", text)                  # by description
        self.assertNotIn("/todos", text)
        self.assertNotIn("/review", text)             # and nothing that does not match
        self.assertIn("/plot", help_text(self, "plot"))   # by name

    def test_a_filter_that_matches_nothing_says_so(self):
        self.assertIn('Nothing here matches "quantum"', help_text(self, "quantum"))

    def test_it_does_not_depend_on_a_hardcoded_list_of_commands(self):
        # The point of pi.getCommands(): a session with one command shows one command.
        out = run_extension(self, "help", """
            globalThis.__commands = [{ name: "only", description: "the only one", source: "extension" }];
            registered.commands["help"].handler("", ctx);
            out(registered.notes[0][0]);
        """)
        self.assertIn("/only - the only one", out)
        self.assertNotIn("/mode", out)

    def test_the_command_is_registered_with_a_description_for_the_menu(self):
        out = run_extension(self, "help", 'out(registered.commands["help"].description);')
        self.assertIn("commands", out)


if __name__ == "__main__":
    unittest.main()
