# Installing elm-pi on a new machine or host

Verified on macOS 15.8 (Intel) and written to work unchanged on Apple Silicon and
Linux x64/arm64. Requires: `curl`, `tar`, and an ELM API key. `git` is
optional — the installer falls back to a source tarball without it. Python 3.8+
is used when the system has one (never conda, a virtualenv or pyenv); otherwise
the installer downloads a standalone CPython into the install.

---

## The short version

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
```

That is `install.sh`: it checks the machine, fetches this repository to
`~/.local/share/elm-pi`, runs `bootstrap.sh`, and links `~/.local/bin/pi`.
Use the `bash -c "$(curl ...)"` form rather than `curl | bash` — piping replaces
stdin, and bootstrap would not be able to prompt you for the key.

If the directory is already on the host (git clone, `scp -r`, tar):

```bash
cd ~/.local/share/elm-pi
./bootstrap.sh
```

The source checkout must travel as a unit: the launch scripts, `config/`, `lib/`,
`scripts/`, `templates/`, shim, proxy and docs are all used by install
or validation. Installed software and runtime state are downloaded or generated.
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

Re-running either is safe: neither overwrites `.env`, sessions, or a config
you have edited, and both repeat the options the install was made with (below).
A re-run installs the tested versions in `config/versions.json` when a pull has
changed them, and otherwise leaves pi and the packages alone. `pi update`
fetches and validates current source, then installs the latest pi and packages
while keeping configs; `pi update --extensions` goes back to the tested set.

Installer knobs, if the defaults do not suit:

| Variable | Default |
|---|---|
| `ELM_PI_PREFIX` | `~/.local/share/elm-pi` — where the install lives |
| `ELM_PI_BINDIR` | `~/.local/bin` — where `pi` is linked |
| `ELM_PI_BRANCH` | the branch the install was made from (`agent/install-options`), else `main` |
| `ELM_PI_REPO` | the repository the install was made from, else `rob-c/elm-pi` on GitHub |
| `ELM_PI_UPDATE` | `0`; `1` passes `--update` through to bootstrap |

To remove everything: `rm -rf ~/.local/share/elm-pi ~/.local/bin/pi`.

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
| `--update` | the latest pi and extension packages, kept only if the checks pass; keep configs (what `pi update` runs) |
| `--force-packages` | reinstall the extension packages at the tested versions, and pi too if it is not at its tested version (what `pi update --extensions` runs) |
| `--no-packages` | pi only: no sub-agents, web access or anchor editing |
| `--no-tools` | do not bundle fd, rg, jq, yq, shellcheck, ast-grep and uv (and so no agent Python either) |
| `--with-python` | give the agent its own Python environment in `agent/python` (~1 GB); also `pi setup --python` |
| `--with-pypi-index` | build an offline search index of PyPI for the agent (`pypi-search`); downloads ~1 GB once, keeps ~390 MB; implies `--with-python`; also `pi setup --pypi-index` |
| `--no-python`, `--no-pypi-index` | take those back: removes `agent/python` (and the index), or the index alone |
| `--no-shim` | no Llama tool-call shim (Qwen unaffected) |
| `--no-auth-lock` | leave `agent/auth.json` writable, so `/login` works |
| `--no-patch` | leave pi's `/share` and `/bug` commands in place |
| `--force` | re-download the tools and reinstall pi and the npm packages, at the tested versions |
| `--reset-options` | forget the options earlier runs recorded, and use only this run's |
| `-h`, `--help` | the flag list, which now lives in one place in the script |

**The options are remembered.** The `--no-*` flags and `ELM_PI_TOOLS` are
written to `agent/install-options`, together with the branch and repository
`install.sh` fetched, and every later run repeats them: re-running the
installer or `./bootstrap.sh`, `pi update` and `pi update --extensions`. An
update therefore keeps the install you chose rather than reinstalling what you
declined, or re-locking `auth.json` after `--no-auth-lock`. A flag given on a
later run is added to the record. To take one back, start the record again
with only the flags you want:

```bash
./bootstrap.sh --reset-options --no-shim     # now: everything except the shim
```

`install.sh` accepts `--reset-options` and passes it through. An install made
before the record existed has its flags inferred from what they left behind,
except `--no-patch` and a tool subset.

`pi --remote` is the flag for work that needs the web. It is on the launcher,
not the installer, so it is a decision per run rather than per host:

```bash
pi --remote                 # web tools on, egress proxy recording not gating
pi --remote --fast -p "..." # open proxy, but --fast loads no web tools
```

It lifts exactly two things — the web tools come back on, and the egress proxy
stops allowing only the ELM gateway and PyPI — and adds one: computer use
(`@injaneity/pi-computer-use`), which lets the agent see the screen and drive
apps and browsers through the accessibility API. It loads in that session
only, never in its sub-agents; on macOS the first use asks for Accessibility
and Screen Recording for its helper, which lives in `agent/helpers/`. **The model policy is untouched**: the
credential scrub, the argument guard and the catalogue strip all stay, so
inference still goes to ELM, no other provider becomes reachable or visible,
and Qwen is still the model. Telemetry and the version check stay off, as they
are in every mode. Every destination the run reaches is recorded in
`agent/egress.log`.

Narrower options, when you know where you are going:

```bash
ELM_PI_PROXY_ALLOW=api.exa.ai pi    # one extra host, nothing else
PI_ELM_WEB=1 pi                     # tools on, proxy unchanged (they will fail)
```

Whatever these flags decide, `agent/settings.json`'s `packages` list is written
to match on every run. It is copied from `templates/settings.json` (emptied by
`--no-packages`), not edited in place — editing in place could only ever
remove, so an install that had once been run with `--no-packages` kept an empty
list for ever after, installed the package set on the next run and then loaded
none of them. A package added to the list by hand is named and removed.
Everything else in that file is yours and is left alone. A package that is
listed but missing or incomplete in `agent/npm/node_modules` is reinstalled,
and the install stops if it is still incomplete, because at runtime it is
silent: pi starts offline, so it does not fetch it either.

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

`package.json` asks for `latest`; `config/versions.json` holds the version this
repo last tested, which every install but `--update` takes (see CONTRIBUTING.md).
`--force-packages` also brings pi back to that version when `pi update` moved it
on, since the packages were tested against it.
Bootstrap runs `npm install --omit=dev --ignore-scripts` in a sibling staging
directory, patches and starts the staged CLI, then swaps its `node_modules` into
place. The tree it replaced is kept until the end of the run and put back if
anything after the swap fails.
The prebuilt pi bundle does not need dependency install scripts.

### 3. `agent/` from `templates/`

`PI_CODING_AGENT_DIR=./agent` (set by the launcher) is what keeps this deployment
self-contained — without it pi writes to `~/.pi/agent` and collides with any other
pi install.

| Generated file | Purpose |
|---|---|
| `agent/models.json` | the ELM provider: base URL, `$ELM_API_KEY`, the two models |
| `agent/settings.json` | defaults, packages, extensions, retry, `sessionDir` |
| `agent/AGENTS.md` | loaded by every top-level session: delegation policy, model choice, project-memory rules. Sub-agents do not see it (nor `APPEND_SYSTEM.md`); their rules are in `agent/agents/*.md` |
| `agent/extensions/elm-only.ts` | the ELM-only policy — always refreshed |
| `agent/extensions/elm-shim.ts` | registers the Llama tool-shim provider |
| `agent/extensions/protected-paths.ts` | blocks writes to `.env`, `.git/`, `node_modules/` |
| `agent/extensions/todo.ts` | adds a `todo` tool for multi-step work |
| `agent/extensions/pinned-instructions.ts` | `pin_instruction`: standing instructions kept in the system prompt, where compaction cannot summarise them away |
| `agent/extensions/skill-router.ts` | adds the skills a request needs (see [Skills](#skills-and-the-skill-router)) |
| `agent/extensions/view-outputs.ts` | shows Qwen its figures: image and PDF files a command writes are attached to its result, `view` renders PDF pages (with their text) and TIFF/BMP, and a PDF given to `read` is rendered. Uses the bundled `mupdf` (WebAssembly; nothing downloaded at run time). SVG, EPS/PS, HEIC and PSD go through a command-line converter first (rsvg-convert, Inkscape, ImageMagick, Ghostscript, epstopdf; sips and qlmanage on macOS) when the machine has one |
| `agent/extensions/install-notes.ts` | when the agent installs something (pip, pixi, docker pull, brew), adds what, where it lives and how to remove it to that command's result for the report, and logs it in `agent/installs.log` |
| `agent/extensions/workflow-model-scope.ts` | keeps Dynamic Workflows agents on ELM models |
| `agent/extensions/subagent/config.json` | fan-out budget: 8 concurrent, 64 per run |
| `agent/bin/pi` | symlink to the launcher, so sub-agent children find `pi` whatever PATH looks like |
| `agent/pixi/` | pixi's global tools, environments and cache (`PIXI_HOME`), when the agent has used it |
| `agent/python/` | with `--with-python`: the agent's Python - uv-managed CPython, `env/` (the venv on PATH), uv's cache |
| `agent/helpers/` | the computer-use helper, created on first use in a `pi --remote` session |
| `agent/web-search.json` | DuckDuckGo then Exa; `unpdf` for PDFs |
| `agent/install-options` | the options this install was made with, repeated by later runs |
| `agent/installed-versions.json` | the exact pi and package versions installed, written after the checks pass |

`agent/` is generated. Put durable changes in `templates/`, commit them, and run
`pi update` on each host so the validated source reaches it.

### 4. pi packages

pi resolves `npm:<name>` from `agent/npm/node_modules`. Bootstrap installs
`templates/packages.json` with `npm install --ignore-scripts` in a staging
directory, at the versions in `config/versions.json`, and swaps the tree into
place once every listed package is present. No package install script runs.

The set is sixteen packages (computer use loads only with `pi --remote`); `templates/packages.json` is the list. The ones
that shape the agent most:

| Package | |
|---|---|
| `pi-subagents` | sub-agent fan-out (`subagent`, `bg_wait`, `subagent_supervisor`) |
| `pi-hashline-edit-pro` | anchor-based editing: its own `read` and `grep` (with 5-letter line anchors), `replace`, `replace_match`, `insert` and `undo_last_change`. pi's built-in `edit` is turned off |
| `pi-web-access` | web search and fetch — off by default, see `pi --remote` above |
| `pi-python` | a persistent Python interpreter as a tool (`python`): cells run in one long-lived process, so data stays loaded between steps. Project `.venv` first, else `python3`; figures it saves are shown to the model like any others |
| `@xl0/pi-lovely-notebook` | `.ipynb` editing cell by cell (`notebook_summary`, `notebook_edit_cell`, `notebook_insert`, ...) without breaking ids or outputs; `notebook_read_cell_output` shows a cell's plots as images |

> pi packages run with full system access. Review before adding more.

`pi install` and `pi remove` are refused by the launcher, with a message
saying why: every bootstrap and `pi update` rebuilds the set from
`templates/`, so a package added that way would be removed again. Add one in
`templates/packages.json` and `templates/settings.json` (CONTRIBUTING.md), or
try a local extension for one session with
`PI_ELM_UNLOCK=1 pi -e /path/to/extension.ts` (plain `-e` is refused; LOCKDOWN.md).

**How sub-agent children find pi.** `pi-subagents` spawns each child by resolving
the pi CLI from `process.argv[1]`, then from package resolution, and if both fail
it falls back to `{ command: "pi" }` — a bare PATH lookup. When this install's
command was still called `elm-pi` there was no `pi` on PATH at all, so on hosts
where the first two routes failed that fallback found nothing and sub-agents
would not start.

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

Run it again any time: `./configure.sh`.

**Not `./configure.sh llama`.** This install deliberately exposes exactly one
Llama, `elm-shim/meta-llama/Llama-3.3-70B-Instruct`, which reaches tool calling
through the local shim. ELM's own endpoint for that model was started without a
tool-call parser and returns 400 to any request carrying tools, so a second
`elm/meta-llama/...` entry is only ever picked by mistake from `/model`. Running
`configure.sh llama` inserts one; delete it from `agent/models.json` if you do.

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
elm       Qwen/Qwen3.5-397B-A17B-FP8         262.1K   32.8K    yes       yes
elm-shim  meta-llama/Llama-3.3-70B-Instruct  128K     8.2K     no        no
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
auth_header=$(mktemp)
trap 'rm -f "$auth_header"' EXIT
chmod 600 "$auth_header"
printf 'Authorization: Bearer %s\n' "$ELM_API_KEY" > "$auth_header"
curl -fsS -H "@$auth_header" -H "Content-Type: application/json" \
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
| `npm view <pkg> version` for every package in `settings.json` | after the prompt appears | one npm process per package, concurrently with the TypeScript transpile below |
| asks `pi.dev` for the latest pi version, and reports the install | after the prompt appears | one request each |
| refreshes the remote model catalogue | after the prompt appears | one request, useless here — the ELM catalogue is `agent/models.json` |

Only the first one blocks, and it only blocks once, because pi keeps the binaries
it downloads. There is a second first-launch cost behind it — the TypeScript
transpile, below — but this is the one that holds the prompt back. The fix is to
have the binaries there already:

Downloads are cached per user, keyed `tool/version/asset`, under
`~/.cache/elm-pi/tools` (`ELM_PI_TOOL_CACHE` moves it). A fresh install on a
machine that has done this before extracts what is already on disk rather than
fetching ~105 MB again, while still getting its own binaries in `agent/bin` —
the cache saves the download, not the ownership. Cache hits are checksummed on
every reuse exactly like a fresh download, so a corrupted or tampered entry
fails the install rather than being installed; `--force` bypasses the cache and
re-fetches.

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
| `uv` | Python interpreters, environments and packages | builds the agent's Python, below, and installs into it |
| `mlr` | Miller: reshape, sort, join and summarise CSV, TSV and JSON | data files too big to read into the context |
| `pixi` | conda-forge packages without sudo - GDAL, HDF5, ROOT, Ghostscript, ffmpeg, compilers | `pixi exec --spec <pkg> <cmd>` runs one without installing it; `pixi global install` keeps it in `agent/pixi` |
| `resvg` | SVG to PNG with no system libraries | how the agent sees an SVG figure on any host (64-bit ARM Linux has no 0.48 build and falls back to the system's converters) |

All ten are a single static binary from the project's own GitHub release,
pinned and sha256-checked, installed the same way and deleted the same way.
`ELM_PI_TOOLS=fd,rg,jq` installs a subset: `shellcheck` and `ast-grep` are 35 MB
and 51 MB, against ~23 MB for the other four.

### Software the machine does not have

The agent works through it in order, preferring whatever changes least (the
`installing-software` skill). It checks what is already installed, including
environment modules on a cluster, and searches for an existing package before
writing one: `pypi-search` (with `--with-pypi-index`), `conda-search` (conda-forge
package names with their summaries, through prefix.dev's public API),
`pixi search`, `docker search`. Then the isolated options - a Python package
into its own environment; **pixi** for anything on conda-forge, run once with
`pixi exec` or kept with `pixi global install`, all under `agent/pixi`; a
container for anything large - and then **Homebrew**, where the
machine has it. Each `brew install`, upgrade or removal asks you first, and,
once approved, runs past the egress proxy (through a campus proxy if there is
one) and is logged in `agent/egress.log`: a formula downloads from wherever its
source lives - on a Mac without a bottle for it, the project's own site - which
no allowlist can name. Casks, third-party taps and formula files are refused.
**apt, dnf, yum, zypper, pacman and apk** are refused outright: the agent tells
you the exact command for your distribution and what it is for. Whatever it
installs, it says beforehand what and why, and its report lists where each
thing lives and how to remove it.

### The agent's Python

Opt-in: `pi setup --python`, or `--with-python` to the installer. Bootstrap
then builds `agent/python`: a uv-managed CPython
(`python.version` in `config/elm-pi.json`), a venv with pip, and the packages in
`python.packages` - numpy, scipy, pandas, matplotlib, openpyxl, xlsxwriter,
pyarrow, h5py, uproot, iminuit, sympy, jupytext, nbformat, nbconvert and
ipykernel. The launcher puts it on `PATH` after `agent/bin`, so `python3` and
`pip` in the agent's shell are this environment - unless pi was started from an
active venv or a conda env other than `base`, which then stays first. The egress
proxy lets PyPI through, so the agent can `pip install` what a task needs into
it in any session. Re-runs keep what it installed; the configured list is
upgraded by `--update` and reinstalled by `--force`. The choice is recorded,
so `pi update` keeps it; `pi setup --no-python` removes `agent/python`, and
with it whatever the agent installed there. An install without it gives the
agent the `python3` on PATH, which it does not install into. (An install that
built `agent/python` before this was opt-in keeps it.)

PyPI no longer has a search API (`pip search` fails, and its search page is a
JavaScript challenge), so finding a package for a job needs the web.
`--with-pypi-index` builds one into the install instead: `agent/pypi-index.db`,
an SQLite full-text index of every package's name, summary, keywords and
classifiers (682,448 packages), and `pypi-search` to query it, ranked by match
and then by downloads. It is built from a published snapshot of PyPI's metadata
(`pypiIndex` in `config/elm-pi.json`, pinned to a revision and checked file by
file against its sha256): a 1 GB download that is deleted after a one-minute
build, and fetched again only when the pinned revision changes. A snapshot is
months old by nature, so the agent confirms versions with `pip index versions`.

### Containers

Software that pip cannot supply - a full TeX Live, pandoc - the agent runs in
Docker or Podman, if the machine has one running (Docker Desktop or a Podman
machine on macOS; either on Linux). Installing the engine is yours to do; elm-pi
only governs how the agent uses it. Images can be pulled, and every container
runs with `--network=none` - the permission gate refuses a `run` or `create`
without it, because a container's traffic does not pass through the egress
proxy. `push`, `login` and remote engines are refused, `build` and `compose`
ask. The `containers` skill has the commands and the images (for LaTeX:
`texlive/texlive:latest-medium`, or `latest` for everything); LOCKDOWN.md has
the reasoning.

`fd` and `rg` are also the two pi will otherwise download for itself, so they
are the two that must be there before the first launch. The others only need to
exist by the time the model types them.
- **The launcher sets `PI_OFFLINE=1`**, pi's own `--offline`, which disables the
  remaining three. It covers startup network operations only: ELM requests, web
  search and anything you type are untouched. `PI_ELM_STARTUP_CHECKS=1 pi`
  restores pi's default behaviour for a run.

Updates then happen when you ask for them, which is what `pi update` is for.

### Startup time: where it goes, and how to cut it

`pi` itself starts in well under a second. The npm package set is what you wait
for: they ship **raw TypeScript**, so every launch transpiles and imports them from
several hundred files. Measured with `PI_TIMING=1` and `/usr/bin/time`, reporting
CPU time (user+sys) because that is the number that does not move with machine load
— taken at load ~8 on 12 threads, where wall ≈ CPU. **These figures are
historical:** they were taken when the set was three packages (`pi-subagents`,
`pi-hashline-edit-pro`, `pi-web-access`). It is now thirteen and has not been
re-measured, so read them as the shape of the cost rather than today's figures.

| Configuration | CPU per launch |
|---|---|
| pi + local extensions only (what `--fast` loads) | **1.4s** |
| \+ `pi-subagents`, `pi-hashline-edit-pro` | 3.0s |
| \+ `pi-web-access` | 3.2s |

So: `pi-subagents` + `pi-hashline-edit-pro` ~1.6s,
`pi-web-access` ~0.2s, pi and the local extensions ~1.4s.

`@tmustier/pi-ralph-wiggum` adds `ralph_start` and `ralph_done`, and a `/ralph`
command: a Ralph Wiggum loop that works a task across **fresh sessions** rather
than one growing context. It costs 0.1s of startup, measured at 6.18s against
6.08s with it removed.

It is worth knowing when it beats an ordinary long session, since the two look
similar from outside. One session accumulates context, which is why
`pi-auto-compact` is here. Ralph restarts each iteration, so context rot never
happens and state lives in the repo and `.ralph/<name>.md` instead. Long
verifiable grinds — make the suite pass, work through a backlog — suit Ralph;
work where the thread of reasoning matters wants one session.

Its completion gate is the part that makes it safe to leave alone: before
emitting `COMPLETE` it must record a final verification command that a separate
monitor can rerun in a fresh shell from the same worktree, and an item whose
test cannot be rerun externally must be marked blocked rather than complete.
That matters here, where a Llama child will report success having changed
nothing.

`@pify/btw` adds a side thread: `/btw <question>` asks a **read-only**,
codebase-aware agent while the main session keeps its place, and the exchange
stays out of the main context unless `--save` is passed. `/btw:new` starts a
fresh thread, `/btw:tangent` asks without the main session's context when you
want an uncoloured read, and `/btw:model` and `/btw:thinking` set what answers
it. Measured at 5.23s of startup against 5.29s without — free, inside the noise.

It earns its place here for two reasons. Read-only means it is safe to use
mid-run, including during an unattended loop, with no chance of a second writer
touching the tree. And context is the scarce resource on this deployment —
`pi-auto-compact` exists because of it — so a channel that answers a question
without spending any is worth more here than the convenience.

`pi-next-prompt` suggests your next prompt, the way Claude Code does: when a
reply finishes, the likely follow-up appears in grey in the empty editor. `Tab`
or `→` takes it, typing hides it, `Esc` dismisses it until the next reply. It
asks the session's own model - ELM, nothing else, no key or provider of its
own - by resending the request pi just sent plus one short instruction, so the
prompt cache covers almost all of it. It is still one extra Qwen request per
finished reply, charged to the allocation like any other, and the suggestion
arrives a few seconds after the reply. It runs only in the interactive TUI:
`pi -p`, sub-agents and workflow agents never trigger it. One file, no
dependencies; to drop it, remove it from `templates/settings.json` and
`templates/packages.json` and re-run `./bootstrap.sh`.

**No footer extension is loaded.** `pi-powerline-footer` was dropped for
`pi-zentui`, and `pi-zentui` was then dropped as well: it used a captured
extension context across the session replacement `pi-dynamic-workflows` performed
during evaluation, so every workflow run logged `This extension ctx is stale after session
replacement or reload` against it. The run completed anyway, and an ordinary
sub-agent fork never triggered it, but a footer is not worth an error on every
workflow. pi's own status line remains.

Either is easy to put back. `pi-powerline-footer` cost nothing measurable — 3.48s
against 3.55s without it, inside the run-to-run variance — but it carries one
trap: setting `cost.currency` to anything but USD turns on a background FX-rate
fetch from `cdn.jsdelivr.net`, which the egress proxy refuses and logs, and which
tells you nothing here because prices are zero in `agent/models.json`.

`pi-zentui` costs processes rather than milliseconds, which is worth knowing if it
is ever reinstated: its statusline shells out to `git` (`rev-parse`,
`status --porcelain=2`, `stash list`, `describe`) and runs `--version` probes to
label the toolchain. All read-only and all through `execFile` with an argument
array rather than a shell — but they run inside the extension, so they do not pass
the permission gate that the agent's own `bash` tool does. Nothing in it reaches
the network.

**Three levers, in order of payoff:**

1. **`pi --fast`** for one-shot work. Loads only local extensions — the policy
   set (the ELM-only guard, protected paths, pinned instructions and the
   permission gate), plus `todo` and the skill router — and keeps pi's built-in
   `edit` tool. No sub-agents, web search or anchor editing. The policy set is
   the same one loaded when you pass `--no-extensions`/`-ne` yourself, and a
   missing policy file stops the launch rather than running without it.
   Measured on the three-package set:

   | | wall | CPU |
   |---|---|---|
   | `pi -p "Reply with exactly: OK"` | 4.68-5.07s | 4.18-4.53s |
   | `pi --fast -p "..."` | **1.43-1.51s** | **1.13-1.20s** |
   | `pi --fast --llama -p "..."` | 1.65-2.33s | 1.29-1.33s |

   End to end on a real edit task (read `calc.py`, fix the bug, write it back):
   **8.01s → 3.49s**, both producing the correct edit.

2. **`./bootstrap.sh --no-packages`** drops the npm set entirely rather than
   skipping it per run, for an install that only ever answers one-shot
   questions. (`pi-hermes-memory` used to be the single biggest item here, and
   `--no-memory` existed to drop it; both are gone.)

3. **Machine load.** Wall time is CPU time multiplied by whatever else the machine
   is doing. The same launch measured 4.7s wall at load 8 and 32-47s wall at load
   350 while CPU barely moved. If pi feels slow, check `uptime` before changing
   any config. If it is slow on an *idle* machine, try excluding the install
   directory from endpoint-protection real-time scanning: 589 npm packages of
   small files is the profile on-open scanning punishes hardest. (Plausible, not
   measured — toggling Defender needs admin rights.)

### The transpile cache: 21s cold, 3.3s warm

The packages are transpiled by jiti, which caches the result in `$TMPDIR/jiti`
and reuses it on every later launch. Measured here with the package set of the
time (three packages) loaded, CPU time, by pointing `TMPDIR` at an empty
directory:

| | CPU |
|---|---|
| cold cache — transpiling ~400 modules | **21.4s** |
| warm cache | **3.3s** |

That is the difference between "the first launch took twenty seconds" and "pi
starts in about three". The cache is real and it works; what it is not is
permanent. It is cold after an install, after a tmp cleaner sweeps it, after a
package update changes the sources, and on the next login node, each with its
own `/tmp`.

So the cost is now paid where waiting is expected rather than where it is not:

- `bootstrap.sh` fills the cache at the end of the install, and says so while
  it does it. `scripts/check-extensions.mjs` loads every extension with pi's
  own resource loader, as a session does, which fills the cache and is also the
  load check: an extension that fails to load gets the packages reinstalled
  once, then stops the install. It needs no ELM key.
- `pi update` fills it again after updating the packages, since new sources
  mean a cold cache.
- `ELM_PI_OWN_TMP=1` moves `TMPDIR` inside the install, so the cache survives
  tmp cleaners and follows a shared home directory between machines. Off by
  default: it moves `TMPDIR` for everything pi runs, the agent's own `bash`
  tool included, so a model that unpacks something large spends home-directory
  quota rather than scratch space. Worth setting on a multi-node estate with an
  aggressive `/tmp`, not worth it on a laptop.

Per-package cost, re-measured warm on the three-package set (`pi
--list-models`, CPU, same machine): pi and the local extensions 0.84s,
`pi-subagents` +0.65s, `pi-hashline-edit-pro` +0.23s, `pi-web-access` +0.16s.
`--fast` remains the single biggest saving available, and skips every package.

**Three things that do not help**, all measured rather than assumed:

- `NODE_COMPILE_CACHE`: 6.5s → 6.4s CPU, and 3.46s → 3.45s on the re-measure.
  V8's bytecode cache covers modules Node itself loads; jiti evaluates the
  packages' modules itself, so they are never offered to it.
- V8 heap tuning (`--max-semi-space-size=32` and `=64`): 3.46s → 3.47s and
  3.39s. Noise.
- `PI_OFFLINE=1`: no difference to `pi -p` (4.2-4.8s wall either way). Print mode
  runs none of the startup checks in the first place, and the model catalogue is
  refreshed when you open the `/model` picker, not on this path. It is set by
  default anyway, for the interactive launch it does change — see above.

Bundling the packages with esbuild was considered and rejected: `pi-subagents`
spawns child processes by path, so bundling changes third-party semantics for a
win the `--fast` path already delivers. It was a stronger objection when
`pi-hermes-memory` was installed and loaded a native SQLite binding; that
package is gone, and with it the only native dependency in the set.

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
re-emitting it, so Llama also loses streaming. That buffering is also why Llama
replies are capped at 8192 tokens (`maxTokens`, set in `elm-shim.ts`): pi gives
up on a connection that sends nothing for 300 s and retries, and at 30-47 tok/s
a 16384-token reply takes 350-550 s, so long replies timed out and were
generated again. `agent/AGENTS.md` tells the session to send sub-agents to
`qwen`, and the `delegate` agent is described as Llama, for numbered steps
only.

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
prompt length, is what to optimise**. Nothing needs enabling. The skill router
is built to keep this: it adds skills as a message after the request rather
than changing the system prompt, which would change the first bytes of every
request and lose the cache (see [below](#skills-and-the-skill-router)).

Compaction (`pi-auto-compact`) starts at **70%** of the context window, an
installer-owned setting (`autoCompactThreshold`; it was 50%). Each compaction
re-sends the history uncached and the next request starts cold, so compacting
early costs more than the context it frees. Standing instructions recorded
with `pin_instruction` (`pinned-instructions.ts`) are put back into the system
prompt on every run, so compaction cannot summarise them away.

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

## Dynamic Workflows, and the one control it lacks

`@quintinshaw/pi-dynamic-workflows` is **installed and loaded**, which is what
provides `/ultracode`, `/deep-research`, `/adversarial-review`, `/code-review`,
`/codebase-audit` and the `/workflows` TUI.

It is enabled knowingly, not safely. Its model-policy hook can be overridden by
an individual workflow script, which is weaker than the strict ELM-only promise
the rest of this install keeps; the package was held out of the default set for
exactly that reason, and was then enabled deliberately. What remains true is
that `agent/extensions/workflow-model-scope.ts` is a **required** extension:
bootstrap refuses to finish without it, and a test asserts it stays in
`requiredExtensions`. The guard is therefore always present — it is simply not
unoverrideable.

What it has no equivalent of is `modelScope`. pi-subagents takes
`enforce: true, strict: true, allow: ["elm/*", "elm-shim/*", "inherit"]` from
settings and no child can leave those providers. Dynamic Workflows can route through
tiers in `agent/workflows/model-tiers.json`, whose documented examples are
`openai-codex/gpt-5.4-mini` and `openai-codex/gpt-5.5`. The installer still deploys
`agent/extensions/workflow-model-scope.ts` as the guard, and it refuses models
outside the configured ELM providers.

Measured on this install:

- A workflow agent pinned to `openai-codex/gpt-5.4` is refused before any session
  is created. The run store records `MODEL_SPAWN_REJECTED` and the policy's own
  text, "This install is restricted to university-hosted models", against a total
  spend of about 3 tokens.
- With `inheritMainModel: true` in `agent/workflows/settings.json`, untagged
  agents inherit the session model. A two-agent workflow recorded
  `elm/Qwen/Qwen3.5-397B-A17B-FP8` for every model reference in its run store and
  nothing else.
- It does **not** turn worktree isolation on by itself. A two-agent workflow that
  edited `m.py` and created `README.md` wrote both into the working directory, and
  `git worktree list` showed only the main tree.

Two things to know before relying on it.

**The policy is weaker than the one it stands in for.** The package documents
per-run `AgentRunOptions.preSpawnModel` and instance
`WorkflowAgentOptions.preSpawnModel` as outranking the process resolver, so a
workflow script that sets its own wins. `strict` scope in pi-subagents has no such
hole.

**It replaces the session, which breaks extensions that hold on to a context.**
`pi-zentui` was removed over this. A Dynamic Workflows run produced `This extension
ctx is stale after session replacement or reload` against
`pi-zentui/extensions/zentui/index.ts` on every run; the run completed, and an
ordinary `qwen` sub-agent fork never triggered it, so it is specific to the
replacement Dynamic Workflows performs. pi's own message names the contract an
extension has to keep — do not use a captured `pi` or command context after
`newSession`, `fork`, `switchSession` or `reload`; move post-replacement work into
`withSession` — so the defect is the extension's, and Dynamic Workflows is only
what exposes it. Worth checking against any extension added later that draws
persistent UI.

And one observation about the output rather than the plumbing: in that two-agent
run, one agent changed `v()` to return 2 while the other wrote a README saying it
returns 1, because it had read the file first. Individually correct, collectively
wrong, and nothing in the workflow caught it. That is the failure a cross-checking
sweep exists for, which is the argument for keeping the standards even when the
orchestration comes from somewhere else.

## Skills and the skill router

`agent/skills` holds thirteen skills from `templates/skills`: physics methods
(fitting, statistics, uncertainties, histograms, derivations, numerical
methods, constants, documents), scientific Python and C++, and the sub-agent
and workflow orchestration rules. pi lists each skill's name and description
and leaves loading it to the model, which measured unreliable here: asked for a
half-life, the model never read `data-fitting` and used the method that skill
forbids.

So `skill-router.ts` matches each request you type against a keyword table and
adds the best two matching skills in full, and names up to two more by path.
They go in as a message **after your request**, shown as a dim
`skills: ...` line (expand it for the paths) and stored in the session — not
as a hidden section of the system prompt, which changed the first bytes of the
request and cost ELM's prefix cache the whole history each time. Each skill is
added at most once per session; it comes back only after a compaction has
summarised it away. The keywords are deliberately narrow: ordinary software
requests ("add a regression test", "make the magic number a named constant")
add nothing.
`tests/test_skill_router.py` runs both kinds of request through it.

Sub-agents are routed by their task alone, with the agent's own instructions
cut out first. Runs not started by a prompt you typed — auto-compaction,
loop drivers, sub-agent completion notices — add nothing. The first
`subagent` or `workflow` call of a session is refused until the orchestration
skill it needs has been read, with the path to read.

## Sessions, memory and artefacts

`sessionDir: ".pi/sessions"` is **relative**, so it resolves against the working
directory and each project keeps its own history. This also fixed an accumulation
problem: sessions had reached 1.9 GB across 699 files in one central directory.

Transcripts contain whatever the agent read, which may include secrets, so in
a git work tree the launcher writes `.pi/.gitignore` containing `*`: the whole
directory is invisible to git, and `git add -A` cannot stage it. Nothing needs
adding to the project's own `.gitignore`.

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
| `pi: the folder this shell is in has been deleted` | The shell is still in a folder that was removed (by `rm -rf`, a branch switch or a rebuild), even if a new one now exists at the same path. `cd "$PWD"` re-enters the new one; otherwise `cd` somewhere that exists. There is no override. |
| `pi: not starting in /Users/you - your home folder` | The folder pi starts in is the project, and nothing inside it is asked about, so home, `~/Documents`, `/` and credential folders such as `~/.ssh` are refused. `cd` to a project folder (or `mkdir ~/scratch` for a quick question). `PI_FORCE=1` starts there anyway. The list is `untrustedFolders` in `config/elm-pi.json`. |
| On a remote host, `/copy` or a selection never reaches your own clipboard | The launcher sends every copy through the terminal as OSC 52, and the terminal must accept it: iTerm2 needs *Settings > General > Selection > Applications in terminal may access clipboard*, tmux needs `set -g set-clipboard on`, and Terminal.app does not support it at all. Allow writes only, never reads. Copies over ~75 KB do not fit in OSC 52. To paste, use the terminal's own paste (Cmd+V): pi's Ctrl+V reads the clipboard of the machine pi runs on, which over SSH is the remote one. `PI_CLIPBOARD_OSC52=0` turns the OSC 52 copy off. |
| `env: node: No such file or directory` | Launcher bypassed, or `.node/` missing — re-run `./bootstrap.sh`. |
| Llama sub-agents unavailable | The shim could not start (pi shows an `elm-shim:` warning), usually because port 8811 is taken. `ELM_SHIM_PORT` moves it. |
| Sub-agents fail to start, or something reports `pi: command not found` | pi-subagents falls back to a bare `pi` on PATH when it cannot resolve the CLI. Fixed three ways — the launcher exports `PI_SUBAGENT_PI_BINARY`, `bootstrap.sh` creates `agent/bin/pi`, and the installer links `~/.local/bin/pi`. Re-run `./bootstrap.sh` if `agent/bin/pi` is missing. |
| `pi: command not found` in a new shell | The installer adds `~/.local/bin` to your shell profile; open a new shell, or `export PATH="$HOME/.local/bin:$PATH"` for the current one. |
| `pi` runs something other than this install | Another `pi` is earlier on PATH — the installer warns when it sees one. `command -v pi` shows which wins; either remove it or put `~/.local/bin` ahead of it. |
| Want vanilla pi, to tell wrapper bugs from pi bugs | `~/.local/share/elm-pi/pi.orig`. It is the unwrapped CLI with pi's own `~/.pi` config, so it starts with no models until you configure one. |
| Startup hangs with no output at all | Seen in clusters, cause unknown; ruled out config, extensions, the launcher, ELM itself and leftover processes. Wait and retry rather than changing config — a change made during a bad window will look causal and is not. |
