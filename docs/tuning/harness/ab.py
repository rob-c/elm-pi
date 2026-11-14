"""A/B of Qwen, Mistral and Llama on small sub-agent-style tasks, through the real launcher.

    python3 ab.py PI_LAUNCHER WORKDIR OUT.json [REPS]

Each task runs in a fresh copy of a small Python project, with `pi --auto -p`, and is
scored by a check written in advance. The three models run each task at the same time.
"""
import json
import shutil
import subprocess
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PI, WORK, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
REPS = int(sys.argv[4]) if len(sys.argv) > 4 else 1
MODELS = {"qwen": [], "mistral": ["--mistral"], "llama": ["--llama"]}

HELPERS = "\n\n".join(
    f"def {name}(x):\n    return x {op} {n}" for n, (name, op) in enumerate(
        [("add_one", "+"), ("add_two", "+"), ("double", "*"), ("triple", "*"), ("halve", "/"),
         ("third", "/"), ("minus_one", "-"), ("minus_two", "-"), ("square", "**"), ("cube", "**"),
         ("mod_three", "%"), ("floor_four", "//")], start=1))

FILES = {
    "src/__init__.py": "",
    "src/timeparse.py": textwrap.dedent('''\
        from datetime import datetime


        def parse_stamp(text):
            """An ISO-8601 timestamp, as a datetime."""
            return datetime.fromisoformat(text)


        def format_stamp(moment):
            return moment.isoformat(timespec="seconds")
        '''),
    "src/units.py": textwrap.dedent('''\
        def kmh(metres_per_second):
            return metres_per_second * 3.6


        class Distance:
            def __init__(self, metres):
                self.metres = metres
        '''),
    "src/report.py": textwrap.dedent('''\
        from src.units import kmh


        def speed_line(name, metres_per_second):
            return f"{name}: {kmh(metres_per_second):.1f} km/h"
        '''),
    "src/stats.py": textwrap.dedent('''\
        def mean(values):
            return sum(values) / (len(values) - 1)


        class RunningTotal:
            def __init__(self):
                self.total = 0

            def add(self, x):
                self.total += x
        '''),
    "src/pipeline.py": textwrap.dedent('''\
        """Three stages: load the CSV, drop rows whose counts are negative, write a summary."""
        import csv
        import json


        def load(path):
            with open(path) as fh:
                return [{"t": float(r["t"]), "counts": int(r["counts"])} for r in csv.DictReader(fh)]


        def clean(rows):
            return [r for r in rows if r["counts"] >= 0]


        def summarise(rows, out_path):
            with open(out_path, "w") as fh:
                json.dump({"rows": len(rows), "total": sum(r["counts"] for r in rows)}, fh)
        '''),
    "src/helpers.py": HELPERS + "\n",
    "tests/__init__.py": "",
    "tests/test_stats.py": textwrap.dedent('''\
        import unittest

        from src.stats import mean


        class MeanTests(unittest.TestCase):
            def test_mean(self):
                self.assertEqual(2.5, mean([1, 2, 3, 4]))

            def test_single(self):
                self.assertEqual(7, mean([7]))
        '''),
    "tests/test_units.py": textwrap.dedent('''\
        import unittest

        from src.report import speed_line


        class UnitTests(unittest.TestCase):
            def test_line(self):
                self.assertEqual("car: 36.0 km/h", speed_line("car", 10))
        '''),
    "data/decay.csv": "t,counts\n" + "".join(f"{t},{c}\n" for t, c in
                                               zip(range(0, 10), [1000, 819, 670, 549, 449, 368, 301, 247, 202, 165])),
    "data/background.csv": "t,counts\n0,12\n1,9\n2,-3\n3,11\n",
    "data/notes.txt": "calibration run 4\n",
}


def mean_counts():
    return round(sum([1000, 819, 670, 549, 449, 368, 301, 247, 202, 165]) / 10, 2)


def py(project, code):
    return subprocess.run([sys.executable, "-c", code], cwd=project, capture_output=True, text=True, timeout=60)


def tests_pass(project, *which):
    args = list(which) or ["discover", "-s", "tests", "-t", "."]
    r = subprocess.run([sys.executable, "-m", "unittest", *args], cwd=project,
                       capture_output=True, text=True, timeout=120)
    return r.returncode == 0


def check_rename(project, reply):
    units = (project / "src/units.py").read_text()
    report = (project / "src/report.py").read_text()
    ok = "def km_per_hour(" in units and "def kmh(" not in units and "km_per_hour" in report and "kmh" not in report
    return ok and tests_pass(project, "tests.test_units")


def check_bugfix(project, reply):
    test = (project / "tests/test_stats.py").read_text()
    return test == FILES["tests/test_stats.py"] and tests_pass(project)


def check_weighted(project, reply):
    r = py(project, textwrap.dedent('''\
        from src.stats import weighted_mean
        assert abs(weighted_mean([1, 2, 3], [1, 1, 2]) - 2.25) < 1e-9
        try:
            weighted_mean([1, 2], [0, 0])
        except ValueError:
            print("ok")
        '''))
    return r.stdout.strip() == "ok"


