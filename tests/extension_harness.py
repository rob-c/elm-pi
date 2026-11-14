"""Load one extension in Node with a recording stand-in for pi, run a few lines against it, and get back
what they print. For the tests of a new extension (scripts/new-extension writes one that uses this).

    from extension_harness import run_extension
    out = run_extension(self, "my-ext", '''
        const tool = registered.tools.word_count;
        const result = await tool.execute("call-1", { path: "a.txt" }, undefined, undefined, ctx);
        out(result.content[0].text);
    ''', files={"a.txt": "one two three"})

Inside the snippet:
    registered.tools[name]       the object given to pi.registerTool
    registered.commands[name]    the object given to pi.registerCommand (call .handler(args, ctx))
    registered.handlers[event]   the functions given to pi.on(event, ...)
    registered.notes             every ctx.ui.notify(message, level), as [message, level]
    registered.statuses          every ctx.ui.setStatus(key, text)
    ctx                          a context: cwd (a scratch folder holding `files`), hasUI, ui, sessionManager
    sh(command)                  run a shell command in ctx.cwd and return its output - to build a case
                                 there: sh("git init -q && git commit -q --allow-empty -m one")
    out(value)                   print value as the result (JSON); the last one printed is returned

`typebox` is stood in for (pi supplies the real one), so a tool's parameters need nothing installed. pi's
own packages (`@earendil-works/pi-coding-agent`, `@earendil-works/pi-tui`) are the real ones after
scripts/dev-setup.sh; before it, `defineTool` alone is stood in for.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRELUDE = r"""
import { pathToFileURL } from "node:url";
const ext = await import(pathToFileURL(process.argv[1]).href);
const registered = { tools: {}, commands: {}, handlers: {}, flags: {}, notes: [], statuses: {}, widgets: {} };
const ui = {
  notify: (message, level) => registered.notes.push([message, level]),
  setStatus: (key, text) => { registered.statuses[key] = text; },
  setWidget: (key, lines) => { registered.widgets[key] = lines; },
  select: async (_title, options) => options?.[0],
  confirm: async () => true,
  input: async () => undefined,
};
const ctx = {
  cwd: process.argv[2], hasUI: true, mode: "tui", ui,
  model: { id: "test-model", provider: "elm" },
  sessionManager: { getBranch: () => [], getEntries: () => [], getSessionId: () => "test-session" },
  isIdle: () => true, abort: () => {}, hasPendingMessages: () => false,
};
const pi = {
  registerTool: (tool) => { registered.tools[tool.name] = tool; },
  registerCommand: (name, command) => { registered.commands[name] = command; },
  registerFlag: (name, flag) => { registered.flags[name] = flag; },
  getFlag: () => undefined,
  on: (event, handler) => { (registered.handlers[event] ??= []).push(handler); },
  getActiveTools: () => [], getAllTools: () => [], setActiveTools: () => {},
  sendMessage: () => {}, sendUserMessage: () => {}, appendEntry: () => {},
  exec: async () => ({ stdout: "", stderr: "", code: 0, killed: false }),
};
const out = (value) => console.log(JSON.stringify(value ?? null));
// A case built in the scratch folder: dev7 (2026-11-14) wrote tests that accepted any answer, and its
// git_summary called a just-initialised repository "not a git repository". git gets an identity here
// because HOME is a scratch folder with no ~/.gitconfig.
const { execSync } = await import("node:child_process");
const sh = (command) => execSync(command, { cwd: ctx.cwd, encoding: "utf8", env: { ...process.env,
  GIT_AUTHOR_NAME: "test", GIT_AUTHOR_EMAIL: "test@example.invalid",
  GIT_COMMITTER_NAME: "test", GIT_COMMITTER_EMAIL: "test@example.invalid" } });
await ext.default(pi);
"""

TYPEBOX = ("const f = (...a) => ({ args: a }); "
           "export const Type = new Proxy({}, { get: () => f });")


def node():
    for candidate in (ROOT / ".node/bin/node",):
        if candidate.exists():
            return str(candidate)
    agent = os.environ.get("PI_CODING_AGENT_DIR")
    if agent and (Path(agent).parent / ".node/bin/node").exists():
        return str(Path(agent).parent / ".node/bin/node")
    return shutil.which("node")


def run_extension(test, name, snippet, files=None, env=None):
    """Run `snippet` against templates/extensions/<name>.ts (or a path); return the last value it printed."""
    binary = node()
    if not binary:
        test.skipTest("needs node")
    source = Path(name) if str(name).endswith((".ts", ".js")) else ROOT / "templates/extensions" / f"{name}.ts"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ext = tmp / "ext"
        (ext / "node_modules/typebox").mkdir(parents=True)
        (ext / "node_modules/typebox/package.json").write_text('{"name":"typebox","type":"module","main":"index.js"}')
        (ext / "node_modules/typebox/index.js").write_text(TYPEBOX)
        # pi's own packages, for an extension that imports a value from them (`defineTool`, pi-tui's `Text`):
        # the real ones once dev-setup has put them here, else a stand-in. dev8 (2026-11-14) imported
        # defineTool, found the harness could not load it, and patched this file.
        scope = ext / "node_modules/@earendil-works"
        if (ROOT / "node_modules/@earendil-works/pi-coding-agent").is_dir():
            scope.symlink_to(ROOT / "node_modules/@earendil-works", target_is_directory=True)
        else:
            stub = scope / "pi-coding-agent"
            stub.mkdir(parents=True)
            (stub / "package.json").write_text('{"name":"@earendil-works/pi-coding-agent","type":"module","main":"index.js"}')
            (stub / "index.js").write_text("export const defineTool = (tool) => tool;\n")
        shutil.copy(source, ext / source.name)
        work = tmp / "work"
        work.mkdir()
        for rel, content in (files or {}).items():
            path = work / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content if isinstance(content, bytes) else content.encode())
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", PRELUDE + snippet,
                              str(ext / source.name), str(work)],
                             capture_output=True, text=True, timeout=120,
                             env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp), **(env or {})})
    if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
        test.skipTest("this node cannot load TypeScript")
    test.assertEqual(0, run.returncode, run.stderr[-3000:])
    lines = [l for l in run.stdout.strip().splitlines() if l.strip()]
    test.assertTrue(lines, "the snippet printed nothing: call out(value)")
    return json.loads(lines[-1])
