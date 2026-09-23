#!/usr/bin/env bash
#
#   ./bootstrap.sh                  install everything, prompt for the ELM key
#   ELM_API_KEY=elm-... ./bootstrap.sh --non-interactive
#   ./bootstrap.sh --no-shim        skip the Llama tool-call shim
#   ./bootstrap.sh --no-packages    pi only, no sub-agent/memory/web packages
#   ./bootstrap.sh --no-memory      drop pi-hermes-memory: ~1.8s off every launch
#   ./bootstrap.sh --update         refresh pi and packages, keep configs
#   ./bootstrap.sh --force          re-download the tools and reinstall npm packages
#   ./bootstrap.sh --no-auth-lock   leave agent/auth.json writable (allows /login)
#   ./bootstrap.sh --no-tools       skip the bundled fd/rg/jq/yq/shellcheck/ast-grep
#   ./bootstrap.sh --no-patch       leave pi's /share and /bug commands in place
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




WITH_SHIM=1; WITH_PACKAGES=1; INTERACTIVE=1; UPDATE=0; AUTH_LOCK=1; WITH_MEMORY=1; FORCE=0
WITH_TOOLS=1; WITH_PATCH=1
for arg in "$@"; do
  case "$arg" in
    --no-shim) WITH_SHIM=0 ;;
    --no-packages) WITH_PACKAGES=0 ;;
    --no-memory) WITH_MEMORY=0 ;;
    --non-interactive) INTERACTIVE=0 ;;
    --update) UPDATE=1 ;;
    --force) FORCE=1 ;;
    --no-auth-lock) AUTH_LOCK=0 ;;
    --no-tools) WITH_TOOLS=0 ;;
    --no-patch) WITH_PATCH=0 ;;
    -h|--help) sed -n '3,16p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m    %s\033[0m\n' "$*"; }
die()  { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# macOS ships shasum, most Linux distros ship sha256sum. Pick before piping:
# a missing binary inside a pipeline still exits 0 through awk.
sha256_of() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    die "neither sha256sum nor shasum found - cannot verify downloads"
  fi
}

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
  got=$(sha256_of "$TMP/$TAR")
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


# When --update or --force is passed, always reinstall to get the latest npm version.
# npm install with "latest" does not update an already-installed package unless we
# remove node_modules first. For --update, we remove and reinstall.
if [ "$UPDATE" = "1" ] || [ "$FORCE" = "1" ]; then
  rm -rf node_modules
  npm install --no-audit --no-fund --loglevel=error
elif [ ! -d "node_modules/@earendil-works/pi-coding-agent" ]; then
  npm install --no-audit --no-fund --loglevel=error
fi




echo "    $(node node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js --version 2>/dev/null || echo installed)"
# /share publishes the session as a GitHub gist and /bug POSTs the whole
# transcript to radius.pi.dev. pi has no way to disable a built-in command, so
# they are patched out of the release here, on every install and every update.
#
# Fatal by design. If a pi release moves the code the patch anchors to, this
# stops the install rather than leaving an unpatched pi behind a message nobody
# reads - and `pi update` then stops before touching the extension packages.
# Re-derive the anchors in patch-pi.py, or re-run with --no-patch if you have
# decided you want those commands.
if [ "$WITH_PATCH" = "1" ]; then
  ./patch-pi.py || die "could not disable /share and /bug - see patch-pi.py"
else
  warn "--no-patch: /share and /bug are live; both upload the whole session off-site"
fi
# npm warns that esbuild / protobufjs / @google/genai have unapproved install
# scripts. pi runs from a prebuilt bundle and does not need them.
# --- 3. agent config --------------------------------------------------------
# PI_CODING_AGENT_DIR points here, so config, sessions and credentials stay in
# this directory instead of ~/.pi.
chmod +x pi pi.orig configure.sh 2>/dev/null || true

