"""A report on one driven session: what it cost, what went wrong, and what it left on disk.

    python3 analyze.py <project dir> <install dir>
"""
import datetime as dt
import glob
import json
import os
import tempfile
import re
import shutil
import subprocess
import sys
from collections import Counter

ITER = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("ELM_PI_REPO") or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
proj, inst = sys.argv[1], sys.argv[2]
# Where this run's rpc.jsonl (the driver's log) and steps.txt are: the third argument.
RUN_OUT = sys.argv[3] if len(sys.argv) > 3 else os.getcwd()
home = os.path.expanduser("~")


def short(text, n=400):
    text = str(text).replace(home, "~")
    text = re.sub(r"\s+", " ", text)
    return text if len(text) <= n else text[:n] + " ..."


def text_of(content):
    if isinstance(content, str):
        return content
    out = []
    for c in content or []:
        if isinstance(c, dict):
            if c.get("type") == "text":
                out.append(c.get("text", ""))
            elif c.get("type") == "image":
                out.append("[image]")
    return "\n".join(out)


def ts(r):
    t = r.get("timestamp")
    try:
        return dt.datetime.fromisoformat(t.replace("Z", "+00:00"))
    except Exception:
        return None


def session_file(directory):
    # The driven session is the first: a session the agent starts itself (a `pi -p` trial run from the
    # project's root) lands in the same folder later.
    files = sorted(glob.glob(os.path.join(directory, ".pi/sessions/*.jsonl")))
    return files[0] if files else None


def read(path):
    rows = []
    for line in open(path):
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    return rows


def summarise(rows, label):
    out = []
    calls = Counter()
    errors = Counter()
    tin = tout = turns = 0
    times = [ts(r) for r in rows if ts(r)]
    error_lines = []
    custom = []
    users = []
    final = ""
    gaps = []
    prev = None
    pending_calls = {}
    for r in rows:
        t = ts(r)
        if t and prev and (t - prev).total_seconds() > 240:
            gaps.append(f"{prev.strftime('%H:%M:%S')} -> {t.strftime('%H:%M:%S')} ({int((t - prev).total_seconds())} s)")
        if t:
            prev = t
        if r.get("type") == "custom_message":
            custom.append(f"{t.strftime('%H:%M:%S') if t else ''} [{r.get('customType')}] {short(text_of(r.get('content')), 600)}")
            continue
        m = r.get("message") or {}
        role = m.get("role")
        if role == "user":
            users.append(short(text_of(m.get("content")), 700))
        elif role == "assistant":
            turns += 1
            u = m.get("usage") or {}
            tin += u.get("input", 0) or 0
            tout += u.get("output", 0) or 0
            text = text_of(m.get("content"))
            if text.strip():
                final = text
            for c in m.get("content") or []:
                if isinstance(c, dict) and c.get("type") == "toolCall":
                    calls[c.get("name")] += 1
                    pending_calls[c.get("id")] = (c.get("name"), short(json.dumps(c.get("arguments")), 300))
            if m.get("stopReason") in ("error", "aborted"):
                error_lines.append(f"{t.strftime('%H:%M:%S') if t else ''} ASSISTANT {m.get('stopReason')}: {short(m.get('errorMessage'), 300)}")
        elif role == "toolResult":
            if m.get("isError"):
                errors[m.get("toolName")] += 1
                call = pending_calls.get(m.get("toolCallId"), ("?", ""))
                error_lines.append(f"{t.strftime('%H:%M:%S') if t else ''} {m.get('toolName')} ERROR: {short(text_of(m.get('content')), 500)}\n      call: {call[1]}")
    wall = (max(times) - min(times)).total_seconds() if times else 0
    out.append(f"### {label}")
    out.append(f"- wall {int(wall // 60)} min {int(wall % 60)} s; {turns} model turns; input {tin:,} tokens, output {tout:,} tokens")
    out.append(f"- tool calls: {dict(calls)}")
    out.append(f"- tool errors: {dict(errors)}")
    if gaps:
        out.append(f"- gaps over 4 min: {gaps}")
    return out, error_lines, custom, users, final, tin, tout


