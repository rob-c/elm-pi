#!/usr/bin/env bash
# Keep this account's own toolchains out of elm-pi's processes. Sourced by
# bootstrap.sh, configure.sh, scripts/check.sh, install.sh (from the downloaded
# source) and the launcher; it must not execute anything at source time.
#
# The install has to come out the same on a clean laptop and on an account with
# an activated conda base, a pyenv shim, an nvm node, PYTHONPATH and
# NODE_OPTIONS in the profile, a ~/.npmrc pointing at a private registry, and a
# root-owned ~/.npm left by a long-ago `sudo npm`. Each of those has broken an
# install somewhere. The one that prompted this file: conda's base env put a
# Python 3.8 first on PATH, and bootstrap died on str.removeprefix halfway
# through, before the launcher was linked.
#
#   Python   one interpreter, chosen here: 3.8 or newer (macOS 11's Command
#            Line Tools ship 3.8), never conda, a virtualenv or a version-manager
#            shim unless named explicitly with ELM_PI_PYTHON, and always run as
#            `python -E -S` - no PYTHON* variables, no site-packages, no .pth
#            files. Every Python file in this repo is stdlib-only, so nothing
#            needs site-packages. When the machine has no such interpreter, the
#            install downloads a pinned, checksummed standalone CPython into
#            .python (elm_ensure_python). Only elm-pi's own scripts need
#            Python: pi is Node, and its npm packages run no Python.
#   npm      the bundled one, run by the bundled node, with its config, cache
#            and global prefix all inside the install (config/npmrc,
#            .npm-cache, .node). ~/.npmrc and npm_config_* are never read.
#   env      install-time work (elm_install_env) drops every variable that
#            redirects Python, conda, Node, npm, git or their version managers,
#            and puts the system directories first on PATH.
#
# The launcher deliberately does NOT scrub: the agent's own bash tool needs the
# researcher's conda and PATH to do their work. It isolates per call instead -
# elm_py for its own Python, pi.orig drops NODE_OPTIONS/NODE_PATH for pi's node,
# and `pi install`/`pi remove` get elm_npm_env.

# ELM_PY_ERROR, ELM_PI_ROOT and ELM_PI_USER_PATH are set here for the scripts
# that source this file.
# shellcheck disable=SC2034

# Variables starting with any of these are removed by elm_scrub_env. install.sh
# carries an identical copy for the steps before this file has been downloaded;
# tests/test_sandbox.py fails if the two drift.
ELM_SCRUB_PREFIXES="PYTHON CONDA _CE_ MAMBA VIRTUAL_ENV PIP_ PYENV npm_config_ NPM_CONFIG_ NODE_ NVM_ VOLTA_ FNM_ ASDF_ COREPACK_ YARN_ PNPM_ BUN_ GIT_"
# Removed by exact name. BASH_ENV/ENV are sourced by every non-interactive
# child bash, CDPATH makes `cd dir` print and land somewhere else, and TAR/GZIP/
# UNZIP/GREP_OPTIONS change how the archive tools behave.
ELM_SCRUB_NAMES="BASH_ENV ENV CDPATH TAR_OPTIONS GZIP UNZIP UNZIPOPT GREP_OPTIONS CURL_HOME LD_PRELOAD LD_LIBRARY_PATH"
# Matched by a prefix above but kept: an institution's TLS-intercepting proxy
# needs its CA, and dropping it turns every download into a certificate error.
ELM_SCRUB_KEEP="NODE_EXTRA_CA_CERTS"

ELM_PY_MIN_MAJOR=3
ELM_PY_MIN_MINOR=8
ELM_NPM_REGISTRY="https://registry.npmjs.org/"
ELM_PY_ERROR=""

elm_scrub_env() {
  local name prefix
  for name in $(compgen -e); do
    case " $ELM_SCRUB_KEEP " in *" $name "*) continue ;; esac
    for prefix in $ELM_SCRUB_PREFIXES; do
      case "$name" in
        "$prefix"*) unset "$name" 2>/dev/null || true; break ;;
      esac
    done
  done
  for name in $ELM_SCRUB_NAMES; do
    unset "$name" 2>/dev/null || true
  done
  # A CA bundle variable that names a file which no longer exists - typically
  # inside a conda env since deleted - fails every TLS connection. One that
  # exists is the institution's and is kept.
  for name in SSL_CERT_FILE CURL_CA_BUNDLE REQUESTS_CA_BUNDLE NODE_EXTRA_CA_CERTS; do
    if [ -n "${!name:-}" ] && [ ! -f "${!name}" ]; then
      unset "$name" 2>/dev/null || true
    fi
  done
}

