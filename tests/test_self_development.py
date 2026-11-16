"""elm-pi developing elm-pi: the dev tools (scripts/dev-setup.sh, scripts/new-extension,
scripts/check-extension, tests/extension_harness.py), the repository's own AGENTS.md, and the guards
that keep a session off the install it runs on (protected-paths.ts for the tools, command-guard.ts for
the shell). Asked for on 2026-11-13: elm-pi should be able to write, test and load-check a plugin for
itself, in a clone.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
EXT = ROOT / "templates/extensions"
PI_LOADER = ROOT / "node_modules/@earendil-works/pi-coding-agent/dist/index.js"


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def fake_install(base):
    """A folder that looks like an elm-pi install: the launcher and bootstrap.sh beside agent/."""
    install = Path(base) / "inst"
    (install / "agent/extensions").mkdir(parents=True)
    (install / "pi").write_text("#!/bin/sh\n")
    (install / "bootstrap.sh").write_text("#!/bin/sh\n")
    (install / "agent/extensions/elm-only.ts").write_text("export default () => {};\n")
    return install.resolve()


class InstallGuardTests(unittest.TestCase):
    """The install a session runs on is not the agent's to change - with a tool or through the shell."""

    def run_js(self, source, script, *args, env=None):
        binary = node()
        if not binary:
            self.skipTest("needs node")
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e",
                              "import { pathToFileURL } from 'node:url';"
                              f"const m = await import(pathToFileURL({json.dumps(str(source))}).href);" + script, *args],
                             capture_output=True, text=True, timeout=60,
                             env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), **(env or {})})
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            self.skipTest("this node cannot load TypeScript")
        self.assertEqual(0, run.returncode, run.stderr[-2000:])
        return json.loads(run.stdout.strip().splitlines()[-1])

    def test_the_writing_tools_are_refused_in_the_install_and_nowhere_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = fake_install(tmp)
            project = Path(tmp) / "project"
            project.mkdir()
            env = {"PI_CODING_AGENT_DIR": str(install / "agent"), "HOME": tmp}
            script = ("const h = {}; m.default({ on: (e, f) => { h[e] = f; } });"
                      "const call = async (path, cwd) => { const r = await h.tool_call({ toolName: 'write', input: { path } },"
                      " { cwd, hasUI: false }); return r?.block ? r.reason : null; };"
                      "const [inst, proj] = process.argv.slice(1);"
                      "console.log(JSON.stringify([await call(inst + '/agent/extensions/elm-only.ts', proj),"
                      " await call('../inst/pi', proj), await call('notes.md', proj), await call('.pi/tmp/x.txt', inst),"
                      " await call('new-file.ts', inst + '/agent/extensions'),"
                      " await call(inst + '/agent/tmp/tmp.abc/trial.txt', proj)]));")
            out = self.run_js(EXT / "protected-paths.ts", script, str(install), str(project), env=env)
        self.assertIn("it is part of the elm-pi install this session runs on", out[0])
        self.assertIn("scripts/dev-setup.sh", out[0])
        self.assertIsNotNone(out[1])                 # relative, through ..
        self.assertIsNone(out[2])                    # the project
        self.assertIsNone(out[3])                    # a session's own .pi folder, even inside the install
        self.assertIsNotNone(out[4])                 # a new file in the install
        self.assertIsNone(out[5])                    # the install's agent/tmp: the session's TMPDIR

    def test_the_shell_is_refused_what_changes_the_install_and_allowed_what_reads_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            install = fake_install(tmp)
            env = {"PI_CODING_AGENT_DIR": str(install / "agent"), "HOME": tmp}
            cases = {
                "cp $PI_CODING_AGENT_DIR/extensions/elm-only.ts ./mine.ts": False,   # copying out of it
                "cp mine.ts $PI_CODING_AGENT_DIR/extensions/": True,
                f"sed -i s/a/b/ {install}/pi": True,
                f"echo x >> {install}/agent/settings.json": True,
                f"cat {install}/pi | head": False,
                f"grep -rn ELM {install}/agent": False,
                f"cd {install} && git checkout -- pi": True,
                f"cd {install} && git log -3": False,
                f'bash -c "rm -f {install}/agent/extensions/elm-only.ts"': True,
                f"mv {install}/pi /tmp/pi.bak": True,
                "rm -rf build && mkdir -p .pi/tmp": False,
                f"echo x > {install}/agent/tmp/tmp.abc/t.py": False,   # the session's TMPDIR (mktemp -d)
            }
            script = ("const [inst, cwd, cases] = [process.argv[1], process.argv[2], JSON.parse(process.argv[3])];"
                      "const env = { HOME: process.env.HOME, PI_CODING_AGENT_DIR: process.env.PI_CODING_AGENT_DIR };"
                      "console.log(JSON.stringify(cases.map((c) => Boolean(m.installWrite(c, cwd, inst, env)))));")
            got = self.run_js(EXT / "command-guard.ts", script, str(install), tmp, json.dumps(list(cases)), env=env)
            reason = self.run_js(EXT / "command-guard.ts",
                                 "console.log(JSON.stringify(m.installWrite(process.argv[1], '/', process.argv[2], {}).reason));",
                                 f"touch {install}/pi", str(install))
        self.assertEqual(list(cases.values()), got, dict(zip(cases, got)))
        self.assertIn("this install changes only through `pi update`", reason)

    def test_without_an_install_nothing_is_refused(self):
        script = "console.log(JSON.stringify(m.installReason('/anything/at/all', '/', undefined) ?? null));"
        self.assertIsNone(self.run_js(EXT / "protected-paths.ts", script))


