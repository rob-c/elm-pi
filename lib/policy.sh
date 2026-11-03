#!/usr/bin/env bash
# Argument-level ELM provider policy. This file is sourced by the launcher and
# by the parser tests; it must not execute anything at source time.

elm_policy_trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

elm_policy_provider_allowed() {
  local candidate allowed
  candidate="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  for allowed in ${ELM_ALLOWED_PROVIDERS:-elm elm-shim}; do
    allowed="$(printf '%s' "$allowed" | tr '[:upper:]' '[:lower:]')"
    [ "$candidate" = "$allowed" ] && return 0
  done
  return 1
}

elm_policy_model_allowed() {
  local candidate lower provider
  candidate="$(elm_policy_trim "$1")"
  lower="$(printf '%s' "$candidate" | tr '[:upper:]' '[:lower:]')"

  # Exact bare ids are accepted for compatibility with pi's cross-provider
  # resolver. Every other slash-bearing value must carry an allowed provider.
  if [ "$lower" = "$(printf '%s' "${ELM_QWEN_MODEL_ID:-}" | tr '[:upper:]' '[:lower:]')" ] || \
     [ "$lower" = "$(printf '%s' "${ELM_LLAMA_MODEL_ID:-}" | tr '[:upper:]' '[:lower:]')" ]; then
    return 0
  fi
  provider="${candidate%%/*}"
  [ "$provider" != "$candidate" ] && elm_policy_provider_allowed "$provider"
}

# True when pi takes the argument after $1 as that option's value whatever it
# is, "--" and other options included: the options pi 1.5.0's parser
# (dist/cli/args.js) reads with args[++i] whenever there is a next argument.
# The others that take a value take it only when it does not start with "-"
# (--mode, --list-models, an unknown --flag) or is "---" text (-p), so never
# an option or "--". Whoever walks pi's arguments skips these values, or
# `--name -- --model x` reads as prompt text to them and as a model to pi.
elm_policy_takes_value() {
  case "$1" in
    --provider|--model|--api-key|--system-prompt|--append-system-prompt|--name|-n|\
    --session|--session-id|--fork|--session-dir|--models|--tools|-t|--exclude-tools|-xt|\
    --thinking|--export|--extension|-e|--skill|--prompt-template|--theme) return 0 ;;
  esac
  return 1
}

# True when pi's own extension discovery is disabled. Parse the short alias as
# well as the long spelling, and stop at -- because everything after it is
# literal prompt text - the -- pi reads as such, not an option's value.
elm_policy_extensions_disabled() {
  local arg value=0
  for arg in "$@"; do
    if [ "$value" = "1" ]; then value=0; continue; fi
    case "$arg" in
      --) return 1 ;;
      --no-extensions|-ne) return 0 ;;
    esac
    if elm_policy_takes_value "$arg"; then value=1; fi
  done
  return 1
}

