"""The permission modes, decided by the permission gate's own code.

patch-pi.py --gate makes pi-permission-system read PI_ELM_PERMISSION_MODE on
every decision (see "The permission gate" in patch-pi.py). Here the installed,
patched package - loaded with jiti, as pi loads it - decides the same requests
in each mode against templates/extensions/pi-permission-system/config.json,
filled in the way bootstrap.sh fills it:

- manual: nothing but reading inside the project, and the tools in
  config/elm-pi.json permissionModes.manualNoPrompt, runs without an ask;
  a deny is still a deny, and a session approval still holds;
- auto: the policy as written;
- yolo: every ask is allowed, a deny is still a deny.

The PermissionManager is built the way the patched index.ts builds it, its yolo
reader included; a test checks that index.ts really says so. The bash cases
also go through command-guard.ts, which pi runs beside the gate. The tests skip
on a checkout that has not been bootstrapped, and on an install whose gate was
not patched (--no-patch).
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/extensions/pi-permission-system/config.json"
GUARD = ROOT / "templates/extensions/command-guard.ts"
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
NPM = ROOT / "agent/npm/node_modules"
PACKAGE = NPM / "@gotgenes/pi-permission-system"
JITI = NPM / "jiti/lib/jiti.mjs"
NO_PROMPT = CONFIG["permissionModes"]["manualNoPrompt"]


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def patched():
    try:
        return ('PI_ELM_PERMISSION_MODE === "manual"' in (PACKAGE / "src/policy/permission-manager.ts").read_text()
                and 'PI_ELM_PERMISSION_MODE === "yolo"' in (PACKAGE / "src/index.ts").read_text())
    except OSError:
        return False


RUNNER = r"""
const [jitiPath, pkg, agentDir, cwd, casesPath, guardPath] = process.argv.slice(1);
const { readFileSync } = await import("node:fs");
const { createJiti } = await import(jitiPath);
const jiti = createJiti(import.meta.url, { fsCache: false });
const load = (p) => jiti.import(`${pkg}/src/${p}`);
const { PermissionManager } = await load("policy/permission-manager.ts");
const { PermissionResolver } = await load("policy/permission-resolver.ts");
const { BashProgram } = await load("access-intent/bash/program.ts");
const { resolveBashCommandCheck } = await load("handlers/gates/bash-command.ts");
const { PathNormalizer } = await load("path/path-normalizer.ts");
const { posixPathFlavor } = await load("path/path-flavor.ts");
const { capabilitySurfaceForTool } = await load("access-intent/path-surfaces.ts");
const { getGlobalConfigPath } = await load("config/config-paths.ts");
const guard = await jiti.import(guardPath);

const cases = JSON.parse(readFileSync(casesPath, "utf8"));
const config = JSON.parse(readFileSync(getGlobalConfigPath(agentDir), "utf8"));
const normalizer = new PathNormalizer(posixPathFlavor, cwd);
const pick = (r) => ({ state: r.state, pattern: r.matchedPattern ?? null });
const out = {};

