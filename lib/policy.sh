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

# True when pi's own extension discovery is disabled. Parse the short alias as
# well as the long spelling, and stop at -- because everything after it is
# literal prompt text.
elm_policy_extensions_disabled() {
  local arg
  for arg in "$@"; do
    case "$arg" in
      --) return 1 ;;
      --no-extensions|-ne) return 0 ;;
    esac
  done
  return 1
}

# Sets ELM_POLICY_ERROR and returns non-zero when the effective final routing
# arguments leave the allowlist. pi itself uses the last repeated option, so the
# guard does too. Tokens after -- are prompt text, not options.
elm_policy_check_args() {
  local prev="" arg value="" provider="" model="" models="" api_key=0
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
    esac
  done

  if [ "$prev" = "provider" ] || [ "$prev" = "model" ] || [ "$prev" = "models" ] || [ "$prev" = "api-key" ]; then
    return 0 # pi reports its own missing-value error
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
    local old_ifs="$IFS" item
    IFS=','
    for item in $models; do
      if ! elm_policy_model_allowed "$item"; then
        IFS="$old_ifs"
        ELM_POLICY_ERROR="model pattern \"$(elm_policy_trim "$item")\" is outside the allowed providers."
        return 1
      fi
    done
    IFS="$old_ifs"
  fi
  return 0
}
