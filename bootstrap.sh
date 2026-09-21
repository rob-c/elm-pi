#!/usr/bin/env bash
#
# Reproduce this pi + ELM install on a fresh machine or host.
#
#   ./bootstrap.sh                  install everything, prompt for the ELM key
#   ELM_API_KEY=elm-... ./bootstrap.sh --non-interactive
#   ./bootstrap.sh --no-shim        skip the Llama tool-call shim
#   ./bootstrap.sh --no-packages    pi only, no sub-agent/memory/web packages
#   ./bootstrap.sh --no-memory      drop pi-hermes-memory: ~1.8s off every launch
#   ./bootstrap.sh --update         refresh pi and packages, keep configs
#   ./bootstrap.sh --no-auth-lock   leave agent/auth.json writable (allows /login)
#
# Idempotent: re-running never overwrites .env, sessions, memory or any config
# you have edited. Nothing is installed system-wide; delete this directory and
# the install is gone.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"





NODE_VERSION="${NODE_VERSION:-v24.21.0}"

# Always install latest pi from npm (no version pin)
# Set PI_VERSION to a specific version only if you need to freeze it
PI_VERSION="${PI_VERSION:-latest}"




WITH_SHIM=1; WITH_PACKAGES=1; INTERACTIVE=1; UPDATE=0; AUTH_LOCK=1; WITH_MEMORY=1
for arg in "$@"; do
  case "$arg" in
    --no-shim) WITH_SHIM=0 ;;
    --no-packages) WITH_PACKAGES=0 ;;
    --no-memory) WITH_MEMORY=0 ;;
    --non-interactive) INTERACTIVE=0 ;;
    --update) UPDATE=1 ;;
    --no-auth-lock) AUTH_LOCK=0 ;;
    -h|--help) sed -n '3,14p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m    %s\033[0m\n' "$*"; }
die()  { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# --- 1. Node ----------------------------------------------------------------
# Bundled inside the install: no brew, no system Node, no version conflict.
# On an Intel Mac `brew install node` has no bottle and compiles V8 from source
# (over an hour). The official prebuilt tarball takes seconds.
say "Node $NODE_VERSION"
if [ -x ".node/bin/node" ] && [ "$(.node/bin/node --version)" = "$NODE_VERSION" ]; then
  echo "    already present: $(.node/bin/node --version)"
else
  case "$(uname -s)" in
    Darwin) OS=darwin ;;
    Linux)  OS=linux ;;
    *) die "unsupported OS: $(uname -s)" ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64) ARCH=x64 ;;
    arm64|aarch64) ARCH=arm64 ;;
    *) die "unsupported architecture: $(uname -m)" ;;
  esac
  TAR="node-$NODE_VERSION-$OS-$ARCH.tar.gz"
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  echo "    downloading $TAR"
  curl -fsSL -o "$TMP/$TAR" "https://nodejs.org/dist/$NODE_VERSION/$TAR"
  curl -fsSL -o "$TMP/SHASUMS256.txt" "https://nodejs.org/dist/$NODE_VERSION/SHASUMS256.txt"
  want=$(grep " $TAR\$" "$TMP/SHASUMS256.txt" | awk '{print $1}')
  # macOS ships shasum, most Linux distros ship sha256sum. Pick before piping:
  # a missing binary inside a pipeline still exits 0 through awk.
  if command -v sha256sum >/dev/null 2>&1; then
    got=$(sha256sum "$TMP/$TAR" | awk '{print $1}')
  elif command -v shasum >/dev/null 2>&1; then
    got=$(shasum -a 256 "$TMP/$TAR" | awk '{print $1}')
  else
    die "neither sha256sum nor shasum found - cannot verify the Node download"
  fi
  [ -n "$want" ] && [ "$want" = "$got" ] || die "checksum mismatch for $TAR"
  rm -rf .node && mkdir -p .node
  tar -xzf "$TMP/$TAR" -C .node --strip-components=1
  echo "    installed $(.node/bin/node --version)"
fi
export PATH="$HERE/.node/bin:$PATH"

# --- 2. pi ------------------------------------------------------------------
say "pi coding agent"
cp -f templates/package.json package.json
if [ "$UPDATE" = "1" ]; then rm -f package-lock.json; fi
npm install --no-audit --no-fund --loglevel=error
echo "    $(node node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js --version 2>/dev/null || echo installed)"
# npm warns that esbuild / protobufjs / @google/genai have unapproved install
# scripts. pi runs from a prebuilt bundle and does not need them.

