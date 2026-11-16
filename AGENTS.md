# Working on elm-pi itself

This repository is elm-pi's source: the installer, the `pi` launcher, and the
extensions, prompts and configuration an install puts around the model. A
session started here is developing elm-pi. (The rules every elm-pi session
follows are in `templates/AGENTS.md`; this file is only for work on the repo.)

## Where to work

- **In this clone, never in the install you are running on.** That install -
  the folder above `$PI_CODING_AGENT_DIR` - is refused to every write: its
  guards, launcher and configuration are what hold the session to ELM, and it
  changes only through `pi update`. If this folder *is* that install, stop and
  ask the user to `git clone` it somewhere else.
- **Once per clone, first:** `scripts/dev-setup.sh`, with `bash`'s `timeout`
  at 600 - it takes one to a few minutes, and a run cut off at 120 s is
  killed mid-install. It makes this clone a
  working install without the network - Node, pi and the packages copied from
  the install you run on, `agent/` rendered from `templates/` - so the tests
  can load extensions and `scripts/check-extension` works. Run it again after
  changing a template, to put the change in this clone's `agent/`.
- The source is `templates/`, `config/`, `scripts/`, `lib/`, `tests/`, `pi`,
  `pi.bash`, `python/`, `bootstrap.sh` and `bootstrap.bash`. `agent/`, `node_modules/` and
  `.node/` are generated: never edit them.
- The launcher is Python: `pi` finds the install and hands over to `python/pi`,
  which starts `python/elmpi` with no `PYTHON*` variable, no site-packages and
  no import from outside the install. `python/README.md` says what each module
  decides. `pi.bash` is the bash implementation it replaced - the reference,
  not installed - and `tests/test_python_launcher.py` runs both on the same
  install and compares every decision, so a change to either must be made to
  both.
- The installer is Python too: `bootstrap.sh` finds an interpreter and hands
  over to `python/elmboot`. `bootstrap.bash` is the bash installer it replaced,
  the reference `tests/test_bootstrap_python.py` and
  `tests/test_bootstrap_installer.py` hold it to: a change to what an install
  does is made to both.

## A new extension, step by step

1. `scripts/new-extension <name> "<what it does, one line>"` - writes
   `templates/extensions/<name>.ts` (a working placeholder: a `/<name>`
   command), `tests/test_ext_<name>.py`, its entry in `config/elm-pi.json`'s
   `requiredExtensions`, and its row in INSTALL.md's extension table.
2. `scripts/check-extension <name>` - it passes at once. Run it after every
   change: it loads the file with pi's own loader and lists what it registers,
   checks it is in `requiredExtensions`, has its INSTALL.md row and a test,
   and runs the docs-against-code tests and its own.
3. Make it do its job - what the user asked, word for word: "the model this
   session is using" is `ctx.model`, not a list of configured ones. The `.ts`
   file starts with notes on pi's extension API (the whole guide:
   `node_modules/@earendil-works/pi-coding-agent/docs/extensions.md` after
   dev-setup). Replace the placeholder; keep `export default function (pi: ExtensionAPI)`.
   A tool needs no `renderCall`/`renderResult`: pi draws it. If you write
   them, import what they use (`import { Text } from "@earendil-works/pi-tui"`) -
   nothing but an interactive session runs them, so check-extension calls each once.
4. Change its test to test what it does: `run_extension` (tests/extension_harness.py)
   runs a few lines of JavaScript against it with a recording stand-in for pi -
   `registered.tools`, `registered.commands`, `registered.notes`, `ctx`. One
   test per case the request names and its edges (empty, new, missing), built in `ctx.cwd` (`files`, or `sh(...)`
   to run a command there), each asserting the exact answer: a test that
   accepts any answer passed a tool that called a new repository "not a git
   repository".
5. Say in its INSTALL.md row what it does and why. A tool name in backticks
   there must be one an extension registers.
6. `scripts/check-extension <name>` until it ends `ok: ... loads, registers ...`.
7. For a tool, try it for real: `scripts/dev-setup.sh`, then, from a new folder
   outside the clone (its `.pi/` is gitignored, which `rg` honours):
   `C=$PWD; T=$(mktemp -d) && cd "$T" && "$C/pi" --auto -p 'use the <tool> tool to ...' < /dev/null`.
   Check the answer against what is true in that folder: a wrong one is a bug
   to fix, not a case to swap for one that passes.
   It uses this session's ELM key: never set `ELM_API_KEY` yourself. A command
   (`/name`) or an event handler cannot be tried this way - `pi -p` has no
   screen for `ctx.ui` - so its test is its trial.
8. Before you report: `python3 -m unittest discover -s tests` - about three
   minutes, so give `bash` a `timeout` of 600 - and give its last line. Report what changed, file by file, and the output of
   the checks - not a summary of how well it went.

## What the tests hold every change to

- The ELM key is never read, shown, logged or stored by an extension, not even
  a few of its characters: pi signs every request with it, and a session cannot
  start without one. `scripts/check-extension` refuses an extension that reads it.
- Docs match code: a tool, command, flag or environment variable named in
  README.md, INSTALL.md or a prompt must exist, and one the launcher reads must
  be documented (`pi --help` text or the docs).
- `templates/AGENTS.md` is in every session's prompt and has a size cap: say
  more there only by saying something else in fewer words.
- A comment says why: the session, request or measurement that showed the need.
- Python works on 3.9 (macOS's); shell scripts pass ShellCheck; no new network
  access at startup.

Do not commit or push unless the user asks.
