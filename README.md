# elm-pi — a coding agent on the University's own hardware

A self-contained [pi](https://pi.dev) coding agent wired to the University of
Edinburgh's ELM gateway, running **Qwen 3.5 397B on university-hosted GPUs**
instead of a commercial provider. Commercial models are removed from the install
on purpose — see [LOCKDOWN.md](LOCKDOWN.md).

## Install

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
```

macOS or Linux, x86_64 or arm64. No `sudo`, nothing installed system-wide. It
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

Nothing lands outside the install directory: bundled Node, local `node_modules`,
and `PI_CODING_AGENT_DIR` pointed at `./agent` so config, sessions and
credentials never touch `~/.pi`. To remove it all:

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
| **Model** | `Qwen/Qwen3.5-397B-A17B-FP8` — 262K context, tool calling, vision |
| **Sub-agents** | 64-child fan-out budget; cheap Llama 3.3 workers via a local tool-call shim |
| **Editing** | Anchor-based (`pi-hashline-edit-pro`) — the built-in `edit` tool is off |
| **Memory** | Per-project `AGENTS.md`, plus `pi-hermes-memory` for cross-session search |
| **Web** | `pi-web-access` (DuckDuckGo, then Exa) |
| **Sessions** | `.pi/sessions/` inside each project, not one central 1.9 GB pile |
| **Models offered** | ELM only. 39 commercial providers stripped from the catalogue |

## Layout

```
install.sh          the curl|bash entry point: fetch, bootstrap, link
bootstrap.sh        one-command install / update, idempotent
pi                  the wrapper: bundled Node, .env, ELM-only guards, preflight
pi.orig             the unwrapped CLI the wrapper hands over to
configure.sh        resolves the model id from the gateway, merges it into config
patch-pi.py         removes /share and /bug from the release; run on every install
templates/          the source of truth for everything under agent/
docs/               the GitHub Pages site
shim/               Llama tool-call shim (Python, loopback only)
agent/              generated: PI_CODING_AGENT_DIR (config, sessions, memory)
agent/bin/          generated: fd rg jq yq shellcheck ast-grep, pinned + checksummed
.node/ node_modules/  generated: Node 24 + pi, ~650 MB
```

`agent/` is generated from `templates/`. Change a template, run
`./bootstrap.sh --update`, and the change reaches every host. Edit `agent/`
directly for one-off local tuning — a plain `./bootstrap.sh` will not overwrite it.

## Daily use

```bash
pi                             # interactive, starts on Qwen 397B
pi -p "..."                    # one-shot
pi --fast -p "..."             # one-shot, ~3x quicker to start
pi --llama -p "..."            # run on Llama 3.3 70B through the tool-call shim
cat file | pi -p "summarise"
pi update                      # elm-pi + pi from GitHub, then the pi packages
```

Nothing updates itself while you are trying to start work: the launcher runs pi
with `PI_OFFLINE=1`, so no version check, package check or tool download happens
at launch. `pi update` is the one place updates happen.

`pi` is a symlink to `~/.local/share/elm-pi/pi`; the launcher resolves symlinks,
so you can move or re-link it freely. `pi.orig` in the install directory is the
unwrapped CLI — vanilla pi, its own `~/.pi` config, no ELM provider and no
policy. It is deliberately not on your PATH; it exists to answer "is this the
wrapper's fault?".

| Flag | |
|---|---|
| `--fast` | skip the four npm packages: ~1.2s of CPU at launch instead of ~4.4s. No sub-agents, cross-session memory, web search or anchor editing; pi's built-in `edit` still works. Right for one-shot questions, wrong for multi-step work. |
| `--llama` | Llama 3.3 70B via the local shim. A fallback, **not** a speed-up — Qwen is faster here. |

| Command | |
|---|---|
| `/model` | switch between the ELM models |
| `/thinking` | reasoning is **off** by default here — see below |
| `/ulw <task>` | ultrawork mode: delegate, verify, keep going until done |
| `/elm-policy` | why only ELM models are available |
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
  transpiled at every launch; `--fast` skips them: 1.4s to start against 4.7s,
  and 3.5s against 8.0s end to end on a small edit task.
- **Prefix caching gives ~8x.** Long stable context is cheap; extra agent *turns*
  are what cost. Verified byte-stable prompt prefixes across a session.
- **Sub-agent fan-out is nearly free past the startup cost** (20 agents ≈ 12), but
  delegating work smaller than the round trip is 10x slower than doing it directly.
- **`retry.maxRetries` is 5, `retry.provider.maxRetries` is 0.** Five gives ~62s of
  tolerance for a shared-gateway 429 storm; SDK-level retries would swallow
  out-of-quota errors before pi sees them.
- **`pi -p` from a terminal is not hung**, it is reading stdin. The launcher closes
  stdin when it is a TTY.
- **Load is reported, not policed.** Each sub-agent is a full Node process, and
  above ~1.5x core count startup gets slow. The launcher says so and starts
  anyway; `PI_FORCE=1` silences the note, `PI_STRICT_LOAD=1` refuses instead.

## Cost and policy

The ELM key is university-issued and metered: Qwen carries a `guidanceCost` of 2
per unit against your department's allocation. Cheaper than commercial models and
running on university hardware (ELM flags it "Climate Sensitive" and "University
Hosted") — but not free.

A coding agent's usage profile is nothing like the ELM chat UI: whole source
files, long loops, retries. If your key was approved for a different stated
purpose, tell the ELM team before they find out from a quota alert.