for (const mode of cases.modes) {
  process.env.PI_ELM_PERMISSION_MODE = mode;
  // As the patched index.ts builds it.
  const manager = new PermissionManager({
    agentDir,
    isYoloEnabled: () => process.env.PI_ELM_PERMISSION_MODE === "yolo",
  });
  manager.configureForCwd(cwd);
  const resolverWith = (session) => new PermissionResolver(manager, { getRuleset: () => session });
  const plain = resolverWith([]);
  const approved = resolverWith(cases.session);
  const bash = async (command, resolver) => {
    const program = await BashProgram.parse(command, normalizer);
    const gate = pick(resolveBashCommandCheck(command, program.commands(), undefined, resolver));
    const denial = gate.state === "deny" ? undefined : guard.deniedSpelling(command, config.permission.bash);
    return denial ? { state: "deny", pattern: denial.pattern } : gate;
  };
  const r = (out[mode] = { bash: {}, tools: {}, path: {}, external: {}, approved: {} });
  for (const command of cases.bash) r.bash[command] = await bash(command, plain);
  for (const command of cases.bash) r.approved[command] = await bash(command, approved);
  for (const [tool, input] of cases.tools) r.tools[tool] = pick(plain.resolve({ kind: "tool", surface: tool, input }));
  const onSurface = (family, tool, path) => pick(plain.resolve({
    kind: "access-path",
    surface: capabilitySurfaceForTool(family, tool),
    path: normalizer.forToolPath(tool, path),
  }));
  for (const [tool, path] of cases.path) r.path[`${tool} ${path}`] = onSurface("path", tool, path);
  for (const [tool, path] of cases.external) r.external[`${tool} ${path}`] = onSurface("external_directory", tool, path);
}
console.log(JSON.stringify(out));
"""

A, ASK, D = "allow", "ask", "deny"

# command: (auto, manual, yolo)
BASH = {
    "ls -la": (A, ASK, A),
    "cat notes.txt": (A, ASK, A),
    "git status": (A, ASK, A),
    "python3 fit.py --plot": (A, ASK, A),
    "rm -rf build": (A, ASK, A),
    "git push": (ASK, ASK, A),
    "sudo ls": (ASK, ASK, A),
    "pi update": (ASK, ASK, A),
    "pi -p hello": (A, ASK, A),
    # A session the agent starts from its own shell asks before it can be yolo.
    "pi --yolo -p 'run the tests'": (ASK, ASK, A),
    "pi -p x --yolo": (ASK, ASK, A),
    "ssh host": (D, D, D),
    "cd x && 'ssh' host": (D, D, D),
}

# tool, input: (auto, manual, yolo)
TOOLS = [
    ("read", {"path": "notes.txt"}, (A, A, A)),
    ("grep", {"pattern": "x", "path": "."}, (A, A, A)),
    ("find", {"pattern": "*.py"}, (A, A, A)),
    ("ls", {"path": "."}, (A, A, A)),
    ("view", {"path": "fig.png"}, (A, A, A)),
    ("todo", {"action": "list"}, (A, A, A)),
    ("ask_user_question", {"question": "?"}, (A, A, A)),
    ("pin_instruction", {"text": "x"}, (A, A, A)),
    ("notebook_read_cell", {"path": "a.ipynb", "index": 0}, (A, A, A)),
    ("bg_wait", {}, (A, A, A)),
    ("contact_supervisor", {"message": "x"}, (A, A, A)),
    ("write", {"path": "notes.txt", "content": "x"}, (A, ASK, A)),
    ("edit", {"path": "notes.txt", "edits": []}, (A, ASK, A)),
    ("replace", {"path": "notes.txt"}, (A, ASK, A)),
    ("python", {"code": "print(1)"}, (A, ASK, A)),
    ("notebook_write_cell", {"path": "a.ipynb", "index": 0, "source": "x"}, (A, ASK, A)),
    ("subagent", {"task": "x"}, (A, ASK, A)),
    ("workflow", {"script": "x"}, (A, ASK, A)),
    ("ralph_start", {}, (A, ASK, A)),
    # A tool nobody has listed yet asks in manual.
    ("some_new_tool", {}, (A, ASK, A)),
]

# The path rules are where, not what: the same in auto and manual.
PATH = {
    ("read", ".env"): (D, D, D),
    ("write", ".env"): (D, D, D),
    ("read", "src/main.py"): (A, A, A),
    # The mode new sessions start in is the user's: denied to the agent's tools
    # in every mode, yolo included.
    ("write", "{agent}/permission-mode"): (D, D, D),
    ("read", "{agent}/permission-mode"): (D, D, D),
}
EXTERNAL = {
    ("read", "/etc/hosts"): (ASK, ASK, A),
}

# An "allow for this session" answer holds in manual mode.
SESSION = [{"surface": "bash", "pattern": "ls *", "action": "allow", "origin": "session", "layer": "session"}]
APPROVED = {"ls -la": A, "git status": ASK, "ssh host": D}

MODES = ("auto", "manual", "yolo")


@unittest.skipUnless(JITI.exists() and PACKAGE.exists() and node(), "needs a bootstrapped checkout")
@unittest.skipUnless(patched(), "the permission gate is not patched (patch-pi.py --gate; --no-patch installs)")
class PermissionModeDecisionTests(unittest.TestCase):
    @classmethod
    def fill(cls, path):
        return path.replace("{agent}", str(cls.tmp / "install/agent"))

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        install, home, cwd = cls.tmp / "install", cls.tmp / "home", cls.tmp / "project"
        for d in (install / "agent", home, cwd):
            d.mkdir(parents=True)
        rendered = TEMPLATE.read_text().replace("@INSTALL_DIR@", str(install)).replace("@AGENT_DIR@", str(install / "agent"))
        target = install / "agent/extensions/pi-permission-system/config.json"
        target.parent.mkdir(parents=True)
        target.write_text(rendered)
        cases = {
            "modes": MODES,
            "bash": list(BASH),
            "tools": [[tool, value] for tool, value, _ in TOOLS],
            "path": [[tool, cls.fill(path)] for tool, path in PATH],
            "external": [list(k) for k in EXTERNAL],
            "session": SESSION,
        }
        (cls.tmp / "cases.json").write_text(json.dumps(cases))
        env = {**os.environ, "HOME": str(home), "PI_CODING_AGENT_DIR": str(install / "agent"),
               "PI_ELM_MANUAL_ALLOW": ",".join(NO_PROMPT)}
        env.pop("PI_ELM_PERMISSION_MODE", None)
        proc = subprocess.run([node(), "--no-warnings", "--input-type=module", "-e", RUNNER, str(JITI), str(PACKAGE),
                               str(install / "agent"), str(cwd), str(cls.tmp / "cases.json"), str(GUARD)],
                              capture_output=True, text=True, env=env, cwd=cwd, timeout=300)
        if proc.returncode != 0:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise AssertionError(f"runner failed:\n{proc.stderr}")
        cls.out = json.loads(proc.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def decided(self, mode, kind, key):
        return self.out[mode][kind][key]["state"]

    def test_bash(self):
        for command, want in BASH.items():
            for mode, state in zip(MODES, want):
                with self.subTest(mode=mode, command=command):
                    self.assertEqual(state, self.decided(mode, "bash", command))

    def test_tools(self):
        for tool, _, want in TOOLS:
            for mode, state in zip(MODES, want):
                with self.subTest(mode=mode, tool=tool):
                    self.assertEqual(state, self.decided(mode, "tools", tool))

    def test_paths(self):
        for (tool, path), want in PATH.items():
            for mode, state in zip(MODES, want):
                with self.subTest(mode=mode, path=f"{tool} {path}"):
                    self.assertEqual(state, self.decided(mode, "path", f"{tool} {self.fill(path)}"))
        for (tool, path), want in EXTERNAL.items():
            for mode, state in zip(MODES, want):
                with self.subTest(mode=mode, external=f"{tool} {path}"):
                    self.assertEqual(state, self.decided(mode, "external", f"{tool} {path}"))

    def test_a_session_approval_holds_in_manual(self):
        for command, state in APPROVED.items():
            with self.subTest(command=command):
                self.assertEqual(state, self.decided("manual", "approved", command))

    def test_manual_keeps_the_pattern_that_decided(self):
        # An ask the floor made still names the rule it came from, so the prompt
        # and the review log say which rule matched.
        self.assertEqual("git push *", self.out["manual"]["bash"]["git push"]["pattern"])

    def test_every_no_prompt_tool_is_covered_here(self):
        self.assertEqual(set(NO_PROMPT) - {"outline", "tool_search", "unpin_instruction", "notebook_read_cell_output",
                                           "notebook_summary"},
                         {tool for tool, _, want in TOOLS if want[1] == A})


@unittest.skipUnless(PACKAGE.exists(), "needs a bootstrapped checkout")
@unittest.skipUnless(patched(), "the permission gate is not patched")
class PatchedGateTests(unittest.TestCase):
    def test_index_builds_the_manager_with_the_process_mode(self):
        index = (PACKAGE / "src/index.ts").read_text()
        self.assertIn('process.env.PI_ELM_PERMISSION_MODE === "yolo" || isYoloModeEnabled(configStore.current())', index)
        self.assertIn("isYoloEnabled,", index)

    def test_the_check_applies_manual_after_yolo(self):
        manager = (PACKAGE / "src/policy/permission-manager.ts").read_text()
        self.assertLess(manager.index("rewriteAsksToYolo(composedWithSession)"),
                        manager.index('PI_ELM_PERMISSION_MODE === "manual"'))


if __name__ == "__main__":
    unittest.main()
