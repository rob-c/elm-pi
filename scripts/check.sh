#!/usr/bin/env bash
set -euo pipefail
unset CDPATH
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"
# shellcheck source=lib/sandbox.sh
. "$HERE/lib/sandbox.sh"
ELM_PI_ROOT="$HERE"
elm_select_python "$HERE" || { echo "check.sh: $ELM_PY_ERROR" >&2; exit 1; }

SOURCE_ONLY=0
[ "${1:-}" = "--source-only" ] && SOURCE_ONLY=1

bash -n install.sh bootstrap.sh configure.sh pi pi.orig shim/run.sh lib/*.sh scripts/*.sh
elm_py -c 'import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(), filename=p) for p in ["patch-pi.py", "proxy/egress.py", "shim/shim.py", "scripts/elm_config.py", "scripts/verify_install.py", "scripts/check_config.py", "scripts/pin_versions.py"]]'
elm_py -m unittest discover -s tests -v

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -x install.sh bootstrap.sh configure.sh pi pi.orig shim/run.sh lib/*.sh scripts/*.sh
fi

# The type check needs a node and typescript and nothing else, so it does not
# need the bundled ones: a checkout without .node (CI, a contributor's clone)
# uses the node on PATH - to run tsc, which installs and executes nothing. Said
# out loud when skipped, because a check that silently does not run reads as a
# pass.
if [ "$SOURCE_ONLY" = "0" ]; then
  NODE_BIN="$HERE/.node/bin/node"
  [ -x "$NODE_BIN" ] || NODE_BIN="$(command -v node 2>/dev/null || true)"
  if [ -z "$NODE_BIN" ]; then
    echo "check.sh: no node, bundled or on PATH - type check skipped" >&2
  elif [ ! -f node_modules/typescript/bin/tsc ]; then
    echo "check.sh: typescript is not installed here; run npm install - type check skipped" >&2
  else
    elm_npm_env "$HERE"   # no NODE_OPTIONS/NODE_PATH from the shell
    "$NODE_BIN" node_modules/typescript/bin/tsc -p tsconfig.json
  fi
fi
