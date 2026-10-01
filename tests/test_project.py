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

    def test_direct_dependencies_are_exact_and_match_locks(self):
        manifests = (
            (ROOT / "package.json", ROOT / "package-lock.json"),
            (ROOT / "templates/packages.json", ROOT / "templates/packages-lock.json"),
        )
        exact = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
        for manifest_path, lock_path in manifests:
            manifest = json.loads(manifest_path.read_text())
            lock = json.loads(lock_path.read_text())
            for field in ("dependencies", "devDependencies"):
                wanted = manifest.get(field, {})
                locked = lock["packages"][""].get(field, {})
                self.assertEqual(wanted, locked)
                for name, version in wanted.items():
                    self.assertRegex(version, exact, name)
                    self.assertEqual(version, lock["packages"][f"node_modules/{name}"]["version"])

    def test_security_overrides_are_present_in_both_locked_graphs(self):
        root_manifest = json.loads((ROOT / "package.json").read_text())
        extension_manifest = json.loads((ROOT / "templates/packages.json").read_text())
        self.assertEqual("5.0.12", root_manifest["overrides"]["brace-expansion"])
        self.assertEqual("5.0.12", extension_manifest["overrides"]["brace-expansion"])
        self.assertEqual("8.10.2", extension_manifest["overrides"]["undici"])

        for lock_path in (ROOT / "package-lock.json", ROOT / "templates/packages-lock.json"):
            packages = json.loads(lock_path.read_text())["packages"]
            brace_versions = {
                value["version"]
                for path, value in packages.items()
                if path.endswith("node_modules/brace-expansion")
            }
            self.assertTrue(brace_versions)
            self.assertEqual({"5.0.12"}, brace_versions)
        extension_packages = json.loads((ROOT / "templates/packages-lock.json").read_text())["packages"]
        undici_versions = {
            value["version"]
            for path, value in extension_packages.items()
            if path.endswith("node_modules/undici")
        }
        self.assertTrue(undici_versions)
        self.assertEqual({"8.10.2"}, undici_versions)
        bootstrap = (ROOT / "bootstrap.sh").read_text()
        self.assertEqual(2, bootstrap.count('scripts/repair-transitives.sh'))

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