class NewExtensionTests(unittest.TestCase):
    """scripts/new-extension, then scripts/check-extension, in a copy of this repository."""

    # Built, not written out: check-extension runs every test module that names an extension, and this one
    # must not be among them for the extensions it makes.
    HELLO = "hello" + "-note"
    BROKEN = "broken" + "-one"
    KEYED = "keyed" + "-one"
    DRAWN = "drawn" + "-one"
    STRAY = "stray"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "elm-pi"
        # No git at all on AlmaLinux and Ubuntu as installed (2026-11-16): an install there is
        # a copied tree, the same as one that is not a checkout.
        files = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True,
                               text=True).stdout.splitlines() if shutil.which("git") else []
        if not files:   # not a git checkout: copy what the tests read
            files = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and not any(
                part in ("node_modules", ".node", "agent", ".git", "__pycache__") for part in p.relative_to(ROOT).parts)]
        for name in files:
            source = ROOT / name
            if name == ".env" or not source.is_file():
                continue
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def scaffold(self, name, summary):
        return subprocess.run(["python3", str(self.repo / "scripts/new-extension"), name, summary],
                              capture_output=True, text=True, timeout=60)

    def check(self, name):
        if not (node() and PI_LOADER.exists()):
            self.skipTest("needs a bootstrapped checkout (pi's loader)")
        env = {**os.environ, "ELM_PI_PI_ROOT": str(ROOT)}
        env.pop("PI_CODING_AGENT_DIR", None)
        return subprocess.run([node(), "--no-warnings", str(self.repo / "scripts/check-extension.mjs"), name],
                              capture_output=True, text=True, timeout=300, cwd=self.repo, env=env)

    def test_a_new_extension_is_registered_documented_tested_and_loads_from_the_start(self):
        name = self.HELLO
        made = self.scaffold(name, f"a /{name} command that says the extension is installed")
        self.assertEqual(0, made.returncode, made.stderr)
        self.assertTrue((self.repo / f"templates/extensions/{name}.ts").exists())
        self.assertTrue((self.repo / f"tests/test_ext_{name.replace('-', '_')}.py").exists())
        self.assertIn(f"{name}.ts", json.loads((self.repo / "config/elm-pi.json").read_text())["requiredExtensions"])
        self.assertIn(f"| `agent/extensions/{name}.ts` | a /{name} command", (self.repo / "INSTALL.md").read_text())
        checked = self.check(name)
        self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
        self.assertIn(f"commands: /{name}", checked.stdout)
        self.assertIn(f"ok: {name}.ts loads, registers 1 thing, and is registered, documented and tested", checked.stdout)
        again = self.scaffold(name, "again")
        self.assertEqual(2, again.returncode)
        self.assertIn("already exists", again.stderr)
        self.assertEqual(2, self.scaffold("Bad_Name", "x").returncode)

    def test_a_broken_or_unregistered_extension_is_named_as_such(self):
        made = self.scaffold(self.BROKEN, "a placeholder that will not parse")
        self.assertEqual(0, made.returncode, made.stderr)
        source = self.repo / f"templates/extensions/{self.BROKEN}.ts"
        source.write_text(source.read_text().replace("export default function (pi: ExtensionAPI) {", "export default function (pi {"))
        broken = self.check(self.BROKEN)
        self.assertEqual(1, broken.returncode)
        self.assertIn("it does not load", broken.stdout)
        source.unlink()
        # a tool whose drawing uses a name it never imported (dev02: new Text(...) without the import)
        made = self.scaffold(self.DRAWN, "draws with a missing import")
        self.assertEqual(0, made.returncode, made.stderr)
        drawn = self.repo / f"templates/extensions/{self.DRAWN}.ts"
        body = drawn.read_text()
        start = body.index("	pi.registerCommand(")
        drawn.write_text(body[:start] + (
            '	pi.registerTool({ name: "drawn_tool", label: "Drawn", description: "d", parameters: {} as any,\n'
            '		async execute() { return { content: [{ type: "text", text: "x" }], details: {} }; },\n'
            '		renderCall(args: any, theme: any) { return new Text(theme.fg("toolTitle", "drawn"), 0, 0); } });\n}\n'))
        found_draw = self.check(self.DRAWN)
        self.assertEqual(1, found_draw.returncode)
        self.assertIn("drawn_tool's renderCall fails: Text is not defined", found_draw.stdout)
        drawn.unlink()
        # one that reads the ELM key (dev01 showed four characters from each end of it)
        made = self.scaffold(self.KEYED, "reads the key")
        self.assertEqual(0, made.returncode, made.stderr)
        keyed = self.repo / f"templates/extensions/{self.KEYED}.ts"
        keyed.write_text(keyed.read_text().replace('ctx.ui.notify("', 'ctx.ui.notify(String(process.env.ELM_API_KEY).slice(0, 4) + "'))
        found_key = self.check(self.KEYED)
        self.assertEqual(1, found_key.returncode)
        self.assertIn("it reads ELM_API_KEY", found_key.stdout)
        keyed.unlink()
        # a file nobody registered or documented
        stray = self.STRAY + ".ts"
        (self.repo / f"templates/extensions/{stray}").write_text(
            'import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";\n'
            'export default function (pi: ExtensionAPI) { pi.on("session_start", async () => {}); }\n')
        found = self.check(self.STRAY)
        self.assertEqual(1, found.returncode)
        self.assertIn(f'"{stray}" is not in requiredExtensions', found.stdout)
        self.assertIn("INSTALL.md: no row", found.stdout)
        self.assertIn(f"no test names {stray}", found.stdout)


