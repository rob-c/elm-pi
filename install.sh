#!/usr/bin/env bash
#
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
#
# Installs into ~/.local/share/elm-pi and links ~/.local/bin/pi. Nothing is
# installed system-wide and nothing needs sudo. The only file touched outside
# those two paths is your shell profile, and only to put ~/.local/bin on PATH
# when it is not already there - skip that with --no-path. Re-running is safe.
# Re-running the installer on an existing installation automatically updates
# pi and npm packages while preserving your configs and sessions.
# Environment overrides:
#   ELM_PI_PREFIX=/path      where to install        (default ~/.local/share/elm-pi)
#   ELM_PI_BINDIR=/path      where to link pi         (default ~/.local/bin)
#   ELM_PI_REPO=url          source repository
#   ELM_PI_BRANCH=name       branch to install       (default main)
#   ELM_API_KEY=elm-...      skip the interactive key prompt
#   ELM_PI_UPDATE=1          refresh pi and the extensions, keeping your configs
#   ELM_PI_NO_PATH=1         do not touch any shell profile
#   ELM_PI_NO_LINK=1         do not create or replace the launcher symlink
#   ELM_PI_FORCE_LINK=1      replace an existing ~/.local/bin/pi symlink
#   ELM_PI_PYTHON=/path      the Python 3.8+ to use (default: the system one;
#                            conda, virtualenv and pyenv are never picked, and
#                            with no usable one a standalone CPython is installed)
#   ELM_PI_BUNDLED_PYTHON=1  always use the standalone CPython
#
#   --no-path                do not add ~/.local/bin to PATH in a shell profile
#   --force-link             replace an existing ~/.local/bin/pi symlink
#
# Run with --help for the flags; that list lives in usage() below and nowhere
# else, so it cannot drift from what is parsed or from what bootstrap.sh takes.
#
set -euo pipefail
# Nothing this writes is writable by others, whatever the account's umask.
umask 022

# --- 0. none of this account's toolchain ------------------------------------
# A first pass, before lib/sandbox.sh exists on disk: bootstrap.sh applies the
# full version. The prefix list is a copy of the one in lib/sandbox.sh and
# tests/test_sandbox.py fails if they drift. In short: an activated conda env,
# PYTHONPATH, NODE_OPTIONS, npm_config_*, GIT_DIR and friends are dropped, the
# system tools come first on PATH, and git and curl ignore ~/.gitconfig and
# ~/.curlrc. The account's PATH is kept for linking pi onto it in step 4.
ELM_SCRUB_PREFIXES="PYTHON CONDA _CE_ MAMBA VIRTUAL_ENV PIP_ PYENV npm_config_ NPM_CONFIG_ NODE_ NVM_ VOLTA_ FNM_ ASDF_ COREPACK_ YARN_ PNPM_ BUN_ GIT_"
ELM_SCRUB_NAMES="BASH_ENV ENV CDPATH TAR_OPTIONS GZIP UNZIP UNZIPOPT GREP_OPTIONS CURL_HOME LD_PRELOAD LD_LIBRARY_PATH"
ELM_SCRUB_KEEP="NODE_EXTRA_CA_CERTS"
for _name in $(compgen -e); do
  case " $ELM_SCRUB_KEEP " in *" $_name "*) continue ;; esac
  for _prefix in $ELM_SCRUB_PREFIXES; do
    case "$_name" in "$_prefix"*) unset "$_name" 2>/dev/null || true; break ;; esac
  done
done
for _name in $ELM_SCRUB_NAMES; do unset "$_name" 2>/dev/null || true; done
ELM_PI_USER_PATH="$PATH"
PATH="/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export PATH
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0

REPO="${ELM_PI_REPO:-https://github.com/rob-c/elm-pi.git}"
BRANCH="${ELM_PI_BRANCH:-main}"
PREFIX="${ELM_PI_PREFIX:-$HOME/.local/share/elm-pi}"
BINDIR="${ELM_PI_BINDIR:-$HOME/.local/bin}"
UPDATE="${ELM_PI_UPDATE:-0}"
SLUG="$(printf '%s' "$REPO" | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')"
DOCS="${ELM_PI_DOCS:-https://rob-c.github.io/elm-pi/}"

