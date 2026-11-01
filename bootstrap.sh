#!/usr/bin/env bash
#
# elm-pi installer: bundled Node, pi, the agent config, the search tools and
# the ELM key. Run ./bootstrap.sh --help for the flags - that list lives in
# usage() below, and nowhere else, so it cannot drift from what is parsed.
#
# Idempotent: re-running never overwrites .env, sessions, memory or any config
# you have edited. Nothing is installed system-wide; delete this directory and
# the install is gone.
set -euo pipefail
unset CDPATH
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

CONFIG_TOOL="$HERE/scripts/elm_config.py"

WITH_SHIM=1; WITH_PACKAGES=1; INTERACTIVE=1; UPDATE=0; AUTH_LOCK=1; FORCE=0
WITH_TOOLS=1; WITH_PATCH=1; WITH_PYTHON=0; WITH_PYPI_INDEX=0; FORCE_PACKAGES=0; RESET_OPTIONS=0
# The --no-* and --with-* flags this run was given, for agent/install-options
# (see below), and the --with-* ones it takes back.
GIVEN_FLAGS=""; DROPPED_FLAGS=""
TMP=""; TOOLS_TMP=""; PYPI_TMP=""; CORE_STAGE=""; PKG_STAGE=""; VERIFY_ERR=""
# The pi release and the extension tree this run replaced. They are kept until
# the run has finished and verified, and put back if it fails, so an update
# whose pi cannot load this install's config leaves the previous working pair
# in place rather than a broken one. Files this run rewrote under agent/ are
# not rolled back.
CORE_OLD=""; PKG_OLD=""

restore() {   # $1 = the kept tree, $2 = where it goes back
  [ -n "$1" ] && [ -d "$1" ] || return 0
  rm -rf -- "$2" && mv -- "$1" "$2" && printf '    put back the previous %s\n' "${2#"$HERE"/}" >&2
}

cleanup() {
  local status=$? path
  if [ "$status" != 0 ]; then
    restore "$CORE_OLD" "$HERE/node_modules"
    restore "$PKG_OLD" "$HERE/agent/npm/node_modules"
  fi
  for path in "$TMP" "$TOOLS_TMP" "$PYPI_TMP" "$CORE_STAGE" "$PKG_STAGE" "$CORE_OLD" "$PKG_OLD" "$VERIFY_ERR"; do
    [ -z "$path" ] || rm -rf -- "$path"
  done
}
trap cleanup EXIT

usage() {
  cat <<'EOU'
elm-pi installer. Installs into this directory; nothing goes system-wide.

  ./bootstrap.sh                  install everything, prompt for the ELM key
  ELM_API_KEY=elm-... ./bootstrap.sh --non-interactive

  --non-interactive   take the key from $ELM_API_KEY, never prompt
  --update            refresh pi, packages and extensions; keep your configs
  --force             re-download the tools and reinstall the npm packages
  --force-packages    reinstall the extension packages at the tested versions,
                      and pi too if it is not at its tested version

  --no-packages       pi only: no sub-agents, web access or anchor edit
  --no-tools          skip the bundled fd/rg/jq/yq/shellcheck/ast-grep/uv
  --with-python       give the agent its own Python: uv-managed CPython and the
                      analysis stack in agent/python (~1GB); `pi setup --python`
  --with-pypi-index   an offline search index of PyPI for the agent, `pypi-search`
                      (downloads ~1GB once, keeps ~390MB); implies --with-python
  --no-python         take --with-python (and --with-pypi-index) back, removing
                      agent/python; --no-pypi-index takes back the index alone
  --no-shim           skip the Llama tool-call shim
  --no-patch          leave pi's /share and /bug commands in place
  --no-auth-lock      leave agent/auth.json writable, so /login works
  --reset-options     forget the --no-* flags and ELM_PI_TOOLS earlier runs
                      recorded, and use only what this run is given
  -h, --help          this text

The --no-* and --with-* flags and ELM_PI_TOOLS are recorded in agent/install-options and
repeated by every later run - pi update, pi update --extensions, re-running
the installer - so an update keeps the install you chose.

Environment: ELM_PI_PYTHON, ELM_PI_BUNDLED_PYTHON, ELM_PI_NODE_VERSION, ELM_PI_NPM_USERCONFIG,
PI_VERSION, ELM_PI_TOOLS, FD_VERSION, RG_VERSION, JQ_VERSION, YQ_VERSION,
SHELLCHECK_VERSION, ASTGREP_VERSION, UV_VERSION.

Your shell's conda/venv/pyenv Python, nvm/volta Node, ~/.npmrc, ~/.npm and
PYTHON*/NODE_*/npm_config_* variables are ignored: see lib/sandbox.sh.
EOU
}

# --help wins over everything, including a typo earlier in the line: someone
# who has just been told "unknown option" is exactly who needs to read it.
for arg in "$@"; do
  case "$arg" in -h|--help) usage; exit 0 ;; esac
done
for arg in "$@"; do
  case "$arg" in
    --no-shim|--no-packages|--no-auth-lock|--no-tools|--no-patch|--with-python|--with-pypi-index)
      case " $GIVEN_FLAGS " in *" $arg "*) ;; *) GIVEN_FLAGS="${GIVEN_FLAGS:+$GIVEN_FLAGS }$arg" ;; esac ;;
    # Taking an opt-in back: not recorded itself, it removes what it names from
    # the record. --no-python takes the index with it, which cannot build without.
    --no-python) DROPPED_FLAGS="$DROPPED_FLAGS --with-python --with-pypi-index" ;;
    --no-pypi-index) DROPPED_FLAGS="$DROPPED_FLAGS --with-pypi-index" ;;
    --non-interactive) INTERACTIVE=0 ;;
    --update) UPDATE=1 ;;
    --force) FORCE=1 ;;
    --force-packages) FORCE_PACKAGES=1 ;;
    --reset-options) RESET_OPTIONS=1 ;;
    *) echo "unknown option: $arg" >&2; echo "try: $0 --help" >&2; exit 2 ;;
  esac
done
apply_flag() {
  case "$1" in
    --no-shim) WITH_SHIM=0 ;;
    --no-packages) WITH_PACKAGES=0 ;;
    --no-auth-lock) AUTH_LOCK=0 ;;
    --no-tools) WITH_TOOLS=0 ;;
    --no-patch) WITH_PATCH=0 ;;
    --with-python) WITH_PYTHON=1 ;;
    --with-pypi-index) WITH_PYPI_INDEX=1; WITH_PYTHON=1 ;;
  esac
}


say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[33m    %s\033[0m\n' "$*"; }
die()  { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# --- 0. this install, not this account --------------------------------------
# From here on nothing of the account's own toolchain is used: no conda or
# virtualenv Python, no nvm/volta/Homebrew Node or npm, no ~/.npmrc or ~/.npm,
# no PYTHON*/NODE_*/npm_config_*/GIT_* variables. lib/sandbox.sh has the list
# and the reasons.
[ -f "$HERE/lib/sandbox.sh" ] || die "lib/sandbox.sh is missing"
# shellcheck source=lib/sandbox.sh
. "$HERE/lib/sandbox.sh"
elm_install_env "$HERE"
say "Python"
elm_ensure_python "$HERE" || die "$ELM_PY_ERROR"
echo "    $ELM_PI_PYTHON ($(elm_py -c 'import platform; print(platform.python_version())'))"
USER_PY="$(PATH="$ELM_PI_USER_PATH" command -v python3 2>/dev/null || true)"
if [ -n "$USER_PY" ] && [ "$USER_PY" != "$ELM_PI_PYTHON" ]; then
  echo "    (not $USER_PY from your PATH: elm-pi always runs its own choice, isolated)"
fi

# --- the options this install was made with ----------------------------------
# --no-packages, --no-shim and the rest describe the install, not one run, and
# `pi update` and `pi update --extensions` used to call this script without
# them - so an update quietly installed the packages, the shim and the tools
# someone had declined, and re-locked auth.json. They are recorded here, with
# ELM_PI_TOOLS and the branch and repository install.sh fetched, and every
# later run repeats them. Flags on the command line are added to the record;
# --reset-options starts it again from this run's flags alone, which is the
# way to take one back. Read as data: key=value lines, nothing is sourced.
OPTIONS_FILE="$HERE/agent/install-options"
saved_option() { [ -f "$OPTIONS_FILE" ] && sed -n "s/^$1=//p" "$OPTIONS_FILE" | tail -1; return 0; }
SAVED_FLAGS=""; SAVED_TOOLS=""; OPTIONS_FROM=""
if [ -f "$OPTIONS_FILE" ]; then
  SAVED_FLAGS="$(saved_option flags)"; SAVED_TOOLS="$(saved_option tools)"
  OPTIONS_FROM="agent/install-options"
elif [ -f agent/settings.json ]; then
  # An install from before the record existed. What the flags left behind is
  # unambiguous for four of them; --no-patch and a tool subset are not inferred.
  grep -q '"packages": \[\]' agent/settings.json && SAVED_FLAGS="$SAVED_FLAGS --no-packages"
  [ -d agent/extensions ] && [ ! -f agent/extensions/elm-shim.ts ] && SAVED_FLAGS="$SAVED_FLAGS --no-shim"
  [ -f agent/auth.json ] && [ -w agent/auth.json ] && SAVED_FLAGS="$SAVED_FLAGS --no-auth-lock"
  if [ -d agent/bin ]; then
    _any_tool=0
    for _t in fd rg jq yq shellcheck ast-grep; do [ -x "agent/bin/$_t" ] && _any_tool=1; done
    [ "$_any_tool" = "1" ] || SAVED_FLAGS="$SAVED_FLAGS --no-tools"
  fi
  OPTIONS_FROM="this install (it has no agent/install-options yet)"
fi
if [ "$RESET_OPTIONS" = "1" ]; then
  [ -z "$SAVED_FLAGS$SAVED_TOOLS" ] || echo "    --reset-options: not repeating $SAVED_FLAGS${SAVED_TOOLS:+ ELM_PI_TOOLS=$SAVED_TOOLS}"
  SAVED_FLAGS=""; SAVED_TOOLS=""
fi
# The agent's Python was built by default before --with-python existed. An
# install that has one keeps it - with the agent's own packages in it - rather
# than losing it to an update; --no-python removes it.
if [ -x agent/python/env/bin/python ] && [ "$RESET_OPTIONS" != "1" ]; then
  case " $SAVED_FLAGS $GIVEN_FLAGS ${DROPPED_FLAGS:-} " in
    *" --with-python "*) ;;
    *) SAVED_FLAGS="$SAVED_FLAGS --with-python"; PY_INFERRED=1 ;;
  esac
fi
REPEATED=""
for flag in $SAVED_FLAGS; do
  case "$flag" in --no-shim|--no-packages|--no-auth-lock|--no-tools|--no-patch|--with-python|--with-pypi-index) ;; *) continue ;; esac
  case " $GIVEN_FLAGS " in *" $flag "*) continue ;; esac
  case " ${DROPPED_FLAGS:-} " in *" $flag "*) continue ;; esac
  GIVEN_FLAGS="${GIVEN_FLAGS:+$GIVEN_FLAGS }$flag"; REPEATED="$REPEATED $flag"
