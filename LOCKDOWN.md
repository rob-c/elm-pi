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

Each is independent; each is verified by `./bootstrap.sh` on every install.

### 1. Credential scrub (`pi`)

The launcher `unset`s every commercial LLM credential before exec'ing pi, so a key
in `~/.zshrc` or a CI environment cannot quietly re-enable a paid provider. Your
shell is untouched — only pi's own environment.

Deliberately **not** scrubbed: `AWS_*` (except `AWS_BEARER_TOKEN_BEDROCK`) and
`GITHUB_TOKEN`. The agent's bash tool needs them for real work, and layer 3
already removes `amazon-bedrock` and `github-copilot` from the catalogue.

### 2. Argument guard (`pi`)

Refuses, with exit code 2:

```
pi --provider anthropic ...
pi --model anthropic/claude-opus-5 ...
pi --models "openai/*,elm/*" ...
pi --api-key sk-... ...
```

`--api-key` is refused outright: its only purpose is to hand a session a
credential the scrub just removed.

### 3. Catalogue strip (`agent/extensions/elm-only.ts`)

The load-bearing one. pi ships ~40 built-in providers. Registering a provider with
an empty `models` array **replaces** its catalogue, so the extension strips every
non-allowed provider to zero models — once at extension load (covers
`--list-models` and other pre-session paths), then again at session start (covers
providers a pi upgrade or another extension adds).

Measured on this install: **1,357 models → 3.**

```
provider  model                              context  max-out  thinking  images
elm       meta-llama/Llama-3.3-70B-Instruct  128K     16.4K    no        no
elm       Qwen/Qwen3.5-397B-A17B-FP8         262.1K   32.8K    yes       yes
elm-shim  meta-llama/Llama-3.3-70B-Instruct  128K     16.4K    no        no
```

This is what makes `/login` pointless: a credential with no catalogue entry is
unreachable. It is also why layer 3 catches what layers 1 and 2 cannot — with a
valid key present *and* both launcher guards bypassed,
`pi --model anthropic/claude-haiku-4-5` fails with `Model not found` and no
request leaves the machine.

### 3b. Read-only `agent/auth.json`

`bootstrap.sh` sets mode 444 on it, so `/login` cannot store a credential it
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

`pi-web-access` registers four tools — `web_search`, `source_check`,
`fetch_content` and `get_search_content`. Between them they send the model's
queries out, and the model composes those from the code in front of it, so a
function name or an error string travels with them. They also fetch arbitrary
pages and then treat what comes back as input, which is the one leak path that
requires nobody to do anything wrong: a fetched page can instruct the agent to
put data in a URL.

The launcher therefore passes `--exclude-tools` for all four. The package stays
installed, so this is a per-run decision rather than a per-install one:

    PI_ELM_WEB=1 pi ...     web search and fetching, for that run

If the caller passes `--tools` or `--exclude-tools` themselves, the launcher
leaves the decision alone. The four names are `pi-web-access` defaults and can
be renamed in `agent/web-search.json`; rename them there and the launcher's
list needs the same edit, because pi silently ignores an exclusion for a tool
that does not exist.

Sub-agents have a second, independent route out: `pi-subagents` can export a
run to HTML and publish it with `gh gist create`. It is off unless
`agent/extensions/subagent/config.json` sets `"share": true`, and that file now
says `"share": false` explicitly rather than relying on the default.

### 6. Egress proxy (`proxy/egress.py`)

The layers above shape what pi *offers*. This one checks where it *goes*.

The launcher starts a small allowlisting proxy on loopback, points pi's
`HTTPS_PROXY` at it, and refuses to start if it cannot. The allowlist has one
entry — the ELM host, taken from `ELM_BASE_URL` so it cannot drift from the
gateway the shim uses. Everything else gets `403` and a line in
`agent/egress.log`, with the hostname and a timestamp, so a call that should
not be happening can be stopped at source rather than merely blocked.

