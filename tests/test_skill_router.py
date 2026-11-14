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
        "what extensions does elm-pi load?",   # a question about elm-pi, not work on it
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
        "explain where the plugin fits in with the module system",
        "the cache fits into memory",
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
        "build a beamer presentation on kaon decay and where CP violation fits in with this": "physics-documents",
        "plot the histogram with matplotlib": "histogram-analysis",
        "compute the derivative of the potential": "derivation-checks",
        "derive the formula for the period": "derivation-checks",
        "what is the mass of the top quark": "physical-constants",
        "use the fine-structure constant from CODATA": "physical-constants",
        "add the systematic uncertainties in quadrature": "uncertainty-propagation",
        "now plot it": "scientific-python",
        "compile the paper to pdf": "containers",
        "pdflatex is not installed, use docker": "containers",
        "ModuleNotFoundError: No module named netCDF4": "installing-software",
        "gdalinfo: command not found": "installing-software",
        # the treadmill (2026-11-13): asked for an elm-pi plugin, a session wrote the files by hand
        "Could you add a plugin to elm-pi that shows the tool-call count in the footer?": "developing-elm-pi",
        "write a new extension for elm-pi that adds a /uptime command": "developing-elm-pi",
        "I'd like a plugin for elm-pi: a find_todos tool. Build it in this repository.": "developing-elm-pi",
        "Can elm-pi get a new json_check tool? Please implement it here.": "developing-elm-pi",
    }

    def test_software_requests_route_no_physics_skill(self):
        # changing-code (2026-11-14) is the one skill a software request may match: a bug, a failing test.
        for prompt, routed in routes(self.SOFTWARE).items():
            self.assertEqual([], [name for name in routed if name != "changing-code"], prompt)

    CODE = {
        "The tests in this project are failing. Find out why and fix the code (not the tests).": True,
        "run.py crashes for my colleague's data. Fix it so it does what the docstring says.": True,
        "Add two functions to intervals.py: merge(windows) and gaps(windows, lo, hi).": True,
        "flow.py says water moves at 99 m/s, which cannot be right. Find the mistake and fix it.": True,
        "`make test` fails in this project. Fix stats.hpp so it passes.": True,
        # the benchmark's other wordings, unmatched at first (2026-11-14)
        "Running counter.py prints fewer hits than were made and the number changes. Fix HitCounter so the count is right.": True,
        "demo.py prints [('day', 3000, 3)] but the day shift took 1500 events. Fix events_per_shift.": True,
        "totals_by_run in export.py takes minutes on a night's data. Make it fast without changing what it returns.": True,
        "Add reservations to stockroom, and add reserve and release to cli.py.": True,
        "example.py should print about 2.449 but it prints 0.0. Fix spread() so it is right.": True,
        "fix the performance regression in the parser": False,      # not a bug hunt by these words; left alone
        "fix the footer so it matches the other pages": False,
        "make me a website about puffins and make it fast to load": False,
        "the stylesheet gives every page the same header": False,
        "write a bug report": False,
        "report the bug to the vendor": False,
        "xelatex fails on the unicode": False,
        "make me a website about otters": False,
        "the colour scheme is too dark, make it lighter on every page": False,
    }

    def test_a_bug_a_failing_test_or_a_function_to_write_routes_changing_code(self):
        for prompt, routed in routes(list(self.CODE)).items():
            self.assertEqual(self.CODE[prompt], "changing-code" in routed, prompt)

    def test_physics_requests_still_route(self):
        for prompt, routed in routes(list(self.PHYSICS)).items():
            self.assertIn(self.PHYSICS[prompt], routed, prompt)

    def test_the_fits_in_idiom_beside_decay_is_not_data_fitting(self):
        # A real session: a Beamer deck on kaon decay got data-fitting in full.
        prompt = "build a beamer presentation on kaon decay and where CP violation fits in with this"
        self.assertEqual(["physics-documents"], routes([prompt])[prompt])

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

    # What pi-dynamic-workflows appends to a message after /ultracode, abridged.
    ARMED = ("\n\n---\n[workflows mode armed. Decide first: ... handle it by calling the `workflow` tool: write a "
             "script\nthat fans the task out across subagents via agent()/parallel()/pipeline().]\n\nEffort: ULTRA. "
             "Be exhaustive - fan out widely (more reviewers/judges ...)")

    def test_workers_by_name_route_the_delegation_rules(self):
        # test4: "use 5 workers in parallel" routed nothing, and the model found the rules at the gate
        for prompt in ("I want to use 5 workers in parallel to make a small framework to visualize water flowing "
                       "down a pipe", "use several subagents for this", "fan the work out to three sub-agents",
                       "split it across 4 parallel workers", "use 5 agents make me a website about frogs"):
            with self.subTest(prompt=prompt):
                self.assertIn("elm-delegation", routes([prompt])[prompt])

    def test_python3_routes_like_python(self):
        # test3: "animates 3d objects in Python3" routed nothing
        prompt = "make me a short program which animates 3d objects in Python3"
        self.assertIn("scientific-python", routes([prompt])[prompt])

    def test_the_ultracode_note_does_not_route_on_its_own_words(self):
        # it says "subagents", "parallel" and "workflow" whatever was asked
        prompt = "rename the helper in utils.ts" + self.ARMED
        self.assertEqual([], routes([prompt])[prompt])

    def test_an_armed_message_gets_the_orchestration_skill_for_its_tools(self):
        cases = [["fix the parser" + self.ARMED, ["read", "subagent"]], ["fix the parser" + self.ARMED, ["workflow"]],
                 ["fix the parser", ["workflow"]], ["fix the parser" + self.ARMED, ["read", "bash"]]]
        run = subprocess.run(
            [NODE, "--no-warnings", "--input-type=module", "-e",
             "const r = await import(process.argv[1]); const cases = JSON.parse(process.argv[2]);"
             "console.log(JSON.stringify(cases.map(([p, t]) => r.orchestrationSkill(p, t) ?? null)));",
             str(ROUTER), json.dumps(cases)], capture_output=True, text=True, timeout=60, cwd=ROOT)
        self.assertEqual(0, run.returncode, run.stderr)
        # a sub-agent (no subagent tool) gets neither
        self.assertEqual(["elm-subagent-workflows", "elm-dynamic-workflows", None, None], json.loads(run.stdout))

    def test_the_built_in_parallel_workflow_needs_only_the_delegation_skill(self):
        # test6: a correct parallel call was bounced until the script skill was read
        cases = [["subagent", {"workflow": "parallel", "args": {"tasks": [{"agent": "qwen", "task": "a"}]}}],
                 ["subagent", {"workflow": ".pi/tmp/flow.js"}], ["subagent", {"agent": "qwen", "task": "a"}],
                 ["subagent", {"action": "status", "id": "x"}], ["workflow", {"script": "x"}]]
        run = subprocess.run(
            [NODE, "--no-warnings", "--input-type=module", "-e",
             "const r = await import(process.argv[1]); const cases = JSON.parse(process.argv[2]);"
             "console.log(JSON.stringify(cases.map(([t, i]) => r.requiredSkill(t, i) ?? null)));",
             str(ROUTER), json.dumps(cases)], capture_output=True, text=True, timeout=60, cwd=ROOT)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual(["elm-delegation", "elm-subagent-workflows", "elm-delegation", None, "elm-dynamic-workflows"],
                         json.loads(run.stdout))

    # pi-subagents' preamble to a forked child's task, verbatim from test5
    PREAMBLE = ("Task: You are a delegated subagent running from a fork of the parent session. Treat the inherited "
                "conversation as reference-only context, not a live thread to continue. Do not continue or answer "
                "prior messages as if they are waiting for a reply. Your sole job is to execute the task below and "
                "return a focused result for that task using your tools.\n\nTask:\n")

    def test_a_child_gets_no_orchestration_skill(self):
        # test5: the preamble's "subagent" routed elm-delegation into all five children
        cases = [[self.PREAMBLE + "Create the main index.html page for a frog website.", ["read", "bash"]],
                 [self.PREAMBLE + "use 5 workers to split this up", ["read", "bash"]],
                 [self.PREAMBLE + "fit this decay curve and give the half-life", ["read", "bash"]],
                 ["use 5 agents make me a website about frogs", ["read", "subagent"]],
                 ["use 5 agents make me a website about frogs", ["read", "bash"]]]
        run = subprocess.run(
            [NODE, "--no-warnings", "--input-type=module", "-e",
             "const r = await import(process.argv[1]); const cases = JSON.parse(process.argv[2]);"
             "console.log(JSON.stringify(cases.map(([p, t]) => r.sessionRoutes(p, t, ''))));",
             str(ROUTER), json.dumps(cases)], capture_output=True, text=True, timeout=60, cwd=ROOT)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertEqual([[], [], ["data-fitting"], ["elm-delegation"], []], json.loads(run.stdout))

    def test_the_child_preamble_is_not_the_request(self):
        prompt = self.PREAMBLE + "Create the main index.html page for a frog website."
        self.assertEqual([], routes([prompt])[prompt])

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

    def test_an_armed_message_routes_its_orchestration_skill_first(self):
        self.assertIn("sessionRoutes(event.prompt, pi.getActiveTools?.() ?? [], process.env.PATH)", self.SOURCE)

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