say "agent configuration"
mkdir -p agent/extensions/subagent agent/prompts agent/agents
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
# Agent definitions are code, not config: pi-subagents discovers them in
# agent/agents, and `subagent qwen "..."` fails with "Unknown agent" without
# them. Refreshed on --update like the extensions.
for f in templates/agents/*.md; do
  [ -e "$f" ] || continue
  install_if_absent "$f" "agent/agents/$(basename "$f")"
done
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

# --- 3b. command-line tools -------------------------------------------------
# pi's find and grep tools shell out to fd and rg. It looks for them in
# agent/bin first, then on PATH, and if it finds neither it downloads them from
# GitHub on the first interactive launch - awaited before the prompt is drawn,
# which is what made the first start crawl. Installing them here means the
# first launch costs what the tenth does.
#
# The rest of the list is for the agent's bash tool rather than for pi: the
# things a model reaches for constantly and cannot rely on finding, on a Mac or
# on a login node. All are a single static binary from the project's own GitHub
# release, so the install stays one directory you can delete.
#
#   - fd          file finding               (pi's find tool)
#   - rg          content search             (pi's grep tool)
#   - jq          JSON on the command line   - macOS 15 ships it, most Linux does not
#   - yq          the same for YAML          - CI configs, k8s, conda envs
#   - shellcheck  lints shell before it runs - this install is mostly bash
#   - ast-grep    structural search and rewrite by syntax tree, not by regex
#
# (The list marker is not decoration: a comment whose first word is the name of
# a certain linter is read by that linter as a directive, and it then refuses to
# parse the rest of the file.)
#
# They are installed even when the machine already has them, so that every host
# behaves the same: the launcher puts agent/bin at the front of PATH, so the
# agent gets these versions and not whatever a login node last updated in 2019.
# Nothing lands outside this directory - rm -rf takes the lot.
#
#   --no-tools          install none of them; the system's own are used instead
#   ELM_PI_TOOLS=fd,rg,jq   install a subset - shellcheck and ast-grep are 35MB
#                           and 51MB respectively, the other four total ~23MB
#   FD_VERSION=10.5.0   pin any of them      (checksums: templates/tools.sha256)
#   RG_VERSION=15.2.0   JQ_VERSION=1.8.2     YQ_VERSION=4.53.6
#   SHELLCHECK_VERSION=0.11.0                ASTGREP_VERSION=0.45.3
if [ "$WITH_TOOLS" = "1" ]; then
  TOOLSET="${ELM_PI_TOOLS:-fd,rg,jq,yq,shellcheck,ast-grep}"
  want_tool() { case ",$TOOLSET," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }
  say "command-line tools (${TOOLSET//,/, })"
  # Three projects, three naming schemes: Rust triples, Go's os_arch, and jq's
  # own spelling of macOS.
  case "$(uname -s)" in
    Darwin) RUST_OS=apple-darwin      ; GNU_OS=apple-darwin        ; GO_OS=darwin ; JQ_OS=macos ;;
    Linux)  RUST_OS=unknown-linux-musl; GNU_OS=unknown-linux-gnu   ; GO_OS=linux  ; JQ_OS=linux ;;
    *) die "unsupported OS: $(uname -s)" ;;
  esac
  case "$(uname -m)" in
    x86_64|amd64)  RUST_ARCH=x86_64 ; GO_ARCH=amd64 ;;
    arm64|aarch64) RUST_ARCH=aarch64; GO_ARCH=arm64 ;;
    *) die "unsupported architecture: $(uname -m)" ;;
  esac
  # musl where it is offered: a static binary has no glibc version to match.
  # ast-grep publishes no musl build, so on Linux it gets the glibc one.
  TRIPLE="$RUST_ARCH-$RUST_OS"
  GNU_TRIPLE="$RUST_ARCH-$GNU_OS"
  # fd 10.4+ is built against a macOS SDK newer than the Intel Macs in the
  # estate. pi pins 10.3.0 there for the same reason; match it.
  if [ "$TRIPLE" = "x86_64-apple-darwin" ]; then
    FD_VERSION="${FD_VERSION:-10.3.0}"
  else
    FD_VERSION="${FD_VERSION:-10.5.0}"
  fi
  RG_VERSION="${RG_VERSION:-15.2.0}"
  JQ_VERSION="${JQ_VERSION:-1.8.2}"
  YQ_VERSION="${YQ_VERSION:-4.53.6}"
  SHELLCHECK_VERSION="${SHELLCHECK_VERSION:-0.11.0}"
  ASTGREP_VERSION="${ASTGREP_VERSION:-0.45.3}"

  TOOLS_TMP="$(mktemp -d)"; trap 'rm -rf "${TMP:-}" "${TOOLS_TMP:-}"' EXIT

  install_tool() {   # $1 binary  $2 version  $3 asset  $4 url  $5 sha256 url ("" if none)
    local bin="$1" version="$2" asset="$3" url="$4" shaurl="$5"
    local dest="agent/bin/$bin" want got found
    want_tool "$bin" || { echo "    $bin skipped (not in ELM_PI_TOOLS)"; return 0; }
    # Already the pinned version? Then there is nothing to update. These are
    # pinned here, not tracked upstream, so --update means "match the pin", the
    # same as the Node step above - it does not mean "fetch 105MB again". Only
    # a changed pin, a missing binary, or one that will not run gets a
    # download; --force gets one regardless.
    if [ "$FORCE" != "1" ] && [ -x "$dest" ] \
       && "$dest" --version 2>/dev/null | grep -q -- "$version"; then
      echo "    $bin $version already in agent/bin"
      return 0
    fi
    echo "    downloading $asset"
    if ! curl -fsSL -o "$TOOLS_TMP/$asset" "$url"; then
      warn "could not download $asset - $bin not installed"
      return 0
    fi
    # Pinned versions are checksummed here, the way the Node tarball is. A
    # version someone pinned by hand falls back to the project's own published
    # checksum, and installs with a warning when there is none to be had.
    want="$(awk -v a="$bin/$version/$asset" '$2 == a {print $1}' templates/tools.sha256 2>/dev/null | head -1)"
    if [ -z "$want" ] && [ -n "$shaurl" ]; then
      want="$(curl -fsSL "$shaurl" 2>/dev/null \
              | awk -v a="$asset" '$2 == a {print $1; exit} NF == 1 {print $1; exit}')"
    fi
    got="$(sha256_of "$TOOLS_TMP/$asset")"
    if [ -n "$want" ]; then
      [ "$want" = "$got" ] || die "checksum mismatch for $asset"
    else
      warn "no published checksum for $asset - installing unverified ($got)"
    fi
    rm -rf "$TOOLS_TMP/x" && mkdir -p "$TOOLS_TMP/x"
    case "$asset" in
      # `tar -xf` auto-detects gzip and xz on both bsdtar and GNU tar; GNU tar
      # needs an `xz` binary on PATH for the latter, bsdtar does not.
      *.tar.gz|*.tar.xz|*.tgz)
        tar -xf "$TOOLS_TMP/$asset" -C "$TOOLS_TMP/x" 2>/dev/null || true ;;
      # bsdtar reads zip files, GNU tar does not - try unzip first.
      *.zip)
        unzip -q "$TOOLS_TMP/$asset" -d "$TOOLS_TMP/x" 2>/dev/null \
          || tar -xf "$TOOLS_TMP/$asset" -C "$TOOLS_TMP/x" 2>/dev/null || true ;;
      *)  # a bare binary, no archive
        mv -f "$TOOLS_TMP/$asset" "$TOOLS_TMP/x/$bin" ;;
    esac
    found="$(find "$TOOLS_TMP/x" -type f -name "$bin" | head -1)"
    if [ -z "$found" ]; then
      warn "could not unpack $bin from $asset - $bin not installed"
      return 0
    fi
    mv -f "$found" "$dest" && chmod 755 "$dest"
    if ! "$dest" --version >/dev/null 2>&1; then
      rm -f "$dest"
      warn "the downloaded $bin does not run on this machine - $bin not installed"
      return 0
    fi
    echo "    $bin $version -> agent/bin/$bin"
  }

  GH=https://github.com
  install_tool fd "$FD_VERSION" "fd-v$FD_VERSION-$TRIPLE.tar.gz" \
    "$GH/sharkdp/fd/releases/download/v$FD_VERSION/fd-v$FD_VERSION-$TRIPLE.tar.gz" ""
  install_tool rg "$RG_VERSION" "ripgrep-$RG_VERSION-$TRIPLE.tar.gz" \
    "$GH/BurntSushi/ripgrep/releases/download/$RG_VERSION/ripgrep-$RG_VERSION-$TRIPLE.tar.gz" \
    "$GH/BurntSushi/ripgrep/releases/download/$RG_VERSION/ripgrep-$RG_VERSION-$TRIPLE.tar.gz.sha256"
  install_tool jq "$JQ_VERSION" "jq-$JQ_OS-$GO_ARCH" \
    "$GH/jqlang/jq/releases/download/jq-$JQ_VERSION/jq-$JQ_OS-$GO_ARCH" \
    "$GH/jqlang/jq/releases/download/jq-$JQ_VERSION/sha256sum.txt"
  install_tool yq "$YQ_VERSION" "yq_${GO_OS}_${GO_ARCH}" \
    "$GH/mikefarah/yq/releases/download/v$YQ_VERSION/yq_${GO_OS}_${GO_ARCH}" ""
  install_tool shellcheck "$SHELLCHECK_VERSION" \
    "shellcheck-v$SHELLCHECK_VERSION.$GO_OS.$RUST_ARCH.tar.xz" \
    "$GH/koalaman/shellcheck/releases/download/v$SHELLCHECK_VERSION/shellcheck-v$SHELLCHECK_VERSION.$GO_OS.$RUST_ARCH.tar.xz" ""
  # The zip also contains `sg`, which is a real command on Linux (shadow-utils).
  # Only ast-grep is installed; shadowing `sg` on PATH would be rude.
  install_tool ast-grep "$ASTGREP_VERSION" "app-$GNU_TRIPLE.zip" \
    "$GH/ast-grep/ast-grep/releases/download/$ASTGREP_VERSION/app-$GNU_TRIPLE.zip" ""
  echo "    agent/bin is $(du -sh agent/bin 2>/dev/null | awk '{print $1}')"
else
  say "command-line tools"
  echo "    skipped (--no-tools): the system's own fd/rg/jq/... are used instead"
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
  # Two lists, and they are not the same list. templates/packages.json is what
  # npm installs, and carries libraries that are not pi packages at all
  # (better-sqlite3, which pi-hermes-memory needs to build against).
  # templates/settings.json is what pi loads. Both are filtered by --no-memory.
  #
  # agent/settings.json's "packages" is derived from the template every run
  # rather than filtered in place. Filtering in place could only ever remove:
  # an install that had once been run with --no-packages kept an empty list for
  # ever after, so a later run installed all four packages into agent/npm and
  # then loaded none of them. Everything else in that file is yours and is left
  # exactly as you left it.
  DROP="$DROP" python3 - <<'PYX'
import json, os
drop = {d for d in os.environ.get("DROP", "").split() if d}

pkg = json.load(open("templates/packages.json"))
pkg["dependencies"] = {k: v for k, v in pkg["dependencies"].items() if k not in drop}
json.dump(pkg, open("agent/npm/package.json", "w"), indent=2)

chosen = [p for p in json.load(open("templates/settings.json")).get("packages", [])
          if p.removeprefix("npm:") not in drop]
s = json.load(open("agent/settings.json"))
was = s.get("packages", [])
s["packages"] = chosen
json.dump(s, open("agent/settings.json", "w"), indent=2); open("agent/settings.json", "a").write("\n")

print("    loading: " + (", ".join(p.removeprefix("npm:") for p in chosen) or "none"))
if drop:
    print("    dropped: " + ", ".join(sorted(drop)))
if sorted(was) != sorted(chosen):
    print("    (agent/settings.json listed %d package(s); corrected to match)" % len(was))
PYX
  CHOSEN="$(python3 -c 'import json; print(" ".join(p.removeprefix("npm:") for p in json.load(open("agent/settings.json")).get("packages", [])))')"

  # Reinstall when asked, or when anything chosen is not actually on disk.
  MISSING=0
  for pkg in $CHOSEN; do
    [ -d "agent/npm/node_modules/$pkg" ] || MISSING=1
  done
  # When --update or --force is passed, remove node_modules first to ensure npm
  # actually installs the latest versions. npm install with "latest" won't update
  # existing packages otherwise.
  if [ "$UPDATE" = "1" ] || [ "$FORCE" = "1" ]; then
    rm -rf agent/npm/node_modules
    ( cd agent/npm && npm install --no-audit --no-fund --loglevel=error )
    echo "    installed into agent/npm/node_modules"
  elif [ "$MISSING" = "1" ]; then
    ( cd agent/npm && npm install --no-audit --no-fund --loglevel=error )
    echo "    installed into agent/npm/node_modules"
  else
    echo "    packages already installed (use --force to reinstall)"
  fi
  # A package pi is told to load but cannot find is a silent no-op at startup:
  # the launcher runs pi offline, so it does not try to fetch it either.
  for pkg in $CHOSEN; do
    [ -d "agent/npm/node_modules/$pkg" ] || \
      warn "$pkg is listed in agent/settings.json but missing from agent/npm/node_modules"
  done

else
  python3 - <<'PY'
import json
s=json.load(open("agent/settings.json")); s["packages"]=[]
json.dump(s,open("agent/settings.json","w"),indent=2); open("agent/settings.json","a").write("\n")
print("    packages disabled in agent/settings.json")
PY
fi

# --- 3c. warm the module cache ----------------------------------------------
# The four packages ship raw TypeScript. pi transpiles them with jiti, which
# caches the result in $TMPDIR/jiti and reuses it on every later launch, so the
# cost is paid once: measured here, ~21s of CPU cold against ~3.3s warm.
#
# "Once" is the problem. The first launch after an install pays it, and so does
# the first launch after a tmp cleaner sweeps the cache, after a package update
# changes the sources, or on the next login node with its own /tmp. Paying it
# here means the install finishes slow and the agent starts fast, which is the
# right way round.
#
# pi.orig rather than pi: the launcher needs the ELM key and this runs before
# the key may exist. Same settings, same packages, same cache.
if [ "$WITH_PACKAGES" = "1" ] && [ -d agent/npm/node_modules ]; then
  say "warming the module cache"
  echo "    transpiling the packages once so the first launch does not have to"
  JITI_CACHE_DIR="${TMPDIR:-/tmp}"; JITI_CACHE_DIR="${JITI_CACHE_DIR%/}/jiti"
  if PI_CODING_AGENT_DIR="$HERE/agent" PI_OFFLINE=1 PI_FORCE=1 \
     ./pi.orig --list-models >/dev/null 2>&1; then
    echo "    done - cached in $JITI_CACHE_DIR"
  else
    warn "warm-up failed; the first launch will transpile instead (slow, not fatal)"
  fi
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
    warn "python3 not found: Llama sub-agents are unavailable - and see the warning below"
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
# python3 stopped being optional when the egress proxy went in: the launcher
# refuses to start without it rather than running unfiltered.
if ! command -v python3 >/dev/null 2>&1; then
  warn "python3 is NOT installed. pi will refuse to start: the egress proxy needs it."
  warn "Install python3, or run with ELM_PI_NO_PROXY=1 to accept unfiltered network access."
fi

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
if [ "$WITH_PATCH" = "1" ]; then
  ./patch-pi.py --check || warn "/share and /bug are NOT disabled in this install"
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
    Update it:     pi update      (elm-pi + pi from GitHub, then the pi packages)
    Verify:        see "Verify the install" in INSTALL.md
EOM
