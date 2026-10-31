# ELM-only: what is blocked, how, and what it does not do

## Why

Staff are allocated **$500 at industry token rates**. Against a commercial coding
agent that is a few weeks of real use, after which work stops until someone finds
more budget. The university's ELM gateway bills a departmental allocation at a
fraction of that for a 397B model on its own GPUs, and it is the thing this
install exists to use.

Leaving 1,357 commercial models one `/model` keypress away produces exactly two
outcomes: accidental spend, and support questions this team cannot answer. So
they are removed.

**This is a cost-control default, not a security control.** It shapes what *this
install* offers. It cannot stop anyone installing their own agent, and it is not
trying to. If commercial models are genuinely needed for a piece of work, the
answer is a funded subscription — the escape hatch below is deliberately easy.

## Six layers

The layers are checked by bootstrap and the repository test suite. They are
defence in depth; features whose third-party hooks cannot enforce the policy are
disabled by default.

### 1. Credential scrub (`pi`)

The launcher `unset`s every commercial LLM credential before exec'ing pi, so a key
in `~/.zshrc` or a CI environment cannot quietly re-enable a paid provider. Your
shell is untouched — only pi's own environment.

The list is `providerCredentials` in `config/elm-pi.json`, kept in step with
the variables pi-ai 1.4 itself reads; a test compares the two when pi is
installed in the checkout. `pi --help` runs with the same scrub.

Deliberately **not** scrubbed: `AWS_*` (except `AWS_BEARER_TOKEN_BEDROCK`) and
`GITHUB_TOKEN` (`COPILOT_GITHUB_TOKEN` is). The agent's bash tool needs them for
real work, and layer 3 already removes `amazon-bedrock` and `github-copilot`
from the catalogue.

### 2. Default-deny argument guard (`pi`)

The parser allows only providers declared in `config/elm-pi.json`, compares
case-insensitively like pi itself, honours repeated-option and `--` semantics,
and refuses everything else with exit code 2:

```
pi --provider anthropic ...
pi --model anthropic/claude-opus-5 ...
pi --models "openai/*,elm/*" ...
pi --api-key sk-... ...
```

`--api-key` is refused outright: its only purpose is to hand a session a
credential the scrub just removed. The guard runs before the launcher looks for
the ELM key, so an install with no key yet refuses these too.

`-e`/`--extension` is refused too, whatever it names. An extension runs inside
pi with this install's access and brings its own network code, and the ones
that exist for pi include exactly what this install is meant not to do: pi's
own `ssh.ts` example sends `read`, `write`, `edit` and `bash` to another
machine over SSH, which the proxy never sees, and published bridges relay
whole sessions through Telegram or serve them to the local network. The
reviewed extensions load without it, and so do the launcher's own `-e`
arguments (`--fast`, `-ne`). `PI_ELM_UNLOCK=1` lifts this with the rest of the
guard; project-local extensions in a repository's `.pi/` stay off unless
`/trust` allows them (`defaultProjectTrust: never`).

### 3. Catalogue strip (`agent/extensions/elm-only.ts`)

The load-bearing one. pi 1.4 ships 42 built-in providers. Registering a provider with
an empty `models` array **replaces** its catalogue, so the extension strips every
non-allowed provider to zero models — once at extension load (covers
`--list-models` and other pre-session paths), then again at session start (covers
providers a pi upgrade or another extension adds).

It loads in every mode. `--fast`, and `--no-extensions`/`-ne` given by the
caller, turn off pi's own extension discovery, so the launcher loads the policy
set explicitly in both cases: this extension, `protected-paths.ts`,
`pinned-instructions.ts` and the permission gate. If one of the three local
files is missing, or the gate package is installed without its entry point,
pi does not start.

Measured on this install: **1,357 built-in models → the ELM catalogue only.**
The local Llama shim appears as `elm-shim` when its loopback service is
available; it is still backed by an ELM-hosted model.

```
provider  model                              context  max-out  thinking  images
elm       Qwen/Qwen3.5-397B-A17B-FP8         262.1K   32.8K    yes       yes
elm-shim  meta-llama/Llama-3.3-70B-Instruct  128K     8.2K     no        no
```

This is what makes `/login` pointless: a credential with no catalogue entry is
unreachable. It is also why layer 3 catches what layers 1 and 2 cannot — with a
valid key present *and* both launcher guards bypassed,
`pi --model anthropic/claude-haiku-4-5` fails with `Model not found` and no
request leaves the machine.

