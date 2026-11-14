"""Tuning runs: model settings compared on 25 tasks, each arm in its own install.

    python3 ab6.py ARMS.json WORKDIR OUT.json REPS

ARMS.json: {"arm name": {"pi": "/path/to/install/pi", "args": [...], "tasks": "all" | "qwen", "env": {...}}}
"env" (optional) is added to the run's environment - e.g. SHIM_TEMPERATURE and ELM_SHIM_PORT,
which reach Llama's shim and nothing else.
"qwen" arms run the 6 held-out and 8 hard tasks only (Qwen passes the first 11 every time).
AB_SUITE=50 in the environment adds the 25 tasks of hard2.py: 50 tasks, run by every arm.
All arms run each task at the same moment, so they see the same gateway load. Each result
records tokens, turns and tool calls as well as pass/fail.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
arms_file, WORK, OUT, REPS = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), int(sys.argv[4])
ARMS = json.loads(arms_file.read_text())

ns = {"__name__": "ab6_base", "__file__": str(HERE / "ab2.py")}
saved = sys.argv
sys.argv = ["ab2.py", "/bin/true", str(WORK), str(OUT), "/tmp/a", "/tmp/g", "1"]
exec(compile((HERE / "ab2.py").read_text().replace("\nmain()\n", "\n"), "ab2.py", "exec"), ns)
sys.argv = saved
hard = {"__name__": "hard"}
exec(compile((HERE / "hard.py").read_text(), "hard.py", "exec"), hard)

TASKS = {name: (prompt, check, {}) for name, (prompt, check) in ns["ALL"].items()}
TASKS.update(hard["HARD"])
HELD_OUT = set(ns["HELD_OUT"]) | set(hard["HARD"])
SET = {**{t: "first11" for t in ns["TASKS"]}, **{t: "held_out" for t in ns["HELD_OUT"]}, **{t: "hard" for t in hard["HARD"]}}
if os.environ.get("AB_SUITE") == "50":
    hard2 = {"__name__": "hard2", "__file__": str(HERE / "hard2.py")}
    exec(compile((HERE / "hard2.py").read_text(), "hard2.py", "exec"), hard2)
    TASKS.update(hard2["HARD2"])
    HELD_OUT |= set(hard2["HARD2"])
    SET.update({t: "hard2" for t in hard2["HARD2"]})


# Text in scripts the agent never needs here: Qwen's card names "language mixing"
# as the cost of a high presence penalty, so it is counted in every reply.
FOREIGN = re.compile(r"[\u0400-\u04ff\u0590-\u06ff\u0e00-\u0e7f\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


def usage(project):
    """Tokens in and out, replies cut off at the output limit, and characters of foreign script."""
    inp = out = length_stops = foreign = 0
    for f in (project / ".pi/sessions").glob("*.jsonl"):
        for line in f.read_text().splitlines():
            m = json.loads(line).get("message") or {}
            if m.get("role") == "assistant":
                u = m.get("usage") or {}
                inp += u.get("input", 0)
                out += u.get("output", 0)
                length_stops += m.get("stopReason") == "length"
                for part in m.get("content") or []:
                    if part.get("type") == "text":
                        foreign += len(FOREIGN.findall(part.get("text") or ""))
    return inp, out, length_stops, foreign


def run(arm, task, rep):
    spec = ARMS[arm]
    project = WORK / f"{task}-{arm}-{rep}"
    shutil.rmtree(project, ignore_errors=True)
    ns["make_project"](project)
    prompt, check, extra = TASKS[task]
    for rel, text in extra.items():
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_text(text)
    started = time.time()
    try:
        done = subprocess.run([spec["pi"], "--auto", *spec["args"], "-p", prompt], cwd=project, capture_output=True,
                              text=True, timeout=900, stdin=subprocess.DEVNULL, env={**os.environ, **spec.get("env", {})})
        reply, rc = done.stdout.strip(), done.returncode
    except subprocess.TimeoutExpired:
        reply, rc = "", "timeout"
    seconds = round(time.time() - started, 1)
    try:
        passed = bool(check(project, reply))
    except Exception as e:  # noqa: BLE001
        passed = False
        reply += f"\n[check crashed: {e}]"
    inp, out, length_stops, foreign = usage(project)
    stats = ns["session_stats"](project)
    guard = sum(f.read_text().count('"claim-guard"') for f in (project / ".pi/sessions").glob("*.jsonl"))
    return {"arm": arm, "task": task, "hard": task in hard["HARD"], "set": SET[task], "rep": rep, "pass": passed,
            "seconds": seconds,
            "rc": rc, "reply": reply[-300:], "input_tokens": inp, "output_tokens": out, "length_stops": length_stops, "foreign_chars": foreign,
            "guard_fired": guard,
            **{k: stats[k] for k in ("turns", "tool_calls", "tool_errors", "errors")}}


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    results = json.loads(OUT.read_text()) if OUT.exists() else []
    done = {(r["arm"], r["task"], r["rep"]) for r in results}
    for rep in range(REPS):
        for task in TASKS:
            arms = [a for a in ARMS if (ARMS[a]["tasks"] == "all" or task in HELD_OUT) and (a, task, rep) not in done]
            if not arms:
                continue
            with ThreadPoolExecutor(len(arms)) as pool:
                batch = list(pool.map(lambda a: run(a, task, rep), arms))
            results += batch
            print(task, rep, " ".join(f"{r['arm']}={'P' if r['pass'] else 'f'}/{r['seconds']:.0f}s" for r in batch),
                  flush=True)
            OUT.write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
