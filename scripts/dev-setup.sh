#!/usr/bin/env bash
# Make this clone of elm-pi a working install - to test, load-check and run a change
# to elm-pi - without the network.
#
#   scripts/dev-setup.sh [--from INSTALL] [--fresh]
#
# Run it again after changing a template: it puts the change in this clone's agent/
# (the trees are copied only the first time, or with --fresh).
#
# Bootstrapping needs Node, pi and the extension packages, which come from
# nodejs.org and the npm registry; an elm-pi session's egress proxy lets neither
# through. So the clone is given the ones the install this shell runs under
# already has (or --from INSTALL's): .node, node_modules, agent/npm, agent/bin and
# the skill library when it has the pinned one,
# copied as APFS clones or reflinks where the filesystem has them (instant, no
# extra disk), else copied. bootstrap.sh then finds each tree at the version it
# expects and only renders this clone's agent/ from its own templates - the
# step that makes an edited extension the one this clone's pi loads. A clone
# whose package.json or config/versions.json changed a version still needs the
# network for that tree.
#
# Bootstrap runs in a clean environment: a session exports a dozen variables
# that point at its own install (PI_CODING_AGENT_DIR, npm's config and cache,
# uv's and pixi's caches), and those must not decide where this clone's files go.
# Only the ELM key and address and the proxy are passed on.
#
# Its output goes to .pi/tmp/dev-setup.log; what it prints here is the result.
set -euo pipefail
unset CDPATH
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

die() { echo "dev-setup: $*" >&2; exit 1; }
usage() {
  sed -n '2,8p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

FROM=""; FRESH=0
while [ $# -gt 0 ]; do
  case "$1" in
    --from) [ $# -ge 2 ] || die "--from needs a folder"; FROM="$2"; shift 2 ;;
    --from=*) FROM="${1#--from=}"; shift ;;
    --fresh) FRESH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1 (see --help)" ;;
  esac
done

if [ -z "$FROM" ] && [ -n "${PI_CODING_AGENT_DIR:-}" ]; then FROM="$(dirname "$PI_CODING_AGENT_DIR")"; fi
[ -n "$FROM" ] || die "no install to copy from: run this inside an elm-pi session, or give --from <install>"
FROM="$(cd "$FROM" 2>/dev/null && pwd -P)" || die "$FROM is not a folder"
[ "$FROM" != "$HERE" ] || die "this is the install itself. Work on a clone: git clone $FROM <folder>, then run this there."
[ -f "$HERE/bootstrap.sh" ] && [ -f "$HERE/pi" ] || die "$HERE is not an elm-pi checkout"
for part in .node node_modules agent/npm/node_modules agent/bin; do
  [ -e "$FROM/$part" ] || die "$FROM/$part is missing: is $FROM a bootstrapped elm-pi install?"
done

# A copy that costs nothing where the filesystem can share blocks.
clone_tree() {   # $1 = source, $2 = destination (inside this clone)
  case "$2" in "$HERE"/*) ;; *) die "refusing to replace $2, outside $HERE" ;; esac
  # Copied beside its place and moved in whole: pi's bash tool kills a command that runs past its
  # timeout with SIGKILL, and a half-copied tree left in place would be taken as done next time (dev8,
  # 2026-11-14, ran this with a 120 s timeout).
  local part="$2.dev-setup-partial"
  mkdir -p "$(dirname "$2")"
  rm -rf "$part"
  cp -cR "$1" "$part" 2>/dev/null \
    || { rm -rf "$part"; cp -a --reflink=auto "$1" "$part" 2>/dev/null; } \
    || { rm -rf "$part"; cp -a "$1" "$part"; } || { rm -rf "$part"; return 1; }
  rm -rf "$2" && mv "$part" "$2"
}

echo "dev-setup: $HERE, from the install at $FROM"
for part in .node node_modules agent/npm/node_modules agent/bin; do
  if [ "$FRESH" = "1" ] || [ ! -e "$HERE/$part" ]; then clone_tree "$FROM/$part" "$HERE/$part"; fi
done

# What a killed run left (its traps do not run under SIGKILL): bootstrap's scratch files and a copy cut off.
rm -rf "$HERE"/.elm-pi-verify.* "$HERE"/.elm-pi-stage-* "$HERE"/*.dev-setup-partial "$HERE"/agent/*.dev-setup-partial "$HERE"/agent/skills/*.dev-setup-partial

mkdir -p "$HERE/.pi/tmp"
LOG="$HERE/.pi/tmp/dev-setup.log"
pass=()
for name in ELM_API_KEY ELM_BASE_URL HTTPS_PROXY HTTP_PROXY NO_PROXY https_proxy http_proxy no_proxy; do
  if [ -n "${!name:-}" ]; then pass+=("$name=${!name}"); fi
done
# The skill library (agent/skills/kdense) is a 245 MB download from GitHub, and this runs without the
# network: the clone gets the install's copy when that is the commit config/skill-library.json pins,
# keeps its own when it already has that commit, and otherwise goes without.
library=(--no-skill-library)
pinned="$(sed -n 's/^ *"commit": "\([0-9a-f]\{40\}\)".*/\1/p' "$HERE/config/skill-library.json" 2>/dev/null | head -n 1)"
has_library() { [ -n "$pinned" ] && grep -q "\"commit\": \"$pinned\"" "$1/agent/skills/kdense/.elm-pi-library" 2>/dev/null; }
if has_library "$HERE" && [ "$FRESH" != "1" ]; then
  library=(--with-skill-library)
elif has_library "$FROM"; then
  mkdir -p "$HERE/agent/skills"
  clone_tree "$FROM/agent/skills/kdense" "$HERE/agent/skills/kdense"
  library=(--with-skill-library)
fi
# --no-python: the agent's Python is built by default, and building it downloads CPython and PyPI
# packages; a development clone needs neither, and this runs without the network.
set +e
( cd "$HERE" && env -i HOME="$HOME" USER="${USER:-}" LOGNAME="${LOGNAME:-}" LANG="${LANG:-C.UTF-8}" TERM=dumb \
    PATH="/usr/bin:/bin:/usr/sbin:/sbin" ${pass[@]+"${pass[@]}"} ./bootstrap.sh --no-python "${library[@]}" < /dev/null ) > "$LOG" 2>&1
status=$?
set -e
loaded="$(grep -o '[0-9]* extensions loaded, [0-9]* failed' "$LOG" | tail -n 1 || true)"
if [ "$status" -ne 0 ]; then
  echo "dev-setup: bootstrap failed (exit $status). The end of $LOG:" >&2
  tail -n 25 "$LOG" >&2
  exit "$status"
fi
echo "dev-setup: done - ${loaded:-extensions not counted}. This clone is now a working elm-pi install:"
echo "    scripts/check-extension <name>     load one extension with pi's own loader, and check it is registered, documented and tested"
echo "    python3 -m unittest discover -s tests     the whole suite (a few minutes)"
echo "    T=\$(mktemp -d) && cd \"\$T\" && $HERE/pi --auto -p 'use the new tool on ...' < /dev/null"
echo "                                       a real session on this clone's code, outside it (its .pi/ is gitignored)"
