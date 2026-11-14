import json, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
key = next(l.split("=", 1)[1].strip().strip("'\"") for l in open(sys.argv[1]) if l.startswith("ELM_API_KEY="))
def ask(model, extra):
    body = {"model": model, "max_tokens": 8, "reasoning_effort": "none",
            "messages": [{"role": "user", "content": "Pick a random whole number from 1 to 100. Reply with the number only."}], **extra}
    req = urllib.request.Request("https://elm.edina.ac.uk/api/v1/chat/completions", json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"].strip()
for model in ("mistralai/Mistral-Small-4-119B-2603", "Qwen/Qwen3.5-397B-A17B-FP8"):
    for label, extra in (("server default", {}), ("temperature 0.15", {"temperature": 0.15}), ("temperature 1.0", {"temperature": 1.0})):
        with ThreadPoolExecutor(12) as pool:
            got = list(pool.map(lambda _: ask(model, extra), range(12)))
        print(f"{model.split('/')[1][:22]:22} {label:17} distinct {len(set(got)):2}/12  {got}")
