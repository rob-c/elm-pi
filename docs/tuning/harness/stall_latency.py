"""How long ELM leaves a request silent, from the pi sessions already on disk.

    python3 stall_latency.py OUT.json DIR_OR_SESSION.jsonl ...

pi's idle timeout (`httpIdleTimeoutMs`, 300 s by default) ends a request that has
sent nothing for that long - no headers, no first token, no next chunk - and pi
retries it. Too short and a slow but healthy request is cut off and sent back to
the end of the queue; too long and a dead stream holds the agent. test6
(2026-11-12) lost eight minutes to one.

Every assistant message pi saves carries the request's start (`message.timestamp`,
ms) and its end (the entry's `timestamp`). A reply of at most SHORT output tokens
spends nearly all of that time waiting for the first token, so those durations
measure the longest silence ELM imposes before a reply starts; a stream's later
gaps are token to token. Thinking (Mistral) arrives as streamed chunks too.
Requests are deduplicated (a forked child's session repeats its parent's), and
sub-agent artifact transcripts, which copy their session, are skipped.

Only counts and durations are written: no paths, prompts or replies.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

SHORT = 100
THRESHOLDS = (30, 60, 90, 120, 180, 300)
STALLS = ("UND_ERR_BODY_TIMEOUT", "UND_ERR_HEADERS_TIMEOUT")


def sessions(args):
    for arg in map(Path, args):
        files = [arg] if arg.is_file() else arg.rglob("*.jsonl")
        for f in files:
            if "subagent-artifacts" not in f.parts and "sessions" in str(f):
                yield f


def kind(f):
    s = str(f)
    return "tuning runs" if "/ab/" in s else "interactive tests" if "/sandbox/test" in s else "other sessions"


def pct(values, p):
    v = sorted(values)
    return v[min(len(v) - 1, int(p * len(v)))] if v else None


requests, seen, files = [], set(), {}
for f in sessions(sys.argv[2:]):
    try:
        lines = f.read_text().splitlines()
    except OSError:
        continue
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        m = r.get("message") or {}
        if m.get("role") != "assistant" or not isinstance(m.get("timestamp"), (int, float)) or not r.get("timestamp"):
            continue
        if "elm" not in str(m.get("provider") or "elm"):
            continue
        key = (m.get("model"), m["timestamp"], r["timestamp"])
        if key in seen:
            continue
        seen.add(key)
        end = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).timestamp()
        usage = m.get("usage") or {}
        requests.append({"model": m.get("model"), "start": m["timestamp"] / 1000, "secs": end - m["timestamp"] / 1000,
                         "input": usage.get("input", 0), "output": usage.get("output", 0), "stop": m.get("stopReason"),
                         "error": m.get("errorMessage") or "", "kind": kind(f)})
        files[str(f)] = kind(f)

ok = [r for r in requests if r["stop"] in ("toolUse", "stop", "length") and r["input"] > 0]
short = [r for r in ok if r["output"] <= SHORT]
out = {
    "date": "2026-11-12",
    "question": "how long ELM leaves a request silent before its reply starts, so httpIdleTimeoutMs can be set",
    "method": __doc__.strip().split("\n\n")[2].replace("\n", " "),
    "corpus": {
        "session_files": {k: sum(v == k for v in files.values()) for k in sorted(set(files.values()))},
        "requests": len(requests), "successful": len(ok), "short_replies": len(short),
        "first": datetime.fromtimestamp(min(r["start"] for r in requests)).date().isoformat(),
        "last": datetime.fromtimestamp(max(r["start"] for r in requests)).date().isoformat(),
    },
    "short_reply_seconds": {},
    "stalls": [],
}
for model in sorted({r["model"] for r in short}):
    d = [r["secs"] for r in short if r["model"] == model]
    out["short_reply_seconds"][model] = {
        "n": len(d), "p50": round(pct(d, 0.5), 1), "p99": round(pct(d, 0.99), 1), "p999": round(pct(d, 0.999), 1),
        "max": round(max(d), 1), "over": {str(t): sum(x > t for x in d) for t in THRESHOLDS}}
out["longest_wait_seconds"] = max(v["max"] for v in out["short_reply_seconds"].values())
for r in requests:
    if r["stop"] == "error" and any(s in r["error"] for s in STALLS):
        out["stalls"].append({"model": r["model"], "seconds": round(r["secs"], 1), "error": r["error"][:80]})
out["stalls"].sort(key=lambda s: s["seconds"])
out["errors"] = {}
for r in requests:
    if r["stop"] == "error":
        label = r["error"].split(":")[0][:40] or "(none)"
        out["errors"][label] = out["errors"].get(label, 0) + 1
Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps({k: out[k] for k in ("corpus", "longest_wait_seconds", "stalls")}, indent=1))
