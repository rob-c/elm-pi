"""Does model-specific guidance fix Mistral? Arms x tasks x reps, through the real launcher.

    python3 ab2.py PI_LAUNCHER WORKDIR OUT.json APPEND_SYSTEM.md GUIDANCE.md REPS

Arms: Mistral as installed, Mistral with the guidance appended, and Qwen as installed.
Both Mistral arms pass the install's APPEND_SYSTEM.md explicitly (--append-system-prompt
replaces the discovered one), so the guidance is the only difference. The original 11
tasks are joined by 6 held-out ones the guidance was not written against; Qwen runs
the held-out ones only, to show how hard they are.
"""
import json
import shutil
import subprocess
import sys
import textwrap
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
PI, WORK, OUT, APPEND, GUIDANCE, REPS = (Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]),
                                         Path(sys.argv[4]), Path(sys.argv[5]), int(sys.argv[6]))

# The original harness's fixture, checks and tasks, without running it.
base = {"__name__": "ab_base"}
saved = sys.argv
sys.argv = ["ab.py", str(PI), str(WORK), str(OUT)]
exec(compile((HERE / "ab.py").read_text().replace("\nmain()\n", "\n"), "ab.py", "exec"), base)
sys.argv = saved
FILES, TASKS, py, tests_pass, make_project, session_stats = (base[k] for k in (
    "FILES", "TASKS", "py", "tests_pass", "make_project", "session_stats"))


def check_median(project, reply):
    r = py(project, textwrap.dedent('''\
        from src.stats import median, RunningTotal
        assert median([3, 1, 2]) == 2
        assert median([4, 1, 3, 2]) == 2.5
        assert median([7]) == 7
        print("ok")
        '''))
    return r.stdout.strip() == "ok"


def check_hints(project, reply):
    r = py(project, textwrap.dedent('''\
        import ast, pathlib
        bad = []
        for f in ("src/timeparse.py", "src/units.py"):
            for n in ast.parse(pathlib.Path(f).read_text()).body:
                if isinstance(n, ast.FunctionDef):
                    if n.returns is None or any(a.annotation is None for a in n.args.args):
                        bad.append(n.name)
        from src.report import speed_line
        from src.timeparse import parse_stamp, format_stamp
        assert speed_line("car", 10) == "car: 36.0 km/h"
        assert format_stamp(parse_stamp("2026-01-02T03:04:05")) == "2026-01-02T03:04:05"
        print("bad:" + ",".join(bad))
        '''))
    return r.returncode == 0 and r.stdout.strip() == "bad:"


def check_filter(project, reply):
    r = py(project, textwrap.dedent('''\
        from src.pipeline import clean
        rows = [{"t": 1.0, "counts": 5}, {"t": -1.0, "counts": 5}, {"t": 2.0, "counts": -1}, {"t": 0.0, "counts": 0}]
        assert clean(rows) == [{"t": 1.0, "counts": 5}, {"t": 0.0, "counts": 0}], clean(rows)
        print("ok")
        '''))
    return r.stdout.strip() == "ok"


def check_main(project, reply):
    r = subprocess.run([sys.executable, "-m", "src"], cwd=project, capture_output=True, text=True, timeout=60)
    return r.stdout.strip() == "car: 36.0 km/h" and "car: 36.0 km/h" in reply


HELD_OUT = {
    "h_median": ("Add a function `median(values)` to src/stats.py that returns the median of a list (the mean of "
                 "the two middle values when the count is even). Reply with one line saying what you did.",
                 check_median),
    "h_where": ("Which test file exercises `speed_line`? Reply with the path only.",
                lambda p, r: r.strip().strip("`") in ("tests/test_units.py", "./tests/test_units.py")),
    "h_hints": ("Add type hints to every module-level function in src/timeparse.py and src/units.py, changing "
                "nothing else. Reply with how many functions you annotated.", check_hints),
    "h_filter": ("Change `clean` in src/pipeline.py so that it also drops rows whose t is negative. Change nothing "
                 "else. Reply with one line.", check_filter),
    "h_rows": ("How many rows of data/decay.csv have counts above 400? Reply with the number only.",
               lambda p, r: r.strip() == "5"),
    "h_main": ("Create src/__main__.py so that `python3 -m src` prints the result of speed_line('car', 10). "
               "Run it, and reply with exactly what it printed.", check_main),
}
ALL = {**TASKS, **HELD_OUT}
ARMS = {
    "mistral": ["--mistral", "--append-system-prompt", str(APPEND)],
    "mistral+md": ["--mistral", "--append-system-prompt", str(APPEND), "--append-system-prompt", str(GUIDANCE)],
    "qwen": [],
}


def run(arm, task, rep):
    project = WORK / f"{task}-{arm.replace('+', '_')}-{rep}"
    shutil.rmtree(project, ignore_errors=True)
    make_project(project)
    prompt, check = ALL[task]
    started = time.time()
    try:
        done = subprocess.run([str(PI), "--auto", *ARMS[arm], "-p", prompt], cwd=project, capture_output=True,
                              text=True, timeout=600, stdin=subprocess.DEVNULL)
        reply, rc = done.stdout.strip(), done.returncode
    except subprocess.TimeoutExpired:
        reply, rc = "", "timeout"
    seconds = round(time.time() - started, 1)
    try:
        passed = bool(check(project, reply))
    except Exception as e:  # noqa: BLE001
        passed = False
        reply += f"\n[check crashed: {e}]"
    return {"arm": arm, "task": task, "held_out": task in HELD_OUT, "rep": rep, "pass": passed, "seconds": seconds,
            "rc": rc, "reply": reply[-300:], **session_stats(project)}


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    results = []
    for rep in range(REPS):
        for task in ALL:
            arms = [a for a in ARMS if a != "qwen" or task in HELD_OUT]
            with ThreadPoolExecutor(len(arms)) as pool:
                batch = list(pool.map(lambda a: run(a, task, rep), arms))
            results += batch
            print(task, rep, " ".join(f"{r['arm']}={'PASS' if r['pass'] else 'fail'}/{r['seconds']}s" for r in batch),
                  flush=True)
            OUT.write_text(json.dumps(results, indent=1))


main()
