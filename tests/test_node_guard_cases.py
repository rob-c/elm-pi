"""lib/node-guard.mjs, case by case, in a temporary install of its own.

The guard keeps packages from outside the install out of pi, whichever loader
asks: Node's (require, import, require.resolve) through a resolve hook, and
jiti's through vm.runInThisContext. A copy is placed in a temporary install, so
its root is known and nothing here touches the checkout:

    base/
      node_modules/above/index.js           a package above the install
      .node_modules/globalish.js            a "global folder" above it
      outside/node_modules/far/index.js      a package elsewhere
      outside/project/ext.js                 a project file, not a package
      inst/                                 the install (the guard's root)
        lib/node-guard.mjs
        node_modules/inside/index.js
        agent/npm/node_modules/pkg/index.js
        agent/extensions/local.ts
        links/to-outside -> ../../outside   a link out of the install
      link-to-inst -> inst                  a link into it

Each case states where a file is and what the guard must decide; one node
process answers every case.
"""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "lib/node-guard.mjs"


def node():
    """The bundled node, or one on PATH with module.registerHooks (22.15+)."""
    bundled = ROOT / ".node/bin/node"
    if bundled.exists():
        return str(bundled)
    found = shutil.which("node")
    if found and subprocess.run([found, "-e", "process.exit(typeof require('node:module').registerHooks === 'function' ? 0 : 1)"],
                                capture_output=True).returncode == 0:
        return found
    return None


# path (from base) -> is it a package from outside the install?
OUTSIDE = {
    # the install's own files and packages
    "inst/node_modules/inside/index.js": False,
    "inst/agent/npm/node_modules/pkg/index.js": False,
    "inst/agent/extensions/local.ts": False,
    "inst/lib/node-guard.mjs": False,
    "inst/node_modules": False,
    "inst/agent/npm/node_modules/pkg/missing-file.js": False,
    # a file not there yet, under a link into the install: placed by its folder
    "link-to-inst/agent/npm/node_modules/pkg/missing-file.js": False,
    "inst/links/to-outside/node_modules/far/missing-file.js": True,
    # reached through a link into the install: still its own
    "link-to-inst/node_modules/inside/index.js": False,
    "link-to-inst/agent/npm/node_modules/pkg/index.js": False,
    "link-to-inst/agent/extensions/local.ts": False,
    # packages from anywhere else
    "node_modules/above/index.js": True,
    "node_modules": True,
    ".node_modules/globalish.js": True,
    ".node_libraries/lib.js": True,
    "outside/node_modules/far/index.js": True,
    "outside/node_modules/far/missing-file.js": True,
    "outside/node_modules/@scope/pkg/index.js": True,
    "outside/a/b/c/node_modules/deep/index.js": True,
    # through a link out of the install: where it really is decides
    "inst/links/to-outside/node_modules/far/index.js": True,
    # files that are not in a package directory: left alone
    "outside/project/ext.js": False,
    "outside/project/node_modules_backup/x.js": False,
    "outside/project/my-node_modules/x.js": False,
    "outside/project/node_modules.js": False,
    "outside/project/.node_modules_old/x.js": False,
    "outside/project/Node_Modules/x.js": False,
    "outside/project/x.node_modules/y.js": False,
    "inst/links/to-outside/project/ext.js": False,
    # a sibling whose name starts with the install's
    "inst-old/node_modules/x/index.js": True,
    "inst-old/lib/thing.js": False,
}

FILES = [
    "node_modules/above/index.js", ".node_modules/globalish.js", ".node_libraries/lib.js",
    "outside/node_modules/far/index.js", "outside/node_modules/@scope/pkg/index.js",
    "outside/a/b/c/node_modules/deep/index.js", "outside/project/ext.js",
    "outside/project/node_modules_backup/x.js", "outside/project/my-node_modules/x.js",
    "outside/project/node_modules.js", "outside/project/.node_modules_old/x.js",
    "outside/project/Node_Modules/x.js", "outside/project/x.node_modules/y.js",
    "inst/node_modules/inside/index.js", "inst/agent/npm/node_modules/pkg/index.js",
    "inst/agent/extensions/local.ts", "inst-old/node_modules/x/index.js", "inst-old/lib/thing.js",
]

