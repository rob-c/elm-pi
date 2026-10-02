#!/usr/bin/env bash
# Narrow permission hardening for state that can contain source, prompts, command
# output or credentials. Do not set a process-wide umask: the agent's bash tool
# inherits it and users reasonably expect ordinary project files to stay 0644.

elm_secure_file() {
  [ -e "$1" ] && chmod 600 "$1" 2>/dev/null || true
}

elm_set_auth_mode() {
  local path="$1" writable="${2:-0}"
  [ -e "$path" ] || return 0
  if [ "$writable" = "1" ]; then chmod 600 "$path"; else chmod 400 "$path"; fi
}

elm_secure_tree() {
  local dir="$1"
  [ -d "$dir" ] || return 0
  chmod 700 "$dir" 2>/dev/null || true
  find "$dir" -type d -exec chmod 700 {} + 2>/dev/null || true
  find "$dir" -type f -exec chmod 600 {} + 2>/dev/null || true
}

elm_secure_session_dir() {
  local dir="$1"
  if [ ! -d "$dir" ]; then
    (umask 077; mkdir -p "$dir")
  fi
  chmod 700 "$dir" 2>/dev/null || true
  # SessionManager writes JSONL transcripts. Do not recursively chmod every
  # file: a mistaken `--session-dir .` must not rewrite a whole project.
  find "$dir" -type f -name '*.jsonl' -exec chmod 600 {} + 2>/dev/null || true
}

# Match pi's path handling before changing permissions. CLI session paths may
# use file:// URLs; CLI, environment and settings paths may use ~. Relative
# paths are rooted at the launcher's working directory.
elm_normalize_session_dir() {
  python3 - "$1" "${2:-$PWD}" <<'PY'
import os
import sys
from urllib.parse import unquote, urlsplit

value, cwd = sys.argv[1:]
if value == "~":
    value = os.path.expanduser("~")
elif value.startswith("~/"):
    value = os.path.join(os.path.expanduser("~"), value[2:])
if value.startswith("file://"):
    parsed = urlsplit(value)
    if parsed.netloc not in ("", "localhost"):
        raise SystemExit(f"unsupported non-local session file URL: {value}")
    value = unquote(parsed.path)
if not os.path.isabs(value):
    value = os.path.join(cwd, value)
print(os.path.abspath(value))
PY
}

elm_secure_install_state() {
  local install_dir="$1"
  [ "${ELM_PI_SHARED_STATE:-0}" = "1" ] && return 0

  chmod 700 "$install_dir/agent" 2>/dev/null || true
  elm_secure_tree "$install_dir/agent/projects-memory"
  elm_secure_file "$install_dir/agent/egress.log"
}

elm_secure_runtime_state() {
  local install_dir="$1" session_dir="$2"
  [ "${ELM_PI_SHARED_STATE:-0}" = "1" ] && return 0

  elm_secure_session_dir "$session_dir"
  elm_secure_install_state "$install_dir"
}
