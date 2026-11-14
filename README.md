# elm-pi — a coding agent on the University's own hardware

A self-contained [pi](https://pi.dev) coding agent wired to the University of
Edinburgh's ELM gateway, running **Qwen 3.5 397B on university-hosted GPUs**
instead of a commercial provider. Commercial models are removed from the install
on purpose — see [LOCKDOWN.md](LOCKDOWN.md).

[ELM](https://information-services.ed.ac.uk/computing/comms-and-collab/elm) is
the University's generative AI platform: a gateway to large language models,
provided by Information Services through EDINA for staff and students. It offers
commercial models and open-weights models it hosts itself; elm-pi uses only the
self-hosted ones. Web interface (and API keys):
<https://elm.edina.ac.uk/elm>. API: `https://elm.edina.ac.uk/api/v1`. Help:
<https://elm.edina.ac.uk/elm/help/help> or the IS Helpline.

## Install

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
```

About 2 GB, the agent's own scientific Python (numpy, scipy, matplotlib, Jupyter
tools) included. With offline PyPI search as well, ~2.4 GB in all (never the open
network; that is `pi --remote`):

```bash
ELM_PI_WITH_ALL=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
```

Or as a separate sandbox in `~/sandbox/elm-pi`, to try it out without touching
another install, your `pi` command or your `PATH` (the installer creates
`~/sandbox` if it is not there); run it as `~/sandbox/elm-pi/pi`:

```bash
ELM_PI_PREFIX="$HOME/sandbox/elm-pi" ELM_PI_NO_LINK=1 ELM_PI_NO_PATH=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
```

macOS or Linux, x86_64 or arm64: Ubuntu, AlmaLinux 8-10, Arch and NixOS
(with nix-ld) are tested, see
[Linux distributions](INSTALL.md#linux-distributions). No `sudo`, nothing installed system-wide. It
lands in `~/.local/share/elm-pi`, links `~/.local/bin/pi`, puts that directory on
your `PATH` in the shell profile you actually use (zsh, bash or fish —
`--no-path` skips it), and asks for your ELM API key —
[how to get one](INSTALL.md#step-1--get-an-elm-api-key).

**The command is `pi`.** The wrapper takes the name and hands over to `pi.orig`,
the unwrapped CLI inside the install, so anything expecting a `pi` gets the
wrapped, ELM-only one — including pi-subagents when it spawns children.

```bash
pi                                 # start working
```

Runtime dependencies stay in the install directory: bundled Node, local
`node_modules`, and `PI_CODING_AGENT_DIR` pointed at `./agent`, so config and
credentials never touch `~/.pi`. The installer also creates the launcher link,
adds its directory to your shell profile unless asked not to, and each project
gets its own ignored `.pi/sessions/` directory. To remove the installed runtime:

```bash
rm -rf ~/.local/share/elm-pi ~/.local/bin/pi
```

Already have the directory (git clone, `scp -r`, tar)? Skip the installer and run
`./bootstrap.sh` in it. Full step-by-step, including the manual equivalent of
every step: **[INSTALL.md](INSTALL.md)**. Web version of this page:
**[rob-c.github.io/elm-pi](https://rob-c.github.io/elm-pi/)**.

## What you get

| | |
|---|---|
| **Model** | `Qwen/Qwen3.5-397B-A17B-FP8` — 262K context, tool calling, vision. `mistralai/Mistral-Small-4-119B-2603` (`--mistral`) is the other university-hosted model with all three |
| **Sub-agents** | 64-child fan-out budget, Qwen by default; Llama 3.3 via a local tool-call shim as a fallback |
| **Editing** | Anchor-based (`pi-hashline-edit-pro`) — the built-in `edit` tool is off |
| **Memory** | Per-project `AGENTS.md`. No memory tool: `pi-hermes-memory` is not installed |
| **Software** | Fetched when a task needs it, the isolated way and without asking: PyPI packages into the agent's or the project's environment, conda-forge packages with pixi (`agent/pixi`), large toolchains in a `--network=none` container. Homebrew asks every time; apt/dnf are refused and the agent gives you the command. Each install is reported (what, where, how to remove) and logged in `agent/installs.log` |
| **Web** | `pi-web-access` (DuckDuckGo, then Exa). **Off by default**; `pi --remote` turns it on for a run. Without it, only ELM, PyPI, conda-forge and the container registries are reachable |
| **Skills** | 16 — physics methods, scientific code, installing software, containers, sub-agent orchestration, developing elm-pi itself. A router adds the ones a request needs, shown as a dim `skills:` line |
| **Prompt suggestions** | `pi-next-prompt`: the likely next prompt in grey after each reply; Tab takes it |
| **Sessions** | `.pi/sessions/` inside each project, not one central 1.9 GB pile |
| **Models offered** | ELM only. 43 non-ELM provider catalogues stripped |

## Layout

```
install.sh          the curl|bash entry point: fetch, bootstrap, link
bootstrap.sh        installs the reviewed runtime at the tested versions; idempotent
pi                  the wrapper: bundled Node, .env, ELM-only guards, preflight
pi.orig             the unwrapped CLI the wrapper hands over to
configure.sh        resolves the Qwen model id from the gateway, merges it into config
patch-pi.py         removes /share and /bug from the release; run on every install
templates/          the source of truth for everything under agent/
config/elm-pi.json  shared model, provider, extension and web-tool policy
lib/                launcher policy and private-state permission helpers
scripts/ tests/     config rendering, checks and regression tests
docs/               the GitHub Pages site
shim/               Llama tool-call shim (Python, loopback only)
proxy/              egress proxy: allowlists ELM, PyPI, conda-forge and container registries; logs and refuses the rest
agent/              generated: PI_CODING_AGENT_DIR (config, extensions, skills, state)
agent/bin/          generated: fd rg jq yq shellcheck ast-grep uv mlr resvg pixi ruff, pinned + checksummed
agent/pixi/         generated on use: conda-forge tools the agent installed with pixi
agent/python/       generated unless --no-python: the agent's own Python (uv-managed CPython + analysis stack, ~1 GB)
.node/ node_modules/  generated: Node 24 + pi, ~400 MB (with the tools, ~1 GB; with agent/python, ~2 GB)
```

`agent/` is generated from `templates/`; shared runtime values come from
`config/elm-pi.json`. npm dependencies install at the versions this repo last
tested, `config/versions.json`; `pi update` takes the latest and keeps them only
if they pass the install's checks. The split
is **code versus config**.

The options an install was made with — `--no-packages` and the other `--no-*`
flags, an `ELM_PI_TOOLS` subset, the branch and repository — are recorded in
`agent/install-options` and repeated by every later run: a re-run of the
installer or `bootstrap.sh`, `pi update`, `pi update --extensions`. Flags given
on a later run are added to the record; `--reset-options` starts it again from
that run's flags alone.

Code and policy — `AGENTS.md`, the agent definitions, the local extensions — are
**refreshed on every run**, so a re-install always runs the current rules. Config you tune — `settings.json`, `models.json`,
`web-search.json`, the extension configs — is kept.

Within the kept config, **one exception**, so a re-install can change its mind. Some values are
decisions this repo makes for a measured or documented reason — thinking off,
compaction owned by `pi-auto-compact` at 70% of the context window, PDFs extracted locally rather than
uploaded, `/share` off for sub-agents, exactly one Llama, the permission
policy, the ELM-only model scope. Every run compares those against
`templates/`, **prints anything you have changed**, and applies the repo's
value over the top. Nothing is overwritten silently.

Everything else is yours and survives: theme, model, concurrency limits, search
routing, and any key the list does not name. Change a decision permanently in
`templates/`, not in `agent/`.

**A re-install never redoes work that is already done.** It does not reinstall
pi, re-download the bundled binaries, or reinstall the extension packages when
they are present — that is minutes spent reproducing a state that already
exists. The exception is a change to the tested set: when a pull changes
`config/versions.json` (or a manifest), the next run installs the new pinned
versions. `pi update` fetches and validates the source, builds dependencies in
staging from the current registry versions, verifies the patched CLI, and only
then swaps the runtime into place. If the new pi then cannot load the config -
Qwen missing from `--list-models`, or a value its schemas reject - the previous
pi and extensions are put back. The elm-pi source and the files regenerated
under `agent/` are not rolled back; a failed update says exactly what was and
was not, and how to return to the previous commit. A genuinely broken install
is a `rm -rf` away from a clean one.

## Daily use

```bash
pi                             # interactive, starts on Qwen 397B
pi -p "..."                    # one-shot; in manual it reads, but runs and edits nothing
pi --auto -p "..."             # one-shot that may run commands and edit
pi --fast -p "..."             # one-shot, much quicker to start
pi --llama -p "..."            # run on Llama 3.3 70B through the tool-call shim
pi --mistral -p "..."          # run on Mistral Small 4 119B
cat file | pi -p "summarise"
pi update                      # latest elm-pi, pi and packages (see below)
pi update --extensions         # back to the tested versions in config/versions.json
```

**Show it things.** Qwen and Mistral both see images, and elm-pi has them look
whenever anything is visual. Paste a screenshot (Ctrl+V), drag an image into
the terminal, add one with `@`, or just name its path in your message
(`what's wrong with figures/fit.png?`, or a screenshot's path from your
Desktop) and it is attached. `pi @plot.png -p "..."` does the same in one shot.
The agent renders and looks at the plots, PDFs and web pages it makes, and
asks for a screenshot when you describe something it cannot see. Looking costs
a few thousand tokens and there is no token budget here. Only Llama
(`--llama`) is blind to images.

Nothing updates itself while you are trying to start work: the launcher runs pi
with `PI_OFFLINE=1`, so no version check, package check or tool download happens
at launch. `pi update` is the one place updates happen: the latest elm-pi
source, then the latest pi and extension packages, kept only if the install's
checks pass. `pi update --extensions` reinstalls the tested set from
`config/versions.json` instead — the packages, and pi itself if an update moved
it on. `agent/installed-versions.json` records what is installed.

`pi install` and `pi remove` are refused: the package set is reviewed and
pinned, and every bootstrap and `pi update` rebuilds it from `templates/`, so a
package added that way would vanish at the next update. To add one for good,
see [CONTRIBUTING.md](CONTRIBUTING.md); to try a local extension for one
session, `PI_ELM_UNLOCK=1 pi -e /path/to/extension.ts` (plain `-e` is refused,
see [LOCKDOWN.md](LOCKDOWN.md)). pi's other subcommands are refused the same
way, each saying what to use instead: `pi auth` (the key is in `.env`),
`pi mcp` (MCP is off), `pi config` and `pi list` (the package set is
`templates/`, what runs is `agent/installed-versions.json`) and
`pi update --models` (ELM's models are `agent/models.json`, refreshed by
`./configure.sh`). `patch-pi.py` takes them out of pi itself too.

### Permission modes

How much the agent may do before it asks you, in three steps:

| Mode | |
|---|---|
| **manual** | where every new session starts. Nothing runs without your yes: every command, edit, Python cell, notebook change, sub-agent and web call asks first. Reading files in the project does not, nor do the tools that only talk to you or keep the session's notes (`todo`, `ask_user_question`, ...; `permissionModes.manualNoPrompt` in `config/elm-pi.json`). Answering "allow for this session" stops the same command asking again. Sub-agents ask once, at launch, and the ask says what allowing it means: the agents it starts then work in auto, while what auto asks about still comes to you (`permissionModes.approvedAgents`; `"manual"` has each of their calls ask as well) |
| **auto** | the permission gate's rules as written: most commands and every edit in the project run, the risky ones ask first (`git push`, `sudo`, `gh`, `brew install`, `pi update`, ...) and some are refused (`ssh`, system package managers) |
| **yolo** | every ask is answered yes, until the session ends. A refusal is still a refusal, and the egress proxy and the ELM-only policy are unchanged |

Change it inside a session with `/mode`, which opens a menu of the three modes
(the footer shows the current one). Picking manual or auto asks **Change for
this session** or **Change default mode**, the second making new sessions start
that way too; picking yolo offers only **Change for this session only**: yolo is never saved and never a
default, so the next session, a resumed one included, starts in the default
again. `pi --manual`, `pi --auto` or `pi --yolo` picks the mode for one run and
leaves the default alone. Sub-agents run in their session's mode and their asks
come to you there. A `PI_ELM_PERMISSION_MODE` in the environment can only make
a run stricter, and `pi --yolo` started by the agent itself asks you first. The
gate applies the mode, through the small patch `patch-pi.py --gate` makes to
it; see [LOCKDOWN.md](LOCKDOWN.md#permission-modes).

With `-p` there is nobody to ask, so in manual mode a one-shot run can read but
not run commands or edit; `pi --auto -p "..."` lets it.

`pi` is a symlink to `~/.local/share/elm-pi/pi`; the launcher resolves symlinks,
so you can move or re-link it freely. `pi.orig` in the install directory is the
unwrapped CLI — vanilla pi, its own `~/.pi` config, no ELM provider and no
policy. It is deliberately not on your PATH; it exists to answer "is this the
wrapper's fault?".

| Flag | |
|---|---|
| `--fast` | skip the npm package set, which is most of the startup time. The policy extensions and the permission gate still load. No sub-agents, web search or anchor editing; pi's built-in `edit` still works. Right for one-shot questions, wrong for multi-step work. |
| `--llama` | Llama 3.3 70B via the local shim. A fallback, **not** a speed-up — Qwen is faster here. |
| `--mistral` | Mistral Small 4 119B (6.5B active per token), on ELM directly: tool calling, images, reasoning on by default. About twice as fast as Qwen; on small agent tasks it passed 46 of 51 where Qwen passed all, so Qwen stays the default and runs the sub-agents. Also in `/model`. Measurements in [INSTALL.md](INSTALL.md#mistral-small-4-the-other-model-with-tools-and-images). |
| `--with-all` | every optional extra, without `--remote`: sets up the agent's Python and the offline PyPI index if missing (once, ~2 GB, recorded so `pi update` keeps them), and offers every tool otherwise left out for size, the `workflow` tools included. The web, the open proxy and computer use stay off. |
| `--no-workflows` | leave the `workflow` tool (pi-dynamic-workflows) out of this run (`PI_ELM_WORKFLOWS=0` does the same); it is offered by default. Its definitions add about 6.9k characters to every request. |
| `--workflows` | offer the `workflow` tool where `PI_ELM_WORKFLOWS=0` would leave it out |
| `--remote` | web tools and computer use (screen and app control) on for this run, and the egress proxy records every destination instead of allowing only ELM and the package sources (PyPI, conda-forge, container registries). Models are unaffected: still ELM only, but the model is told to always research with the web tools, and cite them, rather than answer from memory. `PI_ELM_WEB=1` turns the tools on without opening the proxy. |
| `--no-computer-use` | with `--remote`, the web without the screen: computer use stays off (`PI_ELM_COMPUTER_USE=0` does the same). A new install asks macOS for Screen Recording at its first `--remote`, since its helper app is signed afresh. |
| `--manual` | permission mode for this run: nothing runs without your yes (above); where new sessions start unless auto is the default |
| `--auto` | permission mode for this run: the gate's rules as written. The default stays as it is |
| `--yolo` | permission mode for this run only: every ask answered yes; refusals still apply. Never the default |
| `--help` | the launcher's flags and environment, then pi's own help, run with this install's config, offline and with credentials scrubbed |

A session started at a terminal opens with a "Powered by ELM" banner and the
service's address, <https://elm.edina.ac.uk/elm>; `PI_ELM_BANNER=0` leaves it out.

| Command | |
|---|---|
| `/model` | switch between the ELM models |
| `/thinking` | reasoning is **off** by default here — see below |
| `/elm-policy` | why only ELM models are available |
| `/mode` | a menu of the permission modes: manual or auto for this session or as the default, yolo for this session only. `/mode auto` (and the others) goes straight to its second menu |
| `/export`, `/import` | session to HTML/JSONL and back |

## Things this install already knows

Hard-won settings that are in here deliberately. Full measurements in
[INSTALL.md](INSTALL.md#measured-behaviour).

- **Thinking is off.** On this deployment reasoning measured ~400x slower with no
  quality gain, and at small output budgets it consumes the whole allowance and
  returns empty content.
- **Qwen is faster than Llama here**, single and concurrent: 68-76 tok/s against
  30-47, and 535-566 tok/s aggregate across 12 parallel requests. Splitting a
  fan-out across both models is *slower* than sending it all to Qwen. Llama is a
  fallback, not an optimisation.
- **Startup is the npm packages, not pi.** They ship raw TypeScript and are
  transpiled at every launch; `--fast` skips them. Measured when the set was
  three packages: 1.4s to start against 4.7s, and 3.5s against 8.0s end to end
  on a small edit task. The set is now sixteen and has not been re-measured.
- **Prefix caching gives ~8x.** Long stable context is cheap; extra agent *turns*
  are what cost. Verified byte-stable prompt prefixes across a session; the
  skill router adds skills as a message after your request, not to the system
  prompt, so it keeps them that way.
- **Sub-agent fan-out is nearly free past the startup cost** (20 agents ≈ 12), but
  delegating work smaller than the round trip is 10x slower than doing it directly.
  So the prompt gives a countable line - two or more independent questions, or
  three or more unread files - and one call (pi-subagents' built-in `parallel`
  workflow) launches the lot; up to 12 children run at once.
- **`retry.maxRetries` is 10, `retry.provider.maxRetries` is 0.** Ten from a 1s base
  delay, doubling to 512s, gives ~1023s of tolerance (about 17 minutes) for a
  shared-gateway 429 storm or a bad network. Each wait is jittered by up to 25%
  (`patch-pi.py`), so sub-agents refused together do not retry together. SDK-level
  retries would swallow out-of-quota errors before pi sees them.
- **`pi -p` from a terminal is not hung**, it is reading stdin. The launcher closes
  stdin when it is a TTY.
- **Load is reported, not policed.** Each sub-agent is a full Node process, and
  above ~1.5x core count startup gets slow. The launcher says so and starts
  anyway; `PI_FORCE=1` silences the note, `PI_STRICT_LOAD=1` refuses instead.
- **Transcripts and memory are private by default.** Session and memory directories
  are mode 700, existing state files are tightened to mode 600, and locked
  credentials use mode 400. Set `ELM_PI_SHARED_STATE=1` only for a deliberately
  shared session directory.

## Developing elm-pi

Run `./scripts/check.sh` before committing. It performs shell and Python syntax
checks, policy/runtime tests, ShellCheck when available, and TypeScript checking
when `typescript` is installed in the checkout. The installer runs only its
syntax checks (`--source-only`) on the source it downloads. See [CONTRIBUTING.md](CONTRIBUTING.md) for the
dependency-update and generated-configuration workflow.

## Cost and policy

The ELM key is university-issued and metered: Qwen carries a `guidanceCost` of 2
per unit against your department's allocation. Cheaper than commercial models and
running on university hardware (ELM flags it "Climate Sensitive" and "University
Hosted") — but not free.

A coding agent's usage profile is nothing like the ELM chat UI: whole source
files, long loops, retries. If your key was approved for a different stated
purpose, tell the ELM team before they find out from a quota alert.