# Prints $1 (a PATH value) without relative entries, duplicates, or any
# directory that belongs to conda, a virtualenv or a version manager.
#   $2 = "relative-only": drop only relative entries and duplicates. The
#        launcher uses this - the agent's shell keeps the researcher's conda, but
#        a "." on PATH means a repository's own ./git or ./node runs whenever pi
#        looks for that command in it.
elm_clean_path() {
  local entry out="" old_ifs="$IFS" restore_glob=0 mode="${2:-}"
  case "$-" in *f*) ;; *) set -f; restore_glob=1 ;; esac
  IFS=:
  for entry in $1; do
    case "$entry" in
      /*) ;;
      *) continue ;;   # "", "." or relative: resolves against whatever the cwd is
    esac
    entry="${entry%/}"
    [ -n "$entry" ] || continue
    case ":$out:" in *":$entry:"*) continue ;; esac
    if [ "$mode" = "relative-only" ]; then
      out="${out:+$out:}$entry"; continue
    fi
    case "$entry" in
      */.pyenv/*|*/.nvm/*|*/.volta/*|*/.fnm/*|*/fnm_multishells/*|*/.asdf/*|*/.npm-global*|*/node_modules/*) continue ;;
    esac
    # Structural rather than by name: a conda base or env has conda-meta beside
    # its bin (and condabin), a virtualenv has pyvenv.cfg.
    [ -d "$entry/../conda-meta" ] && continue
    [ -f "$entry/../pyvenv.cfg" ] && continue
    case ":$out:" in *":$entry:"*) continue ;; esac
    out="${out:+$out:}$entry"
  done
  IFS="$old_ifs"
  [ "$restore_glob" = "0" ] || set +f
  printf '%s' "$out"
}

# On a Mac without the Command Line Tools, /usr/bin/python3 and /usr/bin/git
# are stubs that open an install dialog and fail. Never run one to find out.
elm_is_macos_stub() {
  [ "$(uname -s)" = "Darwin" ] || return 1
  case "$1" in /usr/bin/*) ;; *) return 1 ;; esac
  ! xcode-select -p >/dev/null 2>&1
}

# 0 usable, 1 missing or not runnable, 10 too old, 11 conda, 12 virtualenv,
# 13 a version-manager shim (pyenv/asdf: which Python it runs depends on the
# directory it is started in).
elm_python_check() {
  local py="$1"
  case "$py" in /*) ;; *) return 1 ;; esac
  [ -f "$py" ] && [ -x "$py" ] || return 1
  case "$py" in */.pyenv/*|*/.asdf/*|*/shims/*) return 13 ;; esac
  elm_is_macos_stub "$py" && return 1
  # Written to run under any Python at all, 2.x included, so that an old one
  # reports "too old" rather than a syntax error.
  "$py" -E -S -c "import os, sys
if sys.version_info[:2] < ($ELM_PY_MIN_MAJOR, $ELM_PY_MIN_MINOR): sys.exit(10)
if os.path.isdir(os.path.join(sys.prefix, 'conda-meta')): sys.exit(11)
if os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sys.executable))), 'pyvenv.cfg')): sys.exit(12)
" </dev/null >/dev/null 2>&1
}

elm_python_reason() {
  case "$1" in
    10) echo "older than $ELM_PY_MIN_MAJOR.$ELM_PY_MIN_MINOR" ;;
    11) echo "conda" ;;
    12) echo "virtualenv" ;;
    13) echo "version-manager shim" ;;
    *)  echo "does not run" ;;
  esac
}

# Interpreters worth trying, most preferred first, one per line. System and
# package-manager locations come before anything on PATH, so an activated
# environment cannot change which one is picked.
elm_python_candidates() {
  local dir name old_ifs="$IFS" restore_glob=0
  for dir in /usr/bin /usr/local/bin /opt/homebrew/bin \
             /Library/Frameworks/Python.framework/Versions/Current/bin; do
    for name in python3 python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3.8; do
      [ -x "$dir/$name" ] && printf '%s\n' "$dir/$name"
    done
  done
  # Ours, downloaded by elm_ensure_python. After the system ones, so that it is
  # used only where the machine has nothing suitable (or it was asked for).
  [ -z "${1:-}" ] || { [ -x "$1/.python/bin/python3" ] && printf '%s\n' "$1/.python/bin/python3"; }
  case "$-" in *f*) ;; *) set -f; restore_glob=1 ;; esac
  IFS=:
  for dir in $(elm_clean_path "${ELM_PI_USER_PATH:-$PATH}"); do
    [ -x "$dir/python3" ] && printf '%s\n' "$dir/python3"
  done
  IFS="$old_ifs"
  [ "$restore_glob" = "0" ] || set +f
}

# Sets and exports ELM_PI_PYTHON, or sets ELM_PY_ERROR and returns 1.
#   $1 = install dir, for the interpreter bootstrap recorded in agent/python-path
#   $2 = "fast" to trust a recorded interpreter that is still executable without
#        starting it - the launcher runs this on every start, sub-agents included
elm_select_python() {
  local root="${1:-}" mode="${2:-}" py rc recorded="" rejected="" seen=":" candidates
  ELM_PY_ERROR=""

  # Named explicitly: conda or a virtualenv is the caller's decision to make.
  # Too old or not runnable is not, and there is no silent fallback from it.
  if [ -n "${ELM_PI_PYTHON:-}" ]; then
    rc=0; elm_python_check "$ELM_PI_PYTHON" || rc=$?
    case "$rc" in
      0|11|12) export ELM_PI_PYTHON; return 0 ;;
      13) ELM_PY_ERROR="ELM_PI_PYTHON=$ELM_PI_PYTHON is a version-manager shim; name the real interpreter (e.g. \`pyenv which python3\`)" ;;
      10) ELM_PY_ERROR="ELM_PI_PYTHON=$ELM_PI_PYTHON is older than Python $ELM_PY_MIN_MAJOR.$ELM_PY_MIN_MINOR" ;;
      *)  ELM_PY_ERROR="ELM_PI_PYTHON=$ELM_PI_PYTHON is not a runnable Python (it must be an absolute path)" ;;
    esac
    return 1
  fi

  if [ -n "$root" ] && [ -f "$root/agent/python-path" ]; then
    recorded="$(cat "$root/agent/python-path" 2>/dev/null || true)"
    if [ -n "$recorded" ]; then
      if [ "$mode" = "fast" ] && [ -x "$recorded" ]; then
        ELM_PI_PYTHON="$recorded"; export ELM_PI_PYTHON; return 0
      fi
      # Re-validated at install time, and kept when it still passes, so a newly
      # installed Homebrew Python does not swap the interpreter under an install.
      if elm_python_check "$recorded"; then
        ELM_PI_PYTHON="$recorded"; export ELM_PI_PYTHON; return 0
      fi
    fi
  fi

  candidates="$(elm_python_candidates "$root")"
  while IFS= read -r py; do
    [ -n "$py" ] || continue
    case "$seen" in *":$py:"*) continue ;; esac
    seen="$seen$py:"
    rc=0; elm_python_check "$py" || rc=$?
    if [ "$rc" = "0" ]; then
      ELM_PI_PYTHON="$py"; export ELM_PI_PYTHON; return 0
    fi
    [ "$rc" = "1" ] || rejected="$rejected
      $py ($(elm_python_reason "$rc"))"
  done <<EOF
$candidates
EOF

  ELM_PY_ERROR="no usable Python $ELM_PY_MIN_MAJOR.$ELM_PY_MIN_MINOR+ found. elm-pi does not use conda, virtualenv
    or pyenv interpreters, whatever is first on PATH.${rejected:+
    Rejected:$rejected}
    macOS:  xcode-select --install     (provides /usr/bin/python3)
    Linux:  install python3 >= $ELM_PY_MIN_MAJOR.$ELM_PY_MIN_MINOR from the system package manager
    Or name one explicitly:  ELM_PI_PYTHON=/absolute/path/to/python3"
  return 1
}

# A standalone CPython (astral-sh/python-build-standalone, install_only), for
# machines with no usable Python of their own: macOS 11 without the Command Line
# Tools, an old RHEL login node with 3.6 and conda. Pinned like Node, verified
# against the digests below, and unpacked into the install - rm -rf takes it.
# The macOS builds run on 10.13 and later; the Linux ones need glibc 2.17.
ELM_STANDALONE_PY_RELEASE="20261003"
ELM_STANDALONE_PY_VERSION="3.12.15"
elm_standalone_python_asset() {   # prints "<asset> <sha256>" for this machine
  local triple
  case "$(uname -s)/$(uname -m)" in
    Darwin/arm64)                triple=aarch64-apple-darwin ;;
    Darwin/x86_64)               triple=x86_64-apple-darwin ;;
    Linux/x86_64|Linux/amd64)    triple=x86_64-unknown-linux-gnu ;;
    Linux/aarch64|Linux/arm64)   triple=aarch64-unknown-linux-gnu ;;
    *) return 1 ;;
  esac
  printf 'cpython-%s+%s-%s-install_only.tar.gz ' "$ELM_STANDALONE_PY_VERSION" "$ELM_STANDALONE_PY_RELEASE" "$triple"
  case "$triple" in
    aarch64-apple-darwin)      echo 316a463172740e71d8dca1f2730784e325f3f720941137b5d674d5801a632213 ;;
    x86_64-apple-darwin)       echo a8fd7a91852f19b6d959793ef41fad048631ccb2a334a9ecdf573255298f7978 ;;
    x86_64-unknown-linux-gnu)  echo f937814031eab4698ca6d07ec606ede1825768f3f3e99af76d9db3900bee03c5 ;;
    aarch64-unknown-linux-gnu) echo 95c01982c9fcb9d95b0acfdb5eb8a6e0099dd11edf062314a474228d93f2b765 ;;
  esac
}

elm_install_standalone_python() {   # $1 = install dir; prints progress, returns 1 on failure
  local root="$1" spec asset sha got tmp
  spec="$(elm_standalone_python_asset)" || { echo "    no standalone Python build for $(uname -s)/$(uname -m)"; return 1; }
  asset="${spec%% *}"; sha="${spec##* }"
  tmp="$(mktemp -d)"
  echo "    downloading $asset (~20MB)"
  if ! curl -q -fsSL -o "$tmp/$asset" \
       "https://github.com/astral-sh/python-build-standalone/releases/download/$ELM_STANDALONE_PY_RELEASE/${asset//+/%2B}"; then
    rm -rf "$tmp"; echo "    download failed"; return 1
  fi
  if command -v sha256sum >/dev/null 2>&1; then got="$(sha256sum "$tmp/$asset" | awk '{print $1}')"
  else got="$(shasum -a 256 "$tmp/$asset" | awk '{print $1}')"; fi
  if [ "$got" != "$sha" ]; then
    rm -rf "$tmp"; echo "    checksum mismatch for $asset"; return 1
  fi
  mkdir -p "$tmp/x"
  if ! tar -xzf "$tmp/$asset" -C "$tmp/x" --strip-components=1; then
    rm -rf "$tmp"; echo "    could not unpack $asset"; return 1
  fi
  rm -rf "$root/.python" && mkdir -p "$root" && mv "$tmp/x" "$root/.python"
  rm -rf "$tmp"
  echo "    installed $root/.python ($ELM_STANDALONE_PY_VERSION)"
}

# elm_select_python, and when that finds nothing, the standalone build. Install
# time only: the launcher never downloads anything.
#   ELM_PI_BUNDLED_PYTHON=1   use the standalone build even when the machine has
#                             a usable Python of its own
elm_ensure_python() {   # $1 = install dir
  local root="$1" first_error
  if [ "${ELM_PI_BUNDLED_PYTHON:-0}" = "1" ] && [ -z "${ELM_PI_PYTHON:-}" ]; then
    if [ ! -x "$root/.python/bin/python3" ]; then
      elm_install_standalone_python "$root" || { ELM_PY_ERROR="could not install the standalone Python"; return 1; }
    fi
    ELM_PI_PYTHON="$root/.python/bin/python3"
  fi
  elm_select_python "$root" && return 0
  # An explicit ELM_PI_PYTHON that fails is an error, not a cue to download.
  [ -z "${ELM_PI_PYTHON:-}" ] || return 1
  first_error="$ELM_PY_ERROR"
  echo "    no usable system Python $ELM_PY_MIN_MAJOR.$ELM_PY_MIN_MINOR+ (conda/venv/pyenv are not used) - installing a standalone one"
  if elm_install_standalone_python "$root" && elm_select_python "$root"; then
    return 0
  fi
  ELM_PY_ERROR="$first_error"
  return 1
}

# Runs the selected interpreter isolated: no PYTHON* variables (-E), no
# site-packages or .pth files (-S), and started from inside the install so
# that a json.py or os.py in the caller's project cannot shadow the stdlib for
# `-c` and stdin scripts. Arguments must therefore be absolute, or relative to
# ELM_PI_ROOT.
elm_py() {
  ( cd "${ELM_PI_ROOT:-/}" && exec "${ELM_PI_PYTHON:?elm_select_python has not run}" -E -S "$@" )
}

# npm reads, in order of precedence: the command line, npm_config_* variables,
# the project .npmrc, the user .npmrc and the global npmrc. The variables are
# dropped, the user and global files are replaced with this install's own, and
# the cache and global prefix are moved inside the install. Nothing npm writes
# lands in ~/.npm, and nothing in ~/.npmrc is read.
#
#   ELM_PI_NPM_USERCONFIG=/path   use this npmrc instead of config/npmrc, for a
#                                 site that needs its own cafile or proxy
elm_npm_env() {   # $1 = install dir
  local root="$1" name
  for name in $(compgen -e); do
    case "$name" in
      [Nn][Pp][Mm]_[Cc][Oo][Nn][Ff][Ii][Gg]_*) unset "$name" 2>/dev/null || true ;;
    esac
  done
  # npm refuses one file loaded as both the user and the global config.
  export NPM_CONFIG_USERCONFIG="${ELM_PI_NPM_USERCONFIG:-$root/config/npmrc}"
  export NPM_CONFIG_GLOBALCONFIG="/dev/null"
  export NPM_CONFIG_CACHE="$root/.npm-cache"
  export NPM_CONFIG_PREFIX="$root/.node"
  export NPM_CONFIG_UPDATE_NOTIFIER="false"
  unset NODE_OPTIONS NODE_PATH NODE_ENV 2>/dev/null || true
}

# The bundled npm, by the bundled node, by path: never an `npm` found on PATH,
# whose `#!/usr/bin/env node` line would pick up whichever node comes first.
elm_npm() {
  local root="${ELM_PI_ROOT:?}"
  "$root/.node/bin/node" "$root/.node/lib/node_modules/npm/bin/npm-cli.js" "$@"
}

# Confirms npm resolves the configuration elm_npm_env set, by asking npm rather
# than trusting the variables. Prints the first disagreement and returns 1.
# cache, prefix and userconfig are "protected" and npm will not print them, so
# the global prefix is checked through `npm prefix -g` instead.
elm_npm_verify() {   # $1 = install dir
  local root="$1" got
  got="$(cd "$root" && elm_npm prefix -g 2>/dev/null)" || { echo "npm does not run"; return 1; }
  # npm prints UUID-shaped path segments as *** (it redacts them as possible
  # tokens), so compare with the same redaction applied to what we expect.
  elm_py -c '
import re, sys
uuid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
sys.exit(0 if uuid.sub("***", sys.argv[1]) == uuid.sub("***", sys.argv[2]) else 1)
' "$got" "$root/.node" || { echo "npm global prefix is $got, not $root/.node"; return 1; }
  got="$(cd "$root" && elm_npm config list -l --json 2>/dev/null)" || { echo "npm config does not load"; return 1; }
  printf '%s' "$got" | elm_py -c '
import json, sys
config = json.load(sys.stdin)
want = {"registry": sys.argv[1], "ignore-scripts": True, "globalconfig": "/dev/null"}
for key, value in want.items():
    if config.get(key) != value:
        print("npm %s is %r, not %r" % (key, config.get(key), value))
        sys.exit(1)
' "$ELM_NPM_REGISTRY"
}

# Everything install-time work needs: a scrubbed environment, the bundled Node
# and the system directories ahead of anything a profile added, and npm
# confined to the install. The account's PATH is kept in ELM_PI_USER_PATH,
# unexported, for the steps that are about the account rather than the install
# (where to link pi, whether another pi wins).
elm_install_env() {   # $1 = install dir
  local root="$1"
  ELM_PI_USER_PATH="${ELM_PI_USER_PATH:-$PATH}"
  elm_scrub_env
  PATH="$(elm_clean_path "$root/.node/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH")"
  export PATH
  elm_npm_env "$root"
  # npm fetches git dependencies with git, and nothing in ~/.gitconfig (url
  # rewrites, hooks paths, credential helpers) belongs in an install.
  export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_TERMINAL_PROMPT=0
  # Files the install writes are not writable by others whatever the account's
  # umask is; a 000 umask would let anyone on the machine edit pi's code.
  umask 022
  ELM_PI_ROOT="$root"
}

# --- runtime ------------------------------------------------------------------

# .env holds the key. It used to be sourced as shell, which made it a script
# anything could be appended to - a PYTHONPATH, a NODE_OPTIONS, a command. It
# is now read as data: KEY=value lines for ELM_* keys, an optional `export `,
# optional matching quotes, no expansion, nothing executed. Other lines are
# reported and ignored.
elm_load_dotenv() {   # $1 = file
  local file="$1" line key value number=0
  [ -f "$file" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    number=$((number + 1))
    line="${line%$'\r'}"
    line="${line#"${line%%[![:space:]]*}"}"
    case "$line" in ""|"#"*) continue ;; esac
    line="${line#export }"
    key="${line%%=*}"
    if [ "$key" = "$line" ] || ! [[ "$key" =~ ^ELM_[A-Z0-9_]+$ ]]; then
      echo "elm-pi: ignoring line $number of $file - only ELM_*=value lines are read" >&2
      continue
    fi
    value="${line#*=}"
    case "$value" in
      \"*\") value="${value#\"}"; value="${value%\"}" ;;
      \'*\') value="${value#\'}"; value="${value%\'}" ;;
    esac
    export "$key=$value"
  done < "$file"
}

# True when $1 is a real directory, not a symlink, owned by this account and
# writable by nobody else.
elm_dir_is_private() {
  [ -d "$1" ] && [ ! -L "$1" ] && [ -O "$1" ] || return 1
  [ -z "$(find "$1" -maxdepth 0 \( -perm -0002 -o -perm -0020 \) 2>/dev/null)" ]
}

# pi's extensions are transpiled by jiti into $TMPDIR/jiti and the result is
# executed on every later launch. On macOS TMPDIR is already private. On a
# Linux login node it is usually unset, which means /tmp/jiti - shared by every
# account on the node, so whoever creates it first decides what pi runs. Point
# TMPDIR at a directory only this account can write, on the same filesystem,
# for pi and everything it starts.
elm_private_tmpdir() {
  local base="${TMPDIR:-/tmp}" dir
  base="${base%/}"; [ -n "$base" ] || base=/tmp
  elm_dir_is_private "$base" && return 0
  dir="$base/elm-pi-$(id -u)"
  [ -e "$dir" ] || ( umask 077; mkdir "$dir" ) 2>/dev/null || true
  if ! elm_dir_is_private "$dir"; then
    ELM_PY_ERROR="$dir is not a private directory owned by you (a symlink, or someone else's?) - set TMPDIR to one that is"
    return 1
  fi
  TMPDIR="$dir"; export TMPDIR
}

# node_modules directories in the install's ancestors, one per line. Node and
# jiti both search every ancestor of the importing file, so any of these can
# supply a package to pi. lib/node-guard.mjs stops Node's own loader using
# them; jiti resolves on its own and only this check covers it.
elm_external_module_dirs() {   # $1 = install dir
  local start dir
  for start in "$1" "$(cd "$1" && pwd -P)"; do
    dir="$start"
    while [ -n "$dir" ] && [ "$dir" != "/" ]; do
      dir="${dir%/*}"
      if [ -e "${dir:-}/node_modules" ]; then printf '%s\n' "${dir:-}/node_modules"; fi
    done
  done | awk '!seen[$0]++'
  return 0
}

# Makes every code tree in the install writable by its owner only (owner and
# group when ELM_PI_SHARED_STATE=1 says the install is shared on purpose).
# An install unpacked under a 000 or 002 umask, or copied in by a tool that
# keeps modes, is otherwise code anyone on the machine can edit.
elm_tighten_install_perms() {   # $1 = install dir
  local root="$1" mask="go-w" path
  [ "${ELM_PI_SHARED_STATE:-0}" = "1" ] && mask="o-w"
  chmod "$mask" "$root" 2>/dev/null || true
  for path in .node .python node_modules agent/npm agent/bin agent/extensions agent/agents \
              lib config templates proxy shim scripts patch-pi.py pi pi.orig \
              bootstrap.sh install.sh configure.sh; do
    if [ -e "$root/$path" ]; then chmod -R "$mask" "$root/$path" 2>/dev/null || true; fi
  done
}
