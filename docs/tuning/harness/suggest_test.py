"""pi-next-prompt's request, on Qwen and Mistral, for real session endings.

    python3 -I suggest_test.py ENV_FILE SYSTEM_PROMPT_FILE OUT.json SESSION.jsonl...

The request is what the package sends: the conversation pi last sent (system prompt
and messages, no tools), then its [Suggestion mode] prompt; thinking off, max 2000
tokens. Each model gets each request twice in a row (cold, then with its prefix
cache). A suggestion counts only as the package would show it: non-empty, one line,
at most 100 characters once quotes are stripped. The key is read into memory only.
"""
import json
import sys
import time
import urllib.error
import urllib.request

env_file, system_file, out_file, sessions = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
KEY = next(l.split("=", 1)[1].strip().strip("'\"") for l in open(env_file) if l.startswith("ELM_API_KEY="))
MODELS = {"qwen": "Qwen/Qwen3.5-397B-A17B-FP8", "mistral": "mistralai/Mistral-Small-4-119B-2603"}
PROMPT = ("[Suggestion mode] Predict what the user will type next in this conversation. Write it the way they would: "
          "a short instruction, question or reply in their language and tone, under 12 words. A good suggestion is the "
          "obvious next step, such as approving something you proposed or asking for the follow-up they are likely to "
          "want. Reply with only the suggestion, no quotes. If there is no obvious next step, reply with nothing.")
SYSTEM = open(system_file).read()


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")


def conversation(path):
    out = [{"role": "system", "content": SYSTEM}]
    for line in open(path):
        m = json.loads(line).get("message")
        if not m:
            continue
        if m["role"] == "user":
            out.append({"role": "user", "content": text_of(m["content"]) or "(image)"})
        elif m["role"] == "assistant":
            calls = [c for c in m["content"] if c.get("type") == "toolCall"]
            msg = {"role": "assistant", "content": text_of(m["content"]) or None}
            if calls:
                msg["tool_calls"] = [{"id": c["id"], "type": "function",
                                      "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments") or {})}}
                                     for c in calls]
            if msg["content"] or calls:
                out.append(msg)
        elif m["role"] == "toolResult":
            out.append({"role": "tool", "tool_call_id": m["toolCallId"], "content": text_of(m["content"]) or "(no output)"})
    return out


def ask(model, messages):
    body = {"model": model, "messages": messages + [{"role": "user", "content": PROMPT}], "max_tokens": 2000,
            "reasoning_effort": "none"}
    req = urllib.request.Request("https://elm.edina.ac.uk/api/v1/chat/completions", json.dumps(body).encode(),
                                 {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    started = time.time()
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=300).read())
    except urllib.error.HTTPError as e:
        return {"error": f"{e.code} {e.read().decode()[:200]}", "seconds": round(time.time() - started, 2)}
    choice = r["choices"][0]
    raw = (choice["message"].get("content") or "").strip()
    shown = raw.strip("\"'`")
    valid = bool(shown) and "\n" not in shown and len(shown) <= 100 and choice.get("finish_reason") == "stop"
    return {"seconds": round(time.time() - started, 2), "raw": raw, "shown": shown if valid else None,
            "prompt_tokens": (r.get("usage") or {}).get("prompt_tokens")}


results = []
for path in sessions:
    messages = conversation(path)
    # The project a session belongs to: the folder above its .pi/sessions/.
    parts = path.split("/")
    row = {"session": parts[parts.index(".pi") - 1] if ".pi" in parts else path, "messages": len(messages)}
    for name, model in MODELS.items():
        row[name] = [ask(model, messages), ask(model, messages)]
    results.append(row)
    print(row["session"][-40:], {n: [(a.get("seconds"), a.get("shown") or a.get("error", "")[:60]) for a in row[n]] for n in MODELS},
          flush=True)
    json.dump(results, open(out_file, "w"), indent=1)
