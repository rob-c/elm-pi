import json
import re
import subprocess
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

    def test_dynamic_workflows_is_not_enabled_until_guard_is_strict(self):
        packages = json.loads((ROOT / "templates/packages.json").read_text())["dependencies"]
        loaded = json.loads((ROOT / "templates/settings.json").read_text())["packages"]
        self.assertNotIn("@quintinshaw/pi-dynamic-workflows", packages)
        self.assertNotIn("npm:@quintinshaw/pi-dynamic-workflows", loaded)

    def test_model_templates_render_from_shared_state(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "settings.json"
            subprocess.run(
                [
                    "python3",
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


if __name__ == "__main__":
    unittest.main()