### 3b. Read-only `agent/auth.json`

`bootstrap.sh` sets mode 400 on it, so `/login` cannot store a credential it
obtains. Verified: normal startup and ELM use are unaffected. Not verified: how
gracefully the `/login` flow reports the failed write. Install with
`./bootstrap.sh --no-auth-lock`, or `chmod 600 agent/auth.json`, to lift it.

### 4. `/share` and `/bug` removed from the release (`patch-pi.py`)

These two are a different problem from the rest of this document — not spend,
but data leaving Edinburgh — and they are the only part of this install where
patching a third-party release is the proportionate answer.

| Command | Destination | Payload |
|---|---|---|
| `/share` | pi's Radius gateway, else a **GitHub gist** via the `gh` CLI | the session, exported |
| `/bug` | `https://radius.pi.dev/v1/bug-reports` | `report.json`, `diagnostics.json` and **`session.jsonl` — the entire transcript** |

A pi session holds every file the agent read, every command output and anything
pasted in. One keystroke publishes it. `/bug` is especially easy to reach for:
when pi crashes it prints *"Run /bug to report it; the crash details are
attached automatically."*

**pi offers no way to turn a built-in command off.** There is no
`disabledCommands` setting, and an extension cannot shadow one — the command
merge filters extension commands against the built-in names, so the built-in
always wins. So `patch-pi.py` edits the installed bundle: two dispatcher
branches refuse with a message, two entries leave the autocomplete list, and
the three upload functions (`uploadBugReport`, `tryShareViaRadius`,
`shareViaGist`) throw, which also covers any other route that reaches them.

`bootstrap.sh` applies it on every install and every update, and **fails the
install if an anchor no longer matches** rather than leaving an unpatched pi
behind a warning. A pi release that moves this code will therefore stop
`pi update` before it touches the extension packages, which is the intended
behaviour: you find out from a failed update, not from a published transcript.
Re-derive the anchors in `patch-pi.py` when that happens, or install with
`./bootstrap.sh --no-patch` if you want the commands back.

The launcher also sets `PI_RADIUS_GATEWAY=http://127.0.0.1:1`. That is a
supported pi environment variable rather than a patch, so it survives someone
running `npm install` by hand, and it makes both radius upload routes fail to
connect. It costs nothing here because the ELM-only policy leaves radius with
an empty model catalogue.

### 5. Web tools off by default (`pi`)

`pi-web-access` registers five tools — `web_search`, `source_check`,
`fetch_content`, `get_search_content`, and `web_enable`, which switches the
others on. Between them they send the model's
queries out, and the model composes those from the code in front of it, so a
function name or an error string travels with them. They also fetch arbitrary
pages and then treat what comes back as input, which is the one leak path that
requires nobody to do anything wrong: a fetched page can instruct the agent to
put data in a URL.

The launcher therefore passes `--exclude-tools` for all five. The package stays
installed, so this is a per-run decision rather than a per-install one:

    PI_ELM_WEB=1 pi ...     web search and fetching, for that run
    pi --remote ...         the same, and opens the proxy so they can connect

`PI_ELM_WEB=1` on its own turns the tools on while layer 6 still allows only
the gateway, so every search refuses and lands in the log. That is the honest
combination for testing the block; `--remote` is the one that works.

pi keeps only the last `--exclude-tools` it is given, so a caller's own
`--exclude-tools` (or `-xt`) is merged into the launcher's list rather than
replacing it. An explicit `--tools` allowlist is left alone: naming a web tool
there is asking for it. The names are `pi-web-access` defaults and can be
renamed in `agent/web-search.json`; rename them there and `webTools` in
`config/elm-pi.json` needs the same edit, because pi silently ignores an
exclusion for a tool that does not exist. Bootstrap compares the two lists on
every run and warns if the package registers a tool the list does not name.

Sub-agents have a second, independent route out: `pi-subagents` can export a
run to HTML and publish it with `gh gist create`. It is off unless
`agent/extensions/subagent/config.json` sets `"share": true`, and that file now
says `"share": false` explicitly rather than relying on the default.

