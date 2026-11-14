"""Probe the ELM gateway. The key is read from an .env file into memory only and
never printed or written; results go to a JSON file.

    python3 -I probe.py ENVFILE OUT.json quick
    python3 -I probe.py ENVFILE OUT.json long MODEL_SUBSTRING MAX_TOKENS COUNT_TO
"""
import base64
import json
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

BASE = "https://elm.edina.ac.uk/api/v1"
env_file, out_file, what = sys.argv[1], sys.argv[2], sys.argv[3]
KEY = next(line.split("=", 1)[1].strip().strip("'\"") for line in open(env_file)
           if line.startswith("ELM_API_KEY="))


def request(path, body=None, timeout=300, stream=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET",
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    started = time.time()
    try:
        response = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        return {"status": e.code, "error": e.read().decode(errors="replace")[:1500], "seconds": round(time.time() - started, 2)}
    except Exception as e:  # noqa: BLE001 - a probe reports whatever went wrong
        return {"status": None, "error": f"{type(e).__name__}: {e}", "seconds": round(time.time() - started, 2)}
    if not stream:
        payload = json.loads(response.read())
        return {"status": response.status, "body": payload, "seconds": round(time.time() - started, 2)}
    # Server-sent events: assemble content, reasoning and tool calls as pi would.
    content, reasoning, calls, usage, finish, chunks, first = [], [], {}, None, None, 0, None
    try:
        for raw in response:
            line = raw.decode(errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            chunk = json.loads(data)
            chunks += 1
            usage = chunk.get("usage") or usage
            for choice in chunk.get("choices") or []:
                delta = choice.get("delta") or {}
                if first is None and (delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning")):
                    first = round(time.time() - started, 2)
                if delta.get("content"):
                    content.append(delta["content"])
                for key in ("reasoning_content", "reasoning"):
                    if delta.get(key):
                        reasoning.append(delta[key])
                for call in delta.get("tool_calls") or []:
                    slot = calls.setdefault(call.get("index", 0), {"id": None, "name": "", "arguments": ""})
                    slot["id"] = call.get("id") or slot["id"]
                    fn = call.get("function") or {}
                    slot["name"] += fn.get("name") or ""
                    slot["arguments"] += fn.get("arguments") or ""
                finish = choice.get("finish_reason") or finish
    except Exception as e:  # noqa: BLE001
        return {"status": response.status, "error": f"stream broke: {type(e).__name__}: {e}",
                "seconds": round(time.time() - started, 2), "chunks": chunks, "content_chars": len("".join(content)),
                "usage": usage}
    text = "".join(content)
    return {"status": response.status, "seconds": round(time.time() - started, 2), "first_token_seconds": first,
            "chunks": chunks, "finish_reason": finish, "usage": usage, "content_chars": len(text),
            "content_head": text[:200], "content_tail": text[-200:], "reasoning_chars": len("".join(reasoning)),
            "tool_calls": list(calls.values())}


def chat(model, messages, **extra):
    return {"model": model, "messages": messages, **extra}


def summary(result):
    """What matters of a non-streamed reply."""
    if "body" not in result:
        return result
    body = result["body"]
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return {"status": result["status"], "seconds": result["seconds"], "finish_reason": choice.get("finish_reason"),
            "content": (message.get("content") or "")[:300],
            "reasoning_chars": len(message.get("reasoning_content") or message.get("reasoning") or ""),
            "tool_calls": [{"name": c["function"]["name"], "arguments": c["function"]["arguments"]}
                           for c in message.get("tool_calls") or []],
            "usage": body.get("usage")}


def png(rgb=(255, 0, 0), size=16):
    row = b"\x00" + bytes(rgb) * size
    raw = zlib.compress(row * size)
    def part(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return b"\x89PNG\r\n\x1a\n" + part(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + \
        part(b"IDAT", raw) + part(b"IEND", b"")


WEATHER = [{"type": "function", "function": {
    "name": "get_weather", "description": "Current weather for a city",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]
ASK_WEATHER = [{"role": "user", "content": "What is the weather in Edinburgh? Use the tool."}]


def quick():
    out = {}
    listing = request("/models")
    models = (listing.get("body") or {}).get("data") or []
    out["models"] = {"status": listing.get("status"), "ids": sorted(m.get("id") for m in models),
                     "error": listing.get("error")}
    pick = lambda needle: next((m for m in models if needle in m.get("id", "").lower()), None)
    meta = {name: pick(needle) for name, needle in (("qwen", "qwen3.5-397b"), ("mistral", "mistral-small-4"),
                                                    ("llama", "llama-3.3-70b"))}
    out["metadata"] = meta
    mistral = meta["mistral"]["id"] if meta["mistral"] else None
    qwen = meta["qwen"]["id"] if meta["qwen"] else None
    if mistral:
        m = {}
        m["plain"] = summary(request("/chat/completions", chat(mistral, [{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=64)))
        m["reasoning_none"] = summary(request("/chat/completions", chat(mistral, [{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=512, reasoning_effort="none")))
        m["reasoning_high"] = summary(request("/chat/completions", chat(mistral, [{"role": "user", "content": "What is 17*23? Reply with the number only."}], max_tokens=4096, reasoning_effort="high")))
        m["tools"] = summary(request("/chat/completions", chat(mistral, ASK_WEATHER, tools=WEATHER, tool_choice="auto", max_tokens=256)))
        m["tools_streamed"] = request("/chat/completions", chat(mistral, ASK_WEATHER, tools=WEATHER, tool_choice="auto", max_tokens=256, stream=True, stream_options={"include_usage": True}), stream=True)
        calls = m["tools"].get("tool_calls") or []
        if calls:
            follow = ASK_WEATHER + [
                {"role": "assistant", "content": None, "tool_calls": [{"id": "call_1", "type": "function", "function": calls[0]}]},
                {"role": "tool", "tool_call_id": "call_1", "content": json.dumps({"city": "Edinburgh", "sky": "drizzle", "celsius": 9})}]
            m["tool_round_trip"] = summary(request("/chat/completions", chat(mistral, follow, tools=WEATHER, max_tokens=256)))
        m["developer_role"] = summary(request("/chat/completions", chat(mistral, [{"role": "developer", "content": "Answer in one word."}, {"role": "user", "content": "Capital of Scotland?"}], max_tokens=32)))
        m["system_role"] = summary(request("/chat/completions", chat(mistral, [{"role": "system", "content": "Answer in one word."}, {"role": "user", "content": "Capital of Scotland?"}], max_tokens=32)))
        image = "data:image/png;base64," + base64.b64encode(png()).decode()
        m["image"] = summary(request("/chat/completions", chat(mistral, [{"role": "user", "content": [
            {"type": "text", "text": "What colour is this image? One word."}, {"type": "image_url", "image_url": {"url": image}}]}], max_tokens=32)))
        m["max_tokens_32768"] = summary(request("/chat/completions", chat(mistral, [{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=32768)))
        m["max_tokens_81920"] = summary(request("/chat/completions", chat(mistral, [{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=81920)))
        m["max_tokens_1000000"] = summary(request("/chat/completions", chat(mistral, [{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=1000000)))
        m["max_completion_tokens_81920"] = summary(request("/chat/completions", chat(mistral, [{"role": "user", "content": "Reply with exactly: OK"}], max_completion_tokens=81920)))
        out["mistral"] = m
    if qwen:
        q = {}
        q["max_tokens_81920"] = summary(request("/chat/completions", chat(qwen, [{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=81920, reasoning_effort="none")))
        q["max_completion_tokens_81920"] = summary(request("/chat/completions", chat(qwen, [{"role": "user", "content": "Reply with exactly: OK"}], max_completion_tokens=81920, reasoning_effort="none")))
        q["max_tokens_1000000"] = summary(request("/chat/completions", chat(qwen, [{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=1000000, reasoning_effort="none")))
        # How thinking is switched off: elm-pi's way, then pi-elm-models'.
        q["off_by_reasoning_effort_none"] = summary(request("/chat/completions", chat(qwen, [{"role": "user", "content": "What is 17*23? Reply with the number only."}], max_tokens=4096, reasoning_effort="none")))
        q["off_by_enable_thinking_false"] = summary(request("/chat/completions", chat(qwen, [{"role": "user", "content": "What is 17*23? Reply with the number only."}], max_tokens=4096, enable_thinking=False)))
        out["qwen"] = q
    return out


def long_run(needle, max_tokens, count_to):
    listing = request("/models")
    model = next(m["id"] for m in (listing.get("body") or {}).get("data") or [] if needle in m["id"].lower())
    prompt = (f"Write every integer from 1 to {count_to} in order, separated by single spaces, on one line. "
              "Output nothing else: no words, no commas, no line breaks, no explanation.")
    body = chat(model, [{"role": "user", "content": prompt}], max_tokens=max_tokens, stream=True,
                stream_options={"include_usage": True}, reasoning_effort="none")
    result = request("/chat/completions", body, timeout=3600, stream=True)
    result["model"], result["max_tokens"], result["count_to"] = model, max_tokens, count_to
    return result


def images():
    listing = request("/models")
    ids = [m["id"] for m in (listing.get("body") or {}).get("data") or []]
    out = {}
    for needle in ("qwen3.5-397b", "mistral-small-4"):
        model = next(i for i in ids if needle in i.lower())
        for colour, rgb in (("red", (255, 0, 0)), ("blue", (0, 0, 255))):
            for size in (16, 256):
                image = "data:image/png;base64," + base64.b64encode(png(rgb, size)).decode()
                out[f"{needle}_{colour}_{size}px"] = summary(request("/chat/completions", chat(model, [{"role": "user", "content": [
                    {"type": "text", "text": "What colour is this image? One word."},
                    {"type": "image_url", "image_url": {"url": image}}]}], max_tokens=32, reasoning_effort="none")))
    return out


def figures(folder):
    listing = request("/models")
    ids = [m["id"] for m in (listing.get("body") or {}).get("data") or []]
    tasks = {"text": ("text.png", "What text is in this image? Reply with the text only."),
             "plot": ("plot.png", "This is a bar chart. Which label has the tallest bar, and what colour is the shortest bar? "
                                  "Reply exactly as: tallest=<label>; shortest=<colour>")}
    out = {}
    for needle in ("qwen3.5-397b", "mistral-small-4"):
        model = next(i for i in ids if needle in i.lower())
        for name, (file, question) in tasks.items():
            image = "data:image/png;base64," + base64.b64encode(open(f"{folder}/{file}", "rb").read()).decode()
            out[f"{needle}_{name}"] = summary(request("/chat/completions", chat(model, [{"role": "user", "content": [
                {"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": image}}]}],
                max_tokens=64, reasoning_effort="none")))
    return out


def copy_run(needle, max_tokens, lines):
    """Copying is easy, so a model that stops early is not the reason a long output ends."""
    listing = request("/models")
    model = next(m["id"] for m in (listing.get("body") or {}).get("data") or [] if needle in m["id"].lower())
    words = ["proton", "neutron", "lepton", "gluon", "photon", "muon", "quark", "boson", "hadron", "meson"]
    text = "\n".join(f"{i:05d} {words[i % 10]} {words[(i * 7) % 10]} {words[(i * 3) % 10]} {i * 37 % 1000:03d}"
                     for i in range(1, lines + 1))
    prompt = ("Copy the following text exactly, every line, in order, from the first line to the last. "
              "Output only the copied text.\n\n" + text)
    body = chat(model, [{"role": "user", "content": prompt}], max_tokens=max_tokens, stream=True,
                stream_options={"include_usage": True}, reasoning_effort="none", temperature=0)
    result = request("/chat/completions", body, timeout=3600, stream=True)
    result["model"], result["max_tokens"], result["lines"], result["input_chars"] = model, max_tokens, lines, len(text)
    return result


def forced_run(needle, tokens):
    """vLLM's ignore_eos and min_tokens: the reply is exactly `tokens` long, whatever the model would do."""
    listing = request("/models")
    model = next(m["id"] for m in (listing.get("body") or {}).get("data") or [] if needle in m["id"].lower())
    body = chat(model, [{"role": "user", "content": "Write a long essay on the history of particle physics."}],
                max_tokens=tokens, min_tokens=tokens, ignore_eos=True, stream=True,
                stream_options={"include_usage": True}, reasoning_effort="none")
    result = request("/chat/completions", body, timeout=3600, stream=True)
    result["model"], result["max_tokens"] = model, tokens
    return result


def concurrent_run(tokens):
    """Same-day throughput: each model, 1/8/12 requests at once, each forced to `tokens` out."""
    from concurrent.futures import ThreadPoolExecutor
    listing = request("/models")
    ids = [m["id"] for m in (listing.get("body") or {}).get("data") or []]
    out = {}
    for needle in ("mistral-small-4", "qwen3.5-397b", "llama-3.3-70b"):
        model = next(i for i in ids if needle in i.lower())
        for n in (1, 8, 12):
            def one(k):
                body = chat(model, [{"role": "user", "content": f"Write a short paragraph about particle detector number {k}."}],
                            max_tokens=tokens, min_tokens=tokens, ignore_eos=True, stream=True,
                            stream_options={"include_usage": True})
                if "llama" not in needle:
                    body["reasoning_effort"] = "none"
                return request("/chat/completions", body, timeout=600, stream=True)
            started = time.time()
            with ThreadPoolExecutor(n) as pool:
                results = list(pool.map(one, range(n)))
            wall = time.time() - started
            done = [r for r in results if r.get("status") == 200 and not r.get("error")]
            total = sum((r.get("usage") or {}).get("completion_tokens", 0) for r in done)
            out[f"{needle} x{n}"] = {"ok": len(done), "wall_s": round(wall, 2), "aggregate_tok_s": round(total / wall, 1),
                                     "first_token_s": sorted(r.get("first_token_seconds") or 0 for r in done),
                                     "errors": [r.get("error", "")[:200] for r in results if r not in done]}
    return out


if what == "quick":
    result = quick()
elif what == "concurrent":
    result = concurrent_run(int(sys.argv[4]))
elif what == "forced":
    result = forced_run(sys.argv[4], int(sys.argv[5]))
elif what == "copy":
    result = copy_run(sys.argv[4], int(sys.argv[5]), int(sys.argv[6]))
elif what == "figures":
    result = figures(sys.argv[4])
elif what == "images":
    result = images()
else:
    result = long_run(sys.argv[4], int(sys.argv[5]), int(sys.argv[6]))
json.dump(result, open(out_file, "w"), indent=1)
print("written", out_file)
