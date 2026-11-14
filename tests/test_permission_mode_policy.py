"""Every rule of the shipped policy, under each permission mode, by the gate's own code.

templates/extensions/pi-permission-system/config.json is rendered as bootstrap.sh
renders it, and the installed, patched pi-permission-system decides one request
per rule - a command made from each `bash` pattern, a path from each `path` and
`external_directory` pattern, and a call to each tool - in auto, manual and yolo.
The modes must keep to their definitions, whatever the rule says:

  - a deny is a deny in every mode;
  - manual: a bash command, an edit or any tool asks unless auto already denies
    it; the path and external_directory rules (where, not what) keep their own
    answer, and so do the tools in permissionModes.manualNoPrompt;
  - yolo: whatever auto would ask is allowed.

So the cases are checked against auto's decision, which is the policy as
written, and nothing here restates the policy itself. The bash cases also go
through command-guard.ts, as pi runs it. Skipped on a checkout that has not
been bootstrapped, or whose gate is not patched.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/extensions/pi-permission-system/config.json"
GUARD = ROOT / "templates/extensions/command-guard.ts"
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
NO_PROMPT = CONFIG["permissionModes"]["manualNoPrompt"]
PERMISSION = json.loads(TEMPLATE.read_text())["permission"]
NPM = ROOT / "agent/npm/node_modules"
PACKAGE = NPM / "@gotgenes/pi-permission-system"
JITI = NPM / "jiti/lib/jiti.mjs"


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def patched():
    try:
        return 'PI_ELM_PERMISSION_MODE === "manual"' in (PACKAGE / "src/policy/permission-manager.ts").read_text()
    except OSError:
        return False


def command_for(pattern):
    """A command the pattern matches: each * made a word."""
    return re.sub(r"\s+", " ", pattern.replace("*", "x")).strip() or "x"


def path_for(pattern):
    """A path the pattern matches: ** made two folders, * one name."""
    return pattern.replace("**", "a/b").replace("*", "x")


# Every tool a session has (as listed by a probe of a real one), the web and
# workflow tools, and one nobody has registered.
TOOLS = sorted(set(NO_PROMPT) | {
    "bash", "write", "edit", "replace", "replace_match", "insert", "copy", "move", "undo_last_change",
    "python", "python_set_interpreter", "codemode", "powershell", "notebook_create", "notebook_delete",
    "notebook_edit_cell", "notebook_insert", "notebook_write_cell", "subagent", "subagent_launch",
    "subagents_enable", "subagent_supervisor", "workflow", "workflow_control", "ralph_start", "ralph_done",
    *CONFIG["webTools"], "some_tool_nobody_registered"})
# The tools whose input names a file: given one in the project.
PATH_TOOLS = {"read", "write", "edit", "grep", "find", "ls", "view", "outline", "replace", "replace_match",
              "insert", "copy", "move", "undo_last_change"}

BASH = {pattern: command_for(pattern) for pattern in PERMISSION["bash"]}
PATHS = {pattern: path_for(pattern) for pattern in PERMISSION["path"]}
EXTERNAL = {(section, pattern): path_for(pattern) for section in ("external_directory", "external_directory_read")
            for pattern in PERMISSION[section]}

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
const { resolveYoloGrant } = await load("handlers/gates/helpers.ts");
const { PathNormalizer } = await load("path/path-normalizer.ts");
const { posixPathFlavor } = await load("path/path-flavor.ts");
const { capabilitySurfaceForTool } = await load("access-intent/path-surfaces.ts");
const { getGlobalConfigPath } = await load("config/config-paths.ts");
const guard = await jiti.import(guardPath);
const cases = JSON.parse(readFileSync(casesPath, "utf8"));
const config = JSON.parse(readFileSync(getGlobalConfigPath(agentDir), "utf8"));
const normalizer = new PathNormalizer(posixPathFlavor, cwd);
const out = {};
for (const mode of ["auto", "manual", "yolo"]) {
  process.env.PI_ELM_PERMISSION_MODE = mode;
  const manager = new PermissionManager({ agentDir, isYoloEnabled: () => process.env.PI_ELM_PERMISSION_MODE === "yolo" });
  manager.configureForCwd(cwd);
  const resolver = new PermissionResolver(manager, { getRuleset: () => [] });
  const r = (out[mode] = { bash: {}, path: {}, external: {}, tools: {} });
  for (const command of cases.bash) {
    try {
      const program = await BashProgram.parse(command, normalizer);
      // As the tool-call gate does: an ask raised after resolution (a wrapper's
      // floor, an unparsed command) is granted under yolo by the same reader.
      const check = resolveBashCommandCheck(command, program.commands(), undefined, resolver);
      const grant = resolveYoloGrant(check, process.env.PI_ELM_PERMISSION_MODE === "yolo");
      const gate = (grant ?? check).state;
      const denied = gate !== "deny" && guard.deniedSpelling(command, config.permission.bash);
      r.bash[command] = denied ? "deny" : gate;
    } catch (e) { r.bash[command] = "error: " + e.message; }
  }
  const onSurface = (family, tool, path) => plainState(resolver.resolve({
    kind: "access-path", surface: capabilitySurfaceForTool(family, tool), path: normalizer.forToolPath(tool, path) }));
  for (const [tool, path] of cases.path) r.path[`${tool} ${path}`] = onSurface("path", tool, path);
  for (const [tool, path] of cases.external) r.external[`${tool} ${path}`] = onSurface("external_directory", tool, path);
  for (const [tool, input] of cases.tools) r.tools[tool] = plainState(resolver.resolve({ kind: "tool", surface: tool, input }));
}
function plainState(result) { return result.state; }
console.log(JSON.stringify(out));
"""


