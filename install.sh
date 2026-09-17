#!/usr/bin/env bash
#
# elm-pi installer — a coding agent on the University of Edinburgh's own GPUs.
#
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/rob-c/elm-pi/main/install.sh)"
#
# Installs into ~/.local/share/elm-pi and links ~/.local/bin/elm-pi. Nothing is
# installed system-wide, nothing needs sudo, and no file outside those two paths
# is written. Re-running is safe.
#
# Environment overrides:
#   ELM_PI_PREFIX=/path      where to install        (default ~/.local/share/elm-pi)
#   ELM_PI_BINDIR=/path      where to link elm-pi    (default ~/.local/bin)
#   ELM_PI_REPO=url          source repository
#   ELM_PI_BRANCH=name       branch to install       (default main)
#   ELM_API_KEY=elm-...      skip the interactive key prompt
#   ELM_PI_UPDATE=1          refresh pi and the extensions, keeping your configs
#
set -euo pipefail

REPO="${ELM_PI_REPO:-https://github.com/rob-c/elm-pi.git}"
BRANCH="${ELM_PI_BRANCH:-main}"
PREFIX="${ELM_PI_PREFIX:-$HOME/.local/share/elm-pi}"
BINDIR="${ELM_PI_BINDIR:-$HOME/.local/bin}"
UPDATE="${ELM_PI_UPDATE:-0}"
SLUG="$(printf '%s' "$REPO" | sed -e 's#^.*github\.com[:/]##' -e 's#\.git$##')"
DOCS="${ELM_PI_DOCS:-https://rob-c.github.io/elm-pi/}"

for arg in "$@"; do
  case "$arg" in
    --update)  UPDATE=1 ;;
    -h|--help) sed -n '3,17p' "$0" 2>/dev/null || true; exit 0 ;;
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
chmod +x "$PREFIX/pi" "$PREFIX/bootstrap.sh" "$PREFIX/configure.sh" 2>/dev/null || true

# --- 3. hand over to bootstrap ----------------------------------------------
# bootstrap.sh does the real work: Node, pi, packages, agent/, the key, the
# model id, and the ELM-only checks. It is idempotent and never overwrites a
# config you have edited.
say "running bootstrap (Node, pi, extensions — a few minutes)"
BOOT_ARGS=""
[ "$UPDATE" = "1" ] && BOOT_ARGS="--update"
if [ -t 0 ]; then
  # Invoked as bash -c "$(curl ...)", so stdin is still the terminal and
  # bootstrap can prompt for the ELM key.
  "$PREFIX/bootstrap.sh" $BOOT_ARGS
else
  warn "not running on a terminal — bootstrap cannot prompt for your ELM key"
  "$PREFIX/bootstrap.sh" $BOOT_ARGS --non-interactive
fi

# --- 4. put elm-pi on the PATH ----------------------------------------------
say "linking the launcher"
mkdir -p "$BINDIR"
LINK="$BINDIR/elm-pi"
if [ -e "$LINK" ] && [ ! -L "$LINK" ]; then
  warn "$LINK exists and is not a symlink — leaving it alone"
  warn "run elm-pi as: $PREFIX/pi"
else
  ln -sfn "$PREFIX/pi" "$LINK"
  echo "    $LINK -> $PREFIX/pi"
fi

ON_PATH=0
case ":${PATH}:" in *":$BINDIR:"*) ON_PATH=1 ;; esac
if [ "$ON_PATH" = "0" ]; then
  case "$(basename "${SHELL:-bash}")" in
    zsh)  PROFILE="$HOME/.zshrc" ;;
    bash) [ -f "$HOME/.bash_profile" ] && PROFILE="$HOME/.bash_profile" || PROFILE="$HOME/.bashrc" ;;
    fish) PROFILE="$HOME/.config/fish/config.fish" ;;
    *)    PROFILE="your shell profile" ;;
  esac
  printf '\n'
  warn "$BINDIR is not on your PATH. Add it:"
  if [ "$PROFILE" = "$HOME/.config/fish/config.fish" ]; then
    printf '\n      fish_add_path %s\n\n' "$BINDIR"
  else
    printf '\n      echo '\''export PATH="%s:$PATH"'\'' >> %s && exec $SHELL\n\n' "$BINDIR" "$PROFILE"
  fi
fi

# --- 5. what to do next -----------------------------------------------------
say "done"
if [ "$ON_PATH" = "1" ]; then RUN="elm-pi"; else RUN="$PREFIX/pi"; fi
cat <<EOM
    Start it:      $RUN
    One-shot:      $RUN -p "explain this repo"
    Update later:  $PREFIX/bootstrap.sh --update   (or re-run this install command)

    Installed in:  $PREFIX
    Your key:      $PREFIX/.env   (mode 600, never committed)
    Uninstall:     rm -rf $PREFIX $BINDIR/elm-pi

    Docs:          $DOCS
EOM