# Sets ELM_POLICY_ERROR and returns non-zero when the effective final routing
# arguments leave the allowlist, or when they load an extension of the caller's
# choosing. pi itself uses the last repeated --provider, --model and --models,
# so the guard does too; it loads every -e, so any one is refused. Tokens after
# -- are prompt text, not options, unless that -- is the value of an option
# before it (elm_policy_takes_value): pi reads on as options then. An option
# left without its value at the end takes none - pi reads a long one as an
# unknown flag, and has loaded the extensions before it stops on that - so the
# options before it are still checked.
#
# -e/--extension is refused whatever it names, an empty value included: pi
# resolves "" against the working folder and loads that as an extension. An
# extension runs inside pi with this install's access and its own network code:
# pi's own ssh.ts example sends read, write, edit and bash to another machine
# over SSH, which the egress proxy never sees, and the bridges published for pi
# relay whole sessions through Telegram or serve them to the local network. The reviewed extensions load
# without it; the launcher's own -e arguments are added after this check.
elm_policy_check_args() {
  local prev="" arg value="" provider="" model="" models="" api_key=0 extension="" extension_seen=0
  ELM_POLICY_ERROR=""
  export ELM_POLICY_ERROR

  # These are package/catalogue-management commands, not model sessions.
  # In particular, `update --models` uses --models as a valueless switch.
  case "${1:-}" in update|install|remove) return 0 ;; esac

  while [ "$#" -gt 0 ]; do
    arg="$1"; shift
    if [ "$prev" = "stop" ]; then
      continue
    fi
    if [ -n "$prev" ]; then
      case "$prev" in
        provider) provider="$arg" ;;
        model) model="$arg" ;;
        models) models="$arg" ;;
        api-key) api_key=1 ;;
        extension) extension="$arg"; extension_seen=1 ;;
      esac
      prev=""
      continue
    fi
    case "$arg" in
      --) prev="stop" ;;
      --provider) prev="provider" ;;
      --provider=*) provider="${arg#*=}" ;;
      --model|-m) prev="model" ;;
      --model=*|-m=*) model="${arg#*=}" ;;
      -m?*) model="${arg#-m}" ;;
      --models) prev="models" ;;
      --models=*) models="${arg#*=}" ;;
      --api-key) prev="api-key" ;;
      --api-key=*) api_key=1 ;;
      -e|--extension) prev="extension" ;;
      # pi reads this as an unknown flag, not an extension; refused all the
      # same unless it is empty, which loads nothing.
      --extension=?*) extension="${arg#*=}"; extension_seen=1 ;;
      *) if elm_policy_takes_value "$arg"; then prev="value"; fi ;;
    esac
  done

  if [ "$extension_seen" = "1" ]; then
    ELM_POLICY_ERROR="-e/--extension is disabled: \"$extension\" would run unreviewed, with this install's access and its own network code."
    return 1
  fi
  if [ "$api_key" = "1" ]; then
    ELM_POLICY_ERROR="--api-key is disabled: it can route a session to another provider."
    return 1
  fi
  if [ -n "$provider" ] && ! elm_policy_provider_allowed "$(elm_policy_trim "$provider")"; then
    ELM_POLICY_ERROR="provider \"$provider\" is not available."
    return 1
  fi
  if [ -n "$model" ] && ! elm_policy_model_allowed "$model"; then
    ELM_POLICY_ERROR="model \"$model\" is outside the allowed providers."
    return 1
  fi
  if [ -n "$models" ]; then
    # Split on commas by hand, as pi does, dropping empty patterns as it does.
    # Not IFS=, and an unquoted expansion: that IFS reached the allowlist split
    # in elm_policy_provider_allowed, and the expansion globbed elm/* against
    # the current folder.
    local rest="$models," item
    while [ -n "$rest" ]; do
      item="$(elm_policy_trim "${rest%%,*}")"
      rest="${rest#*,}"
      [ -n "$item" ] || continue
      if ! elm_policy_model_allowed "$item"; then
        ELM_POLICY_ERROR="model pattern \"$item\" is outside the allowed providers."
        return 1
      fi
    done
  fi
  return 0
}

# Sets ELM_POLICY_PATH to $1 with a leading ~ or ~/ - a literal one from the
# config, not one for the shell to expand - replaced by $HOME.
elm_policy_tilde() {
  # shellcheck disable=SC2088
  case "$1" in
    "~") ELM_POLICY_PATH="$HOME" ;;
    "~/"*) ELM_POLICY_PATH="$HOME/${1#\~/}" ;;
    *) ELM_POLICY_PATH="$1" ;;
  esac
}

# Sets ELM_POLICY_PATH to $1 made absolute against $PWD and resolved as text,
# as a shell's cd resolves it: repeated slashes and . dropped, .. taking off
# the name before it. A variable rather than output, to save a fork per call.
elm_policy_lexical() {
  local rest out="" part
  case "$1" in /*) rest="$1/" ;; *) rest="$PWD/$1/" ;; esac
  while [ -n "$rest" ]; do
    part="${rest%%/*}"; rest="${rest#*/}"
    case "$part" in
      ""|.) ;;
      ..) out="${out%/*}" ;;
      *) out="$out/$part" ;;
    esac
  done
  ELM_POLICY_PATH="${out:-/}"
}

