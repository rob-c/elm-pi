"""A long pi session with eight facts at known places, for compaction tests.

    python3 make_long.py OUT.jsonl SOURCE_DIR EPISODES CHUNK_CHARS

Each episode: the user asks about a file, the assistant reads it (a real file's
text is the tool result), then answers in a line. The facts sit in user and
assistant messages; the last one is the task left unfinished. FACTS (printed
as JSON on the last line) are what a summary should keep.
"""
import json
import pathlib
import sys
import uuid

out, source, episodes, chunk = sys.argv[1], pathlib.Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
texts = []
for f in sorted(source.rglob("*")):
    if f.is_file() and f.suffix in (".md", ".py", ".sh", ".ts") and ".git" not in f.parts and "node_modules" not in f.parts:
        t = f.read_text(errors="replace")
        for i in range(0, len(t), chunk):
            texts.append((str(f.relative_to(source)), t[i:i + chunk]))
assert len(texts) >= episodes, len(texts)

N = episodes
FACTS = {
    max(1, N * 2 // 40): ("user", "Note for later: the detector calibration constant is 4729.3 ADC/MeV. Use it in every conversion.", "4729.3"),
    N * 6 // 40: ("user", "Decision: we fit with iminuit, not scipy.optimize. The supervisor insists.", "iminuit"),
    N * 11 // 40: ("assistant", "Found it: the off-by-one is in bin_edges() in histo.py, line 88. Not fixed yet.", "bin_edges"),
    N * 15 // 40: ("user", "Never push to main. Open pull requests against the dev-2026 branch.", "dev-2026"),
    N * 20 // 40: ("assistant", "The dataset to use is /data/lhcb/run3/kpipi_v7.root; v6 is corrupt.", "kpipi_v7"),
    N * 26 // 40: ("user", "The draft is due on 28 November.", "28 November"),
    N * 31 // 40: ("assistant", "Benchmark: the C++ port runs 14.2 times faster than the Python loop.", "14.2"),
    N * 34 // 40: ("user", "Next task: rewrite fit_lifetime.py to use the 4729.3 constant and iminuit. Start with the likelihood function.", "fit_lifetime.py"),
}
USAGE = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0,
         "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0}}
rows, parent, clock = [], None, 1794000000000


def add(message):
    global parent, clock
    clock += 1000
    entry = {"type": "message", "id": uuid.uuid4().hex[:8], "parentId": parent,
             "timestamp": f"2026-11-11T10:{(clock // 60000) % 60:02d}:{(clock // 1000) % 60:02d}.000Z",
             "message": {**message, "timestamp": clock}}
    parent = entry["id"]
    rows.append(entry)


def assistant(content, stop):
    return {"role": "assistant", "content": content, "api": "openai-completions", "provider": "elm",
            "model": "Qwen/Qwen3.5-397B-A17B-FP8", "usage": USAGE, "stopReason": stop}


for n in range(N):
    path, text = texts[n * len(texts) // N]
    fact = FACTS.get(n)
    ask = f"Read {path} and tell me in one line what this part does."
    if fact and fact[0] == "user":
        ask = fact[1] + " Also: " + ask
    add({"role": "user", "content": [{"type": "text", "text": ask}]})
    call = f"call_{uuid.uuid4().hex[:12]}"
    add(assistant([{"type": "toolCall", "id": call, "name": "read", "arguments": {"path": path}}], "toolUse"))
    add({"role": "toolResult", "toolCallId": call, "toolName": "read", "content": [{"type": "text", "text": text}],
         "isError": False})
    answer = f"{path}: this part handles {text.split()[0] if text.split() else 'nothing'} and the code after it."
    if fact and fact[0] == "assistant":
        answer = fact[1] + " " + answer
    if fact and fact[2] == "fit_lifetime.py":
        answer = "Started on fit_lifetime.py: read the old fit, the likelihood function is next. " + answer
    add(assistant([{"type": "text", "text": answer}], "stop"))

header = {"type": "session", "version": 3, "id": uuid.uuid4().hex, "timestamp": "2026-11-11T10:00:00.000Z",
          "cwd": "/home/researcher/analysis"}
with open(out, "w") as fh:
    for e in [header, *rows]:
        fh.write(json.dumps(e) + "\n")
print(json.dumps({"facts": [f[2] for f in FACTS.values()], "messages": len(rows)}))