**Computer use is `--remote` only.** `@injaneity/pi-computer-use` lets the
agent see the screen and drive apps through the macOS accessibility API
(AT-SPI on Linux), browsers included - and a logged-in browser goes anywhere,
past the proxy entirely. So it is installed with the other packages but is not
in `settings.json`'s list: the launcher loads it with `-e` only for a
`pi --remote` session, never for a sub-agent child. Its own setup would put a
helper app in `~/Applications` and generate a code-signing certificate in the
login keychain; the launcher points it at `agent/helpers/` instead and has it
signed ad hoc, so nothing outside the install changes. macOS asks once for
Accessibility and Screen Recording for that helper, and both can be revoked in
System Settings > Privacy & Security.

Dynamic Workflows (`@quintinshaw/pi-dynamic-workflows`) **is** loaded by the
default package set, knowingly: its global model-policy hook can be overridden
by an individual workflow script. Its guard, `workflow-model-scope.ts`, is a
required extension and refuses models outside the ELM providers, but that is
weaker than strict `pi-subagents` model scope. INSTALL.md, "Dynamic Workflows,
and the one control it lacks", has the measurements.

### Private local state

The launcher creates the selected session directory as mode 700 and tightens
existing transcript and memory files to mode 600. Install and memory directories
are mode 700; locked `auth.json` is mode 400. This matters on shared login nodes:
transcripts contain every file and command output seen by the agent.
`ELM_PI_SHARED_STATE=1` is the explicit opt-out for a deliberately group-shared
session location. It does not weaken model or network policy.

### Folders that are never a project

The folder pi starts in is the project it works on. The permission gate asks
before the agent touches anything outside it and nothing inside it, so a
session started in home has the whole home folder as its project: every
repository, document and dotfile readable and writable without a prompt, and
searches that sweep all of it. Two pieces keep that from happening by default,
both reading `untrustedFolders` in `config/elm-pi.json`:

- **The launcher refuses to start a session** in home, any folder above it,
  `/`, a container such as `~/Documents`, `~/Downloads`, `~/Library` or the
  OneDrive and iCloud roots, or anywhere inside a credential or system folder
  (`~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.pi`, `~/Library/Keychains`, `/etc`,
  `/usr`, ...). `exact` entries are the folder itself, so a project inside
  `~/Documents` or OneDrive is fine; `tree` entries cover everything beneath.
  `PI_FORCE=1` starts there anyway. `--version`, `--list-models` and
  `pi update` run anywhere, and sub-agent children are not checked: they start
  where their parent already chose.
- **`trust-guard.ts` keeps project trust off the same folders.** Trust decides
  whether a folder's own `.pi/` settings and extensions load. A saved decision
  covers everything below the folder it names, and pi's trust prompt offers
  "Trust parent folder": accepted once in `~/notes`, that would trust `~`, and
  every repository cloned anywhere in it. The guard answers "no" for a listed
  folder and does not let a saved "yes" on one pass down; a project trusted by
  its own name is unaffected. A command-line `--approve` still wins, because
  pi applies it before any extension.

Separately, the gate's `path` rules deny reading or writing credential stores
wherever the session started: `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.azure`,
`~/.config/gh` and `gcloud`, `~/.kube/config`, `~/.docker/config.json`,
`~/.netrc`, `~/.git-credentials`, `~/.npmrc`, `~/.pypirc`, the macOS keychains,
browser profiles, Mail and Messages, other agents' state (`~/.pi`,
`~/.claude`), and `.env` and key files anywhere.

### 6. Egress proxy (`proxy/egress.py`)

The layers above shape what pi *offers*. This one checks where it *goes*.

The launcher starts a small allowlisting proxy on loopback, points pi's
`HTTPS_PROXY` at it, and refuses to start if it cannot. The allowlist is the
ELM host, taken from `ELM_BASE_URL` so it cannot drift from the gateway the
shim uses, and PyPI (below). Everything else gets `403` and a line in
`agent/egress.log`, with the hostname and a timestamp, so a call that should
not be happening can be stopped at source rather than merely blocked.

