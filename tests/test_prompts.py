"""What the model reads: the prompts, agent definitions and skills under templates/.

These pin facts that were once wrong in the prompts and are easy to get wrong
again: tool names and anchor shapes from pi-hashline-edit-pro, which files a
pi-subagents child can actually see, and the routing rule for Llama.
"""

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


def text(name):
    return (TEMPLATES / name).read_text()


def frontmatter(source):
    match = re.match(r"---\n(.*?)\n---\n", source, re.S)
    return dict(line.split(": ", 1) for line in match.group(1).splitlines()) if match else {}


class AnchorToolTests(unittest.TestCase):
    # pi-hashline-edit-pro 7.x registers its anchored search as `grep` and its
    # anchors are five lowercase letters (HASH_LEN in src/hashline/alphabet.ts).

    def test_no_prompt_names_a_tool_that_does_not_exist(self):
        for path in TEMPLATES.rglob("*"):
            if path.is_file() and path.suffix in {".md", ".ts", ".json"}:
                self.assertNotIn("anchor_grep", path.read_text(), path)

    def test_anchor_length_claims_are_five_letters(self):
        for name in ("AGENTS.md", "agents/qwen.md", "agents/llama.md"):
            source = text(name)
            self.assertNotRegex(source, r"(?i)four-character|4-character", name)
            self.assertIn("five lowercase letters", source, name)

    def test_example_anchors_have_the_real_shape(self):
        for path in TEMPLATES.rglob("*.md"):
            for token in re.findall(r"([A-Za-z]+)│", path.read_text()):
                if token != "anchor":
                    self.assertRegex(token, r"^[a-z]{5}$", path)


class ChildContextTests(unittest.TestCase):
    # pi-subagents children see neither APPEND_SYSTEM.md (0.79.2) nor the global
    # AGENTS.md (0.58.0, without inheritGlobalContext), so the rules a child
    # needs live in its own definition.

    def test_children_do_not_load_the_global_context_file(self):
        for name in ("agents/qwen.md", "agents/llama.md"):
            meta = frontmatter(text(name))
            self.assertNotIn("inheritGlobalContext", meta, name)
            self.assertIn("pin_instruction", meta["excludeTools"], name)
            # The workflow tools reached every child although the parent had excluded them (test3):
            # ~6.9k characters of definitions on every child request.
            for tool in ("workflow", "workflow_control"):
                self.assertIn(tool, meta["excludeTools"].split(", "), f"{name}: {tool}")

    def test_a_qwen_child_leaves_the_parents_runs_and_files_alone(self):
        # test4: two children polled the parent's run 394 and 705 times; one wrote stubs over siblings' files
        qwen = text("agents/qwen.md")
        self.assertIn("The parent's runs are not yours.", qwen)
        self.assertIn("never call, poll or wait on it", qwen)
        self.assertIn("Write only the files your task names.", qwen)
        self.assertIn("never a file you only saw in the", qwen)

    def test_parallel_children_keep_scratch_and_cleanup_private(self):
        # python-before/parallel.1 (2026-11-15): both children used .pi/tmp/venv;
        # task-2 removed it after passing, then task-1 could not source activate.
        for name in ("agents/qwen.md", "agents/llama.md", "skills/elm-delegation/SKILL.md"):
            source = " ".join(text(name).split())
            self.assertIn("mkdir -p .pi/tmp", source, name)
            self.assertIn("mktemp -d .pi/tmp/child.XXXXXX", source, name)
            self.assertIn("Clean up only your own directory", source, name)
            self.assertIn("never create or remove a shared `.pi/tmp/venv`", source, name)

    def test_code_verification_runs_saved_tests_after_repairing_runner_setup(self):
        # python-after/parallel.1 (2026-11-15): delivered tests failed during import;
        # passing inline assertions were reported instead of repairing and running those files.
        for name in ("agents/qwen.md", "agents/llama.md", "skills/changing-code/SKILL.md"):
            source = " ".join(text(name).split())
            for rule in ("Run the saved tests", "project's test framework", "standard-library `unittest`",
                         "runner/import setup", "rerun the saved test files", "Keep requested output names",
                         "do not substitute inline assertions", "Do not weaken"):
                self.assertIn(rule, source, (name, rule))
        self.assertNotIn("a throwaway script or `python3 -c` is enough", text("skills/changing-code/SKILL.md"))

    def test_children_carry_the_essential_rules(self):
        for name in ("agents/qwen.md", "agents/llama.md"):
            source = text(name)
            for rule in ("(from memory, unverified)", "English", "units", "sudo", "denied",
                         "failing", ".pi/"):
                self.assertIn(rule, source, f"{name}: {rule}")
        qwen = text("agents/qwen.md")
        self.assertIn("chi2", qwen)
        self.assertIn("uncertainty", qwen)

    def test_append_system_does_not_address_children_it_never_reaches(self):
        source = text("APPEND_SYSTEM.md")
        for phrase in ("`qwen`", "`llama`", "contact_supervisor", "FOR THE PARENT", "sub-agent"):
            self.assertNotIn(phrase, source, phrase)
        self.assertNotIn("A sub-agent reading this file", text("AGENTS.md"))