No certificate, no interception, no decryption: HTTPS through a proxy opens
with a plaintext `CONNECT host:443`, which is all an allowlist needs. The
payload stays encrypted end to end.

- **Fail-closed.** No proxy, no pi. That includes a machine without `python3`,
  which used to be optional here and is not any more.
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

**This is the control that does not need updating when pi changes.**
`patch-pi.py` closed `/share` and `/bug` and will break the day upstream
refactors them. The proxy catches the *next* upload feature without anyone
noticing it was added.

**It is still not enforcement.** Proxy variables are honoured by well-behaved
clients — `curl`, `npm`, `pip`, `requests`, `git` over HTTPS — and ignored by
`git` over SSH, raw sockets, and anything that unsets them. The `bash` tool can
do all three. On Linux a network namespace with no other route out
(`unshare -rn`, `bwrap`, `slirp4netns`) turns this into real enforcement;
macOS has no equivalent without root or a Network Extension, so on a managed
Mac the answer remains `pf` and an administrator.

## Verified behaviour

| Attempt | Result |
|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` set in the shell | scrubbed; catalogue unchanged at 3 models |
| `/model` picker, `Ctrl+P` cycling | only the 3 ELM entries exist |
| `/login` with a real subscription | provider has no models; credential write is blocked |
| `pi --model anthropic/... --api-key ...` | refused by layer 2 (exit 2) |
| Same, with `PI_ELM_UNLOCK=1` and a key in the environment | `Model not found` — layer 3 holds |
| `PI_ELM_UNLOCK=1 PI_ELM_ALLOWED_PROVIDERS="elm,elm-shim,anthropic"` | Anthropic returns — the intended escape hatch |
| `pi --list-models` | ELM only |
| `/share`, `/bug` | absent from autocomplete; both refuse, and their upload paths throw |
| asking the model to list its tools | 17 tools, none of them web: `read, bash, write, todo, subagent, bg_wait, memory_*, skill_manage, session_search, replace, insert, anchor_grep, undo_last_change, subagent_supervisor` |
| the same with `PI_ELM_WEB=1` | 21 tools — `web_search`, `source_check`, `fetch_content`, `get_search_content` return |
| ELM request through the proxy | allowed; a real `pi -p` round trip works |
| agent running `curl https://example.com` in `bash` | refused, `exit=56`, logged as `REJECTED example.com:443 not on the allowlist` |
| `pi update` | runs unproxied, by construction — the proxy starts after the update intercept |
| `proxy/egress.py` missing | pi refuses to start (exit 1) rather than running unfiltered |

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

Permanently, for a host or a person with funded access: edit `ALLOWED` in
`templates/extensions/elm-only.ts`, drop the `unset` block from `pi`, and
`./bootstrap.sh --update --no-auth-lock`.

`PI_ELM_ALLOWED_PROVIDERS` alone does nothing: the launcher unsets it unless
`PI_ELM_UNLOCK=1` is also present, so the escape hatch is always a conscious act.

## If a pi upgrade adds providers

`BUILTIN_PROVIDERS` in `elm-only.ts` and `DENIED_PROVIDERS` in `pi` are static
lists, used for the pre-session pass and the argument guard. The session-start
pass is dynamic and catches anything they miss, so a new provider is still
stripped inside a session — only `--list-models` and the argument guard would be
stale. Regenerate both lists after upgrading pi:

```bash
cat > /tmp/list-providers.ts <<'EOF'
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
export default function (pi: ExtensionAPI) {
  pi.on("session_start", async (_e, ctx: any) => {
    console.error([...new Set(ctx.modelRegistry.getAll().map((m: any) => m.provider))].sort().join("\n"));
  });
}
EOF
./pi --no-extensions -e /tmp/list-providers.ts --no-session -p hi 2>&1 >/dev/null
```

`--no-extensions` is what makes this work: it keeps `elm-only.ts` from stripping
the catalogue before the probe reads it, while the explicit `-e` path still
loads. Paste the result, minus `elm`, into both lists.
