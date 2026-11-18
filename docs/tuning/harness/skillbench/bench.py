#!/usr/bin/env python3
"""SkillsBench's paired protocol for elm-pi's own skills, run through elm-pi itself.

    bench.py validate [task ...]                    every task: oracle scores 1; untouched and naive score 0
    bench.py routes <name>                          which skills the router would give each task's prompt, no session run
    bench.py build <name>                           a fresh install from the working tree, without the K-Dense library
    bench.py run <name> <arm> [--trials N] [--jobs J] [--only a,b] [--round R] [--install OTHER]
                                                    arm: with-skill | no-skill
    bench.py report <name>                          per task and in total, the two arms side by side

SkillsBench (arXiv 2602.12670; benchflow-ai/skillsbench) measures a skill by
running the same task with and without it, and scoring each run with a
deterministic verifier the agent never sees. A task there is a package: the
prompt, an environment, an oracle that solves it by computation, and the
verifier. This is that protocol with one change: the agent is elm-pi, driven
by the treadmill's own driver (../treadmill/drive.mjs), on this machine.

Why not BenchFlow's own runner (`bench run -a pi`): its `pi` is plain pi in a
container. elm-pi's skills reach a session through its skill router, and fifty
of them are hidden from pi's own listing, so a plain pi would never be given
them; nor would it have elm-pi's launcher, guards or prompt, which are what a
user gets. BenchFlow is used for what it can check here: `bench skills
validate` on templates/skills (README.md).

The two arms use one install. `with-skill` is the install as built. For
`no-skill` its agent/skills is moved aside for the length of the arm, so pi
lists no skill, the router finds none to add, and a session that goes looking
for one finds nothing - then it is put back. One arm at a time on an install: the
lock is agent/.skillbench-arm. To run the arms side by side, build a second install from the
same tree and give it to one of them with --install.

Sessions run `--auto --no-computer-use --offline`: no dialogs to answer, and
no network but the ELM gateway, so no run can install a package that a later
run then finds there. TREADMILL_WORK (default ~/sandbox) holds the install
(elm-pi-sb<name>), a project folder per run and the results (skillbench-out/<name>).
ELM_PI_ENV_FILE is the .env with the ELM key, copied mode 600 and never printed.

Python 3.9, standard library only. The oracle and the verifiers run on the
install's own Python (numpy, scipy, iminuit, sympy, uproot, pytest).
"""

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
TASKS = HERE / "tasks"
TREADMILL = HERE.parent / "treadmill"
WORK = Path(os.environ.get("TREADMILL_WORK") or Path.home() / "sandbox")
ARMS = ("with-skill", "no-skill")
FLAGS = ["--auto", "--no-computer-use", "--offline"]


def task_names(only=None):
    names = sorted(p.parent.name for p in TASKS.glob("*/task.md"))
    if only:
        missing = sorted(set(only) - set(names))
        if missing:
            sys.exit("no such task: " + ", ".join(missing))
        names = [n for n in names if n in only]
    return names


def read_task(name):
    """(frontmatter as a dict of strings, the prompt)."""
    text = (TASKS / name / "task.md").read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n(.*)\Z", text, re.S)
    if not match:
        sys.exit("%s/task.md has no frontmatter" % name)
    meta = dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)
    return meta, " ".join(match.group(2).split())


def install(name):
    return WORK / ("elm-pi-sb" + name)


def out_dir(name):
    return WORK / "skillbench-out" / name


def python_of(root):
    py = root / "agent/python/env/bin/python"
    if not (py.is_file() and os.access(py, os.X_OK)):
        sys.exit("no analysis Python in %s: build it without --no-python" % root)
    return str(py)


