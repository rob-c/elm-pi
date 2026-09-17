#!/usr/bin/env bash
# Resolve the real model id from the ELM gateway and update agent/models.json +
# agent/settings.json IN PLACE, then smoke-test one completion.
#
# Unlike a naive rewrite, this merges: your packages, extensions, retry and
# session settings survive. Only the model id and defaultModel change.
#
# Usage: ./configure.sh [model-id-substring]      (default: qwen)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/.env" ] && { set -a; . "$HERE/.env"; set +a; }
: "${ELM_API_KEY:?Set ELM_API_KEY in $HERE/.env first}"

BASE="${ELM_BASE_URL:-https://elm.edina.ac.uk/api/v1}"
MATCH="${1:-qwen}"

echo "Querying $BASE/models ..."
curl -sS -m 30 -H "Authorization: Bearer $ELM_API_KEY" "$BASE/models" > "$HERE/agent/.models-raw.json"

MODEL_ID=$(MATCH="$MATCH" python3 - "$HERE/agent/.models-raw.json" <<'PY'
import json,os,sys
raw=open(sys.argv[1]).read()
try: d=json.loads(raw)
except Exception:
    sys.exit("Gateway did not return JSON:\n"+raw[:400])
if isinstance(d,dict) and "error" in d:
    sys.exit("Gateway error: "+json.dumps(d["error"]))
items=d.get("data",d) if isinstance(d,dict) else d
ids=[m["id"] if isinstance(m,dict) else str(m) for m in items]
m=os.environ["MATCH"].lower()
hits=[i for i in ids if m in i.lower()]
if not hits:
    print("No model id matching %r. Available:" % m, file=sys.stderr)
    for i in sorted(ids): print("   ",i, file=sys.stderr)
    sys.exit(1)
# prefer the largest / most specific match (397 beats a smaller sibling)
hits.sort(key=lambda i: ("397" in i, len(i)), reverse=True)
if len(hits)>1:
    print("Matched %d, choosing %s (others: %s)" % (len(hits),hits[0],", ".join(hits[1:])), file=sys.stderr)
print(hits[0])
PY
)

echo "Model id: $MODEL_ID"

python3 - "$HERE" "$MODEL_ID" "$BASE" "$MATCH" <<'PY'
import json,sys
here,model,base,match=sys.argv[1:5]

mp=here+"/agent/models.json"
models=json.load(open(mp))
elm=models.setdefault("providers",{}).setdefault("elm",{})
elm["baseUrl"]=base
elm.setdefault("api","openai-completions")
elm.setdefault("apiKey","$ELM_API_KEY")
entries=elm.setdefault("models",[])

# Replace the entry this run targets, keeping every other model and every
# hand-tuned field (thinkingLevelMap, compat, samplingParams, context sizes).
idx=next((i for i,e in enumerate(entries) if match.lower() in e.get("id","").lower()), None)
if idx is None:
    entries.insert(0,{"id":model,"name":model+" (ELM, university-hosted)","reasoning":True,
                      "input":["text"],"contextWindow":262144,"maxTokens":32768,
                      "cost":{"input":0,"output":0,"cacheRead":0,"cacheWrite":0}})
    idx=0
else:
    entries[idx]["id"]=model
json.dump(models,open(mp,"w"),indent=2); open(mp,"a").write("\n")

sp=here+"/agent/settings.json"
settings=json.load(open(sp))
# Only re-point the default when this run configured the default model's family.
if match.lower() in settings.get("defaultModel","").lower() or not settings.get("defaultModel"):
    settings["defaultProvider"]="elm"
    settings["defaultModel"]=model
json.dump(settings,open(sp,"w"),indent=2); open(sp,"a").write("\n")
print("Updated agent/models.json and agent/settings.json (merged, nothing else changed)")
PY

echo
echo "Smoke test ..."
curl -sS -m 120 -H "Authorization: Bearer $ELM_API_KEY" -H "Content-Type: application/json" \
  "$BASE/chat/completions" \
  -d "$(python3 -c 'import json,sys;print(json.dumps({"model":sys.argv[1],"messages":[{"role":"user","content":"Reply with exactly: OK"}],"max_tokens":256,"reasoning_effort":"none"}))' "$MODEL_ID")" \
  | python3 -c '
import json,sys
raw=sys.stdin.read()
try: d=json.loads(raw)
except Exception: sys.exit("  non-JSON reply: "+raw[:300])
if "error" in d: sys.exit("  error: "+json.dumps(d["error"]))
print("  reply:", d["choices"][0]["message"].get("content"))
'
rm -f "$HERE/agent/.models-raw.json"
echo
echo "Done. Run ./pi to start the agent."