# vm.runInThisContext(code, options) -> "ran" or "refused"
VM = {
    "options_with_an_outside_package": ({"filename": "outside/node_modules/far/index.js"}, "refused"),
    "a_string_filename_outside": ("outside/node_modules/far/index.js", "refused"),
    "a_package_above_the_install": ({"filename": "node_modules/above/index.js"}, "refused"),
    "a_global_folder": ({"filename": ".node_modules/globalish.js"}, "refused"),
    "the_installs_own_package": ({"filename": "inst/agent/npm/node_modules/pkg/index.js"}, "ran"),
    "the_installs_own_extension": ({"filename": "inst/agent/extensions/local.ts"}, "ran"),
    "a_project_file": ({"filename": "outside/project/ext.js"}, "ran"),
    "through_a_link_into_the_install": ({"filename": "link-to-inst/agent/npm/node_modules/pkg/index.js"}, "ran"),
    "through_a_link_out_of_the_install": ({"filename": "inst/links/to-outside/node_modules/far/index.js"}, "refused"),
    "no_options": (None, "ran"),
    "options_without_a_filename": ({}, "ran"),
    "an_empty_filename": ({"filename": ""}, "ran"),
    "the_default_name": ({"filename": "evalmachine.<anonymous>"}, "ran"),
    "a_relative_package_path": ({"filename": "node_modules/x/index.js", "relative": True}, "refused"),
    # not the guard's to judge: Node refuses it with its own error, as without the guard
    "a_numeric_filename": ({"filename": 7}, "node's own error"),
    "other_options_are_kept": ({"filename": "outside/project/ext.js", "lineOffset": 3}, "ran"),
}

# what each loader may bring in, from a file inside the install
LOAD = {
    "require_a_package_above": ("require", "above", "refused"),
    "import_a_package_above": ("import", "above", "refused"),
    "resolve_a_package_above": ("resolve", "above", "refused"),
    "require_the_installs_own_package": ("require", "inside", "loaded"),
    "import_the_installs_own_package": ("import", "inside", "loaded"),
    "resolve_the_installs_own_package": ("resolve", "inside", "loaded"),
    "require_a_builtin": ("require", "node:path", "loaded"),
    "import_a_builtin": ("import", "node:path", "loaded"),
    "require_a_missing_package": ("require", "no-such-package-anywhere", "missing"),
    "require_an_outside_file_by_path": ("require", "@outside/project/ext.js", "loaded"),
    "require_an_outside_package_file_by_path": ("require", "@outside/node_modules/far/index.js", "refused"),
    "import_an_outside_package_file_by_path": ("import", "@outside/node_modules/far/index.js", "refused"),
}

RUNNER = r"""
import { createRequire } from "node:module";
import vm from "node:vm";
import { pathToFileURL } from "node:url";
import { join } from "node:path";
const [base, casesJson] = process.argv.slice(1);
const cases = JSON.parse(casesJson);
const { outsideFile } = await import(pathToFileURL(join(base, "inst/lib/node-guard.mjs")).href);
const out = { outside: {}, vm: {}, load: {}, env: {} };
for (const rel of cases.outside) out.outside[rel] = outsideFile(join(base, rel));
for (const [name, [options]] of Object.entries(cases.vm)) {
  let arg = options;
  if (options && typeof options === "object" && typeof options.filename === "string" && options.filename)
    arg = { ...options, filename: options.relative ? options.filename : join(base, options.filename) };
  if (arg && typeof arg === "object") delete arg.relative;
  if (typeof options === "string") arg = join(base, options);
  try { vm.runInThisContext("1 + 1", arg ?? undefined); out.vm[name] = "ran"; }
  catch (e) { out.vm[name] = e.message.startsWith("elm-pi: refusing") ? "refused" : "threw: " + e.message; }
}
const from = join(base, "inst/agent/extensions/local.ts");
const req = createRequire(from);
for (const [name, [how, what]] of Object.entries(cases.load)) {
  const target = what.startsWith("@") ? join(base, what.slice(1)) : what;
  const classify = (e) => e.message.startsWith("elm-pi: refusing") ? "refused" : (e.code === "MODULE_NOT_FOUND" || e.code === "ERR_MODULE_NOT_FOUND") ? "missing" : "threw: " + e.message;
  try {
    if (how === "require") req(target);
    else if (how === "resolve") req.resolve(target);
    else await import(target.startsWith("/") ? pathToFileURL(target).href : target.startsWith("node:") ? target : pathToFileURL(req.resolve(target)).href);
    out.load[name] = "loaded";
  } catch (e) { out.load[name] = classify(e); }
}
for (const key of ["LD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "OPENSSL_CONF", "ELM_PI_STASH__LD_LIBRARY_PATH", "ELM_PI_STASH__", "KEEP"])
  out.env[key] = process.env[key] ?? null;
console.log(JSON.stringify(out));
"""


class NodeGuardCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        binary = node()
        if binary is None:
            raise unittest.SkipTest("needs a node with module.registerHooks")
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        base = cls.tmp
        try:
            for rel in FILES:
                path = base / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('module.exports = "loaded";\n' if rel.endswith(".js") else "export default 1;\n")
            for name, rel in (("above", "node_modules/above"), ("inside", "inst/node_modules/inside"),
                              ("far", "outside/node_modules/far")):
                (base / rel / "package.json").write_text(json.dumps({"name": name, "main": "index.js"}))
            (base / "inst/lib").mkdir(parents=True)
            (base / "inst/lib/node-guard.mjs").write_text(GUARD.read_text())
            (base / "inst/links").mkdir()
            (base / "inst/links/to-outside").symlink_to(base / "outside")
            (base / "link-to-inst").symlink_to(base / "inst")
            cases = {"outside": list(OUTSIDE), "vm": {k: [v[0]] for k, v in VM.items()},
                     "load": {k: [v[0], v[1]] for k, v in LOAD.items()}}
            env = {"PATH": "/usr/bin:/bin", "HOME": str(base), "ELM_PI_STASH__LD_LIBRARY_PATH": "/conda/lib",
                   "ELM_PI_STASH__DYLD_FALLBACK_LIBRARY_PATH": "/opt/lib", "ELM_PI_STASH__OPENSSL_CONF": "/etc/ssl.cnf",
                   "ELM_PI_STASH__": "nameless", "KEEP": "kept"}
            run = subprocess.run([binary, "--import", str(base / "inst/lib/node-guard.mjs"), "--input-type=module",
                                  "-e", RUNNER, str(base), json.dumps(cases)],
                                 capture_output=True, text=True, env=env, cwd=base / "outside/project", timeout=120)
            if run.returncode != 0:
                raise AssertionError(run.stderr[-3000:])
            cls.out = json.loads(run.stdout)
            allowed = subprocess.run([binary, "--import", str(base / "inst/lib/node-guard.mjs"), "--input-type=module",
                                      "-e", RUNNER, str(base), json.dumps(cases)],
                                     capture_output=True, text=True, env={**env, "ELM_PI_ALLOW_EXTERNAL_MODULES": "1"},
                                     cwd=base / "outside/project", timeout=120)
            if allowed.returncode != 0:
                raise AssertionError(allowed.stderr[-3000:])
            cls.allowed = json.loads(allowed.stdout)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # the environment the guard hands back to the agent's commands
    def test_a_stashed_library_path_is_restored(self):
        self.assertEqual("/conda/lib", self.out["env"]["LD_LIBRARY_PATH"])

    def test_every_stashed_variable_is_restored(self):
        self.assertEqual(("/opt/lib", "/etc/ssl.cnf"),
                         (self.out["env"]["DYLD_FALLBACK_LIBRARY_PATH"], self.out["env"]["OPENSSL_CONF"]))

    def test_the_stash_names_are_removed(self):
        self.assertIsNone(self.out["env"]["ELM_PI_STASH__LD_LIBRARY_PATH"])

    def test_a_stash_with_no_name_restores_nothing_and_goes(self):
        self.assertIsNone(self.out["env"]["ELM_PI_STASH__"])

    def test_other_variables_are_untouched(self):
        self.assertEqual("kept", self.out["env"]["KEEP"])


def _outside(self, rel, want):
    self.assertIs(want, self.out["outside"][rel], rel)


def _vm(self, name, want):
    if want == "node's own error":
        self.assertTrue(self.out["vm"][name].startswith("threw: "), self.out["vm"][name])
        self.assertEqual(self.out["vm"][name], self.allowed["vm"][name])
        return
    self.assertEqual(want, self.out["vm"][name])
    # with the check lifted, everything runs
    self.assertEqual("ran", self.allowed["vm"][name])


def _load(self, name, want):
    self.assertEqual(want, self.out["load"][name])
    lifted = {"refused": "loaded"}.get(want, want)
    self.assertEqual(lifted, self.allowed["load"][name])


def _slug(text):
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower()


for _rel, _want in OUTSIDE.items():
    setattr(NodeGuardCaseTests, f"test_{'outside' if _want else 'own'}_{_slug(_rel)}",
            lambda self, r=_rel, w=_want: _outside(self, r, w))
for _name, (_, _want) in VM.items():
    setattr(NodeGuardCaseTests, f"test_vm_{_name}", lambda self, n=_name, w=_want: _vm(self, n, w))
for _name, (_, _, _want) in LOAD.items():
    setattr(NodeGuardCaseTests, f"test_load_{_name}", lambda self, n=_name, w=_want: _load(self, n, w))


if __name__ == "__main__":
    unittest.main()