done
for flag in $GIVEN_FLAGS; do apply_flag "$flag"; done
case "$SAVED_TOOLS" in *[!a-z,-]*) SAVED_TOOLS="" ;; esac
if [ -z "${ELM_PI_TOOLS:-}" ] && [ -n "$SAVED_TOOLS" ]; then
  ELM_PI_TOOLS="$SAVED_TOOLS"; REPEATED="$REPEATED ELM_PI_TOOLS=$SAVED_TOOLS"
fi
say "install options"
if [ -n "$REPEATED" ]; then
  echo "    repeating${REPEATED}, from $OPTIONS_FROM"
  echo "    (to drop one: re-run with --reset-options and only the flags you want)"
fi
echo "    this install: ${GIVEN_FLAGS:-the defaults}${ELM_PI_TOOLS:+, ELM_PI_TOOLS=$ELM_PI_TOOLS}"
[ "${PY_INFERRED:-0}" = "0" ] || echo "    (agent/python was already here, so it is kept as --with-python; --no-python removes it)"
# install.sh passes the branch and repository it fetched; any other run keeps
# what was recorded. Values with whitespace in them are not a branch or a URL.
OPT_BRANCH="${ELM_PI_BRANCH:-$(saved_option branch)}"
OPT_REPO="${ELM_PI_REPO:-$(saved_option repo)}"
case "$OPT_BRANCH" in *[[:space:]]*) OPT_BRANCH="" ;; esac
case "$OPT_REPO" in *[[:space:]]*) OPT_REPO="" ;; esac
mkdir -p agent
{
  echo "# The options this install was made with. Written by bootstrap.sh and repeated"
  echo "# by every later run (pi update, pi update --extensions, the installer)."
  echo "# To change them: ./bootstrap.sh --reset-options [the flags you want]"
  echo "flags=$GIVEN_FLAGS"
  echo "tools=${ELM_PI_TOOLS:-}"
  echo "branch=$OPT_BRANCH"
  echo "repo=$OPT_REPO"
} > "$OPTIONS_FILE.tmp" && mv -f "$OPTIONS_FILE.tmp" "$OPTIONS_FILE"

# Before anything runs pi: jiti searches every ancestor of the install for
# packages, so a node_modules above it would be loaded into pi - by the cache
# warm-up and the checks below as much as by the launcher, which refuses to
# start while one exists.
EXTERNAL_MODULES="$(elm_external_module_dirs "$HERE")"
if [ -n "$EXTERNAL_MODULES" ] && [ "${ELM_PI_ALLOW_EXTERNAL_MODULES:-0}" != "1" ]; then
  warn "node_modules outside this install, in a directory above it:"
  printf '%s\n' "$EXTERNAL_MODULES" | sed 's/^/      /'
  die "packages there would be loaded into pi. Move or delete them (usually an \`npm install\` run in the wrong place), or set ELM_PI_ALLOW_EXTERNAL_MODULES=1"
fi

# Not NODE_VERSION: official Node container images and some CI runners export
# that for their own Node, without the leading v, and it used to be read here.
NODE_VERSION="${ELM_PI_NODE_VERSION:-$(elm_py "$CONFIG_TOOL" --root "$HERE" value nodeVersion)}"
case "$NODE_VERSION" in v[0-9]*.[0-9]*.[0-9]*) ;; *) die "Node version \"$NODE_VERSION\" is not of the form v24.1.0" ;; esac
# PI_VERSION=1.4.0 ./bootstrap.sh installs exactly that pi, over both
# config/versions.json and --update (see stage_manifest). Unset, the version
# comes from those.
PI_VERSION="${PI_VERSION:-}"

# macOS ships shasum, most Linux distros ship sha256sum. Pick before piping:
# a missing binary inside a pipeline still exits 0 through awk.
#
# Resolved once, and reported by return code rather than by `die`: this only
# ever runs inside `$( )`, where `die` exits the subshell and leaves the script
# running with an empty hash. That then failed as "checksum mismatch", which
# sends whoever hits it looking for a corrupted download instead of a missing
# tool. Callers turn a non-zero return into the accurate message.
if command -v sha256sum >/dev/null 2>&1; then
  SHA256_CMD=(sha256sum)
elif command -v shasum >/dev/null 2>&1; then
  SHA256_CMD=(shasum -a 256)
else
  SHA256_CMD=()
