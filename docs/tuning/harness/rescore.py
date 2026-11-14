"""Re-check failed runs of the file-based tasks under this interpreter (one with numpy).

    VENV_PYTHON rescore.py ABDIR

A function that imports numpy is correct code; the checks failed it only because the
interpreter they ran under had no numpy. Writes results3/4/5.numpy.json beside the
originals, with "pass" re-checked and "pass_without_numpy" keeping the old verdict.
"""
import json
import sys
from pathlib import Path

A = Path(sys.argv[1])
sys.argv = ["ab2.py", "/bin/true", str(A / "unused"), str(A / "unused.json"), "/tmp/a", "/tmp/g", "1"]
ns = {"__name__": "rescore", "__file__": str(A / "ab2.py")}
exec(compile((A / "ab2.py").read_text().replace("\nmain()\n", "\n"), "ab2.py", "exec"), ns)
FILE_TASKS = {"function", "rename", "bugfix", "every", "json", "h_median", "h_hints", "h_filter"}
for results, work in (("results3", "work3"), ("results4", "work4"), ("results5", "work5")):
    path = A / f"{results}.json"
    if not path.exists():
        continue
    rows = json.loads(path.read_text())
    changed = 0
    for r in rows:
        r["pass_without_numpy"] = r["pass"]
        if r["pass"] or r["task"] not in FILE_TASKS:
            continue
        project = A / work / f"{r['task']}-{r['arm'].replace('+', '_')}-{r['rep']}"
        if ns["ALL"][r["task"]][1](project, r["reply"]):
            r["pass"] = True
            changed += 1
    (A / f"{results}.numpy.json").write_text(json.dumps(rows, indent=1))
    print(f"{results}: {changed} failed runs pass with numpy available")
