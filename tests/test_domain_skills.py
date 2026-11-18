"""The fifty particle and nuclear physics skills and the six batch-computing ones, and how a request reaches them.

They were added on request (2026-11-17) for experimental and theoretical
particle physics and nuclear physics, beside the K-Dense library they refer to.
Three things could go wrong with fifty more skills, and each has its tests here:

* the prompt: a skill pi lists costs every session its description, so these are
  hidden from the listing and reached by the skill router, through the
  `route.json` beside each SKILL.md;
* the routing: a pattern loose enough to fire on everyday software work would
  put a physics procedure into a session that is renaming a variable, so every
  route is run against its own examples, its own counterexamples, and the
  software and general-method requests the router's other tests use;
* the references: a skill that names another skill, or a K-Dense one, names one
  that exists and is installed.
"""

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "templates/skills"
ROUTER = ROOT / "templates/extensions/skill-router.ts"
LIBRARY = json.loads((ROOT / "config/skill-library.json").read_text())
INSTALLED_LIBRARY = set(LIBRARY["skills"]) - set(LIBRARY["exclude"])
ALL = sorted(p.parent.name for p in SKILLS.glob("*/SKILL.md"))
DOMAIN = sorted(p.parent.name for p in SKILLS.glob("*/route.json"))
INDEX = (ROOT / "templates/reference/skills.md").read_text()

EXPERIMENT = ["hep-background-estimation", "hep-columnar-analysis", "hep-cross-section-measurement",
              "hep-data-formats", "hep-detector-performance", "hep-detector-simulation",
              "hep-efficiency-measurement", "hep-event-generators", "hep-event-selection", "hep-flavour-and-cp",
              "hep-jets", "hep-kinematics", "hep-likelihood-limits", "hep-literature-and-data", "hep-ml-classifiers",
              "hep-particle-identification", "hep-reinterpretation", "hep-roofit-models", "hep-root",
              "hep-systematics", "hep-unfolding", "neutrino-oscillations", "rare-event-searches"]
THEORY = ["bsm-model-tools", "effective-field-theory", "group-theory-for-physics", "lattice-qcd-analysis",
          "particle-cosmology", "qcd-parton-distributions", "qft-amplitudes", "qft-computer-algebra",
          "qft-loop-integrals", "qft-phase-space", "qft-renormalisation-group", "tensor-calculus-and-gr"]
NUCLEAR = ["dosimetry-and-shielding", "gamma-spectroscopy", "heavy-ion-collisions", "neutron-activation-and-transport",
           "nuclear-astrophysics", "nuclear-data-lookup", "nuclear-masses-and-q-values", "nuclear-reaction-codes",
           "nuclear-reaction-kinematics", "nuclear-structure-models", "radiation-detectors-and-daq",
           "radiation-transport-monte-carlo", "radioactive-decay-chains", "scattering-theory-and-partial-waves",
           "stopping-power-and-range"]

BATCH = ["batch-grid-engine", "batch-htcondor", "batch-jobs", "batch-lsf", "batch-pbs", "batch-slurm"]

FRONT = re.compile(r"\A---\nname: ([a-z0-9-]+)\ndescription: \"([^\"\n]+)\"\ndisable-model-invocation: true\n---\n\n# \S")
KDENSE_LINE = re.compile(r"- K-Dense library \(read `@AGENT_DIR@/skills/kdense/<name>/SKILL\.md` when you use\s+the tool; "
                         r"absent if the library was left out of this install\):\s*([\s\S]*)\Z")


