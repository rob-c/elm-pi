"""The agent's own Python, and the offline search of PyPI built with it.

A researcher's machine may have no Python with numpy in it, or one that belongs
to a conda env the agent should not install into - and nothing could be
installed from a session. So the agent gets its own: a CPython that uv
downloads (python-build-standalone, no system libraries needed), a venv with
pip seeded, and python.packages from config/elm-pi.json. The launcher puts it
on PATH unless pi was started from a venv or a non-base conda env, and the
egress proxy lets PyPI through, so the agent can add packages to it in any
session. Everything is in agent/python - rm -rf takes the lot.

Re-runs keep the environment and whatever the agent installed into it; the
configured packages are installed again when the list, the Python version or
uv changes, upgraded by --update, and reinstalled by --force.

Built by default since 2026-11-14: in driven test sessions every task that
needed numpy, scipy, matplotlib or Jupyter (5 of 5) worked around its absence -
a pip-built .venv per project, and once `pip install --break-system-packages`
into Homebrew's Python. --no-python (or `pi setup --no-python`), recorded like
the other install options, leaves it out and removes agent/python.
"""

import json
import os
import shutil
import tempfile

from elmboot import console, installenv
from elmboot.tools import disk_usage

ENVIRONMENT = os.path.join("agent", "python", "env")
STAMP = os.path.join("agent", "python", ".elm-pi-packages")
HUGGING_FACE = "https://huggingface.co"


def _value(run, name, what):
    status, text = run.capture(run.python([run.path("scripts", "elm_config.py"), "--root",
                                           run.root, "value", name]))
    if status != 0:
        console.die("cannot read " + what)
    return text


def build(run):
    """Phase 3c."""
    root, env, options = run.root, run.env, run.options
    if not options.python:
        if os.path.isdir(run.path("agent", "python")):
            console.say("the agent's Python")
            shutil.rmtree(run.path("agent", "python"), ignore_errors=True)
            console.note("removed agent/python (--no-python): the agent uses the python3 on PATH")
        return
    console.say("the agent's Python (agent/python)")
    uv = run.path("agent", "bin", "uv")
    if not os.access(uv, os.X_OK):
        console.warn("uv is not in agent/bin (--no-tools, or ELM_PI_TOOLS without uv) - skipped")
        return
    # The account's uv settings are not this install's: no uv.toml, no index or
    # cache variables from the shell.
    for name in [name for name in env if name.startswith("UV_")]:
        del env[name]
    env["UV_NO_CONFIG"] = "1"
    env["UV_PYTHON_INSTALL_DIR"] = os.path.join(root, "agent", "python", "interpreters")
    env["UV_CACHE_DIR"] = os.path.join(root, "agent", "python", "cache")
    version = _value(run, "pythonVersion", "python.version")
    packages = _value(run, "pythonPackages", "python.packages")
    want = "%s %s %s" % (version, console.output([uv, "--version"], env=env), packages)
    python = run.path(ENVIRONMENT, "bin", "python")
    if not os.access(python, os.X_OK):
        console.note("CPython %s (uv-managed) and a venv in %s" % (version, ENVIRONMENT))
        if run.call([uv, "venv", "--quiet", "--seed", "--managed-python", "--python", version,
                     ENVIRONMENT]) != 0:
            console.die("could not create the agent's Python environment (re-run, or take it "
                        "back with --no-python)")
    have = None
    try:
        with open(run.path(STAMP), encoding="utf-8", errors="replace") as handle:
            have = handle.read().rstrip("\n")
    except OSError:
        pass
    if options.force or options.update or have != want:
        how = ["--reinstall"] if options.force else (["--upgrade"] if options.update else [])
        console.note("installing: " + packages)
        if run.call([uv, "pip", "install", "--quiet", "--python",
                     os.path.join(ENVIRONMENT, "bin", "python")] + how + packages.split()) == 0:
            with open(run.path(STAMP), "w", encoding="utf-8") as handle:
                handle.write(want + "\n")
        else:
            console.warn("some packages did not install; the environment works, and the next "
                         "run tries again")
    else:
        console.note("%s: Python %s, packages unchanged" % (ENVIRONMENT, version))
    _, says = run.capture([python, "--version"], merge=True)
    console.note("%s, %s in agent/python" % (says, disk_usage(run, run.path("agent", "python"))))


