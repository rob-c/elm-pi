"""Each arm against its model's control, paired by task and round, with an exact McNemar test.

    python3 paired.py RESULTS.json [RESULTS.json ...]

An arm named <model>-ctrl is the control for every other <model>-* arm in the same
file; <model>-ctrl2 is the same settings run again (the A/A control), compared the
same way, so its result shows what "no real difference" looks like at this size.
Pairs are (task, round): both arms ran that task in that round at the same moment.
A pair where either run ended on a gateway error (a row with "infra": true - see
ended_on_gateway_error) is left out: that verdict was the gateway's, not the model's.

For each comparison: pass rates, the difference, the discordant pairs (arm passed
and control failed, and the reverse), and the two-sided exact McNemar p-value.
Then the side signals: turn errors, tool errors, replies cut off at the output
limit, foreign-script characters, median time and median input tokens per task.
"""
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def mcnemar(b, c):
    """Two-sided exact McNemar p-value for b and c discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def ended_on_gateway_error(project, rc):
    """True when pi exited non-zero, or the session's last assistant message is an error
    (pi gave up retrying, for instance on HTTP 429): the run says nothing about the model."""
    if rc != 0:
        return True
    last = None
    for f in sorted(Path(project).glob(".pi/sessions/*.jsonl")):
        for line in f.read_text().splitlines():
            m = json.loads(line).get("message") or {}
            if m.get("role") == "assistant":
                last = m
    return bool(last and last.get("stopReason") == "error")


def compare(rows, task_set=None, drop_infra=True, control=None):
    """Every <model>-* arm against <model>-ctrl, or against `control` (an arm name) for that
    control's model. The pairs left out for gateway errors are the same whichever is the control."""
    by_arm = defaultdict(dict)
    infra = {(r["task"], r["rep"]) for r in rows if drop_infra and r.get("infra")}
    for r in rows:
        if task_set and r.get("set") != task_set:
            continue
        if (r["task"], r["rep"]) in infra:
            continue
        by_arm[r["arm"]][(r["task"], r["rep"])] = r
    models = sorted({arm.split("-")[0] for arm in by_arm})
    out = []
    for model in models:
        base = control if control and control.startswith(f"{model}-") else f"{model}-ctrl"
        if base not in by_arm or (control and base != control):
            continue
        for arm in sorted(a for a in by_arm if a.startswith(f"{model}-") and a != base):
            keys = sorted(set(by_arm[arm]) & set(by_arm[base]))
            a = [by_arm[arm][k]["pass"] for k in keys]
            c = [by_arm[base][k]["pass"] for k in keys]
            b_only = sum(1 for x, y in zip(a, c) if x and not y)
            c_only = sum(1 for x, y in zip(a, c) if y and not x)
            out.append({"model": model, "arm": arm, "control": base, "pairs": len(keys),
                        "arm_pass": sum(a), "control_pass": sum(c),
                        "difference_points": round(100 * (sum(a) - sum(c)) / len(keys), 1) if keys else 0.0,
                        "arm_only": b_only, "control_only": c_only, "p": round(mcnemar(b_only, c_only), 3)})
    return out


def fold_replicates(rows):
    """Arms run several times side by side as name, name@2, name@3 ... become one arm with
    more rounds: replicate i of round r is round r * k + (i - 1), k the number of replicates.
    So replicate i of one arm pairs with replicate i of another, run at the same moment."""
    def split(arm):
        name, _, i = arm.partition("@")
        return name, int(i) if i else 1
    k = max(split(r["arm"])[1] for r in rows) if rows else 1
    out = []
    for r in rows:
        name, i = split(r["arm"])
        out.append({**r, "arm": name, "rep": r["rep"] * k + i - 1, "replicate_of": r["arm"]})
    return out