def verify(py, name, project):
    """(reward, why) from the task's hidden check, run in the project folder."""
    run = subprocess.run([py, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
                          str(TASKS / name / "verifier/test_outputs.py")],
                         cwd=str(project), capture_output=True, text=True, timeout=600,
                         env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if run.returncode == 0:
        return 1, ""
    failed = re.findall(r"^FAILED \S+::(\w+)", run.stdout, re.M) or re.findall(r"^ERROR \S+", run.stdout, re.M)
    return 0, ", ".join(failed)[:300] or (run.stdout.strip().splitlines() or ["?"])[-1][:300]


def seeded(name, where):
    shutil.copytree(TASKS / name / "environment", where, dirs_exist_ok=True)


# --- validate ------------------------------------------------------------------------

def validate(options):
    py = options.python or os.environ.get("SKILLBENCH_PYTHON") or ""
    if not py:
        sys.exit("validate needs --python (or SKILLBENCH_PYTHON): an install's agent/python/env/bin/python")
    bad = 0
    for name in task_names(options.tasks):
        folder = TASKS / name
        meta, prompt = read_task(name)
        problems = []
        for key in ("skill", "category", "pitfall", "timeout_sec"):
            if not meta.get(key):
                problems.append("task.md has no %s" % key)
        if meta.get("skill") and not (REPO / "templates/skills" / meta["skill"] / "SKILL.md").is_file():
            problems.append("skill %s does not exist" % meta["skill"])
        # SkillsBench: the prompt names no skill and gives no hint which to use.
        for skill in [meta.get("skill", "")] + [s.strip() for s in meta.get("also", "").split(",") if s.strip()]:
            if skill and skill in prompt:
                problems.append("the prompt names the skill %s" % skill)
        if "skill" in prompt.lower().split():
            problems.append("the prompt says 'skill'")
        for needed in ("environment", "oracle/solve.py", "oracle/naive.py", "verifier/test_outputs.py"):
            if not (folder / needed).exists():
                problems.append("no " + needed)
        tests = len(re.findall(r"^def test_", (folder / "verifier/test_outputs.py").read_text(), re.M)) \
            if (folder / "verifier/test_outputs.py").exists() else 0
        if tests and not 3 <= tests <= 10:
            problems.append("%d test functions (3 to 10)" % tests)
        if not problems:
            for label, script, want in (("oracle", "oracle/solve.py", 1), ("untouched", None, 0), ("naive", "oracle/naive.py", 0)):
                with tempfile.TemporaryDirectory() as tmp:
                    seeded(name, tmp)
                    if script:
                        ran = subprocess.run([py, str(folder / script)], cwd=tmp, capture_output=True, text=True, timeout=900)
                        if ran.returncode != 0:
                            problems.append("%s did not run: %s" % (script, (ran.stderr.strip().splitlines() or ["?"])[-1][:200]))
                            continue
                    reward, why = verify(py, name, tmp)
                    if reward != want:
                        problems.append("%s scores %d, not %d%s" % (label, reward, want, (": " + why) if why else ""))
        print("%-38s %s" % (name, "ok" if not problems else "; ".join(problems)))
        bad += bool(problems)
    print("%d task(s), %d with problems" % (len(task_names(options.tasks)), bad))
    return 1 if bad else 0


# --- routes --------------------------------------------------------------------------

ROUTES = '''
const [source, dir, promptsPath] = process.argv.slice(1);
const fs = await import("node:fs");
const router = await import(source);
const out = {};
for (const [task, prompt] of Object.entries(JSON.parse(fs.readFileSync(promptsPath, "utf8")))) {
  const general = router.routesFor(prompt).filter((name) => fs.existsSync(`${dir}/${name}/SKILL.md`));
  const domain = router.domainRoutesFor(prompt, dir).filter((name) => !general.includes(name));
  out[task] = { inlined: [...general.slice(0, 2), ...domain.slice(0, 1)], named: [...general.slice(2, 4), ...domain.slice(1, 3)] };
}
console.log(JSON.stringify(out));
'''


def routes(options):
    """SkillsBench: an installed skill is not a used one. Before any session is paid for: does each task's
    prompt, worded as a user would word it, get its skill from the router at all?"""
    root = install(options.name)
    prompts = {name: read_task(name)[1] for name in task_names()}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "prompts.json"
        path.write_text(json.dumps(prompts))
        ran = subprocess.run([str(root / ".node/bin/node"), "--no-warnings", "--input-type=module", "-e", ROUTES,
                              str(REPO / "templates/extensions/skill-router.ts"), str(REPO / "templates/skills"), str(path)],
                             capture_output=True, text=True, timeout=120)
    if ran.returncode != 0:
        sys.exit("node failed:\n" + ran.stderr[-2000:])
    routed = json.loads(ran.stdout)
    full = named = 0
    for name in sorted(routed):
        skill = read_task(name)[0].get("skill", name)
        where = "in full" if skill in routed[name]["inlined"] else "named" if skill in routed[name]["named"] else "NOT ROUTED"
        full += where == "in full"
        named += where == "named"
        print("%-36s %-10s  in full: %s%s" % (name, where, ", ".join(routed[name]["inlined"]) or "-",
                                              ("; named: " + ", ".join(routed[name]["named"])) if routed[name]["named"] else ""))
    print("%d tasks: the task's skill in full for %d, named for %d, not routed for %d"
          % (len(routed), full, named, len(routed) - full - named))
    return 0


# --- build ---------------------------------------------------------------------------

def build(options):
    root, out = install(options.name), out_dir(options.name)
    env_file = os.environ.get("ELM_PI_ENV_FILE")
    if not env_file:
        sys.exit("set ELM_PI_ENV_FILE to a .env holding ELM_API_KEY")
    if root.exists():
        sys.exit("%s already exists" % root)
    out.mkdir(parents=True, exist_ok=True)
    listed = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=str(REPO), capture_output=True,
                            text=True, check=True).stdout.splitlines()
    for name in listed:
        source = REPO / name
        # Not the tasks: an install a session can read must not hold their oracles and verifiers.
        if name == ".env" or not source.is_file() or name.startswith("docs/tuning/harness/skillbench/tasks/"):
            continue
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, root / name)
    shutil.copy(env_file, root / ".env")
    os.chmod(root / ".env", 0o600)
    with open(out / "bootstrap.txt", "w") as log:
        status = subprocess.call(["./bootstrap.sh", "--no-skill-library"], cwd=str(root), stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT)
    loaded = re.findall(r"\d+ extensions loaded, \d+ failed", (out / "bootstrap.txt").read_text(errors="replace"))
    print("bootstrap exit %d; %s; %s" % (status, loaded[-1] if loaded else "extensions not counted", root))
    return status


