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

## Three layers

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

## What this does not do

- It does not stop `npm i -g` of another agent, a browser tab, or an API call from
  a script. Nothing local can.
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