fi
sha256_of() {
  if [ "${#SHA256_CMD[@]}" -eq 0 ]; then
    echo "neither sha256sum nor shasum is installed" >&2
    return 1
  fi
  "${SHA256_CMD[@]}" "$1" | awk '{print $1}'
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
  TMP="$(mktemp -d)"
  echo "    downloading $TAR"
  curl -q -fsSL -o "$TMP/$TAR" "https://nodejs.org/dist/$NODE_VERSION/$TAR"
  curl -q -fsSL -o "$TMP/SHASUMS256.txt" "https://nodejs.org/dist/$NODE_VERSION/SHASUMS256.txt"
  want=$(grep " $TAR\$" "$TMP/SHASUMS256.txt" | awk '{print $1}')
  got=$(sha256_of "$TMP/$TAR") || die "cannot verify $TAR without a sha256 tool"
  if [ -z "$want" ] || [ "$want" != "$got" ]; then die "checksum mismatch for $TAR"; fi
  rm -rf .node && mkdir -p .node
  tar -xzf "$TMP/$TAR" -C .node --strip-components=1
  echo "    installed $(.node/bin/node --version)"
fi
# elm_install_env already put .node/bin first; prove it rather than assume it.
[ "$(command -v node)" = "$HERE/.node/bin/node" ] || die "node resolves to $(command -v node), not the bundled $HERE/.node/bin/node"
[ -f "$HERE/.node/lib/node_modules/npm/bin/npm-cli.js" ] || die "the bundled npm is missing from .node - delete .node and re-run"
NPM_PROBLEM="$(elm_npm_verify "$HERE")" || die "npm is not isolated to this install: $NPM_PROBLEM"
echo "    npm: config/npmrc, cache .npm-cache, global prefix .node (nothing from ~/.npmrc or ~/.npm)"

# --- 2. pi ------------------------------------------------------------------
say "pi coding agent"

PI_INSTALLED=""
if [ -f node_modules/@earendil-works/pi-coding-agent/package.json ]; then
  PI_INSTALLED=$("$HERE/.node/bin/node" -p \
    'require("./node_modules/@earendil-works/pi-coding-agent/package.json").version' \
    2>/dev/null) || PI_INSTALLED=""
fi

# The versions this repo last ran its checks against are in config/versions.json,
# and every install takes them except --update - which is what `pi update` runs,
# and takes whatever npm calls latest. PI_VERSION overrides pi itself for one
# run. A pin is part of what each tree is stamped with (manifest_digest), so a
# pull that moves one rebuilds that tree at the next run; one that moves none
# leaves a tree on whatever it has, `pi update`'s latest included.
PINS=(elm_py "$HERE/scripts/pin_versions.py" --versions "$HERE/config/versions.json")
stage_manifest() {   # $1 = manifest, $2 = staging dir, $3 = section of versions.json
  local update=()
  [ "$UPDATE" != "1" ] || update=(--update)
  "${PINS[@]}" stage "$HERE/$1" "$2/package.json" "$3" ${update[@]+"${update[@]}"} --pi-version "$PI_VERSION"
}
# What a tree was built from: its manifest and its section of versions.json.
# Each tree is stamped with this, so a pull that moves only a pin rebuilds it.
manifest_digest() {   # $1 = manifest, $2 = section of versions.json
  "${PINS[@]}" digest "$HERE/$1" "$2"
}

# Reinstalling pi is the slowest step in this script, so it runs only when
# something changed. The digest catches an edited dependency list or a moved
# pin in config/versions.json; nothing can catch "latest" moving on the
# registry, which is what --update and --force are for.
#
# --force-packages (`pi update --extensions`) means "back to the tested set",
# and extension packages tested against one pi are not a tested set beside
# another: so it also brings pi back to its pin when `pi update` moved it on.
CORE_MANIFEST_DIGEST="$(manifest_digest package.json core)" || die "cannot hash package.json"
CORE_STAMP="node_modules/.elm-pi-lock.sha256"
PI_TESTED="$("${PINS[@]}" pinned core @earendil-works/pi-coding-agent)" || die "cannot read config/versions.json"
NEED_PI=0
if [ "$FORCE" = "1" ] || [ "$UPDATE" = "1" ] || [ -z "$PI_INSTALLED" ]; then
  NEED_PI=1
elif [ -n "$PI_VERSION" ] && [ "$PI_VERSION" != "$PI_INSTALLED" ]; then
  echo "    $PI_INSTALLED -> $PI_VERSION"
  NEED_PI=1
elif [ "$FORCE_PACKAGES" = "1" ] && [ -n "$PI_TESTED" ] && [ "$PI_TESTED" != "$PI_INSTALLED" ]; then
  echo "    $PI_INSTALLED -> $PI_TESTED, the tested version (--force-packages)"
  NEED_PI=1
elif [ ! -f "$CORE_STAMP" ] || [ "$(cat "$CORE_STAMP" 2>/dev/null)" != "$CORE_MANIFEST_DIGEST" ]; then
  echo "    dependency list changed"
  NEED_PI=1
fi

if [ "$NEED_PI" = "1" ]; then
  CORE_STAGE="$(mktemp -d "$HERE/.elm-pi-stage-core.XXXXXX")"
  stage_manifest package.json "$CORE_STAGE" core
  ( cd "$CORE_STAGE" && elm_npm install --omit=dev --ignore-scripts --no-audit --no-fund \
      --fetch-retries=5 --fetch-retry-maxtimeout=60000 --loglevel=error )
  if [ "$WITH_PATCH" = "1" ]; then
    elm_py "$HERE/patch-pi.py" --bundle "$CORE_STAGE/node_modules/@earendil-works/pi-coding-agent/dist/bundle" \
      || die "could not disable /share and /bug in the staged pi release"
  fi
  "$HERE/.node/bin/node" "$CORE_STAGE/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js" --version >/dev/null \
    || die "the staged pi release does not start"
  printf '%s\n' "$CORE_MANIFEST_DIGEST" > "$CORE_STAGE/node_modules/.elm-pi-lock.sha256"
  CORE_OLD="$HERE/.elm-pi-old-core.$$"
  [ ! -d node_modules ] || mv node_modules "$CORE_OLD"
  if ! mv "$CORE_STAGE/node_modules" node_modules; then
    [ ! -d "$CORE_OLD" ] || mv "$CORE_OLD" node_modules
    die "could not activate the staged pi release"
  fi
  rm -rf "$CORE_STAGE"
  CORE_STAGE=""
else
  echo "    pi $PI_INSTALLED, dependency list and pins unchanged (pi update moves to the latest release)"
fi




echo "    $("$HERE/.node/bin/node" node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js --version 2>/dev/null || echo installed)"
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
  elm_py "$HERE/patch-pi.py" || die "could not disable /share and /bug - see patch-pi.py"
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
mkdir -p agent/extensions/subagent agent/extensions/pi-permission-system \
         agent/config/pi-task-models agent/prompts agent/agents
[ -f "$HERE/lib/state.sh" ] || die "lib/state.sh is missing"
. "$HERE/lib/state.sh"
elm_secure_install_state "$HERE"
# The launcher starts this interpreter rather than searching again on every
# launch; lib/sandbox.sh re-validates it on the next install.
printf '%s\n' "$ELM_PI_PYTHON" > agent/python-path
elm_py "$CONFIG_TOOL" --root "$HERE" init
install_if_absent() {   # never clobber a config someone has tuned
  if [ -f "$2" ]; then
    echo "    keeping existing $2"
  else
    elm_py "$CONFIG_TOOL" --root "$HERE" render "$1" "$2"
    echo "    wrote $2"
  fi
}
# Code is refreshed, config is kept. Everything below is code or policy this
# repo owns - the ELM-only guard, the write protections, the delegation rules,
# the agent definitions - so a re-install picks up whatever the repo now says
# without needing --update. Config you tune (settings.json, models.json,
# web-search.json, the extension configs) is install_if_absent instead, with
# only the keys this repo decides reapplied over the top further down.
REQUIRED_EXTENSIONS="$(elm_py -c 'import json; print(" ".join(json.load(open("config/elm-pi.json"))["requiredExtensions"]))')"
# --no-shim removes the shim's extension here, before anything loads or checks
# the set: it used to be rendered, loaded by the warm-up and passed by the
# checks, and only then deleted. scripts/verify_install.py reads --no-shim
# from agent/install-options and does not count it missing.
if [ "$WITH_SHIM" != "1" ]; then
  _kept=""
  for f in $REQUIRED_EXTENSIONS; do [ "$f" = "elm-shim.ts" ] || _kept="$_kept $f"; done
  REQUIRED_EXTENSIONS="$_kept"
  rm -f agent/extensions/elm-shim.ts
fi
for f in $REQUIRED_EXTENSIONS; do
  [ -f "templates/extensions/$f" ] || continue
  elm_py "$CONFIG_TOOL" --root "$HERE" render \
    "templates/extensions/$f" "agent/extensions/$f"
done
if [ "$WITH_SHIM" = "1" ]; then
  echo "    refreshed required agent extensions (policy, protections, tools, shim)"
else
  echo "    refreshed required agent extensions (policy, protections, tools; no shim)"
fi
for f in $REQUIRED_EXTENSIONS; do
  [ -f "agent/extensions/$f" ] || die "required policy extension was not installed: $f"
done
install_if_absent templates/extensions/subagent/config.json agent/extensions/subagent/config.json
# The permission gate's policy. @AGENT_DIR@ marks this install as pi's own
# infrastructure, so reading its node_modules does not trip the outside-cwd
# prompt. Never clobbered once written: this is a policy file people tune -
# though `permission` is reapplied from templates/ further down, so a rule
# added there reaches installs that already exist.
#
# Two keys do that job and they are not interchangeable.
# piInfrastructureReadPaths auto-allows reads, but only for the four tools the
# package counts as read-only - read, find, grep and ls. A `bash: cat` of the
# same path is not one of them: it goes to the external_directory_read surface
# and hits the `"*": "ask"` catch-all, which is the prompt people actually see.
# So a path that should never prompt needs a line in external_directory_read as
# well, and entries there are matched last-wins, so the specific ones go after
# the catch-all.
if [ -f agent/extensions/pi-permission-system/config.json ]; then
  echo "    keeping existing agent/extensions/pi-permission-system/config.json"
else
  sed -e "s|@AGENT_DIR@|$HERE/agent|g" -e "s|@INSTALL_DIR@|$HERE|g" \
    templates/extensions/pi-permission-system/config.json \
    > agent/extensions/pi-permission-system/config.json
  echo "    wrote agent/extensions/pi-permission-system/config.json"
fi
# Agent definitions are code, not config: pi-subagents discovers them in
# agent/agents, and `subagent qwen "..."` fails with "Unknown agent" without
# them. Refreshed on --update like the extensions.
# @AGENT_DIR@ becomes the real path, for any agent field that needs one. The
# agent definitions deliberately declare no `tools` allowlist: such a list is
# filtered against the host's builtin registry, and pi-hashline-edit-pro
# replaces the builtin `read`, so naming `read` there loses it. See AGENTS.md.
for f in templates/agents/*.md; do
  [ -e "$f" ] || continue
  AGENT_DEST="agent/agents/$(basename "$f")"
  elm_py "$CONFIG_TOOL" --root "$HERE" render "$f" "$AGENT_DEST"
  sed -e "s|@AGENT_DIR@|$HERE/agent|g" "$AGENT_DEST" > "$AGENT_DEST.tmp"
  mv "$AGENT_DEST.tmp" "$AGENT_DEST"
done
echo "    refreshed agent/agents/*.md (model pinning, tools, delegation briefs)"
# pi-auto-compact routes compaction through pi-task-models' "balanced" profile.
# Qwen primary, Llama fallback: compaction is lossy - a bad summary loses
# session context permanently - so the capable model does it and the small one
# only catches a rate limit.
install_if_absent templates/config/pi-task-models/config.json agent/config/pi-task-models/config.json
mkdir -p agent/config/pi-auto-compact
install_if_absent templates/config/pi-auto-compact/config.json agent/config/pi-auto-compact/config.json
install_if_absent templates/settings.json              agent/settings.json
install_if_absent templates/models.json                agent/models.json
elm_py "$CONFIG_TOOL" --root "$HERE" render templates/AGENTS.md agent/AGENTS.md
# Detail AGENTS.md points to rather than carries: it is sent with every request,
# so a section needed now and then costs its length on all of them. Replaced
# whole each run, so a file the repo drops does not linger.
rm -rf agent/reference && mkdir -p agent/reference
for ref in templates/reference/*.md; do
  elm_py "$CONFIG_TOOL" --root "$HERE" render "$ref" "agent/reference/${ref##*/}"
