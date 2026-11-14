#!/bin/bash
# One batch: a fresh elm-pi install from the working tree, then every run in <runs.json> driven against it,
# <jobs> at a time, each in its own project folder. Then a summary table.
#   batch.sh <NAME> <runs.json> [jobs]      runs.json: [{"id":..,"flags":[..],"prompts":[..],"seed":dir?,"max":secs?}]
#
# Where things go, all outside the repository:
#   TREADMILL_WORK   test installs and project folders (default ~/sandbox)
#   TREADMILL_OUT    logs, reports and summaries (default $TREADMILL_WORK/treadmill-out)
#   ELM_PI_ENV_FILE  a .env holding ELM_API_KEY, copied (mode 600) into the test install and never printed.
#                    Required: every session here spends that key's ELM allocation.
#   TREADMILL_EXTENSION  optional: a harness extension (../cache/cache_log.ts) copied into the test install's
#                    agent/extensions/ as zz-<name>, so it loads after the install's own. Never into a real install.
set -u
NAME=$1; RUNS=$2; JOBS=${3:-3}
ITER="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$ITER/../../../.." && pwd)"
WORK="${TREADMILL_WORK:-$HOME/sandbox}"
OUTROOT="${TREADMILL_OUT:-$WORK/treadmill-out}"
: "${ELM_PI_ENV_FILE:?set ELM_PI_ENV_FILE to a .env holding ELM_API_KEY}"
INST=$WORK/elm-pi-b$NAME
OUT=$OUTROOT/b$NAME
if [ -e "$INST" ]; then echo "$INST already exists" >&2; exit 1; fi
mkdir -p "$OUT" "$INST"
step() { echo "$(date +%H:%M:%S) $*" >> "$OUT/steps.txt"; }
(cd "$REPO" && git ls-files -co --exclude-standard) | grep -v '^\.env$' | python3 -c '
import os, shutil, sys
src, dst = sys.argv[1], sys.argv[2]
for name in sys.stdin.read().splitlines():
    s = os.path.join(src, name)
    if not os.path.isfile(s): continue
    d = os.path.join(dst, name)
    os.makedirs(os.path.dirname(d), exist_ok=True)
    shutil.copy2(s, d)
' "$REPO" "$INST"
cp "$ELM_PI_ENV_FILE" "$INST/.env"; chmod 600 "$INST/.env"
(cd "$INST" && ./bootstrap.sh < /dev/null) > "$OUT/bootstrap.txt" 2>&1
BOOT=$?
if [ -n "${TREADMILL_EXTENSION:-}" ]; then
  cp "$TREADMILL_EXTENSION" "$INST/agent/extensions/zz-$(basename "$TREADMILL_EXTENSION" | tr _ -)"
fi
step "bootstrap exit=$BOOT $(grep -o '[0-9]* extensions loaded, [0-9]* failed' "$OUT/bootstrap.txt") commit=$(cd "$REPO" && git rev-parse --short HEAD)$(cd "$REPO" && git diff --quiet HEAD || echo +dirty)"

one() {   # $1 = index into runs.json
  local id flags prompts seed max proj out
  id=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[int(sys.argv[2])]["id"])' "$RUNS" "$1")
  flags=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))[int(sys.argv[2])].get("flags",[])))' "$RUNS" "$1")
  prompts=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))[int(sys.argv[2])]["prompts"]))' "$RUNS" "$1")
  seed=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[int(sys.argv[2])].get("seed",""))' "$RUNS" "$1")
  max=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[int(sys.argv[2])].get("max",2400))' "$RUNS" "$1")
  proj=$WORK/b$NAME-$id; out=$OUT/$id
  mkdir -p "$proj" "$out"
  if [ -n "$seed" ]; then
    cp -R "$seed/." "$proj/"; find "$proj" -name __pycache__ -prune -exec rm -rf {} +
    (cd "$proj" && git init -q && git add -A && git -c user.name=user -c user.email=user@example.invalid commit -qm "the project as it was")
  fi
  "$INST/.node/bin/node" "$ITER/drive.mjs" "$INST/pi" "$proj" "$out/rpc.jsonl" "$flags" "$prompts" "$max"
  ELM_PI_REPO="$REPO" python3 "$ITER/analyze.py" "$proj" "$INST" "$out" > "$out/report.md" 2> "$out/analyze.err"
  step "$id done: $(grep -o '"finish":"[^"]*"' "$out/rpc.jsonl" | tail -1)"
}
COUNT=$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1]))))' "$RUNS")
i=0
while [ "$i" -lt "$COUNT" ]; do
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do sleep 5; done
  one "$i" &
  sleep 3
  i=$((i + 1))
done
wait
TREADMILL_WORK="$WORK" python3 "$ITER/summary.py" "$OUT" > "$OUT/summary.md" 2>&1
step "batch done"
