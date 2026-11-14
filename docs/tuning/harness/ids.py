import json, sys, urllib.request, urllib.error
key = next(l.split("=", 1)[1].strip().strip("'\"") for l in open(sys.argv[1]) if l.startswith("ELM_API_KEY="))
for tool_id in (sys.argv[2], "abcDEF123"):
    body = {"model": "mistralai/Mistral-Small-4-119B-2603", "max_tokens": 20, "messages": [
        {"role": "user", "content": "What is in notes.txt?"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": tool_id, "type": "function", "function": {"name": "read", "arguments": "{\"path\": \"notes.txt\"}"}}]},
        {"role": "tool", "tool_call_id": tool_id, "content": "calibration run 4"},
        {"role": "user", "content": "Reply with the run number only."}]}
    req = urllib.request.Request("https://elm.edina.ac.uk/api/v1/chat/completions", json.dumps(body).encode(), {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=60).read())
        print(f"id {tool_id!r}: 200 ->", r["choices"][0]["message"]["content"])
    except urllib.error.HTTPError as e:
        print(f"id {tool_id!r}: {e.code} ->", e.read().decode()[:300])
