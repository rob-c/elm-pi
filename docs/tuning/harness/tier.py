import json, sys, urllib.request, urllib.error
key = next(l.split("=", 1)[1].strip().strip("'\"") for l in open(sys.argv[1]) if l.startswith("ELM_API_KEY="))
for model in ("Qwen/Qwen3.5-397B-A17B-FP8", "mistralai/Mistral-Small-4-119B-2603", "meta-llama/Llama-3.3-70B-Instruct"):
    for extra in ({}, {"service_tier": "priority"}, {"prompt_cache_key": "abc", "prompt_cache_retention": "24h"}, {"store": False}):
        body = {"model": model, "max_tokens": 5, "messages": [{"role": "user", "content": "Reply with OK"}], **extra}
        if "llama" not in model: body["reasoning_effort"] = "none"
        req = urllib.request.Request("https://elm.edina.ac.uk/api/v1/chat/completions", json.dumps(body).encode(),
                                     {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            r = json.loads(urllib.request.urlopen(req, timeout=60).read())
            got = f"200 {r['choices'][0]['message']['content']!r}"
        except urllib.error.HTTPError as e:
            got = f"{e.code} {e.read().decode()[:160]}"
        print(f"{model.split('/')[1][:20]:20} {json.dumps(extra) or '{}':58} {got}")