PASS_ARGS=()
NO_PATH="${ELM_PI_NO_PATH:-0}"
NO_LINK="${ELM_PI_NO_LINK:-0}"
FORCE_LINK="${ELM_PI_FORCE_LINK:-0}"
usage() {
  cat <<'EOU'
elm-pi installer: fetches the repo, runs bootstrap.sh, links pi onto your PATH.

  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
  ./install.sh [flags]

Installer flags:
  --update            update an existing install in place
  --no-path           do not add ~/.local/bin to PATH in a shell profile
  --no-link           do not create or replace the launcher symlink
  --force-link        replace an existing ~/.local/bin/pi symlink
  -h, --help          this text

Passed through to bootstrap.sh:
  --no-packages       pi only: no sub-agents, memory, web access or anchor edit
  --no-tools          skip the bundled fd/rg/jq/yq/shellcheck/ast-grep
  --no-shim           no Llama tool-call shim
  --no-patch          leave pi's /share and /bug commands in place
  --no-auth-lock      leave agent/auth.json writable, so /login works
  --force             re-download the tools and reinstall the npm packages
  --force-packages    reinstall only the locked extension dependency tree

Environment: ELM_PI_PREFIX, ELM_PI_BINDIR, ELM_PI_REPO, ELM_PI_BRANCH,
ELM_PI_DOCS, ELM_PI_UPDATE, ELM_PI_NO_PATH, ELM_PI_NO_LINK,
ELM_PI_FORCE_LINK, ELM_PI_PYTHON, ELM_PI_BUNDLED_PYTHON, ELM_API_KEY.

Your shell's conda/venv/pyenv Python, nvm/volta Node, ~/.npmrc, ~/.npm,
~/.gitconfig, ~/.curlrc and PYTHON*/NODE_*/npm_config_*/GIT_* variables are
ignored by the install.
EOU
}

# Before anything else, and as a heredoc rather than `sed` over "$0": piped
# into bash there is no "$0" to read, which is how `curl ... | bash -s -- --help`
# came to print nothing at all and exit 0.
for arg in "$@"; do
  case "$arg" in -h|--help) usage; exit 0 ;; esac
done
for arg in "$@"; do
  case "$arg" in
    --update)  UPDATE=1 ;;
    --no-path) NO_PATH=1 ;;
    --no-link) NO_LINK=1 ;;
    --force-link) FORCE_LINK=1 ;;
    # Forwarded verbatim. A flag missing from this list used to be dropped in
    # silence, so `install.sh --no-tools` installed the tools anyway.
    --no-packages|--no-shim|--no-auth-lock|--no-tools|--no-patch|--force|--force-packages)
      PASS_ARGS+=("$arg") ;;
    *) echo "unknown option: $arg" >&2; echo "try: --help" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then B=$'\033[1m'; Y=$'\033[33m'; R=$'\033[31m'; Z=$'\033[0m'
else B=""; Y=""; R=""; Z=""; fi
say()  { printf '\n%s==> %s%s\n' "$B" "$*" "$Z"; }
warn() { printf '%s    %s%s\n' "$Y" "$*" "$Z"; }
die()  { printf '%sERROR: %s%s\n' "$R" "$*" "$Z" >&2; exit 1; }

printf '\n%selm-pi%s — pi coding agent on university-hosted models (ELM)\n' "$B" "$Z"

# --- 1. is this machine supported? ------------------------------------------
say "checking this machine"
case "$(uname -s)" in
  Darwin) OS=macOS ;;
  Linux)  OS=Linux ;;
  *) die "unsupported OS: $(uname -s). elm-pi supports macOS and Linux." ;;
esac
case "$(uname -m)" in
  x86_64|amd64)  ARCH=x64 ;;
  arm64|aarch64) ARCH=arm64 ;;
  *) die "unsupported CPU: $(uname -m). elm-pi supports x86_64 and arm64." ;;
esac
echo "    $OS / $ARCH"

# python3 is chosen later, from the downloaded lib/sandbox.sh: the one on PATH
# is often conda's, and which one runs is not decided by PATH.
missing=""
for t in curl tar; do
  command -v "$t" >/dev/null 2>&1 || missing="$missing $t"
