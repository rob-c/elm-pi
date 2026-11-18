"""templates/extensions/standing-rules.ts: rules the user set for the work that follows come back with each later request.

The sessions: long-keep.1-3, thinking off and high (long-session scenarios, 2026-11-17): six house rules in message 1,
six small requests after it, and three sessions of six ended with a file that broke one.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extension_harness import run_extension  # noqa: E402

RULES = ("I need a services.json for the lab cluster and we will build it up over a few messages. House rules, which apply to "
         "everything we add: every port is an even number from 9000 to 9998; names are lowercase words joined by hyphens, never "
         "underscores; and the list is kept sorted by name. Start with one service: a web front end called frontdoor on port 9000.")
HELPERS = """
const say = async (prompt, messageType = "user") => (await registered.handlers.before_agent_start[0]({ messageType, prompt }, ctx)) ?? null;
"""


class StandingRulesTests(unittest.TestCase):
    def session(self, *prompts, env=None):
        body = HELPERS + "const got = [];\n" + "".join("got.push(await say(%r));\n" % p for p in prompts) + "out(got);"
        return run_extension(self, "standing-rules", body, env=env)

    def test_the_rules_come_back_word_for_word_with_every_later_request(self):
        first, second, third = self.session(RULES, "Rename the Redis cache to session_cache.", "Finally add an API gateway.")
        self.assertIsNone(first)                                         # not in the turn that set them
        for got in (second, third):
            self.assertEqual("standing-rules", got["message"]["customType"])
            content = got["message"]["content"]
            self.assertTrue(content.startswith("Earlier in this session the user set rules for the work that follows:"), content)
            self.assertIn('"""\n%s\n"""' % RULES, content)                   # the user's words, not a summary
            self.assertIn("check what you changed - and what else the change moved - against each rule", content)
            self.assertIn("follow the rule and say so in one line", content)

    def test_a_session_with_no_rules_gets_nothing(self):
        got = self.session("Fix the failing test in test_stats.py", "It never passes on my machine - always times out. Try again.",
                           "Now add a median function.")
        self.assertEqual([None, None, None], got)

    def test_the_phrases_that_set_rules(self):
        for text, sets in (
                ("From now on use natural units in every formula.", True),
                ("For the rest of this session, don't touch analysis/.", True),
                ("Ground rules: tabs not spaces, and no new dependencies.", True),
                ("Use SI units unless I say otherwise.", True),
                ("These conventions apply to everything we write: British spelling, 80 columns.", True),
                ("This test always fails and the build never finishes.", False),
                ("What are the house prices in the dataset?", False),
                ("Apply the patch to everything in src/.", False)):
            with self.subTest(text=text):
                got = self.session(text, "next request")
                self.assertEqual(sets, got[1] is not None)

    def test_a_later_rule_is_added_to_the_first_and_the_two_most_recent_are_kept(self):
        got = self.session(RULES, "From now on every service also has a contact field.", "Add a cache.",
                           "Ground rules for the docs too: British spelling.", "Add a worker.")
        self.assertIn(RULES, got[2]["message"]["content"])
        self.assertIn("From now on every service also has a contact field.", got[2]["message"]["content"])
        self.assertIn("in these messages:", got[2]["message"]["content"])
        last = got[4]["message"]["content"]
        self.assertNotIn("House rules", last)                                # the oldest of three has gone
        self.assertIn("contact field", last)
        self.assertIn("British spelling", last)

    def test_a_very_long_message_is_cut_and_says_so(self):
        long = "House rules: " + "every name is lowercase. " * 200
        content = self.session(long, "next")[1]["message"]["content"]
        self.assertIn(" [...]", content)
        self.assertLess(len(content), 2200)

    def test_not_on_a_notice_and_not_in_a_sub_agent(self):
        got = run_extension(self, "standing-rules", HELPERS + "await say(%r); out(await say('a child has finished', 'extension'));" % RULES)
        self.assertIsNone(got)
        self.assertEqual([None, None], self.session(RULES, "next", env={"PI_SUBAGENT_CHILD": "1"}))


if __name__ == "__main__":
    unittest.main()