# --- an offline search of PyPI (--with-pypi-index) ---------------------------
# PyPI has no search API any more: `pip search` fails, and pypi.org/search is a
# JavaScript challenge. So "is there a package for X" needed the web, which a
# normal session does not have. This builds agent/pypi-index.db - name, summary,
# keywords and classifiers of every package, in an SQLite full-text index - from
# a published snapshot of PyPI's metadata (pypiIndex in config/elm-pi.json), and
# links `pypi-search` into agent/bin. The snapshot is pinned to a revision and
# each file checked against its published sha256; the ~1GB download is deleted
# once the index is built, and repeated only when the revision changes or with
# --force. Opt-in, and recorded like the --no-* flags; without it any index an
# earlier run built is removed.

REVISION_QUERY = ('import sqlite3, sys; print(sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", '
                  'uri=True).execute("SELECT value FROM meta WHERE key = ?", '
                  '("revision",)).fetchone()[0])')


def pypi_index(run):
    """Phase 3d."""
    database = os.path.join("agent", "pypi-index.db")
    link = run.path("agent", "bin", "pypi-search")
    if not run.options.pypi_index:
        if os.path.lexists(run.path(database)) or os.path.islink(link):
            for path in (run.path(database), link):
                if os.path.lexists(path):
                    os.remove(path)
            console.note("removed the offline PyPI index (this install is not --with-pypi-index)")
        return
    console.say("offline PyPI search (agent/pypi-index.db)")
    try:
        with open(run.path("config", "elm-pi.json"), encoding="utf-8") as handle:
            wanted = json.load(handle)["pypiIndex"]
        dataset, revision, folder = wanted["dataset"], wanted["revision"], wanted["folder"]
    except (OSError, ValueError, KeyError, TypeError):
        console.die("cannot read pypiIndex from config/elm-pi.json")
    # The build reads Parquet, which takes pyarrow: the agent's Python has it.
    python = os.path.join(ENVIRONMENT, "bin", "python")
    if not os.access(run.path(python), os.X_OK):
        console.warn("needs the agent's Python (it has pyarrow), which did not build - skipped")
        return
    # Read-only: a plain connect would create an empty file that then passes for an index.
    have = console.output([run.path(python), "-I", "-c", REVISION_QUERY, database],
                          cwd=run.root, env=run.env)
    if not run.options.force and have == revision:
        console.note("%s: %s at %s, unchanged" % (database, dataset, revision[:7]))
    else:
        _build_index(run, python, database, dataset, revision, folder, have)
    if os.path.isfile(run.path(database)) and os.path.getsize(run.path(database)) > 0:
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(run.path("scripts", "pypi-search"), link)
        console.note("agent/bin/pypi-search -> scripts/pypi-search")


def _build_index(run, python, database, dataset, revision, folder, have):
    scratch = run.temp(tempfile.mkdtemp(prefix=".pypi-download.", dir=run.path("agent")))
    data = os.path.join(scratch, "data")
    os.makedirs(data)
    curl = ["curl", "-q", "-fsSL"] + run.retry
    complete = True
    console.note("downloading %s at %s (~1GB, deleted after the build)" % (dataset, revision[:7]))
    tree = os.path.join(scratch, "tree.json")
    if run.call(curl + ["-o", tree, "%s/api/datasets/%s/tree/%s/%s"
                        % (HUGGING_FACE, dataset, revision, folder)]) == 0:
        with open(tree, encoding="utf-8") as handle:
            files = [(entry["lfs"]["oid"], entry["path"]) for entry in json.load(handle)
                     if entry["path"].endswith(".parquet")]
        for want, path in files:
            target = os.path.join(data, path.rsplit("/", 1)[-1])
            if run.call(curl + ["-o", target, "%s/datasets/%s/resolve/%s/%s"
                                % (HUGGING_FACE, dataset, revision, path)]) != 0:
                console.warn("could not download " + path)
                complete = False
                break
            if installenv.sha256_of(target) != want:
                console.die("checksum mismatch for " + path)
    else:
        console.warn("could not list the files of " + dataset)
        complete = False
    if complete and any(name.endswith(".parquet") for name in os.listdir(data)):
        if run.call([run.path(python), "-I", os.path.join("scripts", "pypi_index.py"), "build",
                     data, database, "--dataset", dataset, "--revision", revision]) != 0:
            console.warn("the index did not build; the next run tries again")
    else:
        console.warn("no index built this run%s; the next run tries again"
                     % (" (the existing one is kept)" if have else ""))
    shutil.rmtree(scratch, ignore_errors=True)
    run.forget(scratch)