done
if [ -n "$missing" ]; then
  printf '\n'
  warn "missing required tool(s):$missing"
  case "$OS" in
    macOS) warn "install the Apple command line tools:  xcode-select --install" ;;
    Linux) warn "Debian/Ubuntu:  sudo apt install -y curl tar python3 git"
           warn "Fedora/RHEL:    sudo dnf install -y curl tar python3 git" ;;
  esac
  die "install the tools above, then re-run this command"
fi
echo "    curl, tar present"

if [ "$OS" = "macOS" ] && [ "$(command -v git 2>/dev/null)" = "/usr/bin/git" ] \
   && ! xcode-select -p >/dev/null 2>&1; then
  # The stub that opens the Command Line Tools dialog, not a git.
  HAVE_GIT=0; warn "git is not installed (no Command Line Tools) — installing from a source tarball"
elif command -v git >/dev/null 2>&1; then
  HAVE_GIT=1; echo "    git present — updates will be a one-line git pull"
else
  HAVE_GIT=0; warn "git not found — installing from a source tarball instead"
fi

# 650 MB of Node, pi and packages land in PREFIX.
if command -v df >/dev/null 2>&1; then
  FREE_KB="$(df -Pk "$(dirname "$PREFIX")" 2>/dev/null | awk 'NR==2{print $4}' || echo "")"
  if [ -n "$FREE_KB" ] && [ "$FREE_KB" -lt 1572864 ] 2>/dev/null; then
    warn "only $((FREE_KB/1024)) MB free on this filesystem; the install needs ~650 MB"
  fi
fi

# --- 2. get the source ------------------------------------------------------
say "fetching elm-pi into $PREFIX"
mkdir -p "$(dirname "$PREFIX")"

