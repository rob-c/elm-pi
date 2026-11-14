"""Every Mistral arm side by side, from results3 (default, +md, Qwen), results4 (0.15), results5 (guarded)."""
import json
import statistics
import sys
from pathlib import Path

A = Path(sys.argv[1])
d = []
for name in ("results3.json", "results4.json", "results5.json"):
    p = A / name
    if p.exists():
        d += json.loads(p.read_text())
ARMS = ["mistral", "mistral+md", "mistral@0.15", "mistral@0.15+guard", "mistral-high@0.7+guard",
        "mistral@0.15+vibe+guard", "qwen"]
LABEL = {"mistral": "default temp (1.0)", "mistral+md": "1.0 + written rules", "mistral@0.15": "0.15",
         "mistral@0.15+guard": "0.15 + guard", "mistral-high@0.7+guard": "reasoning high, 0.7 + guard",
         "mistral@0.15+vibe+guard": "0.15 + Vibe rules + guard", "qwen": "Qwen (reference)"}


def frac(rs):
    return f"{sum(r['pass'] for r in rs)}/{len(rs)}" if rs else "-"


print(f"{'Mistral arm':30} {'11 original':>11} {'6 held-out':>11} {'all 17':>8} {'false claims':>13} {'guard fired':>12} {'median s':>9}")
for arm in ARMS:
    rs = [r for r in d if r["arm"] == arm]
    if not rs:
        continue
    o = [r for r in rs if not r["held_out"]]
    h = [r for r in rs if r["held_out"]]
    false_claims = sum(1 for r in rs if not r["pass"] and r["tool_calls"] == 0)
    fired = sum(1 for r in rs if r.get("guard_fired"))
    fired_passed = sum(1 for r in rs if r.get("guard_fired") and r["pass"])
    guard = f"{fired} ({fired_passed} pass)" if "guard" in arm else "-"
    print(f"{LABEL[arm]:30} {frac(o):>11} {frac(h):>11} {frac(rs):>8} {false_claims:>13} {guard:>12} "
          f"{statistics.median(r['seconds'] for r in rs):9.1f}")
print("\nper task, passes of 3, in the order above")
for t in dict.fromkeys(r["task"] for r in d):
    cells = []
    for arm in ARMS:
        rs = [r for r in d if r["arm"] == arm and r["task"] == t]
        cells.append(str(sum(r["pass"] for r in rs)) if rs else "-")
    print(f"  {t:10} {'  '.join(cells)}")