class RoutingTests(unittest.TestCase):
    def test_delegate_description_says_it_runs_on_llama(self):
        delegate = json.loads(text("settings.json"))["subagents"]["agentOverrides"]["delegate"]
        self.assertTrue(delegate["model"].startswith("elm-shim/"))
        self.assertIn("Llama", delegate["description"])
        self.assertIn("Numbered steps", delegate["description"])
        self.assertNotIn("parent model with", delegate["description"])

    def test_llama_examples_are_numbered_steps(self):
        for path in (TEMPLATES / "skills").glob("*/SKILL.md"):
            for line in path.read_text().splitlines():
                if re.search(r'agent:\s*"llama"', line):
                    self.assertIn("Step 1", line, path)

    def test_llama_is_conditional_wherever_its_uses_are_listed(self):
        self.assertIn("rate-limited", frontmatter(text("agents/llama.md"))["description"])
        self.assertIn("rate-limited", text("skills/elm-delegation/SKILL.md").split("**`llama` is for rote")[1][:200])

    def test_independent_children_are_one_call_without_a_script(self):
        # A script means write, validate, fix, launch: enough ceremony that the
        # model did the work itself. pi-subagents' named `parallel` workflow is
        # one call, so the always-on rules and both skills lead with it.
        call = 'workflow: "parallel"'
        for name in ("AGENTS.md", "skills/elm-delegation/SKILL.md",
                     "skills/elm-subagent-workflows/SKILL.md"):
            self.assertIn(call, text(name), name)
        agents = text("AGENTS.md")
        self.assertIn(call, agents.split("# Final Reminder")[1])
        self.assertIn("three or more", agents.split("\n2. ")[0])

    def test_stated_concurrency_matches_the_config(self):
        limit = json.loads(text("extensions/subagent/config.json"))["globalConcurrencyLimit"]
        self.assertIn(f"at most {limit} of a", text("skills/elm-delegation/SKILL.md"))
        self.assertIn(f"{limit} concurrent, 64 per run", (ROOT / "INSTALL.md").read_text())
        owned = (ROOT / "bootstrap.bash").read_text().split("OWNED = {")[1].split("\n}\n")[0]
        self.assertIn('"globalConcurrencyLimit"', owned)

    def test_speed_measurements_have_one_home(self):
        homes = [p.relative_to(TEMPLATES) for p in TEMPLATES.rglob("*.md") if "tok/s" in p.read_text()]
        self.assertEqual([Path("skills/elm-delegation/SKILL.md")], homes)


class PathAndPlaceholderTests(unittest.TestCase):
    def test_egress_log_is_found_through_the_agent_dir(self):
        agents = text("AGENTS.md")
        self.assertNotIn("~/.local/share/elm-pi", agents)
        self.assertIn('"$PI_CODING_AGENT_DIR/egress.log"', agents)

    def test_ref_needed_marker_is_an_explicit_exception(self):
        source = text("skills/physics-documents/SKILL.md")
        self.assertIn("[ref needed:", source)
        self.assertIn("one exception to the rule against placeholders", source)


