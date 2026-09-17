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
lands in `~/.local/share/elm-pi`, links `~/.local/bin/elm-pi`, and asks for your
ELM API key — [how to get one](INSTALL.md#step-1--get-an-elm-api-key).

```bash
elm-pi                                 # start working
```

Nothing lands outside the install directory: bundled Node, local `node_modules`,
and `PI_CODING_AGENT_DIR` pointed at `./agent` so config, sessions and
credentials never touch `~/.pi`. To remove it all:

```bash
rm -rf ~/.local/share/elm-pi ~/.local/bin/elm-pi
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
pi                  launcher: bundled Node, .env, ELM-only guards, preflight
configure.sh        resolves the model id from the gateway, merges it into config
templates/          the source of truth for everything under agent/
docs/               the GitHub Pages site
shim/               Llama tool-call shim (Python, loopback only)
agent/              generated: PI_CODING_AGENT_DIR (config, sessions, memory)
.node/ node_modules/  generated: Node 24 + pi, ~650 MB
```

`agent/` is generated from `templates/`. Change a template, run
`./bootstrap.sh --update`, and the change reaches every host. Edit `agent/`
directly for one-off local tuning — a plain `./bootstrap.sh` will not overwrite it.

## Daily use

```bash
elm-pi                             # interactive, starts on Qwen 397B
elm-pi -p "..."                    # one-shot
cat file | elm-pi -p "summarise"
```

`elm-pi` is a symlink to `~/.local/share/elm-pi/pi`; the launcher resolves it, so
you can move or re-link it freely.

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
- **Prefix caching gives ~8x.** Long stable context is cheap; extra agent *turns*
  are what cost. Verified byte-stable prompt prefixes across a session.
- **Sub-agent fan-out is nearly free past the startup cost** (20 agents ≈ 12), but
  delegating work smaller than the round trip is 10x slower than doing it directly.
- **`retry.maxRetries` is 5, `retry.provider.maxRetries` is 0.** Five gives ~62s of
  tolerance for a shared-gateway 429 storm; SDK-level retries would swallow
  out-of-quota errors before pi sees them.
- **`pi -p` from a terminal is not hung**, it is reading stdin. The launcher closes
  stdin when it is a TTY.
- **Don't pile on load.** Each sub-agent is a full Node process; the launcher
  refuses to start above 1.5x core count (`PI_FORCE=1` overrides).

## Cost and policy

The ELM key is university-issued and metered: Qwen carries a `guidanceCost` of 2
per unit against your department's allocation. Cheaper than commercial models and
running on university hardware (ELM flags it "Climate Sensitive" and "University
Hosted") — but not free.

A coding agent's usage profile is nothing like the ELM chat UI: whole source
files, long loops, retries. If your key was approved for a different stated
purpose, tell the ELM team before they find out from a quota alert.
