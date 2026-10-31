"""Home, the root and credential folders are never a project.

Two halves share one list (untrustedFolders in config/elm-pi.json): the
launcher refuses to start a session in one, and trust-guard.ts keeps pi's
project trust off them - including a saved "trust parent folder" on home,
which pi would otherwise pass down to every folder under it.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
EXACT = "\n".join(CONFIG["untrustedFolders"]["exact"])
TREE = "\n".join(CONFIG["untrustedFolders"]["tree"])


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


class FolderListTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.home)
        for sub in ("src/proj", ".ssh/keys", "Documents/thesis", "Library/CloudStorage/OneDrive/proj"):
            (self.home / sub).mkdir(parents=True)

    def untrusted(self, folder):
        script = 'source "$1/lib/policy.sh"; if elm_untrusted_folder "$2"; then printf "YES:%s" "$ELM_UNTRUSTED_WHAT"; fi'
        env = {**os.environ, "HOME": str(self.home), "ELM_UNTRUSTED_EXACT": EXACT, "ELM_UNTRUSTED_TREE": TREE}
        out = subprocess.run(["bash", "-c", script, "t", str(ROOT), str(folder)],
                             env=env, capture_output=True, text=True, check=True).stdout
        return out.startswith("YES")

    def test_containers_and_credential_folders_are_refused(self):
        for folder in (self.home, self.home.parent, "/", self.home / ".ssh", self.home / ".ssh/keys",
                       self.home / "Documents", self.home / "Library/CloudStorage", "/etc", "/usr/local"):
            with self.subTest(folder=folder):
                self.assertTrue(self.untrusted(folder))

    def test_projects_anywhere_else_are_fine(self):
        for folder in (self.home / "src/proj", self.home / "Documents/thesis",
                       self.home / "Library/CloudStorage/OneDrive/proj", self.home / "src"):
            with self.subTest(folder=folder):
                self.assertFalse(self.untrusted(folder))

    def test_launcher_refuses_sessions_only(self):
        launcher = (ROOT / "pi").read_text()
        block = launcher[launcher.index("# --- not in home"):launcher.index("# --- --remote")]
        self.assertIn('[ "$NEEDS_ELM_KEY" = "1" ]', block)
        self.assertIn('[ "${PI_FORCE:-0}" != "1" ]', block)
        self.assertIn('[ -z "${PI_ELM_CHILD:-}" ]', block)
        self.assertIn("exit 2", block)

    def test_runtime_env_carries_both_lists(self):
        source = (ROOT / "scripts/elm_config.py").read_text()
        self.assertIn('"ELM_UNTRUSTED_EXACT"', source)
        self.assertIn('"ELM_UNTRUSTED_TREE"', source)


class TrustGuardTests(unittest.TestCase):
    SOURCE = ROOT / "templates/extensions/trust-guard.ts"
    RUNNER = (
        "const mod = await import(process.argv[1]);"
        "let handler; mod.default({ on: (e, h) => { if (e === 'project_trust') handler = h; } });"
        "const out = {};"
        "for (const cwd of JSON.parse(process.argv[2])) {"
        "  out[cwd] = (await handler({ type: 'project_trust', cwd }, { hasUI: false })).trusted;"
        "}"
        "console.log(JSON.stringify(out));"
    )

    def decide(self, home, saved, folders):
        binary = node()
        if not binary:
            self.skipTest("no node")
        agent = home / "agent"
        agent.mkdir(exist_ok=True)
        (agent / "trust.json").write_text(json.dumps(saved))
        env = {**os.environ, "HOME": str(home), "PI_CODING_AGENT_DIR": str(agent),
               "ELM_UNTRUSTED_EXACT": EXACT, "ELM_UNTRUSTED_TREE": TREE}
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", self.RUNNER,
                              str(self.SOURCE), json.dumps([str(f) for f in folders])],
                             env=env, capture_output=True, text=True)
        if run.returncode != 0:
            self.skipTest(f"node cannot load TypeScript here: {run.stderr.strip()[:200]}")
        return json.loads(run.stdout)

    def test_trust_is_refused_for_listed_folders_and_not_inherited_from_them(self):
        home = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, home)
        for sub in ("notes", "src/named", "src/other", ".ssh"):
            (home / sub).mkdir(parents=True)
        saved = {str(home): True, str(home / "src/named"): True}
        result = self.decide(home, saved, [home, home / ".ssh", home / "notes", home / "src/named", home / "src/other"])
        self.assertEqual("no", result[str(home)])
        self.assertEqual("no", result[str(home / ".ssh")])
        self.assertEqual("no", result[str(home / "notes")])       # would inherit ~'s trust
        self.assertEqual("no", result[str(home / "src/other")])
        self.assertEqual("undecided", result[str(home / "src/named")])  # trusted by name: pi decides

    def test_ordinary_trust_from_a_project_parent_still_applies(self):
        home = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, home)
        (home / "src/group/repo").mkdir(parents=True)
        result = self.decide(home, {str(home / "src/group"): True}, [home / "src/group/repo"])
        self.assertEqual("undecided", result[str(home / "src/group/repo")])

    def test_it_loads_whenever_policy_extensions_do(self):
        launcher = (ROOT / "pi").read_text()
        self.assertIn("trust-guard", next(l for l in launcher.splitlines() if l.startswith("POLICY_EXTENSIONS=")))
        self.assertIn("trust-guard.ts", CONFIG["requiredExtensions"])


if __name__ == "__main__":
    unittest.main()