class ProtectedPathsTests(unittest.TestCase):
    SOURCE = TEMPLATES / "extensions/protected-paths.ts"
    CASES = {
        ".env": True, ".env.local": True, "app/.env.production": True,
        ".env.example": False, "app/.env.example": False,
        "config.environment": False, ".git/config": True,
    }

    def test_permission_config_and_guard_agree_on_env_example(self):
        config = json.loads(text("extensions/pi-permission-system/config.json"))
        self.assertEqual("allow", config["permission"]["path"]["*.env.example"])
        self.assertIn('".env.example"', self.SOURCE.read_text())

    def test_guard_blocks_real_dotenv_files_only(self):
        node = ROOT / ".node/bin/node"
        node = str(node) if node.exists() else shutil.which("node")
        if not node:
            self.skipTest("no node")
        script = (
            "const mod = await import(process.argv[1]);"
            "let handler; mod.default({ on: (_e, h) => { handler = h; } });"
            "const out = {};"
            "for (const p of JSON.parse(process.argv[2])) {"
            "  out[p] = Boolean(await handler({ toolName: 'write', input: { path: p } }, { hasUI: false }));"
            "}"
            "console.log(JSON.stringify(out));"
        )
        run = subprocess.run(
            [node, "--input-type=module", "-e", script, str(self.SOURCE), json.dumps(list(self.CASES))],
            capture_output=True, text=True,
        )
        if run.returncode != 0:
            self.skipTest(f"node cannot load TypeScript here: {run.stderr.strip()[:200]}")
        self.assertEqual(self.CASES, json.loads(run.stdout))


class PromptTemplateTests(unittest.TestCase):
    """templates/prompts/*.md: the /commands a session can type. Each costs nothing until typed,
    because pi expands the file into the request rather than sending it with every one - which is
    why these are templates and not lines in AGENTS.md, whose size is capped."""

    # Named in INSTALL.md, so a reader learns they exist; the docs-match test holds the reverse.
    SHIPPED = ("explain", "fix", "review", "init", "plot")

    def templates(self):
        return {p.stem: p for p in sorted((TEMPLATES / "prompts").glob("*.md"))}

    def test_the_five_that_ship_are_here_and_nothing_else_is(self):
        self.assertEqual(sorted(self.SHIPPED), sorted(self.templates()))

    def test_each_has_a_description_and_a_body_short_enough_to_read(self):
        for name, path in self.templates().items():
            with self.subTest(template=name):
                head = frontmatter(path.read_text())
                description = head.get("description", "")
                self.assertTrue(description, f"{name} has no description: pi shows it in completion")
                self.assertLessEqual(len(description), 90, f"{name}'s description is a menu line")
                body = re.sub(r"^---\n.*?\n---\n", "", path.read_text(), flags=re.S).strip()
                self.assertGreater(len(body), 200, f"{name} says too little to be worth a command")
                self.assertLessEqual(len(body), 1500, f"{name} is a prompt, not a chapter")

    def test_every_substitution_is_one_pi_documents(self):
        # `${@:+...}` looked handy and is not in pi's list; a wrong form reaches the model literally.
        allowed = re.compile(r"\$\{(?:[1-9]|@(?::[0-9]+(?::[0-9]+)?)?)(?::-?[^}]*)?\}")
        for name, path in self.templates().items():
            for found in re.findall(r"\$\{[^}]*\}", path.read_text()):
                with self.subTest(template=name, found=found):
                    self.assertRegex(found, allowed)

    def test_the_defaults_make_a_bare_command_useful(self):
        # Typing /plot with nothing after it must still be a request, or the command is a trap.
        for name, path in self.templates().items():
            with self.subTest(template=name):
                self.assertIn("${1:-", path.read_text(), f"{name} has no default for its argument")

    def test_bootstrap_renders_them_into_the_agents_prompt_directory(self):
        script = (ROOT / "bootstrap.bash").read_text()
        self.assertIn("templates/prompts/*.md", script)
        self.assertIn('render "$prompt" "agent/prompts/${prompt##*/}"', script)
        self.assertIn("agent/prompts/.elm-pi-managed", script)   # a dropped template leaves, a user's stays

    def test_install_names_every_one(self):
        install = (ROOT / "INSTALL.md").read_text()
        for name in self.SHIPPED:
            self.assertIn(f"`/{name}`", install, f"INSTALL.md does not name /{name}")


if __name__ == "__main__":
    unittest.main()