fetch_tarball() {   # $1 = destination directory
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  SOURCE_TMP="$TMP/source"
  mkdir -p "$SOURCE_TMP"
  curl -q -fsSL "https://codeload.github.com/$SLUG/tar.gz/refs/heads/$BRANCH" \
    | tar -xz -C "$SOURCE_TMP" --strip-components=1 \
    || die "could not download $SLUG@$BRANCH — check the network, or that the repository is public"
  validate_source "$SOURCE_TMP"
  NEW_MANIFEST="$TMP/source-manifest"
  ( cd "$SOURCE_TMP" && find . \( -type f -o -type l \) -print | sed 's|^\./||' | LC_ALL=C sort ) > "$NEW_MANIFEST"
  mkdir -p "$1"
  # Delete only files recorded as source by a previous tarball install. Runtime
  # state and locally created files were never in this list and are untouched.
  if [ -f "$1/.elm-pi-source-manifest" ]; then
    while IFS= read -r rel; do
      case "$rel" in ""|/*|../*|*/../*) continue ;; esac
      if ! grep -Fqx "$rel" "$NEW_MANIFEST"; then rm -f "$1/$rel"; fi
    done < "$1/.elm-pi-source-manifest"
  fi
  # Copy over the top: .env, agent/ and the installed software are not in the
  # tarball, so an existing install keeps its key, sessions and memory.
  ( cd "$SOURCE_TMP" && tar -cf - . ) | ( cd "$1" && tar -xf - )
  cp "$NEW_MANIFEST" "$1/.elm-pi-source-manifest"
}

validate_source() { # $1 = candidate source tree
  local source_dir="$1"
  bash -n "$source_dir/install.sh" "$source_dir/bootstrap.sh" \
    "$source_dir/configure.sh" "$source_dir/pi" "$source_dir/pi.orig" \
    "$source_dir/lib/sandbox.sh" \
    || die "downloaded source failed its shell syntax check"
  # The interpreter is picked by the source being installed, so the rules for
  # it ship with the release. Exported: bootstrap.sh and check.sh inherit it.
  # shellcheck source=lib/sandbox.sh
  . "$source_dir/lib/sandbox.sh"
  # May download the standalone CPython into $PREFIX/.python, which is where
  # bootstrap.sh then finds it.
  elm_ensure_python "$PREFIX" || die "$ELM_PY_ERROR"
  echo "    checking the source with $ELM_PI_PYTHON"
  ELM_PI_ROOT="$source_dir" elm_py - "$source_dir" <<'PY' || die "downloaded source failed its Python/JSON checks"
import ast, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
for path in [root / "patch-pi.py", root / "proxy/egress.py", root / "shim/shim.py",
             root / "scripts/elm_config.py", root / "scripts/verify_install.py"]:
    ast.parse(path.read_text(), filename=str(path))
for path in list((root / "config").glob("*.json")) + list((root / "templates").rglob("*.json")):
    json.loads(path.read_text())
PY
  if [ -x "$source_dir/scripts/check.sh" ]; then
    ( cd "$source_dir" && ./scripts/check.sh --source-only </dev/null ) \
      || die "downloaded source failed its self-checks"
  fi
}

if [ -e "$PREFIX/.git" ] && [ "$HAVE_GIT" = "1" ]; then
  echo "    existing git install — pulling $BRANCH"
  if ! git -C "$PREFIX" diff --quiet || ! git -C "$PREFIX" diff --cached --quiet; then
    die "tracked local changes prevent a safe update; commit or stash them first"
  fi
  git -C "$PREFIX" fetch --quiet origin "$BRANCH" || die "git fetch failed"
  CANDIDATE="$(mktemp -d)"; trap 'rm -rf "$CANDIDATE"' EXIT
  git -C "$PREFIX" archive "origin/$BRANCH" | tar -xf - -C "$CANDIDATE"
  validate_source "$CANDIDATE"
  git -C "$PREFIX" merge --ff-only "origin/$BRANCH" --quiet \
    || die "the install cannot fast-forward to origin/$BRANCH"
  echo "    now at $(git -C "$PREFIX" rev-parse --short HEAD)"
elif [ -d "$PREFIX" ] && [ -f "$PREFIX/bootstrap.sh" ]; then
  echo "    existing install found — refreshing the source files"
  fetch_tarball "$PREFIX"
elif [ -d "$PREFIX" ] && [ -n "$(ls -A "$PREFIX" 2>/dev/null)" ]; then
  die "$PREFIX exists and is not an elm-pi install. Move it, or set ELM_PI_PREFIX."
elif [ "$HAVE_GIT" = "1" ]; then
  git clone --quiet --branch "$BRANCH" --depth 1 "$REPO" "$PREFIX" \
    || die "git clone failed — check the network, or that the repository is public"
  echo "    cloned at $(git -C "$PREFIX" rev-parse --short HEAD)"
else
  fetch_tarball "$PREFIX"
  echo "    downloaded $SLUG@$BRANCH"
fi
chmod +x "$PREFIX/pi" "$PREFIX/pi.orig" "$PREFIX/bootstrap.sh" "$PREFIX/configure.sh" 2>/dev/null || true

# --- 3. hand over to bootstrap ----------------------------------------------
# bootstrap.sh does the real work: Node, pi, packages, agent/, the key, the
# model id, and the ELM-only checks. It is idempotent and never overwrites a
# config you have edited.
if [ -d "$PREFIX/node_modules" ] || [ -d "$PREFIX/agent/npm/node_modules" ]; then
  say "running bootstrap (existing install — keeping pi, binaries and packages)"
  echo "    already installed parts are left alone; configs and policy are refreshed"
  echo "    to reinstall them: pi update, or ./bootstrap.sh --force"
else
  say "running bootstrap (Node, pi, extensions — a few minutes)"
fi
# ${arr[@]+"${arr[@]}"} and not "${arr[@]}": macOS ships bash 3.2, where
# expanding an empty array under `set -u` is an unbound-variable error rather
# than nothing. Every one of these arrays is empty in the common case - an
# install with no flags - so the plain form broke the documented one-line
# install on the platform this targets. bash 4.4 made it harmless, which is
# why it survives review on Linux.
BOOT_ARGS=(${PASS_ARGS[@]+"${PASS_ARGS[@]}"})
[ "$UPDATE" = "1" ] && BOOT_ARGS=(--update ${BOOT_ARGS[@]+"${BOOT_ARGS[@]}"})
# A re-install adds no flags of its own. It deliberately does not reinstall pi,
# re-download the bundled binaries, or reinstall the extension packages when
# they are already present: that is minutes of work to reproduce a state that
# already exists, on every run, for nothing.
#
# The repo's decisions still land, because bootstrap.sh applies them without
# needing a flag - generated code (AGENTS.md, agent definitions, local
# extensions, prompts) is refreshed every run, and the settings this repo owns
# are compared, reported and reapplied every run.
#
# Reinstalling the packages is what `--update` is for, and `pi update` passes
# it. An install that is actually broken is a `rm -rf` away from a clean one.
if [ -t 0 ]; then
  # Invoked as bash -c "$(curl ...)", so stdin is still the terminal and
  # bootstrap can prompt for the ELM key.
  "$PREFIX/bootstrap.sh" ${BOOT_ARGS[@]+"${BOOT_ARGS[@]}"}
else
  warn "not running on a terminal — bootstrap cannot prompt for your ELM key"
  "$PREFIX/bootstrap.sh" ${BOOT_ARGS[@]+"${BOOT_ARGS[@]}"} --non-interactive
fi

# --- 4. put pi on the PATH --------------------------------------------------
# The command is `pi`. The wrapper takes the name and hands over to pi.orig, the
# unwrapped CLI inside the install, so everything that expects a `pi` - muscle
# memory, scripts, and pi-subagents' own bare-`pi` fallback when it spawns
# children - gets the wrapped, ELM-only one.
say "linking the launcher"
LINK="$BINDIR/pi"
LINKED=0
if [ "$NO_LINK" = "1" ]; then
  echo "    skipped (--no-link)"
elif ! mkdir -p "$BINDIR"; then
  warn "could not create $BINDIR — launcher was not linked"
elif [ -e "$LINK" ] && [ ! -L "$LINK" ]; then
  warn "$LINK exists and is not a symlink — leaving it alone"
  warn "run pi as: $PREFIX/pi"
elif [ -L "$LINK" ] && [ "$(readlink "$LINK")" != "$PREFIX/pi" ] && [ "$FORCE_LINK" != "1" ]; then
  warn "$LINK already points at $(readlink "$LINK") — leaving it alone"
  warn "replace it with:  ln -sfn $PREFIX/pi $LINK   (or re-run with --force-link)"
else
  ln -sfn "$PREFIX/pi" "$LINK"
  echo "    $LINK -> $PREFIX/pi"
  LINKED=1
fi

# This install used to be called elm-pi. Retire that symlink, but only when it is
# ours: someone else's elm-pi is none of our business.
OLD_LINK="$BINDIR/elm-pi"
if [ "$NO_LINK" != "1" ] && [ "$LINKED" = "1" ] && [ -L "$OLD_LINK" ]; then
  case "$(readlink "$OLD_LINK")" in
    "$PREFIX/pi") rm -f "$OLD_LINK"; echo "    removed the old $OLD_LINK symlink (the command is now pi)" ;;
  esac
fi

# Say so plainly if another pi will win on PATH: ours is only first once BINDIR
# is, and a globally installed pi in /usr/local/bin is a common way to lose.
# The account's own PATH, not the one this script narrowed for itself.
OTHER_PI="$(PATH="$ELM_PI_USER_PATH" command -v pi 2>/dev/null || true)"
if [ "$LINKED" = "1" ] && [ -n "$OTHER_PI" ] && [ "$OTHER_PI" != "$LINK" ]; then
  case ":${ELM_PI_USER_PATH}:" in
    *":$BINDIR:"*)
      warn "another pi is earlier on your PATH: $OTHER_PI"
      warn "that one will keep winning — remove it, or move $BINDIR ahead of it" ;;
    *) : ;;   # BINDIR is not on PATH yet; the next step fixes that
  esac
fi

# Put BINDIR on PATH for the shells this account actually uses. Writing the
# line is the whole point of an installer - printing "add this yourself" is how
# people end up running the launcher by full path forever. Every write is
# marked and idempotent, re-running never duplicates it, and --no-path (or
# ELM_PI_NO_PATH=1) skips the whole step.
ON_PATH=0
case ":${ELM_PI_USER_PATH}:" in *":$BINDIR:"*) ON_PATH=1 ;; esac

PATH_ADDED=0
PATH_PRESENT=0
add_path_to() {   # $1 = profile file, $2 = syntax: posix|fish
  PROFILE="$1"
  if [ -f "$PROFILE" ] && grep -qF "$BINDIR" "$PROFILE" 2>/dev/null; then
    echo "    already in $(basename "$PROFILE")"
    PATH_PRESENT=1
    return 0
  fi
  mkdir -p "$(dirname "$PROFILE")" 2>/dev/null || true
  if [ "$2" = "fish" ]; then
    printf '\n# added by the elm-pi installer\nfish_add_path %s\n' "$BINDIR" >> "$PROFILE" \
      || { warn "could not write $PROFILE"; return 1; }
  else
    # shellcheck disable=SC2016 # $PATH must expand when the profile is sourced
    printf '\n# added by the elm-pi installer\nexport PATH="%s:$PATH"\n' "$BINDIR" >> "$PROFILE" \
      || { warn "could not write $PROFILE"; return 1; }
  fi
  echo "    added $BINDIR to $(basename "$PROFILE")"
  PATH_ADDED=1
}

if [ "$ON_PATH" = "1" ]; then
  echo "    $BINDIR is already on PATH"
elif [ "$NO_PATH" = "1" ]; then
  warn "$BINDIR is not on PATH, and --no-path was given. Run pi as: $PREFIX/pi"
else
  # The shell you are in now, plus any other login shell configured on this
  # account: $SHELL is often stale (or root's default) and people switch.
  USER_SHELL="$(basename "${SHELL:-}")"
  case "$USER_SHELL" in
    zsh)  add_path_to "$HOME/.zshrc" posix ;;
    fish) add_path_to "$HOME/.config/fish/config.fish" fish ;;
    bash)
      # Linux interactive shells read .bashrc; macOS Terminal opens login
      # shells, which read .bash_profile and often nothing else.
      if [ "$OS" = "macOS" ]; then
        add_path_to "$HOME/.bash_profile" posix
      else
        add_path_to "$HOME/.bashrc" posix
      fi ;;
    *)    : ;;
  esac
  # Cover the other shell if this account has one configured - a $SHELL of bash
  # with a populated .zshrc is common, and the reverse happens on new macOS.
  [ "$USER_SHELL" != "zsh" ]  && [ -f "$HOME/.zshrc" ]  && add_path_to "$HOME/.zshrc" posix
  [ "$USER_SHELL" != "bash" ] && [ -f "$HOME/.bashrc" ] && add_path_to "$HOME/.bashrc" posix
  [ "$USER_SHELL" != "bash" ] && [ "$OS" = "macOS" ] && [ -f "$HOME/.bash_profile" ] \
    && add_path_to "$HOME/.bash_profile" posix
  if [ "$PATH_ADDED" = "0" ] && [ "$PATH_PRESENT" = "0" ]; then
    warn "could not work out which shell profile to edit. Add this line yourself:"
    # shellcheck disable=SC2016 # this is an instruction, not this process's PATH
    printf '\n      export PATH="%s:$PATH"\n\n' "$BINDIR"
  fi
fi

# --- 5. what to do next -----------------------------------------------------
say "done"
PATH_NOTE=""
[ "$PATH_ADDED" = "1" ] || [ "$PATH_PRESENT" = "1" ] && [ "$ON_PATH" = "0" ] && PATH_NOTE="    New shells will find pi. For this one:  export PATH=\"$BINDIR:\$PATH\"

"
if [ "$ON_PATH" = "1" ] || [ "$PATH_ADDED" = "1" ] || [ "$PATH_PRESENT" = "1" ]; then
  RUN="pi"
else
  RUN="$PREFIX/pi"
fi
cat <<EOM
${PATH_NOTE}    Start it:      $RUN
    One-shot:      $RUN -p "explain this repo"
    Update later:  $PREFIX/bootstrap.sh --update   (or re-run this install command)

    Installed in:  $PREFIX
    Your key:      $PREFIX/.env   (mode 600, never committed)
    Unwrapped pi:  $PREFIX/pi.orig     (vanilla CLI, no ELM config - debugging only)
    Uninstall:     rm -rf $PREFIX $BINDIR/pi

    Docs:          $DOCS
EOM