@unittest.skipUnless(JITI.exists() and PACKAGE.exists() and node(), "needs a bootstrapped checkout")
@unittest.skipUnless(patched(), "the permission gate is not patched (patch-pi.py --gate)")
class PolicyUnderEachModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        install, home, cwd = cls.tmp / "install", cls.tmp / "home", cls.tmp / "project"
        for d in (install / "agent/extensions/pi-permission-system", home, cwd):
            d.mkdir(parents=True)
        cls.fill = staticmethod(lambda p: (p.replace("@INSTALL_DIR@", str(install)).replace("@AGENT_DIR@", str(install / "agent"))
                              .replace("~", str(home), 1) if p.startswith("~") else
                              p.replace("@INSTALL_DIR@", str(install)).replace("@AGENT_DIR@", str(install / "agent"))))
        (install / "agent/extensions/pi-permission-system/config.json").write_text(
            TEMPLATE.read_text().replace("@INSTALL_DIR@", str(install)).replace("@AGENT_DIR@", str(install / "agent")))
        cases = {
            "bash": sorted(set(BASH.values())),
            "path": [["read", cls.fill(p)] for p in PATHS.values()] + [["write", cls.fill(p)] for p in PATHS.values()],
            "external": [["read", cls.fill(p)] for p in EXTERNAL.values()] + [["write", cls.fill(p)] for p in EXTERNAL.values()],
            "tools": [[t, {"path": "notes.txt"} if t in PATH_TOOLS else {}] for t in TOOLS],
        }
        (cls.tmp / "cases.json").write_text(json.dumps(cases))
        env = {**os.environ, "HOME": str(home), "PI_CODING_AGENT_DIR": str(install / "agent"), "NO_COLOR": "1",
               "PI_ELM_MANUAL_ALLOW": ",".join(NO_PROMPT)}
        run = subprocess.run([node(), "--no-warnings", "--input-type=module", "-e", RUNNER, str(JITI), str(PACKAGE),
                              str(install / "agent"), str(cwd), str(cls.tmp / "cases.json"), str(GUARD)],
                             capture_output=True, text=True, env=env, cwd=cwd, timeout=600)
        if run.returncode != 0:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise AssertionError(f"runner failed:\n{run.stderr[-3000:]}")
        cls.out = json.loads(run.stdout)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def modes(self, kind, key):
        return tuple(self.out[m][kind][key] for m in ("auto", "manual", "yolo"))

    def check_bash(self, command):
        auto, manual, yolo = self.modes("bash", command)
        self.assertIn(auto, ("allow", "ask", "deny"), command)
        self.assertEqual("deny" if auto == "deny" else "ask", manual, command)
        self.assertEqual("deny" if auto == "deny" else "allow", yolo, command)

    def check_where(self, kind, key):
        auto, manual, yolo = self.modes(kind, key)
        self.assertIn(auto, ("allow", "ask", "deny"), key)
        self.assertEqual(auto, manual, f"{key}: a path rule keeps its own answer in manual")
        self.assertEqual("allow" if auto == "ask" else auto, yolo, key)

    def check_tool(self, tool):
        auto, manual, yolo = self.modes("tools", tool)
        self.assertIn(auto, ("allow", "ask", "deny"), tool)
        if auto == "deny":
            self.assertEqual(("deny", "deny"), (manual, yolo), tool)
            return
        self.assertEqual("allow" if tool in NO_PROMPT else "ask", manual, tool)
        self.assertEqual("allow", yolo, tool)

    # a few facts about the policy itself that the modes depend on
    def test_every_bash_rule_produced_a_decision(self):
        self.assertEqual(set(BASH.values()), set(self.out["auto"]["bash"]))

    def test_auto_runs_most_commands(self):
        self.assertEqual("allow", self.out["auto"]["bash"]["ls"] if "ls" in self.out["auto"]["bash"]
                         else self.out["auto"]["bash"]["x"])

    def test_no_prompt_tools_are_allowed_in_auto_too(self):
        for tool in NO_PROMPT:
            with self.subTest(tool=tool):
                self.assertEqual("allow", self.out["auto"]["tools"][tool])


def _slug(text, limit=70):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:limit] or "star"


_seen = set()
for _i, (_pattern, _command) in enumerate(BASH.items()):
    _name = f"test_bash_{_i:03d}_{_slug(_pattern)}"
    setattr(PolicyUnderEachModeTests, _name, lambda self, c=_command: self.check_bash(c))
for _i, (_pattern, _path) in enumerate(PATHS.items()):
    for _tool in ("read", "write"):
        setattr(PolicyUnderEachModeTests, f"test_path_{_i:02d}_{_tool}_{_slug(_pattern)}",
                lambda self, t=_tool, p=_path: self.check_where("path", f"{t} {self.fill(p)}"))
for _i, ((_section, _pattern), _path) in enumerate(EXTERNAL.items()):
    for _tool in ("read", "write"):
        setattr(PolicyUnderEachModeTests, f"test_{_section}_{_i:02d}_{_tool}_{_slug(_pattern)}",
                lambda self, t=_tool, p=_path: self.check_where("external", f"{t} {self.fill(p)}"))
for _tool in TOOLS:
    setattr(PolicyUnderEachModeTests, f"test_tool_{_tool}", lambda self, t=_tool: self.check_tool(t))


if __name__ == "__main__":
    unittest.main()
