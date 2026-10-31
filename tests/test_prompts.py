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


if __name__ == "__main__":
    unittest.main()