lines = [f"# Report: {proj.replace(home, '~')}", ""]
rpc = os.path.join(RUN_OUT, "rpc.jsonl")
rpc_rows = read(rpc) if os.path.exists(rpc) else []
driver_errors = [f"{r.get('t', '')} DRIVER ERROR: {short(r['error'], 500)}" for r in rpc_rows if "error" in r]
driver_stderr = [short(r["stderr"], 400) for r in rpc_rows if "stderr" in r]
steps = os.path.join(RUN_OUT, "steps.txt")
if os.path.exists(steps):
    lines += ["## Steps", "```", open(steps).read().strip(), "```", ""]

main = session_file(proj)
if not main:
    # Startup refusals have no transcript: the RPC stderr is the only account of what failed.
    lines += ["NO SESSION FILE", "", "## Driver errors", *(driver_errors or ["(none)"]), "",
              "## stderr", *(driver_stderr or ["(none)"]), ""]
    print("\n".join(lines))
    sys.exit(1)
rows = read(main)
summary, error_lines, custom, users, final, tin, tout = summarise(rows, "Parent session")
lines += ["## Cost and shape"] + summary

# children of subagent runs
total_in, total_out = tin, tout
child_rows = []
for meta in sorted(glob.glob(os.path.join(proj, ".pi/sessions/subagent-artifacts/*_meta.json"))):
    try:
        j = json.load(open(meta))
    except Exception:
        continue
    u = j.get("usage") or {}
    total_in += u.get("input", 0) or 0
    total_out += u.get("output", 0) or 0
    transcript = meta.replace("_meta.json", "_transcript.jsonl")
    errs = []
    if os.path.exists(transcript):
        for r in read(transcript):
            m = r.get("message") or {}
            if m.get("role") == "toolResult" and m.get("isError"):
                errs.append(f"{m.get('toolName')}: {short(text_of(m.get('content')), 220)}")
    child_rows.append(f"- {j.get('agent')} {j.get('runId', '')[:8]} exit={j.get('exitCode')} turns={u.get('turns')} in={u.get('input', 0):,} out={u.get('output', 0):,} errors={len(errs)}"
                      + "".join(f"\n    - {e}" for e in errs[:8]))
if child_rows:
    lines += ["", "### Sub-agent children"] + child_rows
wf = []
for r in rows:
    m = r.get("message") or {}
    if m.get("role") == "toolResult" and m.get("toolName") == "workflow":
        t = text_of(m.get("content"))
        mm = re.search(r"Token usage: ([\d,]+)", t)
        wf.append(f"- workflow result: {'ERROR ' if m.get('isError') else ''}{short(t, 300)}")
        if mm:
            total_in += int(mm.group(1).replace(",", ""))
if wf:
    lines += ["", "### Workflow runs"] + wf
lines += ["", f"**Total tokens (parent + children + workflows): {total_in + total_out:,}**", ""]

# What the cost figures above do not say: how big the context got, whether it was ever summarised, which
# skills the router put in front of the model, and whether the session looked at what it made. Each was
# pulled by a throwaway script more than once on 2026-11-14 before it was put here.
def session_facts(rows):
    first = largest = compactions = 0
    inlined, named, skill_reads, views, wrote = [], [], set(), [], set()
    for r in rows:
        if r.get("type") in ("compaction", "compaction_summary") or "compactionSummary" in r:
            compactions += 1
        if r.get("type") == "custom_message" and r.get("customType") == "skill-routing":
            details = r.get("details") or {}
            inlined += details.get("inlined", []); named += details.get("named", [])
        m = r.get("message") or {}
        u = m.get("usage") or {}
        request = (u.get("input") or 0) + (u.get("cacheRead") or 0) + (u.get("cacheWrite") or 0)
        if request:
            first = first or request
            largest = max(largest, request)
        for c in m.get("content") if isinstance(m.get("content"), list) else []:
            if not (isinstance(c, dict) and c.get("type") == "toolCall"):
                continue
            args, name = c.get("arguments") or {}, c.get("name")
            if name == "read" and "SKILL.md" in str(args.get("path", "")):
                skill_reads.add(str(args["path"]).split("/")[-2])
            if name == "view":
                views += [os.path.basename(str(v)) for v in (args.get("paths") or [args.get("path")]) if v]
            if name in ("write", "replace", "replace_match", "insert") and args.get("path"):
                wrote.add(os.path.basename(str(args["path"])))
    looked = sorted(wrote & set(views))
    made = sorted(f for f in wrote if re.search(r"\.(html?|png|jpe?g|svg|pdf)$", f, re.I))
    return [
        f"- first request {first:,} tokens (the floor: system prompt, tool definitions, routed skills); largest {largest:,}",
        f"- compactions: {compactions}",
        f"- skills put in full by the router: {', '.join(dict.fromkeys(inlined)) or 'none'}; named only: {', '.join(dict.fromkeys(named)) or 'none'}; "
        f"SKILL.md read with `read`: {', '.join(sorted(skill_reads)) or 'none'}",
        f"- `view` calls: {len(views)}; pages or figures this session wrote itself: {len(made)}, of which it viewed {len([f for f in made if f in looked])}"
        + ("" if views else " - it looked at nothing"),
    ]