def check_docstrings(project, reply):
    r = py(project, textwrap.dedent('''\
        import ast, pathlib
        tree = ast.parse(pathlib.Path("src/helpers.py").read_text())
        fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        print(len(fns), sum(1 for f in fns if ast.get_docstring(f)))
        import src.helpers as h
        original = {}
        exec(ORIGINAL, original)
        names = [f.name for f in fns]
        assert sorted(names) == sorted(k for k in original if not k.startswith("__")), names
        for name in names:
            for x in (1, 2, 7, 9.5):
                assert getattr(h, name)(x) == original[name](x), name
        ''').replace("ORIGINAL", repr(HELPERS)))
    return r.returncode == 0 and r.stdout.split() == ["12", "12"]


def check_summary_json(project, reply):
    try:
        return json.loads((project / "results/summary.json").read_text()) == {"n_files": 2}
    except (OSError, ValueError):
        return False


def has(*words):
    return lambda project, reply: all(w.lower() in reply.lower() for w in words)


TASKS = {
    "find": ("Which function in src/ parses timestamps? Reply with only its name.",
             lambda p, r: r.strip().strip("`").strip() in ("parse_stamp", "parse_stamp()")),
    "count": ("How many .py files under src/ define at least one class? Reply with the number only.",
              lambda p, r: r.strip() == "2"),
    "rename": ("Do exactly these steps:\n1. In src/units.py rename the function `kmh` to `km_per_hour`.\n"
               "2. Update its caller in src/report.py to match.\n3. Run `python3 -m unittest tests.test_units` "
               "and reply with its last line.", check_rename),
    "bugfix": ("tests/test_stats.py fails. Fix the bug in src/stats.py (do not change the test), run "
               "`python3 -m unittest discover -s tests -t .`, and reply with its last line.", check_bugfix),
    "function": ("Add a function `weighted_mean(values, weights)` to src/stats.py that returns the weighted mean "
                 "and raises ValueError when the weights sum to zero. Reply with one line saying what you did.",
                 check_weighted),
    "data": ("data/decay.csv has columns t and counts. What is the mean of the counts column, to 2 decimal places? "
             "Compute it, and reply with the number only.", lambda p, r: r.strip() == f"{mean_counts():.2f}"),
    "tests": ("Run `python3 -m unittest discover -s tests -t .` and reply exactly as `ran=N failed=M`, where M "
              "counts failures and errors together.", lambda p, r: r.strip().strip("`") == "ran=3 failed=2"),
    "summarise": ("In at most three bullet points, say what src/pipeline.py does. Name the functions.",
                  has("load", "clean", "summarise", "negative")),
    "json": ("Write results/summary.json containing a JSON object with one key, n_files: the number of .csv "
             "files in data/. Reply with the file's contents.", check_summary_json),
    "crossfile": ("Which module imports from src/units.py, and which function of units.py does it use? "
                  "Reply as `module: function`.",
                  lambda p, r: "report" in r and "kmh" in r),
    "every": ("Every function in src/helpers.py lacks a docstring. Add a one-line docstring to every one of them, "
              "changing nothing else, then reply with how many you added.", check_docstrings),
}


def make_project(path):
    for rel, text in FILES.items():
        f = path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)


def session_stats(project):
    stats = {"turns": 0, "tool_calls": 0, "tool_errors": 0, "out_tokens": 0, "errors": []}
    for f in sorted((project / ".pi/sessions").glob("*.jsonl")):
        for line in f.read_text().splitlines():
            r = json.loads(line)
            m = r.get("message") or {}
            if m.get("role") == "assistant":
                stats["turns"] += 1
                stats["out_tokens"] += (m.get("usage") or {}).get("output", 0)
                stats["tool_calls"] += sum(1 for c in m.get("content") or [] if c.get("type") == "toolCall")
                if m.get("stopReason") in ("error", "aborted"):
                    stats["errors"].append((m.get("errorMessage") or "")[:160])
            if m.get("role") == "toolResult" and m.get("isError"):
                stats["tool_errors"] += 1
    return stats


def run(model, task, rep):
    project = WORK / f"{task}-{model}-{rep}"
    shutil.rmtree(project, ignore_errors=True)
    make_project(project)
    prompt, check = TASKS[task]
    started = time.time()
    try:
        done = subprocess.run([str(PI), "--auto", *MODELS[model], "-p", prompt], cwd=project, capture_output=True,
                              text=True, timeout=600, stdin=subprocess.DEVNULL)
        reply, rc = done.stdout.strip(), done.returncode
    except subprocess.TimeoutExpired:
        reply, rc = "", "timeout"
    seconds = round(time.time() - started, 1)
    try:
        passed = bool(check(project, reply))
    except Exception as e:  # noqa: BLE001 - a check that crashes is a fail
        passed = False
        reply += f"\n[check crashed: {e}]"
    return {"model": model, "task": task, "rep": rep, "pass": passed, "seconds": seconds, "rc": rc,
            "reply": reply[-300:], **session_stats(project)}


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    results = []
    for rep in range(REPS):
        for task in TASKS:
            with ThreadPoolExecutor(len(MODELS)) as pool:
                batch = list(pool.map(lambda m: run(m, task, rep), MODELS))
            results += batch
            print(task, rep, " ".join(f"{r['model']}={'PASS' if r['pass'] else 'fail'}/{r['seconds']}s" for r in batch),
                  flush=True)
            OUT.write_text(json.dumps(results, indent=1))


main()
