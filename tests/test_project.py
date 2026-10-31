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
        # --fast and --no-extensions both load POLICY_EXTENSIONS
        self.assertIn('POLICY_EXTENSIONS="elm-only protected-paths trust-guard pinned-instructions"', (ROOT / "pi").read_text())
        source = (ROOT / "templates/extensions/pinned-instructions.ts").read_text()
        for needle in ('name: "pin_instruction"', 'name: "unpin_instruction"',
                       "systemPromptOptions.sections.pinned_instructions", "mode: 0o600"):
            self.assertIn(needle, source)

    def test_compaction_threshold_is_installer_owned(self):
        config = json.loads((ROOT / "templates/config/pi-auto-compact/config.json").read_text())
        self.assertEqual(70, config["autoCompactThreshold"])
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
            (root / "agent/settings.json").write_text(json.dumps(
                {"packages": [{"source": "npm:demo", "themes": []}, "npm:absent"]}))
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
        self.assertEqual(15, len(skills))
        self.assertEqual(set(), routed - skills)          # never routes to a missing skill
        self.assertEqual(skills, routed)                  # and every skill is reachable


PI = ROOT / "node_modules/@earendil-works/pi-coding-agent"
PI_PROVIDERS = ROOT / "node_modules/@earendil-works/pi-ai/dist/providers/all.js"