# --- run -----------------------------------------------------------------------------

def set_arm(root, arm):
    """Put the install in the arm's state. Returns a function that puts it back."""
    skills, aside, lock = root / "agent/skills", root / "agent/skills.skillbench", root / "agent/.skillbench-arm"
    if lock.exists():
        sys.exit("%s says an arm is running (%s). If none is: put agent/skills.skillbench back as agent/skills, "
                 "and remove the lock." % (lock, lock.read_text().strip()))
    if aside.exists():
        sys.exit("%s exists: a no-skill arm did not finish. Put it back as agent/skills first." % aside)
    lock.write_text("%s, pid %d\n" % (arm, os.getpid()))
    if arm == "no-skill":
        skills.rename(aside)
        skills.mkdir()

    def restore():
        if arm == "no-skill" and aside.exists():
            shutil.rmtree(skills, ignore_errors=True)
            aside.rename(skills)
        lock.unlink()
    return restore


def finished(result):
    """A session that ran to its own end. One the driver stopped at the time limit, or that never got an
    answer from a rate-limited gateway, says nothing about a skill: on 2026-11-17 another batch on the same
    key had these sessions waiting out 429s for most of their fifteen minutes."""
    return result.get("finish") == "done" and result.get("driver") == 0


def one(root, py, out, arm, name, trial, limit, scale=1.0):
    run_id = "%s.%d" % (name, trial)
    project = WORK / ("sb%s-%s-%s" % (out.name, arm, run_id))
    folder = out / arm / run_id
    result_file = folder / "result.json"
    if result_file.exists():
        earlier = json.loads(result_file.read_text())
        if finished(earlier):
            return earlier
        # An unfinished run is run again, its files kept beside the new ones for the record.
        attempt = len(list(out.glob("%s/%s.unfinished*" % (arm, run_id)))) + 1
        folder.rename(out / arm / ("%s.unfinished%d" % (run_id, attempt)))
    if project.exists():
        shutil.rmtree(project)
    folder.mkdir(parents=True, exist_ok=True)
    seeded(name, project)
    git = ["git", "-c", "user.name=user", "-c", "user.email=user@example.invalid"]
    subprocess.run(["git", "init", "-q"], cwd=str(project), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(project), check=True)
    subprocess.run(git + ["commit", "--allow-empty", "-qm", "the project as it was"], cwd=str(project), check=True)
    meta, prompt = read_task(name)
    seconds = min(int(int(meta.get("timeout_sec", "900")) * scale), limit)
    started = time.time()
    driven = subprocess.call([str(root / ".node/bin/node"), str(TREADMILL / "drive.mjs"), str(root / "pi"), str(project),
                              str(folder / "rpc.jsonl"), json.dumps(FLAGS), json.dumps([prompt]), str(seconds)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(folder / "report.md", "w") as report, open(folder / "analyze.err", "w") as errors:
        subprocess.call([sys.executable, str(TREADMILL / "analyze.py"), str(project), str(root), str(folder)],
                        stdout=report, stderr=errors, env={**os.environ, "ELM_PI_REPO": str(REPO)})
    text = (folder / "report.md").read_text(errors="replace")
    reward, why = verify(py, name, project)
    grab = lambda pattern, default="": (re.search(pattern, text) or [None, default])[1]
    finish = re.findall(r'"finish":"([^"]*)"', (folder / "rpc.jsonl").read_text(errors="replace"))
    result = {
        "task": name, "arm": arm, "trial": trial, "reward": reward, "why": why,
        "seconds": round(time.time() - started), "driver": driven, "finish": finish[-1] if finish else "?",
        "turns": grab(r"; (\d+) model turns", "?"), "tokens": int(grab(r"Total tokens[^:]*: ([\d,]+)", "0").replace(",", "")),
        "inlined": grab(r"skills put in full by the router: ([^;]*);", "?"),
        "named": grab(r"named only: ([^;]*);", "?"), "read": grab(r"SKILL\.md read with `read`: (.*)", "?"),
        "project": str(project),
    }
    result_file.write_text(json.dumps(result, indent=1))
    print("%-10s %-38s %s  %4ds  %s" % (arm, run_id, "pass" if reward else "FAIL", result["seconds"], why[:70]), flush=True)
    return result


def run(options):
    if options.arm not in ARMS:
        sys.exit("arm is one of: " + ", ".join(ARMS))
    root, out = install(options.install or options.name), out_dir(options.name)
    py = python_of(root)
    names = task_names(options.only.split(",") if options.only else None)
    first = (options.round - 1) * options.trials + 1
    jobs = [(name, trial) for trial in range(first, first + options.trials) for name in names]
    restore = set_arm(root, options.arm)
    try:
        with concurrent.futures.ThreadPoolExecutor(options.jobs) as pool:
            futures = []
            for name, trial in jobs:
                futures.append(pool.submit(one, root, py, out, options.arm, name, trial, options.max, options.patience))
                time.sleep(3)          # as batch.sh: sessions do not all start in the same second
            results = [future.result() for future in futures]
    finally:
        restore()
    done = [r for r in results if finished(r)]
    print("%s: %d of %d finished runs passed; %d did not finish (run the same command again to repeat them)"
          % (options.arm, sum(r["reward"] for r in done), len(done), len(results) - len(done)))
    return 0


# --- report --------------------------------------------------------------------------

def collect(name):
    """(finished runs, unfinished ones). Only the first are evidence."""
    rows, unfinished = [], []
    for arm in ARMS:
        for path in sorted((out_dir(name) / arm).glob("*/result.json")):
            if ".unfinished" in path.parent.name:
                continue
            result = json.loads(path.read_text())
            (rows if finished(result) else unfinished).append(result)
    return rows, unfinished


def report(options):
    rows, unfinished = collect(options.name)
    if not rows:
        sys.exit("no results under %s" % out_dir(options.name))
    tasks = sorted({r["task"] for r in rows})
    print("| task | skill | with-skill | no-skill | skill reached the session | why a with-skill run failed |")
    print("|---|---|---|---|---|---|")
    totals = {arm: [0, 0, 0, 0] for arm in ARMS}        # passed, runs, tokens, seconds
    kinds = {"helped": [], "both pass": [], "both fail": [], "hurt": [], "mixed": []}
    for task in tasks:
        meta, _ = read_task(task)
        cells, rates = {}, {}
        for arm in ARMS:
            mine = [r for r in rows if r["task"] == task and r["arm"] == arm]
            passed = sum(r["reward"] for r in mine)
            cells[arm] = "%d/%d" % (passed, len(mine)) if mine else "-"
            rates[arm] = passed / len(mine) if mine else None
            totals[arm][0] += passed
            totals[arm][1] += len(mine)
            totals[arm][2] += sum(r["tokens"] for r in mine)
            totals[arm][3] += sum(r["seconds"] for r in mine)
        with_runs = [r for r in rows if r["task"] == task and r["arm"] == "with-skill"]
        skill = meta.get("skill", task)
        reached = sum(1 for r in with_runs if skill in (r["inlined"] + "," + r["named"] + "," + r["read"]))
        why = "; ".join(sorted({r["why"] for r in with_runs if not r["reward"] and r["why"]}))[:90]
        print("| %s | %s | %s | %s | %s | %s |" % (task, skill, cells["with-skill"], cells["no-skill"],
                                                 "%d/%d" % (reached, len(with_runs)) if with_runs else "-", why))
        w, n = rates["with-skill"], rates["no-skill"]
        if w is None or n is None:
            continue
        kind = ("both pass" if w == 1 and n == 1 else "both fail" if w == 0 and n == 0 else
                "helped" if w > n else "hurt" if w < n else "mixed")
        kinds[kind].append(task)
    print()
    rate = {}
    for arm in ARMS:
        passed, runs, tokens, seconds = totals[arm]
        rate[arm] = passed / runs if runs else 0.0
        print("%s: %d of %d runs passed (%.1f%%); %.0f k tokens and %.0f s a run"
              % (arm, passed, runs, 100 * rate[arm], tokens / max(runs, 1) / 1000, seconds / max(runs, 1)))
    if totals["with-skill"][1] and totals["no-skill"][1]:
        delta = rate["with-skill"] - rate["no-skill"]
        gain = delta / (1 - rate["no-skill"]) if rate["no-skill"] < 1 else 0.0
        print("difference: %+.1f points; normalised gain %.1f%% (SkillsBench: curated skills +16.6 points, 25.5%%)"
              % (100 * delta, 100 * gain))
    for kind, names in kinds.items():
        print("%s (%d): %s" % (kind, len(names), ", ".join(names)))
    if unfinished:
        print("not counted, cut off before the session ended (%d): %s" % (
            len(unfinished), ", ".join("%s/%s.%d" % (r["arm"], r["task"], r["trial"]) for r in unfinished)))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command")
    checking = commands.add_parser("validate")
    checking.add_argument("tasks", nargs="*")
    checking.add_argument("--python", default="")
    building = commands.add_parser("build")
    building.add_argument("name")
    running = commands.add_parser("run")
    running.add_argument("name")
    running.add_argument("arm")
    running.add_argument("--trials", type=int, default=1)
    running.add_argument("--round", type=int, default=1, help="trial numbers continue from earlier rounds")
    running.add_argument("--jobs", type=int, default=3)
    running.add_argument("--only", default="")
    running.add_argument("--max", type=int, default=1200, help="seconds no session may exceed")
    running.add_argument("--patience", type=float, default=1.0, help="multiply every task's time limit: for a "
                                                                    "rate-limited gateway or a loaded machine")
    running.add_argument("--install", default="", help="run on another install built from the same tree, so that "
                                                        "the two arms can run at once; results still go under <name>")
    reporting = commands.add_parser("report")
    reporting.add_argument("name")
    routing = commands.add_parser("routes")
    routing.add_argument("name")
    options = parser.parse_args()
    if options.command is None:
        parser.print_usage(sys.stderr)
        return 2
    return {"validate": validate, "build": build, "run": run, "report": report, "routes": routes}[options.command](options)


if __name__ == "__main__":
    sys.exit(main())
