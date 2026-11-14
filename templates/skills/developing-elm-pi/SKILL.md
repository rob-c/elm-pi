---
name: developing-elm-pi
description: "Add a plugin (extension) to elm-pi, or change elm-pi itself: work in a clone, set it up with scripts/dev-setup.sh, scaffold with scripts/new-extension, prove it with scripts/check-extension."
---

# Developing elm-pi

The steps, in this order. Each one is a command that tells you whether it worked:
no step is done until its check passes.

0. **Be in a clone of elm-pi, not the install you run on.** The install - the
   folder above `$PI_CODING_AGENT_DIR` - refuses every write. If the current
   folder has no `scripts/new-extension`, ask the user where their clone is, or
   to make one (`git clone <install> ~/src/elm-pi`) and start pi there.
1. **`scripts/dev-setup.sh`** - first, before reading pi's docs or running
   tests: it makes the clone a working install without the network (Node, pi,
   packages, TypeScript), and only then does
   `node_modules/@earendil-works/pi-coding-agent/docs/extensions.md` exist.
2. **`scripts/new-extension <name> "<what it does>"`** - never write the files
   by hand. `<name>` is lower-case words joined by hyphens (`file-stats`); a
   tool's own name may use underscores (file_stats). It writes the extension,
   its test, its `requiredExtensions` entry and its INSTALL.md row.
3. **`scripts/check-extension <name>`** - passes at once. Run it after every
   change from here on.
4. **Make it do exactly what was asked.** The extension's first lines are notes
   on pi's API: a tool (`pi.registerTool`), a command (`pi.registerCommand`), an
   event (`pi.on`); `ctx.model` is the model this session uses,
   `ctx.ui.setStatus(key, text)` the footer, `ctx.ui.notify` a message. Read
   the guide for anything else. No `renderCall`/`renderResult` unless asked
   for; never read the ELM key.
5. **Its test** (`tests/test_ext_<name>.py`): run_extension() runs JavaScript
   against it with a recording stand-in for pi - call the tool's `execute`, the
   command's `handler`, or `registered.handlers["tool_call"][0](event, ctx)`,
   and assert what it returned, `registered.notes` or `registered.statuses`.
   One test per case the request names and its edges (empty, new, missing),
   each built in `ctx.cwd` (`files`, or
   `sh("git init -q")`), asserting the exact answer: a test that accepts any
   answer tests nothing - one passed a tool that called a new repository "not
   a git repository".
6. **Its INSTALL.md row**: what it does and why, in a sentence or two.
7. **`scripts/check-extension <name>`** until it ends `ok: ...`. It also
   type-checks it and calls a tool's drawing functions once.
8. **A tool, for real**: `scripts/dev-setup.sh` again (it re-renders), then, in
   a new folder outside the clone - the clone's `.pi/` is gitignored, and a tool
   that honours .gitignore (`rg`) finds nothing there -
   `C=$PWD; T=$(mktemp -d) && cd "$T" && "$C/pi" --auto -p 'use the <tool> tool on ...' < /dev/null`
   - once, on one case; the test covers the rest. Check its answer against
   what is true in that folder: a wrong one is a bug to fix, not a case to
   swap for one that passes. Not `/tmp`: `mktemp -d` is
   this install's own temporary folder. A command or event handler
   has no `pi -p` trial: its test is its trial. Never set `ELM_API_KEY`.
9. **The whole suite**: `python3 -m unittest discover -s tests` with `bash`'s
   `timeout` at 600 (it takes about three minutes).

Report: the files changed, the last lines of steps 7 and 9, and the trial's
output - the user checks these, not your account of them.
