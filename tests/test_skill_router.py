"""The skill router: what it routes, and how it adds a skill to a session.

The routing table is run with node (type stripping, Node 22.18+/23.6+): the
extension's own module is imported, so the regexes tested are the ones pi runs.
Without a suitable node those tests skip; the static ones always run.
"""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "templates/extensions/skill-router.ts"

# Imports the router and prints, for each prompt, the skills it routes to.
RUNNER = """
const router = await import(process.argv[1]);
const prompts = JSON.parse(process.argv[2]);
console.log(JSON.stringify(prompts.map((p) => router.routesFor(p))));
"""


def node_with_type_stripping():
    node = shutil.which("node")
    if not node:
        return None
    try:
        out = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r"v(\d+)\.(\d+)", out.strip())
    if not m:
        return None
    major, minor = int(m.group(1)), int(m.group(2))
    return node if (major, minor) >= (23, 6) or (major == 22 and minor >= 18) else None


NODE = node_with_type_stripping()


def routes(prompts):
    result = subprocess.run(
        [NODE, "--no-warnings", "--input-type=module", "-e", RUNNER, str(ROUTER), json.dumps(prompts)],
        capture_output=True, text=True, timeout=60, cwd=ROOT,
    )
    if result.returncode != 0:
        raise AssertionError(f"node failed:\n{result.stderr}")
    return dict(zip(prompts, json.loads(result.stdout)))


@unittest.skipUnless(NODE, "needs node 22.18+ or 23.6+ to run the routing table")
class RoutingTableTests(unittest.TestCase):
    # Everyday software requests a reviewer saw misroute, and their neighbours.
    SOFTWARE = [
        "add integration tests for the parser and report what fails",
        "improve its efficiency",
        "make the magic number a named constant",
        "propagate the rename to every caller",
        "be systematic about it",
        "reduce coupling between modules",
        "write a bug report",
        "the derived class overrides fit()",
        "fix the performance regression in the parser",
        "add a regression test",
        "the struct fits in one cache line",
        "simulate a network failure in the tests",
        "sort the list numerically",
        "def make(cls): return cls()",
        "#[derive(Debug)] on the struct",
        "the class derives from Base",
        "fix the borrow checker error about lifetimes",
        "prove that the cache is invalidated",
        "yes, go ahead",
        "export the users table to csv",
        "add a slide-in animation to the panel",
    ]

    PHYSICS = {
        "fit this decay curve and give the half-life": "data-fitting",
        "fit a gaussian to the peak": "data-fitting",
        "propagate the uncertainties": "uncertainty-propagation",
        "what's the 5 sigma p-value": "statistics-and-significance",
        "what is the trigger efficiency": "statistics-and-significance",
        "integrate this ODE numerically": "numerical-methods",
        "simulate the orbit of the moon with RK4": "numerical-methods",
        "make beamer slides for the lecture": "physics-documents",
        "plot the histogram with matplotlib": "histogram-analysis",
        "compute the derivative of the potential": "derivation-checks",
        "derive the formula for the period": "derivation-checks",
        "what is the mass of the top quark": "physical-constants",
        "use the fine-structure constant from CODATA": "physical-constants",
        "add the systematic uncertainties in quadrature": "uncertainty-propagation",
        "now plot it": "scientific-python",
        "compile the paper to pdf": "containers",
        "pdflatex is not installed, use docker": "containers",
    }

    def test_software_requests_route_nothing(self):
        for prompt, routed in routes(self.SOFTWARE).items():
            self.assertEqual([], routed, prompt)

    def test_physics_requests_still_route(self):
        for prompt, routed in routes(list(self.PHYSICS)).items():
            self.assertIn(self.PHYSICS[prompt], routed, prompt)

    def test_histogram_with_matplotlib_routes_both(self):
        routed = routes(["plot the histogram with matplotlib"])["plot the histogram with matplotlib"]
        self.assertEqual(["histogram-analysis", "scientific-python"], routed)

    def test_a_sub_agent_is_routed_by_its_task_alone(self):
        # The qwen agent prompt, as a fork gets it, matches routes on its own
        # ("report", "numerical", "plot"...); only the task may count.
        agent = (ROOT / "templates/agents/qwen.md").read_text()
        wrapped = (
            f"<subagent_instructions>\n{agent}\nFit the data and quote the uncertainty.\n</subagent_instructions>\n\n"
            "Task: [Read from: /tmp/chain/fit-results.md]\n[Write to: /tmp/chain/out.md]\n\n"
            "rename the helper in utils.ts and update its callers"
            "\n\n---\n**Output:**\nWrite your findings to exactly this path: /tmp/report.md"
            "\n\n---\nPrevious step output:\nThe chi2 fit of the spectrum gave a 5 sigma excess."
        )
        self.assertEqual([], routes([wrapped])[wrapped])
        physics = "Task: fit this decay curve and give the half-life"
        self.assertEqual(["data-fitting"], routes([physics])[physics])

    def test_a_skill_command_does_not_route_on_the_skill_text(self):
        body = (ROOT / "templates/skills/data-fitting/SKILL.md").read_text()
        prompt = f'<skill name="data-fitting" location="/x/SKILL.md">\n{body}\n</skill>\n\nrename this variable'
        self.assertEqual([], routes([prompt])[prompt])


class MechanismTests(unittest.TestCase):
    SOURCE = ROUTER.read_text()

    def test_no_system_prompt_sections(self):
        # A section that changes per request changes the leading system message
        # and loses the prefix cache for the whole history.
        self.assertNotIn("systemPromptOptions", self.SOURCE)
        self.assertNotIn("sections.", self.SOURCE)
        self.assertNotIn("systemPrompt:", self.SOURCE)

    def test_skills_go_in_as_a_custom_message_once_per_session(self):
        self.assertRegex(self.SOURCE, r"return \{\s*message: \{ customType: MESSAGE_TYPE")
        # Read back from the compaction-aware context, not a module-level set.
        self.assertIn("skillsIn(ctx.sessionManager.buildContextEntries())", self.SOURCE)
        self.assertIn("!present.has(name)", self.SOURCE)

    def test_only_user_prompts_route(self):
        self.assertLess(self.SOURCE.index('event.messageType !== "user"'), self.SOURCE.index("event.prompt"))

    def test_read_gate_kept(self):
        self.assertIn("block: true", self.SOURCE)
        self.assertIn("ctx.sessionManager.getBranch()", self.SOURCE)
        for skill in ("elm-dynamic-workflows", "elm-subagent-workflows", "elm-delegation"):
            self.assertIn(f'return "{skill}"', self.SOURCE)

    def test_instruction_is_apply_where_relevant(self):
        self.assertNotIn("Follow them", self.SOURCE)
        self.assertIn("ignore", self.SOURCE)


if __name__ == "__main__":
    unittest.main()
