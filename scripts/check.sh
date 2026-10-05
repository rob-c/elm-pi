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
elm_py -c 'import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(), filename=p) for p in ["patch-pi.py", "proxy/egress.py", "shim/shim.py", "scripts/elm_config.py"]]'
elm_py -m unittest discover -s tests -v

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -x install.sh bootstrap.sh configure.sh pi pi.orig shim/run.sh lib/*.sh scripts/*.sh
fi

if [ "$SOURCE_ONLY" = "0" ] && [ -x .node/bin/node ] && [ -x node_modules/.bin/tsc ]; then
  elm_npm_env "$HERE"
  PATH="$HERE/.node/bin:$PATH" elm_npm run typecheck
fi
