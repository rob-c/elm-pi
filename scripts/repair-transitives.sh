#!/usr/bin/env bash
# Repair packages whose own published shrinkwrap defeats npm's root overrides.
# Every replacement source is still an exact, integrity-locked direct dependency.
set -euo pipefail

TREE="${1:?usage: repair-transitives.sh NODE_MODULES_DIR}"

package_version() {
  python3 - "$1/package.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))["version"])
PY
}

replace_with_locked() {
  local package="$1" wanted="$2" nested="$3" source
  source="$TREE/$package"
  [ -f "$source/package.json" ] || {
    echo "repair-transitives: locked source package is missing: $source" >&2
    exit 1
  }
  [ "$(package_version "$source")" = "$wanted" ] || {
    echo "repair-transitives: $source is not the reviewed version $wanted" >&2
    exit 1
  }
  [ -e "$nested" ] || return 0
  rm -rf -- "$nested"
  cp -R "$source" "$nested"
  [ "$(package_version "$nested")" = "$wanted" ] || {
    echo "repair-transitives: failed to install $package $wanted at $nested" >&2
    exit 1
  }
}

PI_ROOT="$TREE/@earendil-works/pi-coding-agent"
[ -f "$PI_ROOT/package.json" ] || {
  echo "repair-transitives: pi-coding-agent is missing from $TREE" >&2
  exit 1
}
replace_with_locked \
  brace-expansion 5.0.12 \
  "$PI_ROOT/node_modules/brace-expansion"

# pi-subagents normally resolves the safe root copy through the override. If a
# future published tree nests its exact old dependency, repair that copy too.
if [ -d "$TREE/pi-subagents" ]; then
  replace_with_locked \
    undici 8.10.2 \
    "$TREE/pi-subagents/node_modules/undici"
fi