lines += ["## Session facts"] + session_facts(read(session_file(proj)) if session_file(proj) else []) + [""]
lines += ["## User prompts"] + [f"- {u}" for u in users] + [""]
lines += ["## Errors and refusals (parent)"] + (error_lines or ["(none)"]) + [""]
lines += ["## Extension messages"] + [f"- {c}" for c in custom if "skill-routing" not in c] + [""]

lines += ["## Driver errors", *(driver_errors or ["(none)"]), ""]
if os.path.exists(rpc):
    dialogs, retries, stderr = [], [], []
    for r in rpc_rows:
        if "dialog" in r:
            dialogs.append(f"{r['t']} {r['dialog']}: {short(r.get('title'), 200)} -> {r.get('answered', '')}")
        if "retry" in r:
            retries.append(f"{r['t']} {r['retry']} {r.get('attempt')} {short(r.get('error'), 160)}")
        if "stderr" in r:
            stderr.append(short(r["stderr"], 200))
    lines += ["## Dialogs answered", *(dialogs[:40] or ["(none)"]), ""]
    if retries:
        lines += ["## Retries", *retries[:30], ""]
    if stderr:
        lines += ["## stderr", *stderr[:20], ""]

lines += ["## Final reply", "", final.strip(), ""]

if os.environ.get("SKIP_SITE"):
    print("\n".join(lines))
    sys.exit(0)

# the site
ext = tempfile.mkdtemp(prefix="treadmill-ext-")   # a scratch copy beside a typebox stub: never inside the repository
os.makedirs(os.path.join(ext, "node_modules/typebox"), exist_ok=True)
open(os.path.join(ext, "node_modules/typebox/package.json"), "w").write('{"name":"typebox","type":"module","main":"index.js"}')
open(os.path.join(ext, "node_modules/typebox/index.js"), "w").write(
    "const f = (...a) => ({ a }); export const Type = { Object: f, String: f, Optional: f, Boolean: f, Array: f, Number: f, Union: f, Literal: f };")
shutil.copy(os.path.join(REPO, "templates/extensions/view-outputs.ts"), os.path.join(ext, "view-outputs.ts"))
node = os.path.join(inst, ".node/bin/node")
run = subprocess.run([node, "--no-warnings", os.path.join(ITER, "audit.mjs"), os.path.join(ext, "view-outputs.ts"), proj],
                     capture_output=True, text=True, timeout=300)
lines.append("## Site audit (view's own checks, run on what was left)")
try:
    audit = json.loads(run.stdout.strip().splitlines()[-1])
    lines += ["### Files", *[f"- {f}" for f in audit["files"][:80]]]
    lines += ["### Comparison per folder of pages"] + [f"- {s['dir']}:\n```\n{s['text']}\n```" for s in audit["sites"]]
    lines += ["### Page notes"] + ([f"- {p['page']}: {short(p['note'], 700)}" for p in audit["pages"]] or ["(none)"])
    lines += ["### Image files that are not images"] + (audit["badImages"] or ["(none)"])
except Exception as e:
    lines.append(f"audit failed: {e} {run.stderr[-800:]}")
print("\n".join(lines))