def task_bootstrap(rows, arm, controls, n=20000, seed=1):
    """The arm's pass rate minus the mean of the controls' on the same (task, round), with a 95%
    interval from resampling whole tasks - a task's rounds rise and fall together, so the task,
    not the run, is the independent unit. Pairs touched by a gateway error are left out."""
    import random
    infra = {(r["task"], r["rep"]) for r in rows if r.get("infra")}
    runs = defaultdict(dict)
    for r in rows:
        if (r["task"], r["rep"]) not in infra:
            runs[r["arm"]][(r["task"], r["rep"])] = int(r["pass"])
    keys = sorted(set(runs[arm]).intersection(*(set(runs[c]) for c in controls)))
    by_task = defaultdict(list)
    for k in keys:
        by_task[k[0]].append(runs[arm][k] - sum(runs[c][k] for c in controls) / len(controls))
    tasks = sorted(by_task)
    observed = sum(v for t in tasks for v in by_task[t]) / len(keys)
    rng = random.Random(seed)
    draws = []
    for _ in range(n):
        picked = [v for t in (rng.choice(tasks) for _ in tasks) for v in by_task[t]]
        draws.append(sum(picked) / len(picked))
    draws.sort()
    return {"pairs": len(keys), "tasks": len(tasks), "difference_points": round(100 * observed, 1),
            "ci95_points": [round(100 * draws[int(0.025 * n)], 1), round(100 * draws[int(0.975 * n) - 1], 1)]}


def holm(pvalues):
    """Holm's step-down adjustment of {name: p} for testing several arms at once."""
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    out, running = {}, 0.0
    for i, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, p * (len(ordered) - i)))
        out[name] = round(running, 3)
    return out


def confirm(rows, arm, control):
    """The decision rule of 2026-11-12/mistral-top-p-confirmation-plan.json, applied as written:
    replicates folded into pairs, gateway-error pairs left out, then `arm` ships only if it is ahead
    with an exact McNemar p below 0.05 and the whole-task 95% interval lies above zero."""
    folded = fold_replicates(rows)
    (c,) = [c for c in compare(folded, control=control) if c["arm"] == arm]
    b = task_bootstrap(folded, arm, [control])
    ships = c["arm_only"] > c["control_only"] and c["p"] < 0.05 and b["ci95_points"][0] > 0
    return {**c, "bootstrap": b, "ships": ships}


def signals(rows):
    out = {}
    for arm in sorted({r["arm"] for r in rows}):  # every run, gateway errors included
        rs = [r for r in rows if r["arm"] == arm]
        k = sum(r["pass"] for r in rs)
        lo, hi = wilson(k, len(rs))
        out[arm] = {"runs": len(rs), "passed": k, "rate_ci95": [round(lo, 3), round(hi, 3)],
                    "turn_errors": sum(len(r.get("errors") or []) for r in rs),
                    "tool_errors": sum(r.get("tool_errors", 0) for r in rs),
                    "length_stops": sum(r.get("length_stops", 0) for r in rs),
                    "foreign_chars": sum(r.get("foreign_chars", 0) for r in rs),
                    "failed_without_a_tool_call": sum(1 for r in rs if not r["pass"] and r["tool_calls"] == 0),
                    "gateway_error_endings": sum(1 for r in rs if r.get("infra")),
                    "median_seconds": round(statistics.median(r["seconds"] for r in rs), 1),
                    "median_input_tokens": int(statistics.median(r["input_tokens"] for r in rs))}
    return out


if __name__ == "__main__":
    rows = [r for path in sys.argv[1:] for r in json.load(open(path))]
    dropped = {(r["task"], r["rep"]) for r in rows if r.get("infra")}
    print(f"({len(dropped)} (task, round) pairs left out: a run in them ended on a gateway error)")
    for label, task_set in (("all tasks", None), ("the 25 hardest (hard2)", "hard2")):
        print(f"== {label}")
        for c in compare(rows, task_set):
            print(f"  {c['arm']:20} vs {c['control']:13} {c['arm_pass']:3}/{c['pairs']} vs {c['control_pass']:3}/{c['pairs']}"
                  f"  {c['difference_points']:+5.1f} pts  discordant {c['arm_only']}:{c['control_only']}  p={c['p']}")
    print("== side signals")
    for arm, s in signals(rows).items():
        print(f"  {arm:20} {s['passed']:3}/{s['runs']} ci95 {s['rate_ci95']}  turn-err {s['turn_errors']:3}  tool-err {s['tool_errors']:3}"
              f"  cut-off {s['length_stops']}  foreign {s['foreign_chars']}  no-tool-fail {s['failed_without_a_tool_call']}"
              f"  gateway-end {s['gateway_error_endings']}"
              f"  {s['median_seconds']}s  {s['median_input_tokens'] // 1000}K")