**PyPI is on the list** - `pypi.org` and `files.pythonhosted.org`,
`proxyAllow` in `config/elm-pi.json` - so the agent can install Python packages
into its own environment (`agent/python`, built with uv when the install asks for it: `pi setup --python`) without
`--remote`. What that costs, said plainly: every process the agent runs can
reach those two hosts, subdomains included. Downloads are public and read-only,
and uploading needs a PyPI token (`~/.pypirc` is on the agent's denied paths),
but a request URL can still carry a little data out - a package name is text
the agent chooses - and an installed package runs its own code with this
install's access. The trade is the same one `pip` on any workstation makes. To
take it back, empty `proxyAllow.hosts` and re-run `bootstrap.sh`; the agent's
environment and the packages already in it stay usable offline.

**conda-forge is on it too**: `conda.anaconda.org` for pixi's packages, and
`api.anaconda.org` and `prefix.dev` for searching them - the same read-only
trade as PyPI, with the same caveat that a request names a package the agent
chose. pixi keeps everything in `agent/pixi`; another channel than conda-forge
asks the user, and `pixi upload`/`auth` are denied.

No certificate, no interception, no decryption: HTTPS through a proxy opens
with a plaintext `CONNECT host:443`, which is all an allowlist needs. The
payload stays encrypted end to end.

- **Fail-closed.** No proxy, no pi. The proxy runs on the Python bootstrap
  chose (the system's, or a standalone CPython it downloaded when there was no
  usable one), so an install whose interpreter has gone does not start.
- **`pi update` is the one exception**, and deliberately: updates need
  `registry.npmjs.org`, `github.com` and `nodejs.org`. The proxy is started
  *after* the update intercept, so an update never sees it, and nothing else
  does not.
- **A campus proxy already in the environment is chained to**, not routed
  around.
- Sub-agents, the Llama shim and every command the agent runs inherit the
  setting, so `curl` in the `bash` tool is filtered too.

Escape hatches, as everywhere else here:

    ELM_PI_NO_PROXY=1 pi ...          run unfiltered, for debugging
    ELM_PI_PROXY_ALLOW=host,host pi   add hosts for one run
    pi --remote ...                   open mode: no gate, but still a record

Open mode is a single `*` in the allowlist. Work that needs the web cannot be
expressed as a list of hosts — `fetch_content` exists to go where the page
points — so `--remote` splices every host through and logs each new destination
once as `OPEN`. Turning the proxy off instead would have been simpler and would
have lost the log, which on a run that may go anywhere is the only thing left.

Worth being clear about what that costs: the proxy is also the backstop that
would stop a *lifted* model policy reaching a commercial API. Under `--remote`
layers 1 to 3 are on their own for that run. They are untouched — inference
still goes to ELM — but the second line of defence is down, by design.

**This is the control that does not need updating when pi changes.**
`patch-pi.py` closed `/share` and `/bug` and will break the day upstream
refactors them. The proxy catches the *next* upload feature without anyone
noticing it was added.

**It is still not enforcement.** Proxy variables are honoured by well-behaved
clients — `curl`, `npm`, `pip`, `requests`, `git` over HTTPS — and ignored by
`git` over SSH, raw sockets, and anything that unsets them. The `bash` tool can
do all three. So the commands that do it are refused at the gate instead.
pi-permission-system's `bash` rules deny:

- SSH and what rides on it: `ssh`, `scp`, `sftp`, `rsync` to a remote
  (`host:path`, `rsync://`; a local `rsync` is fine), `sshfs`, `ssh-copy-id`,
  `autossh`, `mosh`;
- raw connections and other transfer clients: `nc`/`ncat`/`netcat`, `socat`,
  `telnet`, `ftp`, `lftp`, `rclone`;
- tunnels that open this machine to remote control: `ngrok`, `cloudflared`,
  `tailscale serve`/`funnel`/`file`.

Docker and Podman get the same treatment, because a container's network does
not pass through the proxy (Docker's engine, and Podman on macOS, live in their
own daemon or VM). The agent may pull images and run them, but every
`run`/`create` must carry `--network=none`; the rest are denied with that
reason. `push`, `login` and a remote engine (`-H`, `--context`,
`podman --remote`/`--connection`) are denied; `build` and `compose` ask,
since a Dockerfile's `RUN` steps have an open network. The registries are on
the proxy's list for a Podman that pulls through it. A bind mount bypasses the
agent's path protections, so the `containers` skill mounts only the project
folder - a rule of practice, not one the gate can check. The same caveats as
below apply: `--network=none` is matched as text anywhere in the command, and
a `DOCKER_HOST` set in the environment is not seen.

Software installs follow the same line. `brew install`, `upgrade`, `fetch` and
the rest ask the user every time; once approved, `agent/bin/brew` runs that
one command without the egress proxy, because a formula downloads from wherever
its source lives, and writes it to `agent/egress.log` as `UNPROXIED`. The
approval is the control: core formulae only - casks, third-party taps and
formula files are denied, since their own code would run unfiltered - and
calling Homebrew by its full path, past the wrapper, is denied too. Read-only
`brew info`/`list`/`deps` stay behind the proxy. apt, dnf, yum, zypper, pacman,
apk, snap, flatpak, MacPorts, `dpkg -i` and `rpm -i` are denied outright: they
need an administrator, and the agent gives the user the command instead.

Each denial tells the model why, so it stops rather than retrying around it.
The rules see through chains (`cd x && ssh ...`) and through `env`, `xargs`,
`sudo` and the like; `bash -c "ssh ..."` is not parsed inside and drops to
asking you. `git push` still asks: over HTTPS the proxy refuses it anyway, and
over SSH it is your call each time. Like everything here, these are command
names, not enforcement: a copied or renamed binary gets past them, and so do
`!` commands you type yourself, which the gate does not judge. On Linux a network namespace with no other route out
(`unshare -rn`, `bwrap`, `slirp4netns`) turns this into real enforcement;
macOS has no equivalent without root or a Network Extension, so on a managed
Mac the answer remains `pf` and an administrator.

## Verified behaviour

| Attempt | Result |
|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` set in the shell | scrubbed; catalogue remains ELM-only |
| `/model` picker, `Ctrl+P` cycling | only ELM and the local ELM shim can appear |
| `/login` with a real subscription | provider has no models; credential write is blocked |
| `pi --model anthropic/... --api-key ...` | refused by layer 2 (exit 2) |
| Same, with `PI_ELM_UNLOCK=1` and a key in the environment | `Model not found` — layer 3 holds |
| `PI_ELM_UNLOCK=1 PI_ELM_ALLOWED_PROVIDERS="elm,elm-shim,anthropic"` | Anthropic returns — the intended escape hatch |
| `pi --list-models` | ELM only |
| `/share`, `/bug` | absent from autocomplete; both refuse, and their upload paths throw |
| asking the model to list its tools | none of them web |
| the same with `PI_ELM_WEB=1` | the web tools return |
| `pi -e ./ssh.ts --ssh host` | refused by layer 2 (exit 2) |
| agent running `ssh`, `scp` or remote `rsync` in `bash` | denied by the permission gate, with the reason |
| `pi` started in `~`, `/` or `~/.ssh` | refused (exit 2); `PI_FORCE=1` overrides |
| a saved "Trust parent folder" on `~` | ignored: projects under `~` stay untrusted unless trusted by name |
| ELM request through the proxy | allowed; a real `pi -p` round trip works |
| agent running `curl https://example.com` in `bash` | refused, `exit=56`, logged as `REJECTED example.com:443 not on the allowlist` |
| `pi update` | runs unproxied, by construction — the proxy starts after the update intercept |
| `proxy/egress.py` missing | pi refuses to start (exit 1) rather than running unfiltered |

Those two tool rows were measured on an earlier package set, whose list
included a memory tool that is no longer installed; the counts are not given
here because they change with the set. From the code as it stands: editing is
`pi-hashline-edit-pro`'s `read`, `grep`, `replace`, `replace_match`, `insert`
and `undo_last_change`, with pi's own `edit` turned off (pi's `find` and `ls`
are not in its default tool set), beside `bash`, `write` and the tools the
other packages and local extensions add.