def node():
    """A node that can import the extension's TypeScript (22.18+ or 23.6+): the clone's own, else PATH's."""
    for candidate in (str(ROOT / ".node/bin/node"), shutil.which("node")):
        if not candidate or not Path(candidate).exists():
            continue
        try:
            version = subprocess.run([candidate, "--version"], capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        match = re.match(r"v(\d+)\.(\d+)", version.strip())
        if match and ((int(match.group(1)), int(match.group(2))) >= (23, 6)
                      or (int(match.group(1)) == 22 and int(match.group(2)) >= 18)):
            return candidate
    return None


NODE = node()


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def generate(cls, names, check):
    for name in names:
        setattr(cls, "test_" + slug(name), lambda self, name=name: check(self, name))


class TheSetTests(unittest.TestCase):
    def test_there_are_fifty_for_physics_six_for_batch_systems_and_these_are_they(self):
        self.assertEqual(56, len(DOMAIN))
        self.assertEqual(sorted(EXPERIMENT + THEORY + NUCLEAR + BATCH), DOMAIN)

    def test_each_area_asked_for_is_covered(self):
        # Batch computing was asked for the same day: Slurm, Grid Engine (SGE, Univa), PBS, HTCondor, and LSF as the
        # other scheduler university clusters commonly run, with one skill for what they share.
        self.assertEqual((23, 12, 15, 6), (len(EXPERIMENT), len(THEORY), len(NUCLEAR), len(BATCH)))

    def test_a_route_file_is_never_left_without_its_skill(self):
        self.assertEqual([], [p.parent.name for p in SKILLS.glob("*/route.json") if not (p.parent / "SKILL.md").is_file()])

    def test_the_general_skills_are_still_listed_by_pi(self):
        for name in sorted(set(ALL) - set(DOMAIN)):
            self.assertNotIn("disable-model-invocation", (SKILLS / name / "SKILL.md").read_text(), name)

    def test_hidden_they_cost_the_prompt_nothing(self):
        """What pi would otherwise put in every session's system prompt for them: measured, and why they are hidden."""
        listed = sum(len(name) + len(FRONT.match((SKILLS / name / "SKILL.md").read_text()).group(2)) for name in DOMAIN)
        self.assertGreater(listed, 10000)


class SkillFileTests(unittest.TestCase):
    """One test per skill and rule, so a failure names the skill."""


def _frontmatter(self, name):
    match = FRONT.match((SKILLS / name / "SKILL.md").read_text())
    self.assertIsNotNone(match, "frontmatter must be name, a one-line quoted description and "
                                "disable-model-invocation: true, then a title")
    self.assertEqual(name, match.group(1))
    self.assertLessEqual(len(match.group(2)), 230)


def _size(self, name):
    # The router inlines a domain skill whole, after two general ones: 5 kB is about 1,300 tokens.
    size = len((SKILLS / name / "SKILL.md").read_bytes())
    self.assertLessEqual(size, 5000)
    self.assertGreaterEqual(size, 2500, "too short to be a procedure")


def _shape(self, name):
    text = (SKILLS / name / "SKILL.md").read_text()
    self.assertIn("\n## Check before reporting\n", text)
    self.assertEqual(1, text.count("\n## Related\n"))
    self.assertNotRegex(text, r"in a (test|session) on this install|measured on this install",
                        "these skills have no measured sessions behind them yet: none may be invented")


def _related(self, name):
    related = (SKILLS / name / "SKILL.md").read_text().split("\n## Related\n", 1)[1]
    here = re.search(r"- Skills here:([\s\S]*?)\n- K-Dense", related)
    self.assertIsNotNone(here, "no '- Skills here:' line before the K-Dense line")
    named = re.findall(r"`([a-z0-9-]+)`", here.group(1))
    self.assertTrue(named)
    self.assertEqual([], [n for n in named if n not in ALL or n == name])
    library = KDENSE_LINE.search(related)
    self.assertIsNotNone(library, "the K-Dense line is not worded as the others are")
    named = re.findall(r"`([a-z0-9-]+)`", library.group(1))
    self.assertTrue(named, "the K-Dense line names no skill")
    self.assertEqual([], [n for n in named if n not in INSTALLED_LIBRARY],
                     "not a skill the pinned library installs (config/skill-library.json)")


def _names_in_the_body(self, name):
    body = (SKILLS / name / "SKILL.md").read_text().split("\n## Related\n", 1)[0]
    looks_like_a_skill = re.compile(r"^(hep|qft|qcd|nuclear|elm)-|-(analysis|lookup|methods|checks|fitting|propagation)$")
    for token in set(re.findall(r"`([a-z]+(?:-[a-z0-9]+)+)`", body)):
        if looks_like_a_skill.search(token) or token in ALL:
            self.assertIn(token, ALL, "names a skill that does not exist")


def _indexed(self, name):
    self.assertIn("`%s`" % name, INDEX, "templates/reference/skills.md does not list it")


for _rule, _check in (("frontmatter", _frontmatter), ("size", _size), ("shape", _shape), ("related", _related),
                      ("body_names", _names_in_the_body), ("indexed", _indexed)):
    generate(SkillFileTests, ["%s %s" % (name, _rule) for name in DOMAIN],
             lambda self, label, check=_check: check(self, label.rsplit(" ", 1)[0]))


class IndexTests(unittest.TestCase):
    def test_the_index_names_only_skills_that_exist(self):
        listed = re.findall(r"^- `([a-z0-9-]+)`", INDEX, re.M)
        self.assertEqual([], [n for n in listed if n not in ALL])
        self.assertEqual(sorted(ALL), sorted(listed))

    def test_the_prompt_points_at_the_index_and_counts_right(self):
        prompt = " ".join((ROOT / "templates/AGENTS.md").read_text().split())
        self.assertIn("All %d are in `@AGENT_DIR@/reference/skills.md`." % len(ALL), prompt)

    def test_the_index_counts_the_library_right(self):
        self.assertIn("holds %d community skills" % len(INSTALLED_LIBRARY), " ".join(INDEX.split()))

    def test_the_index_says_where_the_library_is_and_whose_rules_win(self):
        flat = " ".join(INDEX.split())
        self.assertIn("`@AGENT_DIR@/skills/kdense/INDEX.md`", flat)
        self.assertIn("this install's rules decide", flat)


# Requests that are everyday software work, or a general method the table's skills take: no domain skill.
NOT_PHYSICS = [
    "what extensions does elm-pi load?", "add integration tests for the parser and report what fails",
    "improve its efficiency", "make the magic number a named constant", "propagate the rename to every caller",
    "be systematic about it", "reduce coupling between modules", "write a bug report",
    "the derived class overrides fit()", "fix the performance regression in the parser", "add a regression test",
    "the struct fits in one cache line", "simulate a network failure in the tests", "sort the list numerically",
    "def make(cls): return cls()", "#[derive(Debug)] on the struct", "the class derives from Base",
    "fix the borrow checker error about lifetimes", "prove that the cache is invalidated", "yes, go ahead",
    "export the users table to csv", "add a slide-in animation to the panel",
    "explain where the plugin fits in with the module system", "the cache fits into memory",
    "the sidebar width jumps at peak load", "the two test files disagree about the return type, which one is wrong",
    "cut the peak memory use of the background worker",
    "The tests in this project are failing. Find out why and fix the code (not the tests).",
    "Add two functions to intervals.py: merge(windows) and gaps(windows, lo, hi).",
    "the root file system is full", "walk the directory tree and trigger a rebuild",
    "track the jet engine telemetry events", "the model selection cut the latency in half",
    "scale the kernel image and flow the text around it", "the event loop has a background task leak",
    "merge the feature branch and tag the release", "the shell script's exit status is wrong",
    "bind the form field to the model", "generate a random sample of users", "group the rows by tenant and loop over them",
    # A topic named in a request for slides is not the analysis: the session these come from
    # (tests/test_feature_extensions.py) got a fitting procedure for a Beamer deck on kaon decay.
    ("I want to build a beamer presentation explaining how Kaon decay works, where CP violation in the SM "
     "fits in with this, the abbrievaited history of this from discovery to modern experiments and what "
     "questions studying this today is hoping to shed light on."),
    "build a beamer presentation on kaon decay and where CP violation fits in with this",
    "how this decay fits into the Standard Model", "make beamer slides for the lecture",
    "the state machine has too many levels", "stand up a redis server for the tests",
    # the general skills' own requests, singular and plural (tests/test_extensions_generated.py)
    "fit the peak in this spectrum", "fit the peaks in these spectra", "what is the p-value of this excess",
    "what are the p-values of these excesses", "estimate the systematic uncertainty",
    "estimate the systematic uncertainties", "make a histogram of the energies", "make histograms of the energies",
    "check the derivation in section two", "check the derivations in section two",
    "solve this ODE with an adaptive step", "solve these ODEs with an adaptive step", "look up the physical constant",
    "look up the physical constants", "write the lab report", "write the lab reports", "port the loop to C++",
    "port the loops to C++", "make a plot of the residues", "make plots of the residues",
    "the module is not installed", "the modules are not installed", "run the build in a podman container",
    "run the builds in podman containers", "now plot it",
]
# ... and all of them in one request, which is how tests/test_extensions_generated.py sends them: a pattern that
# wants two everyday words anywhere in a request finds them here in different sentences.
NOT_PHYSICS.append(". ".join(NOT_PHYSICS[NOT_PHYSICS.index("fit the peak in this spectrum")::2]))
NOT_PHYSICS.append(". ".join(NOT_PHYSICS[NOT_PHYSICS.index("fit the peaks in these spectra"):-1:2]))

ROUTES_RUNNER = """
const [source, dir, promptsPath] = process.argv.slice(1);
const fs = await import("node:fs");
const router = await import(source);
const prompts = JSON.parse(fs.readFileSync(promptsPath, "utf8"));
console.log(JSON.stringify(prompts.map((p) => ({ domain: router.domainRoutesFor(p, dir), library: router.libraryRoutesFor(p, dir),
  general: router.routesFor(p) }))));
"""


def run_node(script, *args, env=None):
    result = subprocess.run([NODE, "--no-warnings", "--input-type=module", "-e", script, *map(str, args)],
                            capture_output=True, text=True, timeout=180, cwd=ROOT, env=env)
    if result.returncode != 0:
        raise AssertionError("node failed:\n" + result.stderr[-3000:])
    return json.loads(result.stdout)


def routes_for(prompts, skills_dir=SKILLS):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "prompts.json"
        path.write_text(json.dumps(prompts))
        return dict(zip(prompts, run_node(ROUTES_RUNNER, ROUTER, skills_dir, path)))


def route_file(name):
    return json.loads((SKILLS / name / "route.json").read_text())


class RouteFileTests(unittest.TestCase):
    def test_every_route_file_has_patterns_and_requests_to_prove_them(self):
        for name in DOMAIN:
            with self.subTest(skill=name):
                route = route_file(name)
                self.assertEqual(set(), set(route) - {"patterns", "caseSensitive", "examples", "counterexamples"})
                self.assertTrue(route.get("patterns") or route.get("caseSensitive"))
                for key in ("patterns", "caseSensitive", "examples", "counterexamples"):
                    self.assertTrue(all(isinstance(item, str) and item for item in route.get(key, [])), key)
                self.assertGreaterEqual(len(route.get("examples", [])), 3)
                self.assertGreaterEqual(len(route.get("counterexamples", [])), 3)


@unittest.skipUnless(NODE, "needs node 22.18+ or 23.6+ to run the router")
class RoutingTests(unittest.TestCase):
    """Every route.json through the router's own domainRoutesFor."""

    @classmethod
    def setUpClass(cls):
        prompts = set(NOT_PHYSICS)
        for name in DOMAIN:
            route = route_file(name)
            prompts.update(route.get("examples", []), route.get("counterexamples", []))
        cls.routed = routes_for(sorted(prompts))

    def test_every_example_reaches_its_skill(self):
        # Three domain skills reach a session for one request: the first in full, two more by name.
        missed = [(name, text, self.routed[text]["domain"]) for name in DOMAIN for text in route_file(name)["examples"]
                  if name not in self.routed[text]["domain"][:3]]
        self.assertEqual([], missed)

    def test_the_skill_a_request_names_first_outranks_one_it_mentions_later(self):
        text = "set up a Geant4 simulation of a lead-scintillator sampling calorimeter and get the energy resolution"
        self.assertEqual("hep-detector-simulation", self.routed[text]["domain"][0])

    def test_most_examples_put_their_own_skill_first(self):
        first = sum(1 for name in DOMAIN for text in route_file(name)["examples"] if self.routed[text]["domain"][:1] == [name])
        total = sum(len(route_file(name)["examples"]) for name in DOMAIN)
        self.assertGreater(first, 0.8 * total, "%d of %d" % (first, total))

    def test_no_counterexample_reaches_its_skill(self):
        hit = [(name, text) for name in DOMAIN for text in route_file(name)["counterexamples"]
               if name in self.routed[text]["domain"]]
        self.assertEqual([], hit)

    def test_software_and_general_method_requests_route_no_domain_skill(self):
        self.assertEqual({}, {text: self.routed[text]["domain"] for text in NOT_PHYSICS if self.routed[text]["domain"]})

    def test_every_pattern_compiles(self):
        # One that does not is dropped by the router in silence: then its skill has fewer routes than its file says.
        script = """
        const [dir] = process.argv.slice(1);
        const fs = await import("node:fs");
        const bad = [];
        for (const name of fs.readdirSync(dir)) {
          let route; try { route = JSON.parse(fs.readFileSync(`${dir}/${name}/route.json`, "utf8")); } catch { continue; }
          for (const [key, flags] of [["patterns", "iu"], ["caseSensitive", "u"]])
            for (const source of route[key] ?? []) { try { new RegExp(source, flags); } catch (e) { bad.push([name, source, String(e)]); } }
        }
        console.log(JSON.stringify(bad));
        """
        self.assertEqual([], run_node(script, SKILLS))


LIBRARY_INDEX = {"library": "Test", "tag": "v1", "skills": [
    {"name": "astropy", "description": "x", "match": ["astropy"]},
    {"name": "scikit-learn", "description": "x", "match": ["scikit-learn", "sklearn"]},
    {"name": "umap-learn", "description": "x", "match": ["umap-learn", "umap"]},
    {"name": "modal", "description": "x", "match": []},
    {"name": "protocolsio-integration", "description": "x", "match": ["protocols.io"]},
]}


@unittest.skipUnless(NODE, "needs node 22.18+ or 23.6+ to run the router")
class LibraryRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "skills"
        (self.dir / "kdense").mkdir(parents=True)
        (self.dir / "kdense/index.json").write_text(json.dumps(LIBRARY_INDEX))

    def tearDown(self):
        self.tmp.cleanup()

    def library(self, *prompts):
        return [routes_for(list(prompts), self.dir)[p]["library"] for p in prompts]

    def test_a_skill_is_named_by_its_name_or_an_alias_as_a_whole_word(self):
        self.assertEqual([["astropy"], ["scikit-learn"], ["scikit-learn"], ["scikit-learn", "umap-learn"], [], []],
                         self.library("convert the coordinates with Astropy", "use scikit learn for it",
                                      "from sklearn import svm fails", "cluster with scikit-learn, then UMAP",
                                      "the astropyx fork", "bump the version"))

    def test_an_everyday_word_names_nothing(self):
        self.assertEqual([[]], self.library("the modal dialog does not close"))

    def test_a_name_with_punctuation_is_matched_as_text_not_as_a_pattern(self):
        self.assertEqual([["protocolsio-integration"], []],
                         self.library("publish the method on protocols.io", "the protocolsXio fork"))

    def test_an_install_without_the_library_names_nothing(self):
        shutil.rmtree(self.dir / "kdense")
        self.assertEqual([[]], self.library("convert the coordinates with astropy"))

    def test_an_index_that_is_not_json_names_nothing(self):
        (self.dir / "kdense/index.json").write_text("{")
        self.assertEqual([[]], self.library("convert the coordinates with astropy"))


MESSAGE_RUNNER = """
const [source, casesPath, agent] = process.argv.slice(1);
const fs = await import("node:fs");
process.env.PI_CODING_AGENT_DIR = agent;
const mod = await import(source);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const out = {};
for (const [id, c] of Object.entries(cases)) {
  const handlers = {};
  mod.default({ on: (e, h) => { handlers[e] = h; }, registerMessageRenderer: () => {} });
  const ctx = { sessionManager: { buildContextEntries: () => c.context ?? [], getBranch: () => [] } };
  const r = await handlers.before_agent_start({ type: "before_agent_start", prompt: c.prompt, messageType: "user" }, ctx);
  out[id] = r ? { details: r.message.details, content: r.message.content } : null;
}
console.log(JSON.stringify(out));
"""

HPGE = "this HPGe spectrum has a Co-60 source in it; get the activity"
CASES = {
    "domain alone": {"prompt": HPGE},
    "general and domain": {"prompt": HPGE + ". Fit the 1332 keV peak and propagate the uncertainties, then plot it with matplotlib"},
    "library alone": {"prompt": "convert the coordinates with astropy"},
    "library again": {"prompt": "convert the coordinates with astropy",
                      "context": [{"type": "custom_message", "customType": "skill-routing",
                                   "details": {"inlined": [], "named": [], "library": ["astropy"]}}]},
    "library read": {"prompt": "convert the coordinates with astropy",
                     "context": [{"type": "message", "message": {"role": "assistant", "content": [
                         {"type": "toolCall", "name": "read", "arguments": {"path": "/x/agent/skills/kdense/astropy/SKILL.md"}}]}}]},
    "domain present": {"prompt": HPGE,
                       "context": [{"type": "custom_message", "customType": "skill-routing",
                                    "details": {"inlined": ["gamma-spectroscopy"], "named": []}}]},
    "nothing": {"prompt": "rename the variable"},
    "general alone": {"prompt": "fit the peak in this spectrum"},
}


@unittest.skipUnless(NODE, "needs node 22.18+ or 23.6+ to run the router")
class SessionMessageTests(unittest.TestCase):
    """before_agent_start: what the three tiers put after a request."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            skills = cls.tmp / "agent/skills"
            skills.mkdir(parents=True)
            for skill in SKILLS.iterdir():
                (skills / skill.name).symlink_to(skill)
            (skills / "kdense/astropy").mkdir(parents=True)
            (skills / "kdense/astropy/SKILL.md").write_text("---\nname: astropy\ndescription: x\n---\n")
            (skills / "kdense/index.json").write_text(json.dumps(LIBRARY_INDEX))
            (cls.tmp / "cases.json").write_text(json.dumps(CASES))
            cls.agent = cls.tmp / "agent"
            cls.results = run_node(MESSAGE_RUNNER, ROUTER, cls.tmp / "cases.json", cls.agent,
                                   env={"PATH": "/usr/bin:/bin", "HOME": str(cls.tmp)})
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_a_domain_skill_is_inlined_whole(self):
        result = self.results["domain alone"]
        self.assertEqual(["gamma-spectroscopy"], result["details"]["inlined"][-1:])
        self.assertIn("## Skill: gamma-spectroscopy\n\n# Gamma-ray spectroscopy", result["content"])
        self.assertNotIn("disable-model-invocation", result["content"])

    def test_the_domain_skill_is_added_to_the_two_general_ones_not_swapped_for_one(self):
        details = self.results["general and domain"]["details"]
        self.assertEqual(["data-fitting", "uncertainty-propagation", "gamma-spectroscopy"], details["inlined"])
        # ... and the general skill that did not fit, then any other domain skill the request touches
        self.assertEqual("scientific-python", details["named"][0])
        self.assertLessEqual(len(details["named"]), 4)
        self.assertNotIn("library", details)

    def test_a_general_request_is_answered_as_before(self):
        self.assertEqual({"inlined": ["data-fitting"], "named": []}, self.results["general alone"]["details"])

    def test_a_library_skill_is_named_with_its_path_and_whose_rules_win(self):
        result = self.results["library alone"]
        self.assertEqual({"inlined": [], "named": [], "library": ["astropy"]}, result["details"])
        self.assertIn("- astropy: %s" % (self.agent / "skills/kdense/astropy/SKILL.md"), result["content"])
        self.assertIn("this install's rules decide, not the skill", result["content"])
        self.assertNotIn("included here in full", result["content"])

    def test_a_library_skill_is_named_once_a_session(self):
        self.assertIsNone(self.results["library again"])
        self.assertIsNone(self.results["library read"])

    def test_a_domain_skill_already_in_the_session_is_not_added_again(self):
        result = self.results["domain present"]
        self.assertTrue(result is None or "gamma-spectroscopy" not in result["details"]["inlined"])

    def test_a_request_that_matches_nothing_adds_nothing(self):
        self.assertIsNone(self.results["nothing"])


class RouterSourceTests(unittest.TestCase):
    def test_the_limits_the_docs_give(self):
        source = ROUTER.read_text()
        install = " ".join((ROOT / "INSTALL.md").read_text().split())
        for constant, claim in (("MAX_DOMAIN_INLINED", "the best matching one is added in full"),
                                ("MAX_DOMAIN_ROUTED", "up to two more are named"),
                                ("MAX_LIBRARY_NAMED", "names up to three library skills")):
            self.assertRegex(source, r"const %s = \d+;" % constant)
            self.assertIn(claim, install)
        self.assertIn("const MAX_DOMAIN_INLINED = 1;", source)
        self.assertIn("const MAX_DOMAIN_ROUTED = 3;", source)
        self.assertIn("const MAX_LIBRARY_NAMED = 3;", source)

    def test_a_library_skill_is_never_inlined(self):
        # 6-30 kB each, written for other agents: named with a path, read on demand.
        source = ROUTER.read_text()
        self.assertNotIn("skillBody(libraryPath", source)
        self.assertIn("library.map((name) => `- ${name}: ${libraryPath(name)}`)", source)


if __name__ == "__main__":
    unittest.main()
