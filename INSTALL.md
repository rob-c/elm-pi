# Installing elm-pi on a new machine or host

Verified on macOS 15.8 (Intel) and written to work unchanged on Apple Silicon and
Linux x64/arm64. Requires: `curl`, `tar`, `python3`, and an ELM API key. `git` is
optional — the installer falls back to a source tarball without it.

---

## The short version

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
```

That is `install.sh`: it checks the machine, fetches this repository to
`~/.local/share/elm-pi`, runs `bootstrap.sh`, and links `~/.local/bin/elm-pi`.
Use the `bash -c "$(curl ...)"` form rather than `curl | bash` — piping replaces
stdin, and bootstrap would not be able to prompt you for the key.

If the directory is already on the host (git clone, `scp -r`, tar):

```bash
cd ~/.local/share/elm-pi
./bootstrap.sh
```

Only these need to travel: `install.sh`, `bootstrap.sh`, `pi`, `configure.sh`,
`templates/`, `shim/`, and the docs. Everything else is downloaded or generated.
`.gitignore` already excludes the key, the installed software and all runtime
state, so the repository is safe to push.

Bootstrap installs Node into `.node/`, pi into `node_modules/`, the pi packages
into `agent/npm/`, generates `agent/` from `templates/`, asks for your ELM key,
resolves the model id from the gateway, smoke-tests a completion, and verifies
the ELM-only policy. Roughly 650 MB and 3 minutes on a warm network.

Unattended:

```bash
ELM_API_KEY=elm-... ./bootstrap.sh --non-interactive
# or, from scratch:
ELM_API_KEY=elm-... /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
```

Re-running either is safe: neither overwrites `.env`, sessions, memory, or a
config you have edited. `./bootstrap.sh --update` refreshes pi, the packages and
the extensions, keeping your configs.

Installer knobs, if the defaults do not suit:

| Variable | Default |
|---|---|
| `ELM_PI_PREFIX` | `~/.local/share/elm-pi` — where the install lives |
| `ELM_PI_BINDIR` | `~/.local/bin` — where `pi` is linked |
| `ELM_PI_BRANCH` | `main` |
| `ELM_PI_UPDATE` | `0`; `1` passes `--update` through to bootstrap |

To remove everything: `rm -rf ~/.local/share/elm-pi ~/.local/bin/elm-pi`.

---

## Step 1 — Get an ELM API key

Keys are **issued on request, not self-service**. In the ELM web UI, submit the
API-key request form describing your use case; it goes to an approval queue.

Check status from the browser console on an ELM tab (⌥⌘I → Console):

```js
await (await fetch("/api/elm-key-requests?page=0&size=20", {credentials:"include"})).json()
```

Look for `"status": "KEY_ISSUED"`; the key is in `elmKeyValue`, with an
`expiryDate` (12 months, typically). Keys look like `elm-xxxxxxxx-xxxxxxxxxxxxxxxx`.

**Check before you request** — you may already have one issued.

Two things people get wrong:

- `/api/key-requests` (no `elm-` prefix) is a *different, older* queue that issues
  raw OpenAI `sk-...` keys hitting OpenAI directly. Not what you want.
- ELM has two APIs. `/api/*` is the web app's cookie-authenticated backend;
  `/api/v1/*` is the OpenAI-compatible gateway and accepts **only**
  `Authorization: Bearer <key>`. Being logged in to ELM in your browser buys you
  nothing at the API level.

---

## Step 2 — Run bootstrap

```bash
./bootstrap.sh
```

| Flag | |
|---|---|
| `--non-interactive` | take the key from `$ELM_API_KEY`, never prompt |
| `--update` | refresh pi, packages and extensions; keep configs |
| `--no-packages` | pi only: no sub-agents, memory, web access or anchor editing |
| `--no-shim` | no Llama tool-call shim (Qwen unaffected) |
| `--no-auth-lock` | leave `agent/auth.json` writable, so `/login` works |

---

## What bootstrap does, and the manual equivalent

Useful when a step fails, or when a host needs something done differently.

### 1. Node, bundled

pi needs Node ≥ 22.19. The official prebuilt tarball is extracted into `.node/`,
after a SHA-256 check against `SHASUMS256.txt`.

> **Do not `brew install node` on an Intel Mac.** There is no bottle for that
> combination any more, so Homebrew compiles V8 from source — over an hour.

```bash
V=v24.21.0; ARCH=x64        # arm64 on Apple Silicon
TAR=node-$V-darwin-$ARCH.tar.gz
curl -fsSL -o "/tmp/$TAR" "https://nodejs.org/dist/$V/$TAR"
curl -fsSL -o /tmp/SHASUMS256.txt "https://nodejs.org/dist/$V/SHASUMS256.txt"
grep " $TAR\$" /tmp/SHASUMS256.txt | shasum -a 256 -c -   # must say OK
mkdir -p .node && tar -xzf "/tmp/$TAR" -C .node --strip-components=1
```

### 2. pi

`templates/package.json` → `package.json`, then `npm install`. npm warns that
esbuild, protobufjs and `@google/genai` have unapproved install scripts; pi runs
from a prebuilt bundle and does not need them.

### 3. `agent/` from `templates/`

`PI_CODING_AGENT_DIR=./agent` (set by the launcher) is what keeps this deployment
self-contained — without it pi writes to `~/.pi/agent` and collides with any other
pi install.

| Generated file | Purpose |
|---|---|
| `agent/models.json` | the ELM provider: base URL, `$ELM_API_KEY`, the two models |
| `agent/settings.json` | defaults, packages, extensions, retry, `sessionDir` |
| `agent/AGENTS.md` | loaded every session: delegation policy, model choice, memory rules |
| `agent/prompts/ulw.md` | the `/ulw` ultrawork mode |
| `agent/extensions/elm-only.ts` | the ELM-only policy — always refreshed |
| `agent/extensions/elm-shim.ts` | registers the Llama tool-shim provider |
| `agent/extensions/protected-paths.ts` | blocks writes to `.env`, `.git/`, `node_modules/` |
| `agent/extensions/todo.ts` | adds a `todo` tool for multi-step work |
| `agent/extensions/subagent/config.json` | fan-out budget: 8 concurrent, 64 per run |
| `agent/bin/pi` | symlink to the launcher, so sub-agent children find `pi` whatever PATH looks like |
| `agent/web-search.json` | DuckDuckGo then Exa; `unpdf` for PDFs |
| `agent/hermes-memory-config.json` | cross-session memory, 30-day retention |

`agent/` is generated. Put durable changes in `templates/` and re-run
`./bootstrap.sh --update` so every host gets them.

### 4. pi packages

pi resolves `npm:<name>` from `agent/npm/node_modules`, so bootstrap writes
`agent/npm/package.json` and runs `npm install` there. Equivalent to
`./pi install npm:pi-subagents` etc., but deterministic and offline-friendly.

| Package | |
|---|---|
| `pi-subagents` | sub-agent fan-out (`subagent`, `bg_wait`, `subagent_supervisor`) |
| `pi-hashline-edit-pro` | anchor-based editing; the built-in `edit` tool is disabled |
| `pi-hermes-memory` | cross-session memory with SQLite FTS5 search |
| `pi-web-access` | web search and fetch |

> pi packages run with full system access. Review before adding more.

**How sub-agent children find pi.** `pi-subagents` spawns each child by resolving
the pi CLI from `process.argv[1]`, then from package resolution, and if both fail
it falls back to `{ command: "pi" }` — a bare PATH lookup. This install puts
no `pi` on PATH at all — the command was `elm-pi` — so on hosts where the first
two routes fail that fallback found nothing and sub-agents would not start.

Three independent fixes, any one of which is sufficient:

- the launcher exports `PI_SUBAGENT_PI_BINARY="$HERE/pi"`, the documented
  override, which short-circuits resolution entirely;
- `bootstrap.sh` creates `agent/bin/pi -> <install>/pi`. `agent/bin` is pi's
  managed-binary directory (`fd`, `rg`) and pi prepends it to `PATH` for every
  child process it spawns, so a bare `pi` lands on the launcher whatever the
  inherited PATH looks like;
- the installer links `~/.local/bin/pi` at the launcher, so a bare `pi` is the
  wrapped one for you as well as for children.

Children go through the **launcher** rather than `cli.js` on purpose: the
ELM-only policy, the `.env` key and the bundled Node then apply to them too. The
launcher sets `PI_ELM_CHILD=1` before exec so nested invocations skip the load
preflight instead of printing one warning per child.

### 5. The Llama tool-call shim

ELM's vLLM instance for Llama 3.3 was started without
`--enable-auto-tool-choice` / `--tool-call-parser`, so **any** request carrying
`tools` returns HTTP 400 — Llama cannot call tools on ELM natively. `shim/shim.py`
lifts tool definitions into a system prompt, strips `tools`, and parses the JSON
call back out of the reply, re-emitting it as OpenAI `tool_calls`.

`elm-shim.ts` starts it on demand on `127.0.0.1:8811` and reuses a running one, so
a fan-out of sub-agents does not start dozens of copies. Qwen never goes through
it. No shim, no Llama sub-agents; everything else is unaffected.

One bug was fixed while porting it here. OpenAI clients append `/v1/chat/completions`
to the base URL they are given, and `ELM_BASE_URL` already ends in `/api/v1`, so
the passthrough branch built `.../api/v1/v1/chat/completions` and the gateway
answered `400 Unknown or unsupported endpoint`. It went unnoticed because only
requests carrying `tools` had ever been exercised, and those take the shimmed
branch, which builds its own path. `_url()` now strips the duplicate segment;
passthrough, shimmed tool calls and `GET /v1/models` are all verified.

### 6. The key, the model id, the smoke test

`.env` is written mode 600 and is gitignored. Then `./configure.sh`:

- queries `GET /api/v1/models` with your key — **the gateway is authoritative**;
  the published Information Services model list was seven months stale when
  checked, naming Llama 3.3 and EuroLLM and not mentioning Qwen at all
- picks the best match for a substring (default `qwen`) and **merges** it into
  `agent/models.json` and `agent/settings.json`, leaving your other settings alone
- sends one completion and prints the reply

Run it again any time: `./configure.sh` or `./configure.sh llama`.

Model ids are exact: `Qwen/Qwen3.5-397B-A17B-FP8` — vendor prefix, capital Q,
`-A17B-FP8` suffix. Not `qwen-3.5-397b`. The other university-hosted models are
`meta-llama/Llama-3.3-70B-Instruct` and `utter-project/EuroLLM-22B-Instruct-2512`;
everything else your key can see is a commercial model proxied through ELM.

**`maxTokens` from ELM's metadata is the context window, not the output budget.**
ELM reports 262144 for Qwen — that belongs in `contextWindow`, with a smaller
`maxTokens` for output. Conflating them produces 400s partway through a session
rather than a clean error at startup.

---

## Verify the install

Bootstrap runs checks 1 and 4 for you.

**1. Only ELM models are offered** — with commercial keys in the environment:

```bash
ANTHROPIC_API_KEY=x OPENAI_API_KEY=x ./pi --list-models
```

```
provider  model                              context  max-out  thinking  images
elm       meta-llama/Llama-3.3-70B-Instruct  128K     16.4K    no        no
elm       Qwen/Qwen3.5-397B-A17B-FP8         262.1K   32.8K    yes       yes
elm-shim  meta-llama/Llama-3.3-70B-Instruct  128K     16.4K    no        no
```

**2. A round trip completes:**

```bash
./pi -p "Reply with exactly: hello from Qwen"
```

**3. Tool calling actually works** — the one that matters. A coding agent drives
everything through tool calls; a model that chats fine but never emits them will
never edit a file:

```bash
mkdir -p /tmp/pitest && cd /tmp/pitest
printf 'def add(a, b):\n    return a - b\n' > calc.py
pi -p "Read calc.py, fix the bug in add, write it back. Then say DONE."
cat calc.py          # expect: return a + b
```

**4. The policy holds:**

```bash
./pi --model anthropic/claude-opus-5 -p x     # exit 2, refused by the launcher
```

If 3 fails while 2 succeeds, test the gateway directly:

```bash
curl -s -H "Authorization: Bearer $ELM_API_KEY" -H "Content-Type: application/json" \
  https://elm.edina.ac.uk/api/v1/chat/completions \
  -d '{"model":"Qwen/Qwen3.5-397B-A17B-FP8",
       "messages":[{"role":"user","content":"Read /etc/hosts using the tool."}],
       "tools":[{"type":"function","function":{
         "name":"read_file","description":"Read a file",
         "parameters":{"type":"object","properties":{"path":{"type":"string"}},
                       "required":["path"]}}}],
       "tool_choice":"auto"}'
```

You want `finish_reason: "tool_calls"` and a populated `tool_calls` array. If it is
empty, that model's vLLM deployment has no tool-call parser — server side, report
it to the ELM team.

---

## Measured behaviour

Numbers from this deployment, not from documentation. They are why the config
looks the way it does.

### The first interactive launch, and why it used to crawl

The first `pi` on a fresh install took far longer than every launch after it, and
none of that time was pi's own startup. Reading `dist/bundle`, interactive mode
does four things over the network while it comes up:

| What | When | Cost |
|---|---|---|
| downloads `fd` and `rg` from GitHub into `agent/bin` | **awaited before the prompt is drawn** | two release lookups + two tarballs, and a 10s/120s timeout each if GitHub is slow |
| `npm view <pkg> version` for every package in `settings.json` | after the prompt appears | four npm processes, concurrently with the TypeScript transpile below |
| asks `pi.dev` for the latest pi version, and reports the install | after the prompt appears | one request each |
| refreshes the remote model catalogue | after the prompt appears | one request, useless here — the ELM catalogue is `agent/models.json` |

Only the first one blocks, and it only blocks once, because pi keeps the binaries
it downloads. The fix is to have them there already:

- **`bootstrap.sh` installs `fd` and `rg` into `agent/bin`** (pinned versions,
  sha256-checked against `templates/tools.sha256`), whether or not the machine
  already has them. The install owns its tools — `rm -rf` this directory and they
  go with it — and the launcher puts `agent/bin` first on `PATH`, so the agent's
  `bash` tool gets the same two binaries the `find` and `grep` tools use.
  `--no-tools` skips this and leaves pi to find a system `fd`/`rg`.

### The rest of the toolbox

`fd` and `rg` are there because pi needs them. Four more are there because the
*model* keeps reaching for them and cannot rely on finding them — not on a Mac,
and not on a login node someone else administers:

| | | |
|---|---|---|
| `jq` | JSON on the command line | macOS 15 ships it, most Linux images do not |
| `yq` | the same for YAML | CI configs, k8s manifests, conda envs |
| `shellcheck` | lints shell before it runs | this install is mostly bash; it found a stray character in `install.sh` the first time it was pointed at it |
| `ast-grep` | structural search and rewrite, by syntax tree rather than by regex | the thing `rg` cannot do |

All six are a single static binary from the project's own GitHub release,
pinned and sha256-checked, installed the same way and deleted the same way.
`ELM_PI_TOOLS=fd,rg,jq` installs a subset: `shellcheck` and `ast-grep` are 35 MB
and 51 MB, against ~23 MB for the other four.

`fd` and `rg` are also the two pi will otherwise download for itself, so they
are the two that must be there before the first launch. The others only need to
exist by the time the model types them.
- **The launcher sets `PI_OFFLINE=1`**, pi's own `--offline`, which disables the
  remaining three. It covers startup network operations only: ELM requests, web
  search and anything you type are untouched. `PI_ELM_STARTUP_CHECKS=1 pi`
  restores pi's default behaviour for a run.

Updates then happen when you ask for them, which is what `pi update` is for.

### Startup time: where it goes, and how to cut it

`pi` itself starts in well under a second. The four npm packages are what you wait
for: they ship **raw TypeScript**, so every launch transpiles and imports them from
several hundred files. Measured with `PI_TIMING=1` and `/usr/bin/time`, reporting
CPU time (user+sys) because that is the number that does not move with machine load
— taken at load ~8 on 12 threads, where wall ≈ CPU:

| Configuration | CPU per launch |
|---|---|
| pi + local extensions only (what `--fast` loads) | **1.4s** |
| \+ `pi-subagents`, `pi-hashline-edit-pro` | 3.0s |
| \+ `pi-web-access` | 3.2s |
| \+ `pi-hermes-memory` (the default install) | **5.0s** |

So: `pi-hermes-memory` ~1.8s, `pi-subagents` + `pi-hashline-edit-pro` ~1.6s,
`pi-web-access` ~0.2s, pi and the local extensions ~1.4s.

**Three levers, in order of payoff:**

1. **`pi --fast`** for one-shot work. Loads only the local extensions — the
   ELM-only policy, protected paths and `todo` — and keeps pi's built-in `edit`
   tool. No sub-agents, cross-session memory, web search or anchor editing.

   | | wall | CPU |
   |---|---|---|
   | `pi -p "Reply with exactly: OK"` | 4.68-5.07s | 4.18-4.53s |
   | `pi --fast -p "..."` | **1.43-1.51s** | **1.13-1.20s** |
   | `pi --fast --llama -p "..."` | 1.65-2.33s | 1.29-1.33s |

   End to end on a real edit task (read `calc.py`, fix the bug, write it back):
   **8.01s → 3.49s**, both producing the correct edit.

2. **`./bootstrap.sh --no-memory`** drops `pi-hermes-memory` permanently, ~1.8s of
   CPU off every launch including interactive sessions. Per-project `AGENTS.md`
   memory is unaffected — that is a pi built-in, not a package. You lose
   cross-session FTS5 search.

3. **Machine load.** Wall time is CPU time multiplied by whatever else the machine
   is doing. The same launch measured 4.7s wall at load 8 and 32-47s wall at load
   350 while CPU barely moved. If pi feels slow, check `uptime` before changing
   any config. If it is slow on an *idle* machine, try excluding the install
   directory from endpoint-protection real-time scanning: 589 npm packages of
   small files is the profile on-open scanning punishes hardest. (Plausible, not
   measured — toggling Defender needs admin rights.)

**Two things that do not help**, both measured rather than assumed:

- `NODE_COMPILE_CACHE`: 6.5s → 6.4s CPU. V8's bytecode cache does not cover the
  TypeScript transform that dominates here.
- `PI_OFFLINE=1`: no difference to `pi -p` (4.2-4.8s wall either way). Print mode
  runs none of the startup checks in the first place, and the model catalogue is
  refreshed when you open the `/model` picker, not on this path. It is set by
  default anyway, for the interactive launch it does change — see above.

Bundling the packages with esbuild was considered and rejected: `pi-subagents`
spawns child processes by path and `pi-hermes-memory` loads a native SQLite
binding, so bundling changes third-party semantics for a win the `--fast` path
already delivers.

### Qwen is faster than Llama here — Llama is not a speed optimisation

Measured against the gateway directly, so machine load does not enter into it:

| | Qwen 3.5 397B | Llama 3.3 70B |
|---|---|---|
| ~180 tokens out | 2.7-3.0s, **68-76 tok/s** | 3.7-5.7s, 30-47 tok/s |
| 8 concurrent | 2.1s wall, **399 tok/s** | 3.4s wall, 295 tok/s |
| 12 concurrent, all Qwen | **2.5-2.7s wall, 535-566 tok/s** | |
| 12 concurrent, 6 + 6 split | 3.7-4.0s wall, 309-347 tok/s | |

A 397B MoE with 17B active parameters beats a 70B dense model on the same tp4
hardware, and Qwen scales cleanly to 12 concurrent requests. **Splitting a fan-out
across both models is slower than sending it all to Qwen** — the Llama half sets
the wall time.

Llama still has its uses — a fallback when Qwen is rate-limited, and possibly a
cheaper allocation charge (ELM's `guidanceCost` is only visible in the web UI, so
that is unverified). It is reached with:

```bash
pi --llama -p "..."                                    # via the shim
pi --model elm-shim/meta-llama/Llama-3.3-70B-Instruct  # the long form
```

Both go through the local tool-call shim, which buffers the whole response before
re-emitting it, so Llama also loses streaming. `agent/AGENTS.md` now tells
sub-agents to default to Qwen.

### Thinking is off by default

Same task, same 32K output budget:

| | thinking off | thinking on |
|---|---|---|
| Latency | 0.7s | 286.7s |
| Answer | caught both bugs | caught one, missed the other |

~400x slower and worse. At smaller output budgets it is worse still: reasoning
consumes the whole allowance and `content` comes back empty with
`finish_reason: "length"`. `/thinking` turns it on per session when a task
genuinely warrants it.

### Prefix caching gives ~8x

ELM's vLLM does prefix caching, measured directly:

| | Latency |
|---|---|
| 30,215-token prefix, first call | 3.34s |
| Same prefix, repeat | **0.40s / 0.55s** |
| Fresh prefix | 3.01s |

pi's half is verified too, by capturing its real request bodies through a
streaming-preserving proxy: the `developer` system message is byte-identical every
turn, each message list is a strict verbatim extension of the last, and TTFB fell
from 3.02s to 0.96s **while the prompt grew** — the cache signature.

So: `AGENTS.md` and long stable context are nearly free, and **turn count, not
prompt length, is what to optimise**. Nothing needs enabling.

Two settings were tried and removed: `compat.sendSessionAffinityHeaders` /
`sessionAffinityFormat`, and `PI_CACHE_RETENTION=long`. Neither produced a
measurable gain.

### Sub-agent fan-out

| Concurrent sub-agents | Wall time | Result |
|---|---|---|
| 3 | 98s | all correct |
| 6 | 110s | all correct |
| 12 | 269s | all correct |
| 20 | 264s | all correct |

Wide fan-out is close to free past the fixed startup cost. But delegation is
priced per round trip: forcing it on a four-file docstring task turned a
36-second direct edit into a 560-second run that never finished. `AGENTS.md`
therefore keys the rule to **work size, not file count**.

At 20 children some results came back as "previews omitted by budget" — tell
sub-agents to report tersely or raise `maxOutput`.

Each sub-agent is a full Node process. A 32-worker run drove load average to 104
on a 12-thread laptop and made every new pi invocation hang, which is why the
launcher warns above 1.5x core count and starts anyway: a shared login node or a
busy desktop sits over that line most of the day, and a refusal there costs more
than the slow start it prevents. `PI_FORCE=1` drops the warning too;
`PI_STRICT_LOAD=1` restores the old refusal, which is what you want in a batch
job or a cron run.

### Retry under a gateway storm

Verified by injecting faults through a local proxy: five injected 503s, then a
success, backing off 2/4/8/16/32s — exact doubling from `baseDelayMs`, and the
agent run continued as if nothing had happened.

The default `maxRetries: 3` gives ~14s of tolerance; against a 429 storm on a
shared university gateway pi surfaced `429: Rate limit exceeded` after ~15s.
**5** gives ~62s. `retry.provider.maxRetries` stays at **0** — SDK-level retries
can swallow out-of-quota errors before pi sees them, blocking the agent until the
provider quota resets. pi uses its own backoff and ignores `Retry-After`.

### Latency variance is pi, not ELM

Identical pi tasks have ranged from 8s to 98s. Twelve identical calls straight to
ELM measured min 2.89s, median 3.43s, max 5.53s. The spread comes from pi's agent
loop taking more turns on some runs. Do not tune config against a single timing
sample — the noise is larger than most config effects.

### Extensions: add them one at a time

Same survey task, same directory:

| Extensions loaded | Result |
|---|---|
| none (`--no-extensions`) | 18s, correct |
| `protected-paths` + `todo` | 77s, correct |
| \+ `notify`, `session-name`, `model-status` | 540s timeout, no output |
| \+ `git-checkpoint`, `dirty-repo-guard` | 540s timeout, no output |

`git-checkpoint` and `dirty-repo-guard` act on git state and hang outside a
repository; the others were not isolated individually. Only the three that measure
clean ship here. Add any more one at a time and time a known task before and after.

### Llama needs steps, not goals

With anchor editing in place:

| Task given to Llama | Result |
|---|---|
| Single file, "fix the bug" | works, 18s |
| Two files, "read each and add docstrings" | **claimed FINISHED, changed nothing** |
| Two files, numbered steps | **both correct, 17s** |

The difference is planning, not editing. Give a Llama sub-agent a numbered list of
concrete actions and exact paths, and always verify its report. Anything that
needs deciding *what* to do goes to Qwen.

---

## Sessions, memory and artefacts

`sessionDir: ".pi/sessions"` is **relative**, so it resolves against the working
directory and each project keeps its own history. This also fixed an accumulation
problem: sessions had reached 1.9 GB across 699 files in one central directory.

Add `.pi/` to each project's `.gitignore` — transcripts contain whatever the agent
read, which may include secrets.

Precedence is `--session-dir` > `PI_CODING_AGENT_SESSION_DIR` > `sessionDir`.

Durable project facts go in that project's own `AGENTS.md`, which pi loads from
the working directory and its ancestors on every session, so they travel with the
repo. `agent/AGENTS.md` carries the policy for what belongs there (durable,
project-specific, not derivable from the code — and never secrets).

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| `401 Missing or invalid Authorization header` | No bearer token. Cookies don't work on `/api/v1`. |
| `401 Invalid API key` | Key wrong, revoked or expired — check `expiryDate` on the request record. |
| `Model not found` for an ELM model | Wrong case or missing vendor prefix. Copy it verbatim from `/api/v1/models`, or re-run `./configure.sh`. |
| `Model not found` for a commercial model | Working as designed — see [LOCKDOWN.md](LOCKDOWN.md). |
| Empty response, `finish_reason: "length"` | Reasoning consumed the output budget. Raise `maxTokens` or keep thinking off. |
| Chats fine, never edits files | No `tool_calls` from the backend. Test the gateway directly (verify step 3). |
| 400s partway through a session | `contextWindow` set higher than the model supports. |
| `pi -p "..."` hangs at a prompt | Not a bug: print mode reads stdin and a terminal never sends EOF. The launcher closes stdin when it is a TTY; if you bypass the launcher, add `< /dev/null`. |
| `pi: this machine is busy ...` | Informational. It starts anyway, just slowly. `PI_FORCE=1` silences it. |
| `env: node: No such file or directory` | Launcher bypassed, or `.node/` missing — re-run `./bootstrap.sh`. |
| Llama sub-agents unavailable | `python3` missing, or port 8811 taken. `ELM_SHIM_PORT` moves it. |
| Sub-agents fail to start, or something reports `pi: command not found` | pi-subagents falls back to a bare `pi` on PATH when it cannot resolve the CLI. Fixed three ways — the launcher exports `PI_SUBAGENT_PI_BINARY`, `bootstrap.sh` creates `agent/bin/pi`, and the installer links `~/.local/bin/pi`. Re-run `./bootstrap.sh --update` if `agent/bin/pi` is missing. |
| `pi: command not found` in a new shell | The installer adds `~/.local/bin` to your shell profile; open a new shell, or `export PATH="$HOME/.local/bin:$PATH"` for the current one. |
| `pi` runs something other than this install | Another `pi` is earlier on PATH — the installer warns when it sees one. `command -v pi` shows which wins; either remove it or put `~/.local/bin` ahead of it. |
| Want vanilla pi, to tell wrapper bugs from pi bugs | `~/.local/share/elm-pi/pi.orig`. It is the unwrapped CLI with pi's own `~/.pi` config, so it starts with no models until you configure one. |
| Startup hangs with no output at all | Seen in clusters, cause unknown; ruled out config, extensions, the launcher, ELM itself and leftover processes. Wait and retry rather than changing config — a change made during a bad window will look causal and is not. |