# --- 3. agent config --------------------------------------------------------
# PI_CODING_AGENT_DIR points here, so config, sessions and credentials stay in
# this directory instead of ~/.pi.
chmod +x pi pi.orig configure.sh 2>/dev/null || true

say "agent configuration"
mkdir -p agent/extensions/subagent agent/prompts
install_if_absent() {   # never clobber a config someone has tuned
  if [ -f "$2" ] && [ "$UPDATE" != "1" ]; then
    echo "    keeping existing $2"
  else
    cp -f "$1" "$2"; echo "    wrote $2"
  fi
}
# Extensions are code, not config: --update refreshes them, a plain run installs
# them once. elm-only.ts is the ELM-only policy and is always refreshed.
cp -f templates/extensions/elm-only.ts agent/extensions/elm-only.ts
echo "    wrote agent/extensions/elm-only.ts (ELM-only policy)"
for f in protected-paths.ts todo.ts elm-shim.ts; do
  install_if_absent "templates/extensions/$f" "agent/extensions/$f"
done
install_if_absent templates/extensions/subagent/config.json agent/extensions/subagent/config.json
install_if_absent templates/settings.json              agent/settings.json
install_if_absent templates/models.json                agent/models.json
install_if_absent templates/AGENTS.md                  agent/AGENTS.md
install_if_absent templates/prompts/ulw.md             agent/prompts/ulw.md
install_if_absent templates/web-search.json            agent/web-search.json
install_if_absent templates/hermes-memory-config.json  agent/hermes-memory-config.json
[ -f agent/auth.json ] || printf '{}\n' > agent/auth.json

# agent/bin is pi's managed-binary directory (fd, rg), and pi prepends it to
# PATH for every child process it spawns. pi-subagents falls back to a bare
# `pi` PATH lookup when it cannot resolve the CLI any other way, which used to
# find nothing here. The installer now links ~/.local/bin/pi, but that only
# helps when BINDIR is on the child's PATH, so the symlink stays: it makes the
# fallback land on this launcher whatever PATH looks like, keeping the ELM-only
# policy and the .env key in force for children. The launcher also exports
# PI_SUBAGENT_PI_BINARY, the documented override; any one of the three is
# enough on its own.
mkdir -p agent/bin
ln -sfn "$HERE/pi" agent/bin/pi
echo "    agent/bin/pi -> $HERE/pi (sub-agent children)"
if [ "$AUTH_LOCK" = "1" ]; then
  # /login writes the credential it obtains to agent/auth.json. Read-only means
  # that write fails, so a commercial subscription cannot be attached to this
  # install even by someone who has one. Verified: normal startup and ELM use
  # are unaffected. Undo with: chmod 600 agent/auth.json
  chmod 444 agent/auth.json
  echo "    agent/auth.json is read-only (/login cannot store credentials)"
else
  chmod 600 agent/auth.json
  echo "    agent/auth.json is writable (--no-auth-lock)"
fi

if [ "$WITH_PACKAGES" = "1" ]; then
  say "pi packages (sub-agents, memory, web access, anchor editing)"
  mkdir -p agent/npm
  # Every package is transpiled and imported at each launch. Measured CPU cost
  # per launch on this install: hermes-memory ~1.8s, subagents+hashline ~1.6s,
  # web-access ~0.2s, against ~1.4s for pi and the local extensions alone.
  # `pi --fast` skips all of them for one-shot work; --no-memory drops the
  # most expensive one permanently.
  DROP=""
  [ "$WITH_MEMORY" = "1" ] || DROP="pi-hermes-memory"
  DROP="$DROP" python3 - <<'PYX'
import json, os
drop = {d for d in os.environ.get("DROP", "").split() if d}
pkg = json.load(open("templates/packages.json"))
pkg["dependencies"] = {k: v for k, v in pkg["dependencies"].items() if k not in drop}
json.dump(pkg, open("agent/npm/package.json", "w"), indent=2)
s = json.load(open("agent/settings.json"))
s["packages"] = [p for p in s.get("packages", []) if p.removeprefix("npm:") not in drop]
json.dump(s, open("agent/settings.json", "w"), indent=2); open("agent/settings.json", "a").write("\n")
if drop:
    print("    dropped: " + ", ".join(sorted(drop)))
