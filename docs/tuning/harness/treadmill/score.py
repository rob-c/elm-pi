"""Score a benchmark batch: run each task's hidden check in its project folder with the install's Python.
   score.py <batch name> <dir holding checks/>  -> a table, and scores.json beside the batch's reports.
   A run named task.2 is scored by checks/task.py. TREADMILL_WORK and TREADMILL_OUT as for batch.sh."""
import json, os, re, subprocess, sys
from pathlib import Path
S = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent; name = sys.argv[1]
WORK = Path(os.environ.get("TREADMILL_WORK") or Path.home() / "sandbox")
inst = WORK / f"elm-pi-b{name}"; out = Path(os.environ.get("TREADMILL_OUT") or WORK / "treadmill-out") / f"b{name}"
py = inst / "agent/python/env/bin/python"
rows = []
for run in sorted(p.name for p in out.iterdir() if (p / "rpc.jsonl").exists()):
    task = re.sub(r"\.\d+$", "", run); proj = WORK / f"b{name}-{run}"
    r = subprocess.run([str(py), str(S / f"checks/{task}.py")], cwd=proj, capture_output=True, text=True, timeout=300,
                       env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": ".:src"})
    why = "" if r.returncode == 0 else (r.stderr.strip().splitlines() or ["?"])[-1][:110]
    rep = (out / run / "report.md").read_text() if (out / run / "report.md").exists() else ""
    wall = (re.search(r"wall ([^;]+);", rep) or [None, "?"])[1]; tok = (re.search(r"Total tokens[^:]*: ([\d,]+)", rep) or [None, "0"])[1]
    turns = (re.search(r"; (\d+) model turns", rep) or [None, "?"])[1]
    rows.append({"run": run, "pass": r.returncode == 0, "wall": wall, "tokens": int(tok.replace(",", "")), "turns": turns, "why": why})
json.dump(rows, open(out / "scores.json", "w"), indent=1)
print("| task | result | wall | turns | tokens | why |\n|---|---|---|---|---|---|")
for r in rows: print(f"| {r['run']} | {'pass' if r['pass'] else 'FAIL'} | {r['wall']} | {r['turns']} | {r['tokens']:,} | {r['why']} |")
print(f"\n{sum(r['pass'] for r in rows)}/{len(rows)} passed, {sum(r['tokens'] for r in rows):,} tokens")
