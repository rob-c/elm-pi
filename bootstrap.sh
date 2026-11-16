#!/usr/bin/env bash
# bootstrap.sh - the installer, and now only a hand-over.
#
# The installer itself is python/elmboot (python/README.md): which flags an
# install was made with, the Node, pi, tools and Python it downloads, what
# agent/ holds, and every check before "done" are decided there, in modules
# that can be read and tested one at a time. This file does the one thing that
# has to happen before any Python can run: find an interpreter - downloading a
# standalone one where the machine has none it can use - and start
# python/elmboot with it, isolated.
#
#   ./bootstrap.sh                  install everything, prompt for the ELM key
#   ELM_API_KEY=elm-... ./bootstrap.sh --non-interactive
#   ./bootstrap.sh --help           the flags
#
# The previous implementation is bootstrap.bash beside it: unchanged apart from
# naming itself, not what an install runs, and held to this one by the tests.
set -euo pipefail
unset CDPATH
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

die() { printf '\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

[ -f "$HERE/lib/sandbox.sh" ] || die "lib/sandbox.sh is missing"
[ -f "$HERE/python/elmboot/__main__.py" ] || die "python/elmboot is missing from this install"
# shellcheck source=lib/sandbox.sh
. "$HERE/lib/sandbox.sh"

# One interpreter, never conda's, a virtualenv's or a version manager's shim
# (lib/sandbox.sh says why): the one named, else the one this install recorded,
# else the system's. Found quietly, so that --help and a mistyped flag are
# answered by the installer before anything else is said.
if ! elm_select_python "$HERE"; then
  # A named interpreter that fails is an error, not a cue to download.
  [ -z "${ELM_PI_PYTHON:-}" ] || die "$ELM_PY_ERROR"
  # None the machine has will do: the standalone build, into .python. This is
  # the "Python" step of the install, said here because there is nothing to
  # run the installer with until it has finished.
  printf '\n\033[1m==> %s\033[0m\n' "Python"
  elm_ensure_python "$HERE" || die "$ELM_PY_ERROR"
  export ELM_PI_BOOTSTRAP_SAID_PYTHON=1
fi
export ELM_PI_PYTHON
# "try: ./bootstrap.sh --help" names this command as it was typed.
export ELM_PI_BOOTSTRAP_NAME="$0"

# A clean room for the installer itself:
#   -E  no PYTHON* variable is read      -s  no user site directory
#   -S  no site-packages, no .pth file   -B  no __pycache__ in the install
#   -u  what it says appears in order, between the lines of npm, uv and curl
#   -X utf8  the same decoding whatever the account's locale is
exec "$ELM_PI_PYTHON" -E -s -S -B -u -X utf8 "$HERE/python/elmboot/__main__.py" "$@"