PYX
  ( cd agent/npm && npm install --no-audit --no-fund --loglevel=error )
  echo "    installed into agent/npm/node_modules"
else
  python3 - <<'PY'
import json
s=json.load(open("agent/settings.json")); s["packages"]=[]
json.dump(s,open("agent/settings.json","w"),indent=2); open("agent/settings.json","a").write("\n")
print("    packages disabled in agent/settings.json")
PY
fi

# --- 4. Llama tool-call shim ------------------------------------------------
# ELM's vLLM instance for Llama 3.3 was started without a tool-call parser, so
# any request carrying `tools` returns 400. The shim prompt-engineers tool
# calling on top of it, which is what makes cheap Llama sub-agents possible.
if [ "$WITH_SHIM" = "1" ]; then
  say "Llama tool-call shim"
  if command -v python3 >/dev/null 2>&1; then
    echo "    $(python3 --version) at $(command -v python3) - shim will start on demand (127.0.0.1:8811)"
  else
    warn "python3 not found: Llama sub-agents will be unavailable, Qwen is unaffected"
  fi
else
  rm -f agent/extensions/elm-shim.ts
  echo "    shim skipped (agent/extensions/elm-shim.ts removed)"
fi

# --- 5. the key -------------------------------------------------------------
# ELM keys are issued on request through the ELM web UI, not self-service.
say "ELM API key"
if [ -f .env ]; then
  echo "    keeping existing .env"
elif [ -n "${ELM_API_KEY:-}" ]; then
  umask 077; printf 'ELM_API_KEY=%s\n' "$ELM_API_KEY" > .env; chmod 600 .env
  echo "    wrote .env from the environment"
elif [ "$INTERACTIVE" = "1" ] && [ -t 0 ]; then
  printf '    paste your ELM API key (elm-...): '
  read -r key
  [ -n "$key" ] || die "no key given"
  umask 077; printf 'ELM_API_KEY=%s\n' "$key" > .env; chmod 600 .env
  echo "    wrote .env (mode 600)"
else
  cp -f .env.example .env; chmod 600 .env
  warn "no key available - edit .env before running ./pi"
fi

# --- 6. resolve the model id and smoke-test ---------------------------------
if grep -q '^ELM_API_KEY=.\+' .env 2>/dev/null; then
  say "resolving the model id from the gateway"
  ./configure.sh || warn "configure.sh failed - check the key and the gateway, then re-run ./configure.sh"
fi

# --- 7. verify the lockdown -------------------------------------------------
say "verifying the ELM-only policy"
LIST="$(PI_FORCE=1 PI_OFFLINE=1 ANTHROPIC_API_KEY=probe-should-be-ignored \
        OPENAI_API_KEY=probe-should-be-ignored ./pi --list-models </dev/null 2>/dev/null || true)"
if printf '%s' "$LIST" | grep -qE '^(anthropic|openai|google) '; then
  die "commercial providers are still visible - the credential scrub in ./pi is not working"
fi
printf '%s\n' "$LIST" | sed 's/^/    /'
if [ -x agent/bin/pi ] && [ "$(cd "$(dirname "$(readlink agent/bin/pi)")" && pwd)/$(basename "$(readlink agent/bin/pi)")" = "$HERE/pi" ]; then
  echo "    sub-agent launcher: agent/bin/pi resolves to the launcher"
else
  warn "agent/bin/pi is missing or points elsewhere - sub-agents may fail to start"
fi
GUARD="$(PI_FORCE=1 ./pi --model anthropic/claude-opus-5 -p x </dev/null 2>&1 || true)"
case "$GUARD" in
  *"not available"*) echo "    argument guard: --model anthropic/... refused" ;;
  *) warn "argument guard did not refuse --model anthropic/... - check the launcher" ;;
esac

say "done"
cat <<EOM
    Run it:        pi            (or $HERE/pi if it is not on your PATH yet)
    Unwrapped:     $HERE/pi.orig   (vanilla CLI, no ELM config - debugging only)
    Policy:        $HERE/LOCKDOWN.md   (/elm-policy inside pi)
    Fast one-shot: $HERE/pi --fast -p "..."    (skips the npm packages)
    Verify:        see "Verify the install" in INSTALL.md
EOM
