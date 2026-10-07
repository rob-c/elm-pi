import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectConsistencyTests(unittest.TestCase):
    def test_required_extensions_exist_and_workflow_guard_is_required(self):
        config = json.loads((ROOT / "config/elm-pi.json").read_text())
        self.assertIn("workflow-model-scope.ts", config["requiredExtensions"])
        for name in config["requiredExtensions"]:
            self.assertTrue((ROOT / "templates/extensions" / name).is_file(), name)

    def test_model_templates_render_from_shared_state(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "settings.json"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/elm_config.py"),
                    "--root",
                    str(ROOT),
                    "render",
                    str(ROOT / "templates/settings.json"),
                    str(destination),
                ],
                check=True,
            )
            text = destination.read_text()
            self.assertNotIn("@QWEN_MODEL@", text)
            self.assertNotIn("@LLAMA_MODEL@", text)
            json.loads(text)

    def test_policy_inventory_includes_meta_and_has_no_allowed_provider(self):
        config = json.loads((ROOT / "config/elm-pi.json").read_text())
        self.assertIn("meta", config["builtinProviders"])
        self.assertIn("META_API_KEY", config["providerCredentials"])
        self.assertTrue(set(config["allowedProviders"]).isdisjoint(config["builtinProviders"]))

    def test_launcher_reloads_guard_when_extensions_are_disabled(self):
        launcher = (ROOT / "pi").read_text()
        self.assertIn('elm_policy_extensions_disabled "$@"', launcher)
        self.assertIn('agent/extensions/elm-only.ts', launcher)

    def test_allowed_provider_parser_accepts_generated_runtime_format(self):
        extension = (ROOT / "templates/extensions/elm-only.ts").read_text()
        self.assertIn(r".split(/[\s,]+/)", extension)


    def test_web_loader_is_excluded_everywhere_the_web_tools_are(self):
        config = json.loads((ROOT / "config/elm-pi.json").read_text())
        self.assertIn("web_enable", config["webTools"])
        for name in ("qwen.md", "llama.md"):
            self.assertIn("web_enable", (ROOT / "templates/agents" / name).read_text(), name)

    def test_system_prompt_addendum_is_rendered_by_bootstrap(self):
        self.assertTrue((ROOT / "templates/APPEND_SYSTEM.md").is_file())
        self.assertIn("render templates/APPEND_SYSTEM.md agent/APPEND_SYSTEM.md",
                      (ROOT / "bootstrap.sh").read_text())

    def test_qwen_sampling_is_the_cards_non_thinking_profile(self):
        models = json.loads((ROOT / "templates/models.json").read_text())
        qwen = models["providers"]["elm"]["models"][0]["samplingParams"]
        self.assertEqual({"temperature": 0.7, "top_p": 0.8, "top_k": 20, "min_p": 0.0,
                          "presence_penalty": 1.5}, qwen)

    def test_protected_paths_guards_every_writing_tool(self):
        source = (ROOT / "templates/extensions/protected-paths.ts").read_text()
        for tool in ("write", "edit", "replace", "replace_match", "insert", "copy", "move", "undo_last_change"):
            self.assertIn(f'"{tool}"', source, tool)
        self.assertIn("must name the file it changes", source)

    def test_hashline_requires_paths_and_disables_copy_move(self):
        config = json.loads((ROOT / "templates/hashline/config.json").read_text())
        self.assertEqual({"requirePath": True, "copyMoveEnabled": False}, config)
        self.assertIn('export PI_HASHLINE_DIR="$HERE/agent/hashline"', (ROOT / "pi").read_text())

    def test_commercial_cli_agents_are_disabled_and_cannot_be_reenabled(self):
        subagents = json.loads((ROOT / "templates/settings.json").read_text())["subagents"]
        for name in ("claude-code", "claude-code-writer", "codex-exec", "codex-exec-writer",
                     "cursor-agent", "cursor-agent-writer"):
            self.assertEqual({"disabled": True}, subagents["agentOverrides"][name], name)
        self.assertTrue(subagents["disableThinking"])
        config = json.loads((ROOT / "templates/extensions/subagent/config.json").read_text())
        self.assertIn("agent-management", config["disabledFeatures"])

    def test_workflow_settings_are_owned_by_bootstrap(self):
        settings = json.loads((ROOT / "templates/workflows/settings.json").read_text())
        self.assertTrue(settings["inheritMainModel"])
        self.assertFalse(settings["keywordTriggerEnabled"])
        self.assertIn("@gotgenes/pi-permission-system", settings["providerMiddlewareExtensions"])
        self.assertIn("templates/workflows/settings.json", (ROOT / "bootstrap.sh").read_text())

    def test_steering_names_only_tools_and_apis_that_exist(self):
        for name in ("AGENTS.md", "APPEND_SYSTEM.md", "agents/qwen.md", "agents/llama.md"):
            text = (ROOT / "templates" / name).read_text()
            # removed in pi-subagents 0.74.0 / 0.70.1, or not installed here
            self.assertNotIn("workflowScript:", text, name)
            self.assertNotIn("completed without making edits", text, name)
            self.assertNotIn("`grep`, `find` and `ls`\n  rather than", text, name)
            self.assertNotIn("Prefer `read`/`grep`/`find`", text, name)

    def test_workflow_check_uses_the_packages_parser(self):
        node = ROOT / ".node/bin/node"
        package = ROOT / "agent/npm/node_modules/@quintinshaw/pi-dynamic-workflows/dist/workflow.js"
        if not (node.exists() and package.exists()):
            self.skipTest("bundled node or pi-dynamic-workflows not installed")
        good = (
            "export const meta = { name: 'probe', description: 'probe' };\n"
            "const out = await parallel(['a'].map((x) => () => agent(`say ${x}`)));\n"
            "return { report: out.join('') };\n"
        )
        # the failure seen in a real run: .map( opened, never closed
        bad = good.replace("agent(`say ${x}`)));", "agent(`say ${x}`));")
        with tempfile.TemporaryDirectory() as directory:
            results = {}
            for name, text in (("good", good), ("bad", bad)):
                path = Path(directory) / f"{name}.mjs"
                path.write_text(text)
                results[name] = subprocess.run([str(ROOT / "scripts/workflow-check"), str(path)],
                                               capture_output=True, text=True)
        self.assertEqual(0, results["good"].returncode, results["good"].stderr)
        self.assertIn("ok:", results["good"].stdout)  # top-level return is valid here
        self.assertEqual(1, results["bad"].returncode)
        self.assertIn(":2:", results["bad"].stderr)
        self.assertIn("hint:", results["bad"].stderr)

    def test_pinned_instructions_load_everywhere_the_policy_does(self):
        config = json.loads((ROOT / "config/elm-pi.json").read_text())
        self.assertIn("pinned-instructions.ts", config["requiredExtensions"])
        workflows = json.loads((ROOT / "templates/workflows/settings.json").read_text())
        self.assertIn("pinned-instructions", workflows["providerMiddlewareExtensions"])
        self.assertIn("todo pinned-instructions", (ROOT / "pi").read_text())  # --fast
        source = (ROOT / "templates/extensions/pinned-instructions.ts").read_text()
        for needle in ('name: "pin_instruction"', 'name: "unpin_instruction"',
                       "systemPromptOptions.sections.pinned_instructions", "mode: 0o600"):
            self.assertIn(needle, source)

    def test_compaction_threshold_is_installer_owned(self):
        config = json.loads((ROOT / "templates/config/pi-auto-compact/config.json").read_text())
        self.assertEqual(50, config["autoCompactThreshold"])
        self.assertIn('"config/pi-auto-compact/config.json": (', (ROOT / "bootstrap.sh").read_text())

    def test_every_skill_has_valid_frontmatter_matching_its_directory(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_install import frontmatter
        skills = sorted((ROOT / "templates/skills").glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skills), 13)
        for skill in skills:
            fields = frontmatter(skill.read_text())
            self.assertIsNotNone(fields, skill)
            self.assertEqual(skill.parent.name, fields.get("name"), skill)
            self.assertTrue(20 < len(fields.get("description", "")) <= 1024, skill)
        # an unquoted ": " is a YAML error that makes pi drop the skill
        self.assertIsNone(frontmatter("---\nname: x\ndescription: a: b\n---\n"))

    def test_agents_md_stays_slim_and_points_to_the_orchestration_skills(self):
        agents = (ROOT / "templates/AGENTS.md").read_text()
        self.assertLess(len(agents), 24000)
        for skill in ("elm-delegation", "elm-subagent-workflows", "elm-dynamic-workflows"):
            self.assertIn(f"`{skill}`", agents)
            self.assertTrue((ROOT / "templates/skills" / skill / "SKILL.md").is_file())

    def test_verify_install_reports_a_missing_declared_extension(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_install import package_problems
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "agent/npm/node_modules/demo").mkdir(parents=True)
            (root / "agent/settings.json").write_text(json.dumps({"packages": ["npm:demo", "npm:absent"]}))
            (root / "agent/npm/node_modules/demo/package.json").write_text(
                json.dumps({"name": "demo", "pi": {"extensions": ["./dist/index.js"]}}))
            problems = package_problems(root)
            self.assertIn("package demo: declared extension ./dist/index.js is missing", problems)
            self.assertTrue(any(p.startswith("package absent: not installed") for p in problems))
            (root / "agent/npm/node_modules/demo/dist").mkdir()
            (root / "agent/npm/node_modules/demo/dist/index.js").write_text("export default () => {}\n")
            self.assertEqual(1, len(package_problems(root)))  # only "absent" left

    def test_skill_router_routes_to_skills_that_exist(self):
        config = json.loads((ROOT / "config/elm-pi.json").read_text())
        self.assertIn("skill-router.ts", config["requiredExtensions"])
        source = (ROOT / "templates/extensions/skill-router.ts").read_text()
        routed = set(re.findall(r'\["([a-z-]+)", /', source))
        routed |= set(re.findall(r'return "(elm-[a-z-]+)"', source))
        skills = {p.parent.name for p in (ROOT / "templates/skills").glob("*/SKILL.md")}
        self.assertEqual(13, len(skills))
        self.assertEqual(set(), routed - skills)          # never routes to a missing skill
        self.assertEqual(skills, routed)                  # and every skill is reachable

if __name__ == "__main__":
    unittest.main()