done
# Who the users are and how to work with them (peers, Python 3/C++, evidence
# over assumption, ask about unknowns, report with units and uncertainty).
# pi appends it to the main session's system prompt, ahead of AGENTS.md, and
# workflow agents load it too; pi-subagents children do not (since 0.79.2), so
# templates/agents/*.md carry the rules they need.
elm_py "$CONFIG_TOOL" --root "$HERE" render templates/APPEND_SYSTEM.md agent/APPEND_SYSTEM.md
# Skills: pi lists each one's name and description in the system prompt and
# loads the body only when a task calls for it, so the orchestration detail and
# the physics methods cost nothing until used. Refreshed every run like the
# extensions. agent/skills/.elm-pi-managed lists the ones this repo owns, so a
# skill removed from templates/ is removed here too and one you added yourself
# is never touched.
mkdir -p agent/skills
SKILLS_MANIFEST=agent/skills/.elm-pi-managed
if [ -f "$SKILLS_MANIFEST" ]; then
  while IFS= read -r old_skill; do
    case "$old_skill" in ""|*/*|.*) continue ;; esac
    [ -d "templates/skills/$old_skill" ] || rm -rf "agent/skills/$old_skill"
  done < "$SKILLS_MANIFEST"
fi
: > "$SKILLS_MANIFEST"
for skill_dir in templates/skills/*/; do
  skill="$(basename "$skill_dir")"
  [ -f "$skill_dir/SKILL.md" ] || continue
  rm -rf "agent/skills/$skill" && mkdir -p "agent/skills/$skill"
  cp -R "$skill_dir". "agent/skills/$skill/"
  elm_py "$CONFIG_TOOL" --root "$HERE" render "$skill_dir/SKILL.md" "agent/skills/$skill/SKILL.md"
  printf '%s\n' "$skill" >> "$SKILLS_MANIFEST"
done
echo "    refreshed agent/skills ($(wc -l < "$SKILLS_MANIFEST" | tr -d ' ') skills)"
echo "    refreshed agent/AGENTS.md and agent/reference/"
install_if_absent templates/web-search.json            agent/web-search.json
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
# workflow-check: the pi-dynamic-workflows parser as a command, so the agent can
# find a syntax error by line before sending a script to the `workflow` tool.
ln -sfn "$HERE/scripts/workflow-check" agent/bin/workflow-check
# conda-search: conda-forge by package name (prefix.dev's API), beside pixi.
ln -sfn "$HERE/scripts/conda-search" agent/bin/conda-search
echo "    agent/bin/pi -> $HERE/pi (sub-agent children)"
# brew: the machine's Homebrew, with approved installs run past the egress proxy
# (scripts/brew says why). Linked only where Homebrew exists, so `command -v
# brew` keeps telling the agent the truth.
rm -f agent/bin/brew
while IFS= read -r _d; do
  if [ -n "$_d" ] && [ -x "$_d/brew" ]; then
    ln -sfn "$HERE/scripts/brew" agent/bin/brew
    echo "    agent/bin/brew -> scripts/brew (Homebrew at $_d)"
    break
  fi
done < <(elm_clean_path "${ELM_PI_USER_PATH:-$PATH}" | tr ':' '\n'; printf '%s\n' /opt/homebrew/bin /usr/local/bin /home/linuxbrew/.linuxbrew/bin)
if [ "$AUTH_LOCK" = "1" ]; then
  # /login writes the credential it obtains to agent/auth.json. Read-only means
  # that write fails, so a commercial subscription cannot be attached to this
  # install even by someone who has one. Verified: normal startup and ELM use
  # are unaffected. Undo with: chmod 600 agent/auth.json
  elm_set_auth_mode agent/auth.json 0
  echo "    agent/auth.json is read-only (/login cannot store credentials)"