# The folder's own path: symlinks followed, and the spelling the disk has, not
# the one typed. bash's cd and its pwd -P keep a leading // and, on a case- or
# normalisation-insensitive volume (macOS), the typed case and Unicode form, so
# ~/downloads would not be ~/Downloads to a text comparison. /bin/pwd asks the
# kernel (getcwd), which reports the folder as the disk has it, as pi's
# process.cwd() does. A path that does not exist is resolved up to the deepest
# folder that does, and the rest kept as text.
elm_policy_canonical() {
  local p rest="" real
  elm_policy_tilde "$1"; elm_policy_lexical "$ELM_POLICY_PATH"; p="$ELM_POLICY_PATH"
  while [ "$p" != "/" ] && [ ! -d "$p" ]; do
    rest="/${p##*/}$rest"; p="${p%/*}"; p="${p:-/}"
  done
  if [ -x /bin/pwd ]; then
    real="$(cd "$p" 2>/dev/null && exec /bin/pwd -P 2>/dev/null)"
  else
    real="$(cd "$p" 2>/dev/null && pwd -P)"
  fi
  [ -n "$real" ] && p="$real"
  elm_policy_lexical "$p$rest"
  printf '%s' "$ELM_POLICY_PATH"
}

# True when $1 is a folder no session should start in: home, an ancestor of
# home, or another container listed in ELM_UNTRUSTED_EXACT (the folder itself,
# not what is under it), or anywhere inside a credential or system folder listed
# in ELM_UNTRUSTED_TREE. Both lists come from untrustedFolders in
# config/elm-pi.json through runtime.env, one path per line, ~ for home.
# Sets ELM_UNTRUSTED_WHAT to a short description for the refusal message.
#
# A folder that exists is compared by device and inode ([ -ef ], which follows
# symlinks), itself against home and the exact entries, and it and each folder
# above its canonical path against the tree entries: no spelling of a listed
# folder - /tmp for /private/tmp, a case or Unicode variant on macOS - gets
# past that, and it costs no process per entry. A path that does not exist (an
# argument, never the launcher's $PWD) cannot be inside a folder that does, so
# it is compared as canonical text, as pi does.
elm_untrusted_folder() {
  local dir home entry up exists=0
  ELM_UNTRUSTED_WHAT=""
  export ELM_UNTRUSTED_WHAT
  dir="$(elm_policy_canonical "$1")"
  [ -e "$dir" ] && exists=1
  home="$(elm_policy_canonical "~")"
  if [ "$dir" = "$home" ] || { [ "$exists" = "1" ] && [ "$dir" -ef "$HOME" ]; }; then
    ELM_UNTRUSTED_WHAT="your home folder"; return 0
  fi
  up="$home"
  while [ "$up" != "/" ] && [ -n "$up" ]; do
    up="${up%/*}"; up="${up:-/}"
    if [ "$dir" = "$up" ] || { [ "$exists" = "1" ] && [ "$dir" -ef "$up" ]; }; then
      ELM_UNTRUSTED_WHAT="a folder that contains your home folder"; return 0
    fi
  done
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    elm_policy_tilde "$entry"
    if [ "$exists" = "1" ]; then
      [ "$dir" -ef "$ELM_POLICY_PATH" ] || continue
    else
      [ "$dir" = "$(elm_policy_canonical "$entry")" ] || continue
    fi
    ELM_UNTRUSTED_WHAT="$entry, which holds far more than one project"; return 0
  done <<< "${ELM_UNTRUSTED_EXACT:-}"
  while IFS= read -r entry; do
    [ -n "$entry" ] || continue
    if [ "$exists" = "1" ]; then
      elm_policy_tilde "$entry"
      [ -d "$ELM_POLICY_PATH" ] || continue
      up="$dir"
      while ! [ "$up" -ef "$ELM_POLICY_PATH" ]; do
        [ "$up" != "/" ] || continue 2
        up="${up%/*}"; up="${up:-/}"
      done
    else
      up="$(elm_policy_canonical "$entry")"
      case "$dir/" in "$up"/*) ;; *) continue ;; esac
    fi
    ELM_UNTRUSTED_WHAT="inside $(elm_policy_canonical "$entry"), which holds credentials or system files"; return 0
  done <<< "${ELM_UNTRUSTED_TREE:-}"
  return 1
}
