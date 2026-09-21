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
#   ELM_PI_FORCE_LINK=1      replace an existing ~/.local/bin/pi symlink
#
#   --no-path                do not add ~/.local/bin to PATH in a shell profile
#   --force-link             replace an existing ~/.local/bin/pi symlink
#
# Flags forwarded to bootstrap.sh:
#   --no-memory              drop pi-hermes-memory: ~1.8s off every launch
#   --no-packages            pi only: no sub-agents, memory, web access
#   --no-shim                no Llama tool-call shim
#   --no-auth-lock           leave agent/auth.json writable, so /login works
#
set -euo pipefail

REPO="${ELM_PI_REPO:-https://github.com/rob-c/elm-pi.git}"
BRANCH="${ELM_PI_BRANCH:-main}"
PREFIX="${ELM_PI_PREFIX:-$HOME/.local/share/elm-pi}"
BINDIR="${ELM_PI_BINDIR:-$HOME/.local/bin}"
UPDATE="${ELM_PI_UPDATE:-0}"
SLUG="$(printf '%s' "$REPO" | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')"
DOCS="${ELM_PI_DOCS:-https://rob-c.github.io/elm-pi/}"

PASS_ARGS=""
NO_PATH="${ELM_PI_NO_PATH:-0}"
FORCE_LINK="${ELM_PI_FORCE_LINK:-0}"
for arg in "$@"; do
  case "$arg" in
    --update)  UPDATE=1 ;;
    --no-path) NO_PATH=1 ;;
    --force-link) FORCE_LINK=1 ;;
    --no-memory|--no-packages|--no-shim|--no-auth-lock) PASS_ARGS="$PASS_ARGS $arg" ;;
    -h|--help) sed -n '3,24p' "$0" 2>/dev/null || true; exit 0 ;;
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

missing=""
for t in curl tar python3; do
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
echo "    curl, tar, python3 present"

if command -v git >/dev/null 2>&1; then
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
  curl -fsSL "https://codeload.github.com/$SLUG/tar.gz/refs/heads/$BRANCH" \
    | tar -xz -C "$TMP" --strip-components=1 \
    || die "could not download $SLUG@$BRANCH — check the network, or that the repository is public"
  mkdir -p "$1"
  # Copy over the top: .env, agent/ and the installed software are not in the
  # tarball, so an existing install keeps its key, sessions and memory.
  ( cd "$TMP" && tar -cf - . ) | ( cd "$1" && tar -xf - )
}

if [ -e "$PREFIX/.git" ] && [ "$HAVE_GIT" = "1" ]; then
  echo "    existing git install — pulling $BRANCH"
  git -C "$PREFIX" fetch --quiet origin "$BRANCH" || die "git fetch failed"
  if git -C "$PREFIX" merge --ff-only "origin/$BRANCH" --quiet 2>/dev/null; then
    echo "    now at $(git -C "$PREFIX" rev-parse --short HEAD)"
  else
    warn "local changes prevent a fast-forward — leaving $PREFIX as it is"
    warn "resolve with:  git -C $PREFIX status"
  fi
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
say "running bootstrap (Node, pi, extensions — a few minutes)"
BOOT_ARGS="$PASS_ARGS"
# If this is an existing install, treat it as an update (refresh pi and packages)
EXISTING_INSTALL=0
if [ -d "$PREFIX/node_modules" ] || [ -d "$PREFIX/agent/npm/node_modules" ]; then
  EXISTING_INSTALL=1
  echo "    existing installation detected — updating pi and packages"
fi
[ "$UPDATE" = "1" ] && BOOT_ARGS="--update$BOOT_ARGS"
[ "$EXISTING_INSTALL" = "1" ] && BOOT_ARGS="$BOOT_ARGS --force"
if [ -t 0 ]; then
  # Invoked as bash -c "$(curl ...)", so stdin is still the terminal and
  # bootstrap can prompt for the ELM key.
  "$PREFIX/bootstrap.sh" $BOOT_ARGS
else
  warn "not running on a terminal — bootstrap cannot prompt for your ELM key"
  "$PREFIX/bootstrap.sh" $BOOT_ARGS --non-interactive
fi

# --- 4. put pi on the PATH --------------------------------------------------
# The command is `pi`. The wrapper takes the name and hands over to pi.orig, the
# unwrapped CLI inside the install, so everything that expects a `pi` - muscle
# memory, scripts, and pi-subagents' own bare-`pi` fallback when it spawns
# children - gets the wrapped, ELM-only one.
say "linking the launcher"
mkdir -p "$BINDIR"
LINK="$BINDIR/pi"
LINKED=0
if [ -e "$LINK" ] && [ ! -L "$LINK" ]; then
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
if [ "$LINKED" = "1" ] && [ -L "$OLD_LINK" ]; then
  case "$(readlink "$OLD_LINK")" in
    "$PREFIX/pi") rm -f "$OLD_LINK"; echo "    removed the old $OLD_LINK symlink (the command is now pi)" ;;
  esac
fi

# Say so plainly if another pi will win on PATH: ours is only first once BINDIR
# is, and a globally installed pi in /usr/local/bin is a common way to lose.
OTHER_PI="$(command -v pi 2>/dev/null || true)"
if [ "$LINKED" = "1" ] && [ -n "$OTHER_PI" ] && [ "$OTHER_PI" != "$LINK" ]; then
  case ":${PATH}:" in
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
case ":${PATH}:" in *":$BINDIR:"*) ON_PATH=1 ;; esac

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