else
  elm_set_auth_mode agent/auth.json 1
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
#   - uv          Python interpreters, environments and packages - builds the
#                 agent's own Python below, and installs into it later
#   - mlr         Miller: CSV/TSV/JSON reshaping, sorting and stats in one pass
#   - resvg       SVG to PNG with no system libraries, so view-outputs can show
#                 the agent an SVG figure on any host
#   - pixi        conda-forge packages - GDAL, HDF5, ROOT, Ghostscript, ffmpeg,
#                 compilers - without sudo, kept in agent/pixi (the launcher
#                 sets PIXI_HOME); `pixi exec` runs one without installing it
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
#   ELM_PI_TOOL_CACHE=/path where verified archives are kept between installs
#                           (default ~/.cache/elm-pi/tools)
#   ELM_PI_TOOLS=fd,rg,jq   install a subset - shellcheck and ast-grep are 35MB
#                           and 51MB respectively, the other four total ~23MB
#   FD_VERSION=10.5.0   pin any of them      (checksums: templates/tools.sha256)
#   RG_VERSION=15.2.0   JQ_VERSION=1.8.2     YQ_VERSION=4.53.6
#   SHELLCHECK_VERSION=0.11.0                ASTGREP_VERSION=0.45.3
#   UV_VERSION=0.12.24  MLR_VERSION=6.22.0   RESVG_VERSION=0.48.1
#   PIXI_VERSION=0.82.0
if [ "$WITH_TOOLS" = "1" ]; then
  TOOLSET="${ELM_PI_TOOLS:-fd,rg,jq,yq,shellcheck,ast-grep,uv,mlr,resvg,pixi}"
  want_tool() { case ",$TOOLSET," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }
  say "command-line tools (${TOOLSET//,/, })"
  # Three projects, three naming schemes: Rust triples, Go's os_arch, and jq's
  # own spelling of macOS.
  case "$(uname -s)" in
    Darwin) RUST_OS=apple-darwin      ; GNU_OS=apple-darwin        ; GO_OS=darwin ; JQ_OS=macos ; RESVG_OS=macos ; RESVG_EXT=zip ;;
    Linux)  RUST_OS=unknown-linux-musl; GNU_OS=unknown-linux-gnu   ; GO_OS=linux  ; JQ_OS=linux ; RESVG_OS=linux ; RESVG_EXT=tar.gz ;;
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
  UV_VERSION="${UV_VERSION:-0.12.24}"
  MLR_VERSION="${MLR_VERSION:-6.22.0}"
  RESVG_VERSION="${RESVG_VERSION:-0.48.1}"
  PIXI_VERSION="${PIXI_VERSION:-0.82.0}"

  # Archives are cached per user, keyed tool/version/asset, so a second install
  # - a new prefix, another machine account, a rebuilt install - extracts what
  # is already on disk instead of fetching 105MB again. Each install still gets
  # its own binaries in agent/bin: the cache saves the download, not the
  # ownership. Cache hits are checksummed on every reuse, exactly like a fresh
  # download, so a corrupted or tampered entry fails the same way.
  TOOL_CACHE="${ELM_PI_TOOL_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/elm-pi/tools}"

  TOOLS_TMP="$(mktemp -d)"

  install_tool() {   # $1 binary  $2 version  $3 asset  $4 url  $5 sha256 url ("" if none)
    local bin="$1" version="$2" asset="$3" url="$4" shaurl="$5"
    local dest="agent/bin/$bin" want got found
    local cached="$TOOL_CACHE/$bin/$version/$asset" from_cache=0
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
    if [ "$FORCE" != "1" ] && [ -s "$cached" ]; then
      # --force deliberately bypasses the cache: it means "fetch it again".
      echo "    $asset from the tool cache"
      cp -f "$cached" "$TOOLS_TMP/$asset"
      from_cache=1
    else
      echo "    downloading $asset"
      if ! curl -q -fsSL -o "$TOOLS_TMP/$asset" "$url"; then
        warn "could not download $asset - $bin not installed"
        return 0
      fi
    fi
    # Pinned versions are checksummed here, the way the Node tarball is. A
    # version someone pinned by hand falls back to the project's own published
    # checksum, and installs with a warning when there is none to be had.
    want="$(awk -v a="$bin/$version/$asset" '$2 == a {print $1}' templates/tools.sha256 2>/dev/null | head -1)"
    if [ -z "$want" ] && [ -n "$shaurl" ]; then
      want="$(curl -q -fsSL "$shaurl" 2>/dev/null \
              | awk -v a="$asset" '$2 == a {print $1; exit} NF == 1 {print $1; exit}')"
    fi
    got="$(sha256_of "$TOOLS_TMP/$asset")" || die "cannot verify $asset without a sha256 tool"
    if [ -n "$want" ]; then
      [ "$want" = "$got" ] || die "checksum mismatch for $asset"
    else
      warn "no published checksum for $asset - installing unverified ($got)"
    fi
    # Verified: keep it for the next install. A cache we cannot write is not
    # worth failing over.
    if [ "$from_cache" = "0" ] && mkdir -p "$(dirname "$cached")" 2>/dev/null; then
      cp -f "$TOOLS_TMP/$asset" "$cached" 2>/dev/null || true
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
  # The archive also has uvx, which is only `uv tool run`.
  install_tool uv "$UV_VERSION" "uv-$TRIPLE.tar.gz" \
    "$GH/astral-sh/uv/releases/download/$UV_VERSION/uv-$TRIPLE.tar.gz" \
    "$GH/astral-sh/uv/releases/download/$UV_VERSION/uv-$TRIPLE.tar.gz.sha256"
  install_tool mlr "$MLR_VERSION" "miller-$MLR_VERSION-$GO_OS-$GO_ARCH.tar.gz" \
    "$GH/johnkerl/miller/releases/download/v$MLR_VERSION/miller-$MLR_VERSION-$GO_OS-$GO_ARCH.tar.gz" \
    "$GH/johnkerl/miller/releases/download/v$MLR_VERSION/miller-$MLR_VERSION-checksums.txt"
  # resvg publishes no build for 64-bit ARM Linux before 0.49; there it is
  # skipped with a warning and view-outputs falls back to the system's tools.
  # The Linux build links glibc, like ast-grep's.
  install_tool resvg "$RESVG_VERSION" "resvg-$RESVG_OS-$RUST_ARCH.$RESVG_EXT" \
    "$GH/linebender/resvg/releases/download/v$RESVG_VERSION/resvg-$RESVG_OS-$RUST_ARCH.$RESVG_EXT" ""
  install_tool pixi "$PIXI_VERSION" "pixi-$TRIPLE.tar.gz" \
    "$GH/prefix-dev/pixi/releases/download/v$PIXI_VERSION/pixi-$TRIPLE.tar.gz" \
    "$GH/prefix-dev/pixi/releases/download/v$PIXI_VERSION/pixi-$TRIPLE.tar.gz.sha256"
  echo "    agent/bin is $(du -sh agent/bin 2>/dev/null | awk '{print $1}'), cache $(du -sh "$TOOL_CACHE" 2>/dev/null | awk '{print $1}' || echo 0B) in $TOOL_CACHE"
else
  say "command-line tools"
  echo "    skipped (--no-tools): the system's own fd/rg/jq/... are used instead"
fi

# --- 3c. the agent's Python ---------------------------------------------------
# A researcher's machine may have no Python with numpy in it, or one that
# belongs to a conda env the agent should not install into - and nothing could
# be installed from a session. So the agent gets its own: a CPython that uv
# downloads (python-build-standalone, no system libraries needed), a venv with
# pip seeded, and python.packages from config/elm-pi.json. The launcher puts it
# on PATH unless pi was started from a venv or a non-base conda env, and the
# egress proxy lets PyPI through (proxyAllow), so the agent can add packages
# to it in any session. Everything is in agent/python - rm -rf takes the lot.
#
# Re-runs keep the environment and whatever the agent installed into it; the
# configured packages are installed again when the list, the Python version or
# uv changes, upgraded by --update, and reinstalled by --force.
#
# Opt-in: --with-python (or `pi setup --python`), recorded like the other
# install options. --no-python takes it back and removes agent/python - the
# packages the agent installed with it.
if [ "$WITH_PYTHON" = "1" ]; then
  say "the agent's Python (agent/python)"
  if [ ! -x agent/bin/uv ]; then
    warn "uv is not in agent/bin (--no-tools, or ELM_PI_TOOLS without uv) - skipped"
  else
    # The account's uv settings are not this install's: no uv.toml, no index or
    # cache variables from the shell.
    for _v in $(compgen -e | grep '^UV_' || true); do unset "$_v"; done
    export UV_NO_CONFIG=1
    export UV_PYTHON_INSTALL_DIR="$HERE/agent/python/interpreters"
    export UV_CACHE_DIR="$HERE/agent/python/cache"
    PY_ENV="agent/python/env"
    PY_VERSION="$(elm_py "$CONFIG_TOOL" --root "$HERE" value pythonVersion)" || die "cannot read python.version"
    PY_PACKAGES="$(elm_py "$CONFIG_TOOL" --root "$HERE" value pythonPackages)" || die "cannot read python.packages"
    PY_STAMP="agent/python/.elm-pi-packages"
    PY_WANT="$PY_VERSION $("agent/bin/uv" --version 2>/dev/null) $PY_PACKAGES"
    if [ ! -x "$PY_ENV/bin/python" ]; then
      echo "    CPython $PY_VERSION (uv-managed) and a venv in $PY_ENV"
      agent/bin/uv venv --quiet --seed --managed-python --python "$PY_VERSION" "$PY_ENV" \
        || die "could not create the agent's Python environment (re-run, or take it back with --no-python)"
    fi
    if [ "$FORCE" = "1" ] || [ "$UPDATE" = "1" ] || [ "$(cat "$PY_STAMP" 2>/dev/null)" != "$PY_WANT" ]; then
      _upgrade=()
      [ "$UPDATE" = "1" ] && _upgrade=(--upgrade)
      [ "$FORCE" = "1" ] && _upgrade=(--reinstall)
      echo "    installing: $PY_PACKAGES"
      # shellcheck disable=SC2086 # the package list is words by design
      if agent/bin/uv pip install --quiet --python "$PY_ENV/bin/python" ${_upgrade[@]+"${_upgrade[@]}"} $PY_PACKAGES; then
        printf '%s\n' "$PY_WANT" > "$PY_STAMP"
      else
        warn "some packages did not install; the environment works, and the next run tries again"
      fi
    else
      echo "    $PY_ENV: Python $PY_VERSION, packages unchanged"
    fi
    echo "    $("$PY_ENV/bin/python" --version 2>&1), $(du -sh agent/python 2>/dev/null | awk '{print $1}') in agent/python"
  fi
elif [ -d agent/python ]; then
  say "the agent's Python"
  rm -rf agent/python
  echo "    removed agent/python (not --with-python): the agent uses the python3 on PATH"
fi

# --- 3d. an offline search of PyPI (--with-pypi-index) ------------------------
# PyPI has no search API any more: `pip search` fails, and pypi.org/search is a
# JavaScript challenge. So "is there a package for X" needed the web, which a
# normal session does not have. This builds agent/pypi-index.db - name, summary,
# keywords and classifiers of every package, in an SQLite full-text index - from
# a published snapshot of PyPI's metadata (pypiIndex in config/elm-pi.json),
# and links `pypi-search` into agent/bin. The snapshot is pinned to a revision
# and each file checked against its published sha256; the ~1GB download is
# deleted once the index is built, and repeated only when the revision changes
# or with --force. Opt-in, and recorded like the --no-* flags; without it any
# index an earlier run built is removed.
if [ "$WITH_PYPI_INDEX" = "1" ]; then
  say "offline PyPI search (agent/pypi-index.db)"
  PYPI_DB="agent/pypi-index.db"
  AGENT_PY="agent/python/env/bin/python"
  read -r PYPI_DATASET PYPI_REVISION PYPI_FOLDER < <(elm_py -c 'import json; c = json.load(open("config/elm-pi.json"))["pypiIndex"]; print(c["dataset"], c["revision"], c["folder"])') \
    || die "cannot read pypiIndex from config/elm-pi.json"
  # The build reads Parquet, which takes pyarrow: the agent's Python has it.
  if [ ! -x "$AGENT_PY" ]; then
    warn "needs the agent's Python (it has pyarrow), which did not build - skipped"
  else
    # Read-only: a plain connect would create an empty file that then passes for an index.
    PYPI_HAVE="$("$AGENT_PY" -I -c 'import sqlite3, sys; print(sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True).execute("SELECT value FROM meta WHERE key = ?", ("revision",)).fetchone()[0])' "$PYPI_DB" 2>/dev/null || true)"
    if [ "$FORCE" != "1" ] && [ "$PYPI_HAVE" = "$PYPI_REVISION" ]; then
      echo "    $PYPI_DB: $PYPI_DATASET at ${PYPI_REVISION:0:7}, unchanged"
    else
      PYPI_TMP="$(mktemp -d "$HERE/agent/.pypi-download.XXXXXX")"
      mkdir -p "$PYPI_TMP/data"
      HF=https://huggingface.co
      pypi_ok=1
      echo "    downloading $PYPI_DATASET at ${PYPI_REVISION:0:7} (~1GB, deleted after the build)"
      if curl -q -fsSL -o "$PYPI_TMP/tree.json" "$HF/api/datasets/$PYPI_DATASET/tree/$PYPI_REVISION/$PYPI_FOLDER"; then
        while read -r want path; do
          file="$PYPI_TMP/data/${path##*/}"
          if ! curl -q -fsSL --retry 3 -o "$file" "$HF/datasets/$PYPI_DATASET/resolve/$PYPI_REVISION/$path"; then
            warn "could not download $path"; pypi_ok=0; break
          fi
          [ "$(sha256_of "$file")" = "$want" ] || die "checksum mismatch for $path"
        done < <(elm_py -c 'import json, sys; [print(f["lfs"]["oid"], f["path"]) for f in json.load(open(sys.argv[1])) if f["path"].endswith(".parquet")]' "$PYPI_TMP/tree.json")
      else
        warn "could not list the files of $PYPI_DATASET"; pypi_ok=0
      fi
      if [ "$pypi_ok" = "1" ] && ls "$PYPI_TMP"/data/*.parquet >/dev/null 2>&1; then
        "$AGENT_PY" -I scripts/pypi_index.py build "$PYPI_TMP/data" "$PYPI_DB" \
          --dataset "$PYPI_DATASET" --revision "$PYPI_REVISION" \
          || warn "the index did not build; the next run tries again"
      else
        warn "no index built this run${PYPI_HAVE:+ (the existing one is kept)}; the next run tries again"
      fi
      rm -rf "$PYPI_TMP"; PYPI_TMP=""
    fi
    if [ -s "$PYPI_DB" ]; then
      ln -sfn "$HERE/scripts/pypi-search" agent/bin/pypi-search
      echo "    agent/bin/pypi-search -> scripts/pypi-search"
    fi
  fi
elif [ -e agent/pypi-index.db ] || [ -L agent/bin/pypi-search ]; then
  rm -f agent/pypi-index.db agent/bin/pypi-search
  echo "    removed the offline PyPI index (this install is not --with-pypi-index)"
fi

# --- installer-owned settings ------------------------------------------------
# agent/ is yours to tune, with one exception: some values are decisions this
# repo makes, usually for a measured or documented reason, and a re-install has
# to be able to change its mind about them. Worktree isolation is the worked
# example - it went on, then came back off once it proved to need a git
# repository - and install_if_absent would have kept the stale `true` on every
# existing install for ever.
#
# So every run compares the live file against templates/, prints anything you
# have changed, and then applies the repo's decision over the top. Nothing is
# overwritten silently. Every other key in those files - theme, model,
# concurrency, search routing, your own additions - is left exactly as it is.
# To change a decision permanently, change templates/, not agent/.
say "installer-owned settings"
HERE="$HERE" elm_py - <<'PYX'
import json, os, collections

HERE = os.environ["HERE"]
models_path = os.path.join(HERE, "agent", "model-ids.json")
model_ids = json.load(open(models_path))

# file -> keys this repo decides. The reason for each is in the file it
# belongs to; the short version is in the comment beside it.
OWNED = {
    "settings.json": (
        "extensions",            # where local extensions are discovered
        "compaction",            # off: pi-auto-compact owns compaction
        "subagents",             # model tiering, fallbacks, ELM-only modelScope
        "sessionDir",            # per-project .pi/sessions, not one central pile
        "defaultThinkingLevel",  # off: measured ~400x slower here for no gain
        "retry",                 # gateway retry policy
        "defaultProjectTrust",   # never: a repo's .pi/ cannot load code or
                                 # override settings unless /trust says so
    ),
    "extensions/subagent/config.json": (
        "share",                 # false: `gh gist create` publishes a run
        "worktree",              # false: isolation needs git, so it is opt-in
        "worktreeProvider",
        "worktreeBaseDir",
        "maxSubagentSpawnsPerRun",
        "disabledFeatures",      # agent-management: the model cannot enable,
                                 # create or edit agents (e.g. the disabled
                                 # commercial-CLI builtins) through the tool
    ),
    "extensions/pi-permission-system/config.json": (
        "permission",            # the gate: outside-cwd, secrets, bash
        "piInfrastructureReadPaths",
    ),
    "config/pi-task-models/config.json": (
        "profiles",              # frontier/balanced/fast -> Qwen+think, Qwen, Llama
        "tasks",                 # compaction routed to balanced
    ),
    "config/pi-auto-compact/config.json": (
        "autoCompactThreshold",  # 70, the package's default: each compaction
                                 # re-sends the history uncached and the next
                                 # request starts cold, so compacting early
                                 # costs more than the context it frees. The
                                 # pinned-instructions extension keeps the
                                 # user's standing instructions out of summaries
    ),
    "web-search.json": (
        "pdf",                   # provider unpdf: keeps PDFs off Datalab/Gemini
    ),
}

def load(path):
    with open(path) as fh:
        raw = fh.read()
    raw = raw.replace("@QWEN_MODEL@", model_ids["qwen"])
    raw = raw.replace("@LLAMA_MODEL@", model_ids["llama"])
    return json.loads(raw, object_pairs_hook=collections.OrderedDict)

def brief(value):
    text = json.dumps(value)
    return text if len(text) <= 60 else text[:57] + "..."

for rel, keys in OWNED.items():
    tmpl_path = os.path.join(HERE, "templates", rel)
    live_path = os.path.join(HERE, "agent", rel)
    if not (os.path.exists(tmpl_path) and os.path.exists(live_path)):
        continue
    tmpl, live = load(tmpl_path), load(live_path)
    changed = []
    for key in keys:
        if key not in tmpl:
            continue
        raw = json.dumps(tmpl[key])
        raw = raw.replace("@AGENT_DIR@", os.path.join(HERE, "agent"))
        raw = raw.replace("@INSTALL_DIR@", HERE)
        want = json.loads(raw)
        if live.get(key) != want:
            changed.append((key, live.get(key), want))
            live[key] = want
    if changed:
        with open(live_path, "w") as fh:
            json.dump(live, fh, indent=2)
            fh.write("\n")
        print(f"    agent/{rel}")
        for key, was, now in changed:
            print(f"      {key}: yours {brief(was)} -> repo {brief(now)}")
    else:
        print(f"    agent/{rel} matches")

# models.json is not a key merge: configure.sh resolves the Qwen id from the
# gateway, so the ids are live data. The decision here is that exactly one
# Llama exists, the shim one - `configure.sh llama` re-adds a direct ELM entry
# that cannot call tools at all.
models_path = os.path.join(HERE, "agent", "models.json")
if os.path.exists(models_path):
    models = load(models_path)
    elm = models.get("providers", {}).get("elm", {})
    models_dirty = False
    # Three per-model keys are this repo's decisions, reapplied to the live Qwen
    # entry on every run because configure.sh preserves them:
    #   samplingParams                 the Qwen3.5 card's Instruct (non-thinking)
    #                                  profile - this install runs with thinking
    #                                  off - presence_penalty=1.5 included, against
    #                                  repetition loops. Verified accepted by the gateway.
    #   samplingParamsByThinkingLevel  the card's thinking-mode profile (0.6/0.95,
    #                                  presence_penalty 0) for when /thinking turns it on
    #   compat                         how the gateway takes the thinking switch. pi
    #                                  1.4.0 stopped accepting "reasoning_effort" as a
    #                                  thinkingFormat and dropped the whole elm
    #                                  provider over it, so an install updated without
    #                                  this would lose Qwen.
    tmpl_models = load(os.path.join(HERE, "templates", "models.json"))
    tmpl_qwen = tmpl_models["providers"]["elm"]["models"][0]
    for m in elm.get("models", []):
        if "qwen" not in m.get("id", "").lower():
            continue
        for key in ("samplingParams", "samplingParamsByThinkingLevel", "compat"):
            if key in tmpl_qwen and m.get(key) != tmpl_qwen[key]:
                print(f"    agent/models.json: {key} {json.dumps(m.get(key))} -> {json.dumps(tmpl_qwen[key])}")
                m[key] = tmpl_qwen[key]
                models_dirty = True

    strays = [m for m in elm.get("models", []) if "llama" in m.get("id", "").lower()]
    if strays or models_dirty:
        elm["models"] = [m for m in elm.get("models", []) if m not in strays]
        with open(models_path, "w") as fh:
            json.dump(models, fh, indent=2)
            fh.write("\n")
        for m in strays:
            print(f"    agent/models.json: removed elm/{m.get('id')} - it cannot call tools;")
            print("      the shim entry elm-shim/meta-llama/... is the supported one")
    else:
        print("    agent/models.json matches")
PYX

# --- workflow settings (pi-dynamic-workflows) --------------------------------
# The package reads agent/workflows/settings.json: since 3.14.0 it follows
# $PI_CODING_AGENT_DIR, which the launcher sets. Before that it read
# ~/.pi/workflows, and this wrote there too - into the account's own pi, which
# is not this install's to change. The keys below are reapplied every run;
# other keys in the file are left alone.
#   inheritMainModel              true: an agent with no model runs on the
#                                 session model, which is ELM
#   keywordTriggerEnabled         false: otherwise any message containing the
#                                 word "workflow" forces a fan-out
#   providerMiddlewareExtensions  workflow children load no extensions at all
#                                 by default - no permission gate, no protected
#                                 paths, no safety net. These are loaded into them.
#   defaultAgentTimeoutMs         30 min: without it a workflow agent has no
#                                 deadline at all, and one that stalls holds the
#                                 run open until someone notices. pi-subagents
#                                 puts the same 30-minute backstop on its runs.
#                                 There is deliberately no defaultTokenBudget:
#                                 nothing here measures what a normal run spends,
#                                 and a gate set by guesswork refuses real work.
# pi-hashline-edit-pro reads agent/hashline/config.json (the launcher exports
# PI_HASHLINE_DIR). requirePath makes every anchor edit name its file, which is
# what lets protected-paths.ts check it; copy and move are off because a move's
# destination comes from an anchor, not from the path it names.
mkdir -p agent/hashline
HERE="$HERE" elm_py - <<'PYHL'
import json, os
here = os.environ["HERE"]
want = json.load(open(os.path.join(here, "templates/hashline/config.json")))
path = os.path.join(here, "agent/hashline/config.json")
try:
    live = json.load(open(path))
except (OSError, ValueError):
    live = {}
changed = sorted(k for k, v in want.items() if live.get(k) != v)
live.update(want)
with open(path, "w") as fh:
    json.dump(live, fh, indent=2); fh.write("\n")
print("    agent/hashline/config.json: " + ("set " + ", ".join(changed) if changed else "matches"))
PYHL

say "workflow settings"
HERE="$HERE" elm_py - <<'PYWF'
import json, os

here = os.environ["HERE"]
want = json.load(open(os.path.join(here, "templates/workflows/settings.json")))
for path in (os.path.join(here, "agent", "workflows", "settings.json"),):
    try:
        live = json.load(open(path))
    except (OSError, ValueError):
        live = {}
    changed = {k: v for k, v in want.items() if live.get(k) != v}
    if changed:
        live.update(want)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            json.dump(live, fh, indent=2)
            fh.write("\n")
        print(f"    {path}: set {', '.join(sorted(changed))}")
    else:
        print(f"    {path} matches")
PYWF

# Build the extension package tree in a sibling staging directory and swap it in
# only once npm has finished and every listed package is present.
install_packages() {
  local pkg
  PKG_STAGE="$(mktemp -d "$HERE/.elm-pi-stage-packages.XXXXXX")"
  stage_manifest agent/npm/package.json "$PKG_STAGE" packages
  ( cd "$PKG_STAGE" && elm_npm install --ignore-scripts --no-audit --no-fund \
      --fetch-retries=5 --fetch-retry-maxtimeout=60000 --loglevel=error )
  # Package scripts stay disabled. Transitive packages still ship install
  # scripts (esbuild, protobufjs, tree-sitter-bash); none of them run.
  for pkg in $CHOSEN; do
    [ -d "$PKG_STAGE/node_modules/$pkg" ] || die "staged package is missing: $pkg"
  done
  printf '%s\n' "$PACKAGE_MANIFEST_DIGEST" > "$PKG_STAGE/node_modules/.elm-pi-lock.sha256"
  PKG_OLD="$HERE/.elm-pi-old-packages.$$"
  [ ! -d agent/npm/node_modules ] || mv agent/npm/node_modules "$PKG_OLD"
  if ! mv "$PKG_STAGE/node_modules" agent/npm/node_modules; then
    [ ! -d "$PKG_OLD" ] || mv "$PKG_OLD" agent/npm/node_modules
    die "could not activate the staged extension packages"
  fi
  rm -rf "$PKG_STAGE"
  PKG_STAGE=""
  echo "    installed into agent/npm/node_modules"
}

if [ "$WITH_PACKAGES" = "1" ]; then
  say "pi packages (sub-agents, web access, anchor editing)"
  mkdir -p agent/npm
  # Every loaded package is transpiled and imported at each launch. Measured CPU
  # cost per launch when three packages shipped: subagents+hashline ~1.6s,
  # web-access ~0.2s, against ~1.4s for pi and the local extensions alone; the
  # set is larger now. `pi --fast` skips all of them for one-shot work.
  #
  # Two lists, and they are not the same list. templates/packages.json is what
  # npm installs; templates/settings.json is what pi loads.
  #
  # agent/settings.json's "packages" is derived from the template every run
  # rather than filtered in place. Filtering in place could only ever remove:
  # an install that had once been run with --no-packages kept an empty list for
  # ever after, so a later run installed every package into agent/npm and
  # then loaded none of them. Everything else in that file is yours and is left
  # exactly as you left it.
  #
  # An entry is either "npm:name" or pi's object form, {"source": "npm:name",
  # "themes": [...]}, which narrows what loads from the package. The object
  # form is how awesome-pi-themes drops codex-slate.json, whose statusLine*
  # colours pi 1.4's theme schema rejects with a warning at every launch.
  cp -f templates/packages.json agent/npm/package.json
  elm_py - <<'PYX'
import json

def name(spec):
    spec = spec["source"] if isinstance(spec, dict) else spec
    # spec[4:], not removeprefix: that is 3.9+, and macOS 11's /usr/bin/python3 is 3.8.
    return spec[4:] if spec.startswith("npm:") else spec

chosen = json.load(open("templates/settings.json")).get("packages", [])
s = json.load(open("agent/settings.json"))
was = s.get("packages", [])
s["packages"] = chosen
json.dump(s, open("agent/settings.json", "w"), indent=2); open("agent/settings.json", "a").write("\n")

print("    loading: " + (", ".join(name(p) for p in chosen) or "none"))
if sorted(map(json.dumps, was)) != sorted(map(json.dumps, chosen)):
    print("    (agent/settings.json listed %d package(s); corrected to match)" % len(was))
    # Named, not counted: a package added by hand (or by `pi install`, which
    # the launcher now refuses) stops loading here, and its files go with the
    # next rebuild of agent/npm.
    wanted = set(name(p) for p in chosen)
    dropped = sorted(set(name(p) for p in was) - wanted)
    if dropped:
        print("    not in templates/: %s - removed. Packages come from templates/packages.json" % ", ".join(dropped))
        print("      and templates/settings.json; add one there to keep it (CONTRIBUTING.md)")
PYX
  CHOSEN="$(elm_py - <<'PYC'
import json
specs = [p["source"] if isinstance(p, dict) else p
         for p in json.load(open("agent/settings.json")).get("packages", [])]
print(" ".join(p[4:] if p.startswith("npm:") else p for p in specs))
PYC
)"

  # Packages are reinstalled when the reviewed manifest changes, when forced, and
  # whenever what is on disk does not match what pi is told to load: every run
  # checks each listed package and every extension and skill its pi manifest
  # declares (scripts/verify_install.py). A broken or half-installed tree is
  # repaired here rather than discovered as a silently missing tool later.
  PACKAGE_MANIFEST_DIGEST="$(manifest_digest templates/packages.json packages)" || die "cannot hash the package manifest"
  PACKAGE_STAMP="agent/npm/node_modules/.elm-pi-lock.sha256"
  NEED_PACKAGES=0
  if [ "$FORCE" = "1" ] || [ "$UPDATE" = "1" ] || [ "$FORCE_PACKAGES" = "1" ] \
     || [ ! -f "$PACKAGE_STAMP" ] \
     || [ "$(cat "$PACKAGE_STAMP" 2>/dev/null)" != "$PACKAGE_MANIFEST_DIGEST" ]; then
    NEED_PACKAGES=1
  elif ! elm_py "$HERE/scripts/verify_install.py" --root "$HERE" --packages-only >/dev/null; then
    echo "    installed packages do not match agent/settings.json - reinstalling:"
    elm_py "$HERE/scripts/verify_install.py" --root "$HERE" --packages-only || true
    NEED_PACKAGES=1
  fi
  if [ "$NEED_PACKAGES" = "1" ]; then
    install_packages
  else
    echo "    packages match the reviewed manifest and are complete (use --force to reinstall)"
  fi
  # Still incomplete after a fresh install means npm resolved something that
  # does not contain what it declares: stop rather than run without it.
  elm_py "$HERE/scripts/verify_install.py" --root "$HERE" --packages-only \
    || die "extension packages are incomplete even after reinstalling (above); re-run with --force"
else
  elm_py - <<'PY'
import json
s=json.load(open("agent/settings.json")); s["packages"]=[]
json.dump(s,open("agent/settings.json","w"),indent=2); open("agent/settings.json","a").write("\n")
print("    packages disabled in agent/settings.json")
PY
fi

# --- 3b2. nobody else writes to this install ---------------------------------
# Whatever umask the account had when any of this was unpacked, code here ends
# up writable by its owner only - shared deliberately (ELM_PI_SHARED_STATE=1):
# owner and group.
elm_tighten_install_perms "$HERE"

# --- 3c. warm the module cache ----------------------------------------------
# The packages ship raw TypeScript. pi transpiles them with jiti, which
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
  # The same private directory the launcher will use, or the warm cache would
  # land somewhere pi never looks.
  elm_private_tmpdir || die "$ELM_PY_ERROR"
  JITI_CACHE_DIR="${TMPDIR%/}/jiti"
  # This is also the load check. scripts/check-extensions.mjs loads every
  # extension with pi's own resource loader, exactly as a session does, which
  # fills the transpile cache and reports each one that fails ("Failed to load
  # extension"). `pi --list-models`, used here before, returns before pi
  # reports load errors, so a package that was on disk but did not load passed.
  # A failure is repaired by reinstalling the packages once; if it still fails,
  # the install stops with the error.
  warm_up() {
    ELM_PI_INSTALL_DIR="$HERE" PI_CODING_AGENT_DIR="$HERE/agent" PI_OFFLINE=1 \
      "$HERE/.node/bin/node" "$HERE/scripts/check-extensions.mjs" > "$WARM_LOG" 2>&1
  }
  WARM_LOG="$(mktemp)"
  WARM_OK=0; warm_up && WARM_OK=1
  if grep -q "Failed to load extension" "$WARM_LOG"; then
    warn "pi could not load an extension - reinstalling the packages once:"
    grep "Failed to load extension" "$WARM_LOG" | sed 's/^/      /' | head -5
    PACKAGE_MANIFEST_DIGEST="$(manifest_digest templates/packages.json packages)" || die "cannot hash the package manifest"
    install_packages
    WARM_OK=0; warm_up && WARM_OK=1
    if grep -q "Failed to load extension" "$WARM_LOG"; then
      grep "Failed to load extension" "$WARM_LOG" | sed 's/^/      /' | head -5
      rm -f "$WARM_LOG"
      die "extensions still fail to load after reinstalling (above)"
    fi
  fi
  if [ "$WARM_OK" = "1" ]; then
    echo "    $(tail -1 "$WARM_LOG" | sed 's/^ *//') - cached in $JITI_CACHE_DIR"
  else
    warn "warm-up failed; the first launch will transpile instead (slow, not fatal)"
  fi
  rm -f "$WARM_LOG"
fi

# --- 3d. everything pi is told to load is present -----------------------------
# Packages, required local extensions and skills, checked on
# every run. Anything missing here is not something a reinstall of the npm
# packages fixes, so it stops the install with the list.
say "checking the installed extensions, skills and tools"
elm_py "$HERE/scripts/verify_install.py" --root "$HERE" \
  || die "the install is incomplete (above)"
echo "    all packages, extensions, skills and tools present"

# --- 4. Llama tool-call shim ------------------------------------------------
# ELM's vLLM instance for Llama 3.3 was started without a tool-call parser, so
# any request carrying `tools` returns 400. The shim prompt-engineers tool
# calling on top of it, which is what makes cheap Llama sub-agents possible.
if [ "$WITH_SHIM" = "1" ]; then
  say "Llama tool-call shim"
  echo "    $ELM_PI_PYTHON - shim will start on demand (127.0.0.1:8811)"
else
  say "Llama tool-call shim"
  echo "    skipped (--no-shim): agent/extensions/elm-shim.ts was not installed"
fi

# Existing installs may contain state created under the account's ordinary 022
# umask. Tighten only known private state; do not alter project-file defaults.
elm_secure_install_state "$HERE"

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
VERIFY_ERR="$(mktemp "$HERE/.elm-pi-verify.XXXXXX")"
LIST="$(PI_FORCE=1 PI_OFFLINE=1 ELM_PI_NO_PROXY=1 ANTHROPIC_API_KEY=probe-should-be-ignored \
        OPENAI_API_KEY=probe-should-be-ignored ./pi --list-models </dev/null 2>"$VERIFY_ERR" || true)"
if printf '%s' "$LIST" | grep -qE '^(anthropic|openai|google) '; then
  die "commercial providers are still visible - the credential scrub in ./pi is not working"
fi
# Qwen by its id, not "any elm row": pi drops a provider whose models.json entry
# it rejects, and when 1.4.0 rejected Qwen's, elm-shim alone still matched the
# old pattern and the install passed with its main model gone. pi says why only
# on stderr, which this used to discard.
QWEN_ID="$(elm_py "$CONFIG_TOOL" --root "$HERE" value qwen)"
if ! printf '%s\n' "$LIST" | awk -v id="$QWEN_ID" '$1 == "elm" && $2 == id { found = 1 } END { exit !found }'; then
  sed 's/^/    /' "$VERIFY_ERR" >&2
  die "pi did not load elm/$QWEN_ID (pi's own messages above) - check agent/models.json, runtime.env and elm-only.ts"
fi
if grep -q 'errors loading models.json' "$VERIFY_ERR"; then
  sed 's/^/    /' "$VERIFY_ERR" >&2
  die "pi reported errors in agent/models.json (above)"
fi
printf '%s\n' "$LIST" | sed 's/^/    /'
# The same files against the schemas this pi release ships. A value pi stopped
# accepting fails the run, and the trap puts the previous pi back. A theme it
# rejects only costs a warning at every launch, so that is a warning here too.
if elm_py "$HERE/scripts/check_config.py" --root "$HERE" --config; then
  echo "    config: agent/models.json and agent/settings.json match pi $("$HERE/.node/bin/node" -p 'require("./node_modules/@earendil-works/pi-coding-agent/package.json").version')'s schemas"
else
  die "agent/models.json or agent/settings.json has values this pi rejects (above)"
fi
if [ "$WITH_PACKAGES" = "1" ]; then
  if elm_py "$HERE/scripts/check_config.py" --root "$HERE" --themes; then
    echo "    themes: every theme the packages load is valid"
  else
    warn "pi will skip the themes above with a warning at every launch - exclude them in templates/settings.json"
  fi
fi
if [ -x agent/bin/pi ] && [ "$(cd "$(dirname "$(readlink agent/bin/pi)")" && pwd)/$(basename "$(readlink agent/bin/pi)")" = "$HERE/pi" ]; then
  echo "    sub-agent launcher: agent/bin/pi resolves to the launcher"
else
  warn "agent/bin/pi is missing or points elsewhere - sub-agents may fail to start"
fi
if [ "$WITH_PATCH" = "1" ]; then
  elm_py "$HERE/patch-pi.py" --check || warn "/share and /bug are NOT disabled in this install"
fi
# The module guard is only worth having if it fires. Plant a package outside
# the install and ask the guarded node for it, through require and import.
GUARD_PROBE="$(mktemp -d)"
mkdir -p "$GUARD_PROBE/node_modules/elm-pi-guard-probe"
printf 'module.exports = "loaded";\n' > "$GUARD_PROBE/node_modules/elm-pi-guard-probe/index.js"
GUARD_OUT="$(cd "$GUARD_PROBE" || exit 1; "$HERE/.node/bin/node" --import "$HERE/lib/node-guard.mjs" -e '
let blocked = 0;
try { require("elm-pi-guard-probe"); } catch (e) { if (/elm-pi: refusing/.test(e.message)) blocked++; }
import("elm-pi-guard-probe").catch((e) => { if (/elm-pi: refusing/.test(e.message)) blocked++; })
  .then(() => console.log(blocked));' 2>&1)" || true
rm -rf "$GUARD_PROBE"
if [ "$GUARD_OUT" = "2" ]; then
  echo "    module guard: packages outside the install are refused (require and import)"
else
  warn "module guard did not refuse a package outside the install ($GUARD_OUT)"
fi
# The launcher hides pi-web-access's tools by naming them in --exclude-tools, and
# pi ignores an exclusion for a tool that does not exist - so a version that adds
# a fifth tool would leave it live in the default mode, silently. Compare the two
# lists rather than trusting that they still agree.
HERE="$HERE" elm_py - <<'PYW' || warn "could not check the web-tool exclusion list"
import json, os, re, sys

here = os.environ["HERE"]
pkg = os.path.join(here, "agent/npm/node_modules/pi-web-access")
if not os.path.isdir(pkg):
    print("    web tools: pi-web-access is not installed, nothing to exclude")
    sys.exit(0)

# Every top-level source file, not index.ts alone: 0.37 moved the names into
# web-tool-core.ts and added a loader tool, web_enable, that switches the others
# on - which a check reading index.ts could not see.
source = "\n".join(
    open(os.path.join(pkg, name), encoding="utf-8", errors="replace").read()
    for name in sorted(os.listdir(pkg)) if name.endswith(".ts"))
block = re.search(r"const DEFAULT_TOOL_NAMES[^=]*=\s*\{(.*?)\}", source, re.S)
registers = set(re.findall(r'"([a-z][a-z0-9_]*)"', block.group(1))) if block else set()
registers |= set(re.findall(r'const LOADER_NAME\s*=\s*"([a-z][a-z0-9_]*)"', source))

# config/elm-pi.json is the source of truth. The launcher passes the list as
# "$ELM_WEB_TOOLS", so scraping ./pi for a literal list finds nothing and
# reported a working exclusion as an unreadable one.
config = json.load(open(os.path.join(here, "config/elm-pi.json"), encoding="utf-8"))
excluded = set(config.get("webTools") or [])

if not registers or not excluded:
    print("    web tools: could not read one of the two lists - check\n          config/elm-pi.json and pi-web-access by hand")
    sys.exit(1)
missing = registers - excluded
if missing:
    print("    web tools: %s registered but NOT excluded - live in the default mode"
          % ", ".join(sorted(missing)))
    sys.exit(1)
stale = excluded - registers
print("    web tools: %d registered, all excluded by default (pi --remote enables them)"
      % len(registers))
if stale:
    print("    web tools: %s excluded but no longer registered - harmless, tidy when convenient"
          % ", ".join(sorted(stale)))
PYW
# The other excluded tools (excludedTools): the same failure mode - pi ignores
# an exclusion for a tool that does not exist, so a package that renamed one
# would put it back in every request with nothing said.
if [ -d agent/npm/node_modules ]; then
  _xt_missing=""; _xt_n=0
  for _t in $(elm_py -c 'import json; c = json.load(open("config/elm-pi.json"))["excludedTools"]; print(" ".join(c["always"] + c["workflows"]))'); do
    _xt_n=$((_xt_n + 1))
    grep -rqsF --include='*.ts' --include='*.js' "\"$_t\"" agent/npm/node_modules || _xt_missing="$_xt_missing $_t"
  done
  if [ -n "$_xt_missing" ]; then
    warn "excluded tools that no installed package registers:$_xt_missing - a renamed tool is back in every request; update excludedTools in config/elm-pi.json"
  else
    echo "    other excluded tools: all $_xt_n still registered, left out by default (pi --workflows brings back the workflow tools)"
  fi
fi
# Match the sentence both refusal paths share. lib/policy.sh says "is not
# available" for --provider and "is outside the allowed providers" for --model,
# so probing for the first reported a working guard as broken. The launcher
# checks arguments before it looks for the key, so on an install with no key
# yet this still probes the guard rather than the key check.
GUARD="$(PI_FORCE=1 ELM_PI_NO_PROXY=1 ./pi --model anthropic/claude-opus-5 -p x </dev/null 2>&1 || true)"
case "$GUARD" in
  *"restricted to the University"*) echo "    argument guard: --model anthropic/... refused" ;;
  *) warn "argument guard did not refuse --model anthropic/... - check the launcher" ;;