## What this does not do

- It does not stop `npm i -g` of another agent, a browser tab, or an API call from
  a script. Nothing local can.
- Removing `/share` and `/bug` removes an accident, not an intent. The `bash`
  tool can `curl` a session file anywhere, and so can the person using it.
- It does not touch the ELM key's own spend — ELM still meters it.
- Only **egress control** (firewall or proxy policy on `api.anthropic.com`,
  `api.openai.com`, ...) actually prevents commercial API use on a managed host.
  If that is the requirement, this install is the wrong layer; talk to IT.

## `pi.orig` is not a hole, but know it is there

The install ships `pi.orig`, the unwrapped CLI that `pi` hands over to. Run
directly it is vanilla pi: pi's own `~/.pi` config, no `.env`, no ELM provider
and none of the three layers above. On a fresh account that means **no models at
all** — it is a debugging tool, not a route to Claude — but someone who ran
`/login` under it would be using a commercial provider on their own credentials.

It is therefore not linked onto your PATH; only the wrapper is. The supported way
to lift the policy is below, and it keeps your key and configuration.

## Lifting it

For one run:

```bash
PI_ELM_UNLOCK=1 pi ...                                        # layers 1 and 2 off
PI_ELM_UNLOCK=1 PI_ELM_ALLOWED_PROVIDERS="elm,elm-shim,anthropic" pi ...   # + layer 3
```