class DevSetupTests(unittest.TestCase):
    def run_setup(self, args, env):
        return subprocess.run(["bash", str(ROOT / "scripts/dev-setup.sh"), *args], capture_output=True, text=True,
                              timeout=60, env={"PATH": "/usr/bin:/bin", "HOME": env.get("HOME", "/tmp"), **env})

    def test_it_will_not_run_on_the_install_itself_or_without_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            alone = self.run_setup([], {"HOME": tmp})
            itself = self.run_setup(["--from", str(ROOT)], {"HOME": tmp})
            empty = Path(tmp) / "empty"
            empty.mkdir()
            not_one = self.run_setup(["--from", str(empty)], {"HOME": tmp})
        self.assertEqual(1, alone.returncode)
        self.assertIn("no install to copy from", alone.stderr)
        self.assertEqual(1, itself.returncode)
        self.assertIn("this is the install itself", itself.stderr)
        self.assertEqual(1, not_one.returncode)
        self.assertIn("a bootstrapped elm-pi install?", not_one.stderr)

    def test_it_says_how_it_is_used(self):
        shown = self.run_setup(["--help"], {})
        self.assertEqual(0, shown.returncode)
        self.assertIn("scripts/dev-setup.sh [--from INSTALL] [--fresh]", shown.stdout)


class GuideTests(unittest.TestCase):
    """The repository's AGENTS.md, which a session started in a clone reads."""

    def test_it_gives_the_steps_and_the_rule_about_the_install(self):
        guide = " ".join((ROOT / "AGENTS.md").read_text().split())
        for step in ("scripts/dev-setup.sh", "scripts/new-extension <name>", "scripts/check-extension <name>",
                     "tests/extension_harness.py", "python3 -m unittest discover -s tests"):
            self.assertIn(step, guide)
        self.assertIn("never in the install you are running on", guide)
        for script in ("dev-setup.sh", "new-extension", "check-extension", "check-extension.mjs"):
            self.assertTrue(os.access(ROOT / "scripts" / script, os.X_OK) or script.endswith(".mjs"), script)


