"""Summarise the tuning run per arm and per task, with a paired comparison against each model's A arm.

    python3 tuning_report.py results6.json
"""
import json
import statistics
import sys
from collections import defaultdict

rows = json.load(open(sys.argv[1]))
arms = sorted(dict.fromkeys(r["arm"] for r in rows))
print(f"{'arm':10} {'pass':>8} {'hard':>6} {'held-out':>8} {'first11':>8} {'no-tool':>7} {'guard':>5} {'median s':>8} {'in-tok':>7} {'out-tok':>7}")
for arm in arms:
    rs = [r for r in rows if r["arm"] == arm]
    hard = [r for r in rs if r["hard"]]
    held = [r for r in rs if r["task"].startswith("h_")]
    first = [r for r in rs if not r["hard"] and not r["task"].startswith("h_")]
    f = lambda x: f"{sum(r['pass'] for r in x)}/{len(x)}" if x else "-"
    print(f"{arm:10} {f(rs):>8} {f(hard):>6} {f(held):>8} {f(first):>8} "
          f"{sum(1 for r in rs if not r['pass'] and r['tool_calls'] == 0):>7} {sum(1 for r in rs if r['guard_fired']):>5} "
          f"{statistics.median(r['seconds'] for r in rs):8.1f} {statistics.median(r['input_tokens'] for r in rs)/1000:6.0f}K "
          f"{statistics.median(r['output_tokens'] for r in rs):7.0f}")

# Paired by task and round: where an arm differs from its model's A arm.
print("\nper task, passes of 3 (A / B / C)")
by = defaultdict(lambda: defaultdict(int))
for r in rows:
    by[(r["arm"].split("-")[0], r["task"])][r["arm"].split("-")[1]] += r["pass"]
for (model, task), cell in sorted(by.items()):
    if len(set(cell.get(x, 0) for x in "ABC")) > 1:
        print(f"  {model:8} {task:10} {cell.get('A', 0)} / {cell.get('B', 0)} / {cell.get('C', 0)}")