esac

# Recorded only now, after every check above has passed: the exact versions
# this install is running, in config/versions.json's format. After a
# `pi update` that works, copying this over config/versions.json is how the
# tested set moves forward (CONTRIBUTING.md).
elm_py - "$HERE" <<'PYV'
import json, os, sys

here = sys.argv[1]
def installed(tree, manifest):
    found = {}
    for name in json.load(open(os.path.join(here, manifest))).get("dependencies", {}):
        meta = os.path.join(here, tree, name, "package.json")
        if os.path.exists(meta):
            found[name] = json.load(open(meta))["version"]
    return found
record = {"core": installed("node_modules", "package.json"),
          "packages": installed("agent/npm/node_modules", "templates/packages.json")}
with open(os.path.join(here, "agent/installed-versions.json"), "w") as fh:
    json.dump(record, fh, indent=2)
    fh.write("\n")
tested = {}
if os.path.exists(os.path.join(here, "config/versions.json")):
    tested = json.load(open(os.path.join(here, "config/versions.json")))
newer = [f"{name} {version}" for section in record for name, version in record[section].items()
         if tested.get(section, {}).get(name) not in (None, version)]
print("    versions: agent/installed-versions.json")
if newer:
    print("      differs from config/versions.json: " + ", ".join(newer))
PYV

say "done"
cat <<EOM
    Run it:        pi            (or $HERE/pi if it is not on your PATH yet)
    Unwrapped:     $HERE/pi.orig   (vanilla CLI, no ELM config - debugging only)
    Policy:        $HERE/LOCKDOWN.md   (/elm-policy inside pi)
    Fast one-shot: $HERE/pi --fast -p "..."    (skips the npm packages)
    Update it:     pi update      (elm-pi + pi from GitHub, then the pi packages)
    Verify:        see "Verify the install" in INSTALL.md
EOM