class PiReleaseTests(unittest.TestCase):
    """What a pi upgrade can break without failing to install."""

    def test_qwen_thinking_sampling_is_the_cards_thinking_profile(self):
        qwen = json.loads((ROOT / "templates/models.json").read_text())["providers"]["elm"]["models"][0]
        self.assertEqual({"high": {"temperature": 0.6, "top_p": 0.95, "top_k": 20, "min_p": 0.0,
                                   "presence_penalty": 0.0}}, qwen["samplingParamsByThinkingLevel"])
        # high is the only level the Qwen thinkingLevelMap turns on
        self.assertEqual(["high"], [k for k, v in qwen["thinkingLevelMap"].items() if v not in (None, "none")])

    @unittest.skipUnless(PI_PROVIDERS.is_file(), "pi is not installed in this checkout")
    def test_provider_inventory_matches_the_installed_pi(self):
        registered = set(re.findall(r'^import \{ \w+Provider \} from "\./([a-z0-9-]+)\.js"',
                                    PI_PROVIDERS.read_text(), re.M))
        self.assertGreater(len(registered), 30)
        config = json.loads((ROOT / "config/elm-pi.json").read_text())
        self.assertEqual(set(), registered - set(config["builtinProviders"]), "pi providers not stripped")
        self.assertEqual(set(), set(config["builtinProviders"]) - registered, "stripped providers pi no longer has")

    @unittest.skipUnless((PI / "schemas").is_dir(), "pi is not installed in this checkout")
    def test_templates_match_the_installed_pis_schemas(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from check_config import config_problems
        self.assertEqual([], config_problems(ROOT / "templates", PI / "schemas"))

    def test_check_config_reports_a_value_pi_stopped_accepting(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from check_config import validate
        schema = {"type": "object", "additionalProperties": False, "properties": {
            "thinkingFormat": {"anyOf": [{"const": "openai"}, {"const": "qwen"}]}}}
        problems = []
        validate({"thinkingFormat": "reasoning_effort", "statusLineBg": "#000"}, schema, schema, "m", problems)
        self.assertEqual(['m.thinkingFormat: "reasoning_effort" is not one of "openai", "qwen"',
                          "m: unknown key statusLineBg"], problems)
        problems = []
        validate({"thinkingFormat": "openai"}, schema, schema, "m", problems)
        self.assertEqual([], problems)

    def test_theme_exclusions_follow_pis_filter_rules(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from check_config import _selected
        self.assertTrue(_selected("themes/a.json", None))
        self.assertFalse(_selected("themes/a.json", []))
        self.assertFalse(_selected("themes/codex-slate.json", ["!themes/codex-slate.json"]))
        self.assertTrue(_selected("themes/other.json", ["!themes/codex-slate.json"]))
        self.assertFalse(_selected("themes/a.json", ["-themes/a.json"]))
        self.assertFalse(_selected("themes/b.json", ["themes/a.json"]))

    def test_patch_anchors_survive_a_reworded_description(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "chunk.js").write_text(
                'if(text==="/share"){await this.handleShareCommand(),this.editor.setText("");return}'
                'if(text==="/bug"||text.startsWith("/bug ")){let hint=text.slice(4).trim();'
                'this.editor.setText(""),await this.handleBugCommand(hint||void 0);return}'
                '[{name:"share",description:"Some wording no release has used yet"},'
                '{name:"bug",description:"Also new",argumentHint:"<what>"},{name:"copy"}]'
                "async function uploadBugReport(bundle,options={}){}"
                "async function tryShareViaRadius(tmpFile,context){}"
                "async function shareViaGist(tmpFile,context){}")
            run = lambda *extra: subprocess.run([sys.executable, str(ROOT / "patch-pi.py"), "--bundle", str(bundle), *extra],
                                                capture_output=True, text=True)
            self.assertEqual(0, run().returncode)
            self.assertEqual(0, run("--check").returncode)
            patched = (bundle / "chunk.js").read_text()
            self.assertNotIn('name:"share"', patched)
            self.assertNotIn('name:"bug"', patched)
            self.assertIn('{name:"copy"}', patched)

    def test_tested_versions_cover_every_direct_dependency(self):
        versions = json.loads((ROOT / "config/versions.json").read_text())
        core = json.loads((ROOT / "package.json").read_text())["dependencies"]
        packages = json.loads((ROOT / "templates/packages.json").read_text())["dependencies"]
        self.assertEqual(set(core), set(versions["core"]))
        self.assertEqual(set(packages), set(versions["packages"]))
        for version in [*versions["core"].values(), *versions["packages"].values()]:
            self.assertRegex(version, r"^\d+\.\d+\.\d+")

    def test_builtin_mcp_and_llama_cpp_are_off_and_installer_owned(self):
        settings = json.loads((ROOT / "templates/settings.json").read_text())
        self.assertIn("-builtin:mcp", settings["extensions"])
        self.assertIn("-builtin:llama.cpp", settings["extensions"])
        self.assertIn('"extensions",', (ROOT / "bootstrap.sh").read_text())

    def test_skill_router_ignores_runs_without_a_user_prompt(self):
        source = (ROOT / "templates/extensions/skill-router.ts").read_text()
        self.assertLess(source.index('event.messageType !== "user"'), source.index("event.prompt"))

    def test_install_writes_nothing_under_the_accounts_own_pi(self):
        for name in ("bootstrap.sh", "install.sh", "templates/extensions/pi-permission-system/config.json"):
            text = (ROOT / name).read_text()
            self.assertNotIn('".pi", "workflows"', text, name)
            self.assertNotIn('"~/.pi/workflows', text, name)

    def test_verification_requires_qwen_by_id_and_reads_pis_errors(self):
        bootstrap = (ROOT / "bootstrap.sh").read_text()
        self.assertNotIn("^elm(-shim)?", bootstrap)
        self.assertIn('$1 == "elm" && $2 == id', bootstrap)
        self.assertIn("errors loading models.json", bootstrap)
        self.assertIn("check_config.py", bootstrap)

    def test_workflow_agents_have_the_same_deadline_as_subagents(self):
        settings = json.loads((ROOT / "templates/workflows/settings.json").read_text())
        self.assertEqual(30 * 60 * 1000, settings["defaultAgentTimeoutMs"])
        self.assertNotIn("defaultTokenBudget", settings)

    def test_launcher_warns_when_started_inside_the_install(self):
        with tempfile.TemporaryDirectory() as directory:
            inside = Path(directory) / "install"
            (inside / "sub").mkdir(parents=True)
            outside = Path(directory) / "project"
            outside.mkdir()
            launcher = (ROOT / "pi").read_text()
            start = launcher.index("# --- note a session started inside the install")
            block = launcher[start:launcher.index("# -----", start + 10)]
            script = f'HERE="{inside}"; NEEDS_ELM_KEY="$1"; unset PI_FORCE PI_ELM_CHILD\n{block}'
            run = lambda cwd, needs="1": subprocess.run(["bash", "-c", script, "probe", needs], cwd=cwd,
                                                        capture_output=True, text=True).stderr
            self.assertIn("inside the elm-pi install", run(inside / "sub"))
            self.assertEqual("", run(outside))
            self.assertEqual("", run(inside, needs="0"))  # update, --version, --list-models

    def test_launcher_copies_through_the_terminal_unless_told_not_to(self):
        line = next(line for line in (ROOT / "pi").read_text().splitlines()
                    if line.startswith("export PI_CLIPBOARD_OSC52="))
        probe = lambda env: subprocess.run(["bash", "-c", f'{line}; printf %s "$PI_CLIPBOARD_OSC52"'],
                                           env=env, capture_output=True, text=True).stdout
        self.assertEqual("1", probe({"PATH": "/usr/bin:/bin"}))
        self.assertEqual("0", probe({"PATH": "/usr/bin:/bin", "PI_CLIPBOARD_OSC52": "0"}))

if __name__ == "__main__":
    unittest.main()
