#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$HERE"

SOURCE_ONLY=0
[ "${1:-}" = "--source-only" ] && SOURCE_ONLY=1

bash -n install.sh bootstrap.sh configure.sh pi pi.orig shim/run.sh lib/*.sh scripts/*.sh
python3 -c 'import ast, pathlib; [ast.parse(pathlib.Path(p).read_text(), filename=p) for p in ["patch-pi.py", "proxy/egress.py", "shim/shim.py", "scripts/elm_config.py"]]'
python3 -m unittest discover -s tests -v

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck -x install.sh bootstrap.sh configure.sh pi pi.orig shim/run.sh lib/*.sh scripts/*.sh
fi

if [ "$SOURCE_ONLY" = "0" ] && [ -x .node/bin/node ] && [ -x node_modules/.bin/tsc ]; then
  PATH="$HERE/.node/bin:$PATH" npm run typecheck
fi