Layer 6 still allows only the gateway, so a request to the provider is
refused by the proxy until its host is allowed too, for example
`ELM_PI_PROXY_ALLOW=api.anthropic.com`.

Permanently, for a host or a person with funded access, change the policy at
its source, `config/elm-pi.json`, which every layer reads (through
`agent/runtime.env`):

- add the provider to `allowedProviders` — the argument guard, `elm-only.ts`
  and `workflow-model-scope.ts` all take their allowlist from it;
- remove that provider's variables from `providerCredentials`, which is the
  list the scrub unsets;
- add `"<provider>/*"` to `subagents.modelScope.allow` in
  `templates/settings.json`, or sub-agents still refuse it;

then re-run `./bootstrap.sh --no-auth-lock` (the flag is then remembered). The
proxy allowlist has no config file: set `ELM_PI_PROXY_ALLOW` in the
environment. Be aware that bootstrap's own lockdown check ("verifying the
ELM-only policy") stops the run with "commercial providers are still visible"
if any `anthropic`, `openai` or `google` model is listed, and it sets fake
Anthropic and OpenAI keys to provoke exactly that; lifting one of those three
means changing that check in `bootstrap.sh` as well.

Note that `pi --remote` is **not** this. It lifts layers 5 and 6 — the network
ones — and leaves 1, 2 and 3 exactly where they are. Inference still goes to
ELM and nothing else becomes reachable or visible.

`PI_ELM_ALLOWED_PROVIDERS` alone does nothing: the launcher unsets it unless
`PI_ELM_UNLOCK=1` is also present, so the escape hatch is always a conscious act.

## If a pi upgrade adds providers

`builtinProviders` in `config/elm-pi.json` feeds the pre-session catalogue pass.
The argument guard is default-deny and needs no provider inventory. The
session-start pass is dynamic and catches anything the inventory misses -
providers with chat models, and providers an extension registered, including
classifier-only ones such as `typesafe` - but `--list-models` would still be
stale.

The inventory is checked rather than remembered: `tests/test_project.py` reads
the providers pi-ai itself registers (`dist/providers/all.js`) and fails if one
is missing from `builtinProviders`, or if the list names one pi no longer has.
pi 1.0.3 renamed `azure-openai-responses` to `azure` and 0.99 added `typesafe`;
the list carried the old name and missed the new one until that test existed.
After upgrading pi, `npm test` says what to change.

## pi's built-in extensions

pi 0.99 added four extensions that load by default, ahead of anything in
`agent/extensions`: `builtin:mcp`, `builtin:llama.cpp`, `builtin:codemode` and
`builtin:tool-search`. `templates/settings.json` turns two of them off, and the
installer reapplies that on every run (`extensions` is an installer-owned key):

- **`-builtin:mcp`.** An MCP server is either a command pi starts or a remote
  endpoint it calls, configured in `mcp.json` - a third route to tools and to
  the network, beside the bash tool and the npm packages, that none of the
  layers above were written for. The egress proxy reaches only programs that
  honour `HTTPS_PROXY`. Off, rather than reviewed server by server.
- **`-builtin:llama.cpp`.** It registers a provider for a local llama.cpp
  server. Local models cost the allocation nothing, but they are outside the
  ELM-only scope this install is built around, and elm-only.ts would strip the
  provider at session start anyway.

`codemode` and `tool-search` stay loaded but inactive: neither tool is offered
to the model unless `defaultTools` or `--tools` names it, and this install sets
neither. Codemode runs model-written JavaScript that calls the other tools
through `ctx.executeTool`. Whether the permission gate and `protected-paths.ts`
see those nested calls has **not** been checked here - do that before turning
codemode on.

To restore one for a single project, `+builtin:mcp` in that project's
`.pi/settings.json`; pi applies it only once the project is trusted.