class HarnessCaseTests(unittest.TestCase):
    """sh() in tests/extension_harness.py builds a case in the scratch folder. Round dev7 (2026-11-14) wrote a
    git_summary whose tests accepted any answer; its tool called a just-initialised repository "not a git
    repository", and nothing caught it. This is the test that would have."""

    TOOL = (
        'import { execSync } from "node:child_process";\n'
        'export default function (pi) { pi.registerTool({ name: "git_summary", parameters: {},\n'
        '  async execute(_id, _p, _s, _u, ctx) {\n'
        '    try { execSync("git rev-parse --is-inside-work-tree", { cwd: ctx.cwd, stdio: "pipe" }); }\n'
        '    catch { return { content: [{ type: "text", text: "not a git repository" }] }; }\n'
        '    const branch = execSync("git branch --show-current", { cwd: ctx.cwd, encoding: "utf8" }).trim();\n'
        '    const changed = execSync("git status --porcelain", { cwd: ctx.cwd, encoding: "utf8" }).split("\\n").filter(Boolean).length;\n'
        '    return { content: [{ type: "text", text: `${branch}: ${changed} changed` }] };\n'
        '  } }); }\n')

    def answer(self, setup, files=None):
        from extension_harness import run_extension
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / "git-summary.js"
            tool.write_text(self.TOOL)
            return run_extension(self, tool, setup + """
                const r = await registered.tools.git_summary.execute("c1", {}, undefined, undefined, ctx);
                out(r.content[0].text);""", files=files)

    def test_each_case_is_built_and_answered_exactly(self):
        if not shutil.which("git"):
            self.skipTest("needs git")
        self.assertEqual("not a git repository", self.answer(""))
        self.assertEqual("main: 1 changed", self.answer('sh("git init -q -b main");', files={"a.txt": "x"}))
        self.assertEqual("work: 0 changed", self.answer(
            'sh("git init -q -b work && git add -A && git commit -q -m one");', files={"a.txt": "x"}))

    def test_an_extension_can_import_values_from_pis_own_package(self):
        """dev8 imported defineTool, the harness could not load it, and the session patched the harness."""
        from extension_harness import run_extension
        with tempfile.TemporaryDirectory() as tmp:
            tool = Path(tmp) / "defined.ts"
            tool.write_text('import { defineTool } from "@earendil-works/pi-coding-agent";\n'
                            'export default function (pi) { pi.registerTool(defineTool({ name: "hello", parameters: {},\n'
                            '  async execute() { return { content: [{ type: "text", text: "hi" }] }; } })); }\n')
            self.assertEqual("hi", run_extension(self, tool, """
                const r = await registered.tools.hello.execute("c1", {}, undefined, undefined, ctx);
                out(r.content[0].text);"""))

    def test_a_killed_setup_leaves_nothing_git_would_pick_up(self):
        """pi kills a timed-out command with SIGKILL, so bootstrap's trap does not run: dev8 left
        .elm-pi-verify.XXXXXX in the clone. dev-setup.sh sweeps such leftovers, copies trees in whole, and
        the guides give it a timeout it fits in."""
        if not shutil.which("git"):
            self.skipTest("needs git")
        # An install from the source tarball has git's files and is no repository, and there
        # `git check-ignore` answers nothing at all (the macOS VM, 2026-11-16).
        if subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT,
                          capture_output=True).returncode != 0:
            self.skipTest("needs a git checkout: this tree is a copy of one")
        names = [".elm-pi-verify.8NLWk3", "node_modules.dev-setup-partial", ".elm-pi-stage-core.abc123/x"]
        ignored = subprocess.run(["git", "check-ignore", "--no-index", *names], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(sorted(names), sorted(ignored.stdout.split()))
        setup = (ROOT / "scripts/dev-setup.sh").read_text()
        self.assertIn('rm -rf "$HERE"/.elm-pi-verify.*', setup)
        self.assertIn('mv "$part" "$2"', setup)
        guide = " ".join((ROOT / "AGENTS.md").read_text().split())
        self.assertIn("`scripts/dev-setup.sh`, with `bash`'s `timeout` at 600", guide)

    def test_the_guides_say_to_test_each_case_and_to_fix_a_wrong_trial(self):
        for path in ("AGENTS.md", "templates/skills/developing-elm-pi/SKILL.md"):
            guide = " ".join((ROOT / path).read_text().split())
            self.assertIn("a test that accepts any answer", guide, path)
            self.assertIn("a wrong one is a bug to fix, not a case to swap for one that passes", guide, path)


if __name__ == "__main__":
    unittest.main()
