"""Four feature extensions, case by case: install-notes, skill-router, todo and view-outputs.

Each extension's own .ts module is run under the bundled node (type stripping)
against a stub ExtensionAPI that records the handlers and tools it registers;
the handlers are then driven with the events pi would send. One node process
per TestCase class runs every case of that class and prints the results as
one JSON object, and one test method is generated per case, so a failure names
the exact input.

- install-notes: every install command form it knows, with versions, extras,
  flags, chains and redirections; commands that are not installs; the note and
  the agent/installs.log line a successful install leaves.
- skill-router: real requests that must route to each skill and near-misses
  that must not; the routing message, its one-line rendering and the read gate
  in front of the first subagent/workflow call.
- todo: every action, invalid input, state rebuilt from the session, rendering
  and the /todos command. pi's packages are stubs here - only the extension's
  own logic is under test.
- view-outputs: which files a command wrote are noticed (extension, folder,
  age, size, named paths), what is attached and how, the converters for
  formats MuPDF cannot read, and the `view` tool's and `read`'s handling.
  Rendering uses the installed mupdf package, so those cases skip on a
  checkout that has not been bootstrapped.

Cases marked expectedFailure are real bugs, named in a comment beside each.
"""

import base64
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = ROOT / "templates/extensions"
SKILLS = ROOT / "templates/skills"


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def run_node(script, args, env, cwd, timeout=300):
    """Run a module script under node and return its JSON; skip when node cannot load .ts."""
    binary = node()
    if not binary:
        raise unittest.SkipTest("needs node")
    run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", script, *map(str, args)],
                         capture_output=True, text=True, env=env, cwd=cwd, timeout=timeout)
    if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
        raise unittest.SkipTest("this node cannot load TypeScript")
    if run.returncode != 0:
        raise AssertionError(f"node failed:\n{run.stderr[-3000:]}")
    return json.loads(run.stdout)


def slug(text):
    text = text.replace("σ", " sigma").replace("χ²", "chi2")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:90]


def generate(cls, cases, check):
    """One test method per case: test_<slug>, calling check(self, case, result)."""
    for name, case in cases.items():
        method = f"test_{slug(name)}"
        assert not hasattr(cls, method), f"duplicate case name: {name}"

        def test(self, name=name, case=case):
            check(self, case, self.results[name])

        test.__name__ = method
        test.__doc__ = name
        if case.get("bug"):
            test = unittest.expectedFailure(test)
        setattr(cls, method, test)


def fill(value, **names):
    """Replace {bin}, {agent}... placeholders in a nested expected value."""
    if isinstance(value, str):
        for key, sub in names.items():
            value = value.replace("{" + key + "}", str(sub))
        return value
    if isinstance(value, list):
        return [fill(v, **names) for v in value]
    if isinstance(value, dict):
        return {fill(k, **names): fill(v, **names) for k, v in value.items()}
    return value


def write_executable(path, script):
    path.write_text("#!/bin/sh\n" + script)
    path.chmod(0o755)


# --------------------------------------------------------------------------
# install-notes
# --------------------------------------------------------------------------

INSTALL_RUNNER = r"""
const [source, casesPath] = process.argv.slice(1);
const fs = await import("node:fs");
const { join } = await import("node:path");
const mod = await import(source);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const base = { ...process.env };
const out = {};
for (const [id, c] of Object.entries(cases)) {
  for (const key of Object.keys(process.env)) if (!(key in base)) delete process.env[key];
  Object.assign(process.env, base, c.env ?? {});
  if (c.kind === "describe") { out[id] = mod.describe(c.command, c.cwd ?? "/proj"); continue; }
  let handler;
  mod.default({ on: (event, h) => { if (event === "tool_result") handler = h; } });
  const returned = [];
  for (const event of c.events) returned.push((await handler(event, c.noCwd ? {} : { cwd: c.cwd ?? "/proj" })) ?? null);
  const log = join(process.env.PI_CODING_AGENT_DIR, "installs.log");
  out[id] = { returned, log: fs.existsSync(log) ? fs.readFileSync(log, "utf8") : null };
}
console.log(JSON.stringify(out));
"""

PIP = "the Python environment of {bin}/pip"
PIP3 = "the Python environment of {bin}/pip3"
BREW_WHERE = "Homebrew's prefix (`brew --prefix`), shared with everything else on this machine that uses Homebrew"
GLOBAL_WHERE = "{agent}/pixi/envs, with its commands in {agent}/pixi/bin on PATH"
EXEC_WHERE = "downloaded packages cached in {agent}/pixi/cache"


def pypi(what, where, undo):
    return {"what": f"{what} from PyPI", "where": where, "undo": undo}


def exec_(specs, where=EXEC_WHERE):
    return {"what": f"{specs} from conda-forge, run with pixi exec (nothing installed)", "where": where,
            "undo": "pixi clean cache"}


def image(name, tool="docker"):
    return {"what": f"the container image {name}", "where": f"{tool}'s image store", "undo": f"{tool} rmi {name}"}


def brew(pkgs):
    return {"what": f"{', '.join(pkgs)} (Homebrew)", "where": BREW_WHERE, "undo": f"brew uninstall {' '.join(pkgs)}"}


def pixi_add(pkgs, cwd="/proj"):
    return {"what": f"{', '.join(pkgs)} added to this project's pixi environment",
            "where": f"{cwd}/pixi.toml and {cwd}/.pixi", "undo": f"pixi remove {' '.join(pkgs)}"}


def pixi_global(pkgs, where=GLOBAL_WHERE):
    return {"what": f"{', '.join(pkgs)} from conda-forge (pixi global install)", "where": where,
            "undo": f"pixi global uninstall {' '.join(pkgs)}"}


# command -> what describe() must return. {bin} holds fake pip, pip3 and python3;
# python and python3.12 are not on PATH. cwd is /proj.
DESCRIBE = {
    # pip and its spellings
    "pip install numpy": [pypi("numpy", PIP, "pip uninstall numpy")],
    "pip3 install scipy": [pypi("scipy", PIP3, "pip uninstall scipy")],
    "python3 -m pip install requests": [pypi("requests", "the Python environment of {bin}/python3", "pip uninstall requests")],
    # Not on PATH: the bare name is all that can be said.
    "python3.12 -m pip install requests": [pypi("requests", "the Python environment of python3.12", "pip uninstall requests")],
    "uv pip install -p /opt/py/bin/python3 lmfit": [pypi("lmfit", "the Python environment of /opt/py/bin/python3", "pip uninstall lmfit")],
    # versions, extras, several packages, flags
    "pip install numpy==1.26.4": [pypi("numpy==1.26.4", PIP, "pip uninstall numpy==1.26.4")],
    'pip install "lmfit[emcee]>=1.2"': [pypi("lmfit[emcee]>=1.2", PIP, "pip uninstall lmfit[emcee]>=1.2")],
    "pip install 'numpy<2' 'scipy>=1.11'": [pypi("numpy<2, scipy>=1.11", PIP, "pip uninstall numpy<2 scipy>=1.11")],
    "pip install numpy scipy matplotlib": [pypi("numpy, scipy, matplotlib", PIP, "pip uninstall numpy scipy matplotlib")],
    "pip install -r requirements.txt": [pypi("the packages in requirements.txt", PIP, "pip uninstall <package>")],
    "pip install --requirement reqs/dev.txt pytest": [pypi("pytest, the packages in reqs/dev.txt", PIP, "pip uninstall pytest")],
    "pip install -i https://test.pypi.org/simple/ mypkg": [pypi("mypkg", PIP, "pip uninstall mypkg")],
    "pip install --index-url=https://mirror/simple mypkg": [pypi("mypkg", PIP, "pip uninstall mypkg")],
    # --target puts the files in a plain folder, which pip uninstall does not search.
    "pip install -t vendor requests": [pypi("requests", "the folder vendor/ (--target), not a Python environment",
                                            "delete requests from vendor/ (pip uninstall does not look there)")],
    "pip install --prefix /opt/tools numpy": [pypi("numpy", "the prefix /opt/tools/ (--prefix), outside the Python environment",
                                                   "delete numpy from /opt/tools/ (pip uninstall does not look there)")],
    "pip install --root /stage numpy": [pypi("numpy", "under /stage/ (--root), outside the Python environment",
                                             "delete numpy from /stage/ (pip uninstall does not look there)")],
    "pip install --user numpy": [pypi("numpy", "your user site-packages (`python3 -m site --user-site`)", "pip uninstall numpy")],
    "pip install": [pypi("Python packages", PIP, "pip uninstall <package>")],
    # prefixes the shell runs the command under
    "sudo pip3 install pyyaml": [pypi("pyyaml", PIP3, "pip uninstall pyyaml")],
    "PIP_NO_INPUT=1 PIP_QUIET=1 pip install pyyaml": [pypi("pyyaml", PIP, "pip uninstall pyyaml")],
    # chains, pipes and redirections
    "cd analysis && pip install numpy": [pypi("numpy", PIP, "pip uninstall numpy")],
    "pip install numpy; pip3 install scipy": [pypi("numpy", PIP, "pip uninstall numpy"), pypi("scipy", PIP3, "pip uninstall scipy")],
    "pip install numpy || pip3 install numpy": [pypi("numpy", PIP, "pip uninstall numpy"), pypi("numpy", PIP3, "pip uninstall numpy")],
    "pip install numpy &> install.log": [pypi("numpy", PIP, "pip uninstall numpy")],
    # pixi exec runs a package without installing it
    "pixi exec -s imagemagick magick a.heic a.png": [exec_("imagemagick")],
    "pixi exec --spec gdal --spec proj gdalinfo x.tif": [exec_("gdal, proj")],
    "pixi exec ruff check .": [exec_("a package")],
    # pixi global install
    "pixi global install -c conda-forge -c bioconda samtools": [pixi_global(["samtools"])],
    "pixi global install gnuplot ffmpeg": [pixi_global(["gnuplot", "ffmpeg"])],
    "pixi global install --expose gs=gs ghostscript": [pixi_global(["ghostscript"])],
    # pixi add, into the project in cwd
    "pixi add numpy scipy": [pixi_add(["numpy", "scipy"])],
    "pixi add -p linux-64 'cuda>=12'": [pixi_add(["cuda>=12"])],
    "pixi add --pypi requests": [pixi_add(["requests"])],
    # container images
    "docker pull python:3.12-slim": [image("python:3.12-slim")],
    "docker image pull ghcr.io/org/tool:v1": [image("ghcr.io/org/tool:v1")],
    "podman pull docker.io/library/alpine:3.20": [image("docker.io/library/alpine:3.20", "podman")],
    "docker pull --platform linux/amd64 rootproject/root:6.32.02-ubuntu24.04": [image("rootproject/root:6.32.02-ubuntu24.04")],
    # Homebrew
    "brew install pandoc gnuplot": [brew(["pandoc", "gnuplot"])],
    "brew reinstall ffmpeg": [brew(["ffmpeg"])],
    "brew install --cask mactex-no-gui": [brew(["mactex-no-gui"])],
    "/opt/homebrew/bin/brew install wget": [brew(["wget"])],
    # not installs
    "pip list": [],
    "pip download numpy -d wheels": [],
    "pip uninstall -y numpy": [],
    "pixi run python fit.py": [],
    "docker run --rm --network=none alpine true": [],
    "brew uninstall pandoc": [],
    "echo pip install numpy": [],
    "python3 -m venv .venv": [],
}

# Cases whose expected value checks one field.
DESCRIBE_SPECIAL = {
    # The interpreter named by path is that one, not the first python on PATH.
    "venv python named by path": {
        "command": ".venv/bin/python -m pip install numpy",
        "check": lambda t, r: t.assertIn(".venv/bin/python", r[0]["where"])},
    # VAR=x after `env` is skipped like the env itself.
    "env with an assignment before pip": {
        "command": "env PIP_INDEX_URL=https://mirror/simple pip install numpy",
        "check": lambda t, r: t.assertEqual(["numpy from PyPI"], [i["what"] for i in r])},
    # --prefix takes a value, so its directory is not a package.
    "pip prefix value is not a package": {
        "command": "pip install --prefix /opt/tools numpy",
        "check": lambda t, r: t.assertEqual(["numpy from PyPI"], [i["what"] for i in r])},
    # So does -f/--find-links.
    "pip find links value is not a package": {
        "command": "pip install -f ./wheels mypkg",
        "check": lambda t, r: t.assertEqual("mypkg from PyPI", r[0]["what"])},
    # With -t the packages go to that folder, not into the Python environment.
    "pip target says where the files went": {
        "command": "pip install -t vendor requests",
        "check": lambda t, r: t.assertIn("vendor", r[0]["where"])},
    # A subshell's closing parenthesis is not part of the last package name.
    "install inside a subshell": {
        "command": "(cd sub && pip install numpy)",
        "check": lambda t, r: t.assertEqual("pip uninstall numpy", r[0]["undo"])},
    # `uv add` installs into the project's environment.
    "uv add": {
        "command": "uv add numpy",
        "check": lambda t, r: t.assertEqual(1, len(r))},
    # `pixi add --manifest-path` changes that manifest, not ./pixi.toml.
    "pixi add manifest path": {
        "command": "pixi add --manifest-path tools/pixi.toml ruff",
        "check": lambda t, r: t.assertIn("tools/pixi.toml", r[0]["where"])},
    # Without --python or VIRTUAL_ENV the where is not wrapped in "the Python environment of".
    "uv pip install without an environment says which": {
        "command": "uv pip install polars",
        "check": lambda t, r: t.assertEqual("the environment uv chose", r[0]["where"])},
    "uv pip install from a requirements file": {
        "command": "uv pip install -r requirements.txt",
        "check": lambda t, r: t.assertEqual([("the packages in requirements.txt from PyPI", "pip uninstall <package>")],
                                            [(i["what"], i["undo"]) for i in r])},
    "pip then uv pip on separate lines": {
        "command": "pip install numpy\nuv pip install scipy",
        "check": lambda t, r: t.assertEqual(["pip uninstall numpy", "pip uninstall scipy"], [i["undo"] for i in r])},
    "uv pip install follows VIRTUAL_ENV": {
        "command": "uv pip install polars", "env": {"VIRTUAL_ENV": "/venvs/a"},
        "check": lambda t, r: t.assertEqual("the Python environment of /venvs/a/bin/python", r[0]["where"])},
    "pip not on PATH is named by its bare name": {
        "command": "pip install numpy", "env": {"PATH": "/nonexistent"},
        "check": lambda t, r: t.assertEqual("the Python environment of pip", r[0]["where"])},
    "pixi exec cache follows PIXI_HOME": {
        "command": "pixi exec --spec ghostscript gs -v", "env": {"PIXI_HOME": "/ph"},
        "check": lambda t, r: t.assertEqual("downloaded packages cached in /ph/cache", r[0]["where"])},
    "pixi exec cache follows PIXI_CACHE_DIR": {
        "command": "pixi exec --spec ghostscript gs -v", "env": {"PIXI_HOME": "/ph", "PIXI_CACHE_DIR": "/pc"},
        "check": lambda t, r: t.assertEqual("downloaded packages cached in /pc", r[0]["where"])},
    "pixi global follows PIXI_HOME": {
        "command": "pixi global install gdal", "env": {"PIXI_HOME": "/ph"},
        "check": lambda t, r: t.assertEqual("/ph/envs, with its commands in /ph/bin on PATH", r[0]["where"])},
    "pixi add uses the given cwd": {
        "command": "pixi add hdf5", "cwd": "/work/thesis",
        "check": lambda t, r: t.assertEqual("/work/thesis/pixi.toml and /work/thesis/.pixi", r[0]["where"])},
}

NOTE_HEAD = ("[install-notes] This command installed software. Tell the user in your report - what, where it lives, "
             "and how to remove it (also logged in {agent}/installs.log):\n")


def bash(command, error=False, content=None, tool="bash"):
    return {"toolName": tool, "isError": error, "input": {"command": command} if command is not None else {},
            "content": content if content is not None else [{"type": "text", "text": "done"}]}


STAMP = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"

HANDLER = {
    "note follows the output with what where and remove": {
        "events": [bash("pip install numpy")],
        "check": lambda t, r, n: t.assertEqual(
            [{"type": "text", "text": "done"},
             {"type": "text", "text": n(NOTE_HEAD + "- numpy from PyPI\n  where: " + PIP + "\n  remove: pip uninstall numpy")}],
            r["returned"][0]["content"])},
    "a failed install leaves no note and no log": {
        "events": [bash("pip install numpy", error=True)],
        "check": lambda t, r, n: t.assertEqual(([None], None), (r["returned"], r["log"]))},
    "another tool naming an install is ignored": {
        "events": [bash("pip install numpy", tool="python")],
        "check": lambda t, r, n: t.assertEqual(([None], None), (r["returned"], r["log"]))},
    "a command that installs nothing is left alone": {
        "events": [bash("pip list")],
        "check": lambda t, r, n: t.assertEqual(([None], None), (r["returned"], r["log"]))},
    "an event without a command string is left alone": {
        "events": [bash(None)],
        "check": lambda t, r, n: t.assertEqual([None], r["returned"])},
    "log line is stamp cwd what where remove": {
        "events": [bash("brew install pandoc")], "cwd": "/work/paper",
        "check": lambda t, r, n: t.assertRegex(
            r["log"], "^" + STAMP + re.escape("\t/work/paper\tpandoc (Homebrew)\t" + BREW_WHERE
                                              + "\tremove: brew uninstall pandoc\n") + "$")},
    "two installs in one command give two entries": {
        "events": [bash("pip install numpy && docker pull alpine")],
        "check": lambda t, r, n: (
            t.assertTrue(r["returned"][0]["content"][-1]["text"].endswith(
                "remove: pip uninstall numpy\n- the container image alpine\n  where: docker's image store\n  remove: docker rmi alpine")),
            t.assertEqual(2, r["log"].count("\n")))},
    "the log is appended to not overwritten": {
        "events": [bash("pip install numpy"), bash("brew install wget")],
        "check": lambda t, r, n: t.assertEqual(
            ["remove: pip uninstall numpy", "remove: brew uninstall wget"],
            [line.split("\t")[-1] for line in r["log"].splitlines()])},
    "an unwritable log still gives the note": {
        "events": [bash("brew install wget")], "missingAgent": True,
        "check": lambda t, r, n: (t.assertIsNone(r["log"]),
                                  t.assertIn("brew uninstall wget", r["returned"][0]["content"][-1]["text"]))},
    "earlier content parts are kept in order": {
        "events": [bash("docker pull alpine", content=[{"type": "text", "text": "a"},
                                                       {"type": "image", "data": "AA==", "mimeType": "image/png"}])],
        "check": lambda t, r, n: (
            t.assertEqual(["text", "image", "text"], [c["type"] for c in r["returned"][0]["content"]]),
            t.assertEqual("a", r["returned"][0]["content"][0]["text"]),
            t.assertTrue(r["returned"][0]["content"][2]["text"].startswith("[install-notes]")))},
    "without a cwd in the context the process cwd is used": {
        "events": [bash("pixi add hdf5")], "noCwd": True,
        "check": lambda t, r, n: t.assertIn(n("where: {tmp}/pixi.toml and {tmp}/.pixi"),
                                            r["returned"][0]["content"][-1]["text"])},
}


class InstallNotesTests(unittest.TestCase):
    """install-notes.ts: describe() per command, and the tool_result handler."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        cls.bin = cls.tmp / "bin"
        cls.bin.mkdir()
        for tool in ("pip", "pip3", "python3"):
            write_executable(cls.bin / tool, "exit 0\n")
        cls.agent = cls.tmp / "agent"
        cls.agent.mkdir()
        cases = {}
        for command in DESCRIBE:
            cases[command] = {"kind": "describe", "command": command}
        for name, case in DESCRIBE_SPECIAL.items():
            cases[name] = {"kind": "describe", "command": case["command"], "cwd": case.get("cwd"),
                           "env": case.get("env", {})}
        for i, (name, case) in enumerate(HANDLER.items()):
            agent = cls.tmp / ("missing" if case.get("missingAgent") else f"agent{i}")
            if not case.get("missingAgent"):
                agent.mkdir()
            cases[name] = {"kind": "handler", "events": case["events"], "cwd": case.get("cwd"),
                           "noCwd": case.get("noCwd", False), "env": {"PI_CODING_AGENT_DIR": str(agent)},
                           "agent": str(agent)}
        cls.cases = cases
        (cls.tmp / "cases.json").write_text(json.dumps(cases))
        env = {"PATH": str(cls.bin), "HOME": str(cls.tmp), "PI_CODING_AGENT_DIR": str(cls.agent)}
        try:
            cls.results = run_node(INSTALL_RUNNER, [EXTENSIONS / "install-notes.ts", cls.tmp / "cases.json"],
                                   env, cls.tmp)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def names(self, value, name):
        return fill(value, bin=self.bin, agent=self.cases[name].get("agent", self.agent), tmp=self.tmp)


def _check_describe(self, case, result):
    self.assertEqual(self.names(case["expected"], case["name"]), result)


def _check_special(self, case, result):
    case["check"](self, result)


def _check_handler(self, case, result):
    case["check"](self, result, lambda text: self.names(text, case["name"]))


generate(InstallNotesTests, {c: {"name": c, "expected": e} for c, e in DESCRIBE.items()}, _check_describe)
generate(InstallNotesTests, {n: {**c, "name": n} for n, c in DESCRIBE_SPECIAL.items()}, _check_special)
generate(InstallNotesTests, {n: {**c, "name": n} for n, c in HANDLER.items()}, _check_handler)


# --------------------------------------------------------------------------
# skill-router
# --------------------------------------------------------------------------

ROUTER_RUNNER = r"""
const [source, casesPath, agent, partial] = process.argv.slice(1);
const fs = await import("node:fs");
const mod = await import(source);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const theme = { fg: (c, s) => `<${c}>${s}</>`, bold: (s) => s };
const out = {};
for (const [id, c] of Object.entries(cases)) {
  if (c.kind === "routes") { out[id] = mod.routesFor(c.prompt); continue; }
  if (c.kind === "request") { out[id] = mod.requestText(c.prompt); continue; }
  process.env.PI_CODING_AGENT_DIR = c.partial ? partial : agent;
  const handlers = {}; const renderers = {};
  mod.default({ on: (e, h) => { handlers[e] = h; }, registerMessageRenderer: (t, f) => { renderers[t] = f; } });
  const ctx = { sessionManager: { buildContextEntries: () => c.context ?? [], getBranch: () => c.branch ?? [] } };
  const steps = [];
  for (const s of c.steps) {
    if (s.op === "start") steps.push((await handlers.before_agent_start({ type: "before_agent_start", prompt: s.prompt, messageType: s.messageType ?? "user" }, ctx)) ?? null);
    else if (s.op === "call") steps.push((await handlers.tool_call({ type: "tool_call", toolCallId: "t", toolName: s.tool, input: s.input }, ctx)) ?? null);
    else if (s.op === "render") steps.push(renderers["skill-routing"]({ details: s.details }, { expanded: !!s.expanded, outputPad: s.pad ?? 0 }, theme).render(s.width ?? 200));
  }
  out[id] = steps;
}
console.log(JSON.stringify(out));
"""

# request -> the skills routesFor() returns, in order. Prompts already in
# tests/test_skill_router.py are not repeated.
ROUTES = {
    # data-fitting
    "Fit an exponential to these counts and quote the decay constant": ["data-fitting"],
    "what's the best-fit value and its error": ["data-fitting"],
    "use iminuit to minimise the likelihood": ["data-fitting"],
    "half-lives of the isotopes": ["data-fitting"],
    "Fit The Data": ["data-fitting"],
    "fit, data.": ["data-fitting"],
    "the figure fits on the page": [],
    "call fit (data) twice": [],
    "calibrate the touch screen": [],
    # statistics-and-significance
    "is a 3 sigma excess enough to claim evidence": ["statistics-and-significance"],
    "what upper limit at 95% CL does that give": ["statistics-and-significance"],
    "improve the selection efficiency of the cut": ["statistics-and-significance"],
    "the cache is significantly faster now": [],
    "the efficiency of the algorithm": [],
    # uncertainty-propagation
    "what's the uncertainty on the mean": ["uncertainty-propagation"],
    "take the weighted average of the three measurements": ["uncertainty-propagation"],
    "draw error bars on the plot": ["uncertainty-propagation", "scientific-python"],
    "the error handling is uncertain": [],
    # histogram-analysis
    "choose the binning for the invariant mass": ["histogram-analysis"],
    "open the ROOT file with uproot and read the TTree": ["histogram-analysis"],
    "write a ROOT macro to fill the tree": ["scientific-cpp"],
    "the root macro folder for the build is missing": [],
    "show the cut flow for the event selection": ["histogram-analysis"],
    "bin the data by date in the dashboard": [],
    # derivation-checks
    "check the derivation of the dispersion relation": ["derivation-checks"],
    "is there a closed-form solution": ["derivation-checks"],
    "prove that the commutator vanishes": ["derivation-checks"],
    "derive from the base class": [],
    # numerical-methods
    "solve this stiff ODE system": ["numerical-methods"],
    "use Runge-Kutta for the pendulum": ["numerical-methods"],
    "estimate pi with monte carlo": ["numerical-methods"],
    "simulate a user clicking the button": [],
    "integrate the stripe payment API": [],
    # physical-constants
    "what is the Boltzmann constant in eV/K": ["physical-constants"],
    "look up the mass of the muon in the PDG": ["physical-constants"],
    "what's the branching ratio of the Higgs to two photons": ["physical-constants"],
    "make the timeout a constant": [],
    "the speed of the build": [],
    # physics-documents
    "write the lab report for the pendulum experiment": ["physics-documents"],
    "draft the thesis introduction": ["physics-documents"],
    "convert my notes to LaTeX with siunitx": ["physics-documents"],
    "the report button is broken": [],
    # scientific-cpp
    "compile the C++ code with -O2": ["scientific-cpp"],
    "set up cmake for the project": ["scientific-cpp"],
    "compile with g++ and clang": ["scientific-cpp"],
    # scientific-python
    "load the csv with pandas": ["scientific-python"],
    "make a scatter plot of x against y": ["scientific-python"],
    # installing-software
    "brew install gnuplot": ["installing-software"],
    "apt-get install libhdf5-dev": ["installing-software"],
    "update the installer UI": [],
    # containers
    "run it in a docker container": ["containers"],
    "xelatex fails on the unicode": ["containers"],
    # several at once, in table order
    "compile the thesis with latexmk": ["physics-documents", "containers"],
    "zsh: command not found: pdflatex": ["installing-software", "containers"],
    "No module named 'scipy'": ["scientific-python", "installing-software"],
    "Fit the histogram and quote the chi2": ["data-fitting", "histogram-analysis"],
    "PLOT THE HISTOGRAM": ["histogram-analysis", "scientific-python"],
    "Fit the Gaussian; give the uncertainty on the mean, then plot it in matplotlib":
        ["data-fitting", "uncertainty-propagation", "scientific-python"],
    # Non-ASCII symbols: word boundaries around them are Unicode-aware.
    "a 5σ discovery": ["statistics-and-significance"],
    "the χ² of the fit": ["data-fitting"],
    "what's the p value of the excess": ["statistics-and-significance"],
    "what are the masses of the quarks": ["physical-constants"],
    # ROOT the framework is matched in its own casing only.
    "the root file system is full": [],
    # "apt" the English word, and "upper limit" without statistics around it.
    "suggest an apt name for this function": [],
    "add an upper limit to the retry count": [],
}

REQUESTS = {
    "a skill block is dropped": ('<skill name="x" location="/s/SKILL.md">\nbody\n</skill>\n\nplot it', "plot it"),
    "read and write path lines are dropped": ("[Read from: /a.md]\nfit the data\n[Write to: /b.md]", "fit the data"),
    "a progress footer is dropped": ("fit the data\n---\nCreate and maintain progress at: /p.md\nmore", "fit the data"),
    "an update progress footer is dropped": ("fit the data\n---\nUpdate progress at: /p.md", "fit the data"),
    "any other rule is kept": ("fit the data\n---\nnotes below", "fit the data\n---\nnotes below"),
    "task is stripped only at the start": ("My Task: plot it", "My Task: plot it"),
}

ALL_SIX = "Fit the histogram data, propagate the uncertainty, give the p-value, derive the formula, plot in python"
ONE_HEAD = ("# Skills for this request\n\nThe request above matches this skill, included here in full: data-fitting. "
            "Apply it to the parts of the work it covers; where the request is not about that, ignore it.\n\n"
            "## Skill: data-fitting\n\n")
TWO_HEAD = ("# Skills for this request\n\nThe request above matches these skills, included here in full: "
            "data-fitting and histogram-analysis. Apply them to the parts of the work they cover; where the request "
            "is not about that, ignore them.\n\n## Skill: data-fitting\n\n")


def read_call(path):
    return {"type": "message", "message": {"role": "assistant", "content": [
        {"type": "toolCall", "name": "read", "arguments": {"path": path}}]}}


def routed(name):
    return {"type": "custom_message", "customType": "skill-routing", "details": {"inlined": [name], "named": []}}


def gate(skill, tool):
    return {"block": True, "reason": f"Read the {skill} skill before the first {tool} call of this session: "
                                     f"read {{agent}}/skills/{skill}/SKILL.md, then make this call again following it."}


def details(result):
    return result and result["message"]["details"]


SESSIONS = {
    "one match is inlined with an apply where relevant preamble": {
        "steps": [{"op": "start", "prompt": "fit this decay curve"}],
        "check": lambda t, r, a: (t.assertTrue(r[0]["message"]["content"].startswith(ONE_HEAD)),
                                  t.assertEqual(("skill-routing", True), (r[0]["message"]["customType"], r[0]["message"]["display"])))},
    "the skill text goes in without its frontmatter": {
        "steps": [{"op": "start", "prompt": "fit this decay curve"}],
        "check": lambda t, r, a: (t.assertTrue(r[0]["message"]["content"].endswith(
            re.sub(r"^---\n[\s\S]*?\n---\n", "", (SKILLS / "data-fitting/SKILL.md").read_text()).strip())),
            t.assertNotIn("\nname: data-fitting\n", r[0]["message"]["content"]))},
    "two matches are both inlined": {
        "steps": [{"op": "start", "prompt": "Fit the histogram and quote the chi2"}],
        "check": lambda t, r, a: (t.assertTrue(r[0]["message"]["content"].startswith(TWO_HEAD)),
                                  t.assertEqual({"inlined": ["data-fitting", "histogram-analysis"], "named": []}, details(r[0])))},
    "beyond two matches are named up to four": {
        "steps": [{"op": "start", "prompt": ALL_SIX}],
        "check": lambda t, r, a: t.assertEqual(
            {"inlined": ["data-fitting", "statistics-and-significance"],
             "named": ["uncertainty-propagation", "histogram-analysis"]}, details(r[0]))},
    "named skills are listed with their paths": {
        "steps": [{"op": "start", "prompt": ALL_SIX}],
        "check": lambda t, r, a: t.assertIn(
            fill("\n\nAlso possibly relevant - read with `read` before work that they cover:\n"
                 "- uncertainty-propagation: {agent}/skills/uncertainty-propagation/SKILL.md\n"
                 "- histogram-analysis: {agent}/skills/histogram-analysis/SKILL.md\n\n## Skill: data-fitting\n", agent=a),
            r[0]["message"]["content"])},
    "a run not started by the user adds nothing": {
        "steps": [{"op": "start", "prompt": "fit this decay curve", "messageType": "custom"}],
        "check": lambda t, r, a: t.assertEqual([None], r)},
    "a request matching nothing adds nothing": {
        "steps": [{"op": "start", "prompt": "rename the helper"}],
        "check": lambda t, r, a: t.assertEqual([None], r)},
    "a skill routed earlier in the session is not added again": {
        "context": [routed("data-fitting")],
        "steps": [{"op": "start", "prompt": "Fit the histogram and quote the chi2"}],
        "check": lambda t, r, a: t.assertEqual({"inlined": ["histogram-analysis"], "named": []}, details(r[0]))},
    "a skill only named earlier is inlined now": {
        "context": [{"type": "custom_message", "customType": "skill-routing",
                     "details": {"inlined": [], "named": ["data-fitting"]}}],
        "steps": [{"op": "start", "prompt": "fit this decay curve"}],
        "check": lambda t, r, a: t.assertEqual({"inlined": ["data-fitting"], "named": []}, details(r[0]))},
    "a skill the model read is not added": {
        "context": [read_call("/x/skills/data-fitting/SKILL.md")],
        "steps": [{"op": "start", "prompt": "fit this decay curve"}],
        "check": lambda t, r, a: t.assertEqual([None], r)},
    "a skill expanded from a skill command is not added": {
        "context": [{"type": "message", "message": {"role": "user", "content": '<skill name="data-fitting" location="/x">b</skill>'}}],
        "steps": [{"op": "start", "prompt": "fit this decay curve"}],
        "check": lambda t, r, a: t.assertEqual([None], r)},
    "a skill missing from agent skills is not routed": {
        "partial": True,
        "steps": [{"op": "start", "prompt": "Fit the histogram and quote the chi2"}],
        "check": lambda t, r, a: t.assertEqual({"inlined": ["histogram-analysis"], "named": []}, details(r[0]))},
    # The renderer: one dim line, paths when expanded, truncated to the width.
    "collapsed rendering is one dim skills line": {
        "steps": [{"op": "render", "pad": 2, "details": {"inlined": ["data-fitting", "histogram-analysis"],
                                                         "named": ["scientific-python"]}}],
        "check": lambda t, r, a: t.assertEqual(
            ["  <dim>skills: data-fitting, histogram-analysis (also named: scientific-python)</>"], r[0])},
    "expanded rendering adds each skill's path": {
        "steps": [{"op": "render", "expanded": True, "details": {"inlined": ["containers"], "named": ["physics-documents"]}}],
        "check": lambda t, r, a: t.assertEqual(
            ["<dim>skills: containers (also named: physics-documents)</>",
             fill("<dim>  {agent}/skills/containers/SKILL.md</>", agent=a),
             fill("<dim>  {agent}/skills/physics-documents/SKILL.md</>", agent=a)], r[0])},
    "a narrow terminal truncates with an ellipsis": {
        "steps": [{"op": "render", "pad": 2, "width": 20, "details": {"inlined": ["data-fitting"], "named": []}}],
        "check": lambda t, r, a: t.assertEqual(["  <dim>skills: data-fitt…</>"], r[0])},
    # The read gate before the first subagent or workflow call.
    "the first workflow call waits for its skill": {
        "steps": [{"op": "call", "tool": "workflow", "input": {"script": "x"}}],
        "check": lambda t, r, a: t.assertEqual([fill(gate("elm-dynamic-workflows", "workflow"), agent=a)], r)},
    "a subagent workflow waits for the workflows skill": {
        "steps": [{"op": "call", "tool": "subagent", "input": {"workflow": "parallel"}}],
        "check": lambda t, r, a: t.assertEqual([fill(gate("elm-subagent-workflows", "subagent"), agent=a)], r)},
    "a delegation by agent waits for the delegation skill": {
        "steps": [{"op": "call", "tool": "subagent", "input": {"agent": "qwen", "task": "x"}}],
        "check": lambda t, r, a: t.assertEqual([fill(gate("elm-delegation", "subagent"), agent=a)], r)},
    "a subagent status call needs nothing": {
        "steps": [{"op": "call", "tool": "subagent", "input": {"action": "status"}}],
        "check": lambda t, r, a: t.assertEqual([None], r)},
    "other tools are not gated": {
        "steps": [{"op": "call", "tool": "bash", "input": {"command": "ls"}}],
        "check": lambda t, r, a: t.assertEqual([None], r)},
    "reading the skill opens the gate": {
        "steps": [{"op": "call", "tool": "workflow", "input": {}},
                  {"op": "call", "tool": "read", "input": {"path": "/any/elm-dynamic-workflows/SKILL.md"}},
                  {"op": "call", "tool": "workflow", "input": {}}],
        "check": lambda t, r, a: t.assertEqual([True, None, None], [s and s["block"] for s in r])},
    "a windows style path counts as reading the skill": {
        "steps": [{"op": "call", "tool": "read", "input": {"path": "C:\\pi\\skills\\elm-delegation\\SKILL.md"}},
                  {"op": "call", "tool": "subagent", "input": {"agent": "qwen"}}],
        "check": lambda t, r, a: t.assertEqual([None, None], r)},
    "reading another skill does not open the gate": {
        "steps": [{"op": "call", "tool": "read", "input": {"path": "/s/elm-delegation/SKILL.md"}},
                  {"op": "call", "tool": "workflow", "input": {}}],
        "check": lambda t, r, a: t.assertTrue(r[1]["block"])},
    "a read earlier in the branch opens the gate": {
        "branch": [read_call("/s/elm-delegation/SKILL.md")],
        "steps": [{"op": "call", "tool": "subagent", "input": {"agent": "qwen"}}],
        "check": lambda t, r, a: t.assertEqual([None], r)},
    "a routed copy earlier in the branch opens the gate": {
        "branch": [routed("elm-dynamic-workflows")],
        "steps": [{"op": "call", "tool": "workflow", "input": {}}],
        "check": lambda t, r, a: t.assertEqual([None], r)},
    "a gate skill that is not installed blocks nothing": {
        "partial": True,
        "steps": [{"op": "call", "tool": "workflow", "input": {}}],
        "check": lambda t, r, a: t.assertEqual([None], r)},
}


class SkillRouterTests(unittest.TestCase):
    """skill-router.ts: routesFor, requestText, and its two handlers and renderer."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        cls.agent = cls.tmp / "agent"
        (cls.agent / "skills").mkdir(parents=True)
        for skill in SKILLS.iterdir():
            (cls.agent / "skills" / skill.name).symlink_to(skill)
        # An install with only one routable skill and none of the gate skills.
        cls.partial = cls.tmp / "partial"
        (cls.partial / "skills").mkdir(parents=True)
        (cls.partial / "skills/histogram-analysis").symlink_to(SKILLS / "histogram-analysis")
        cases = {}
        for prompt in ROUTES:
            cases[prompt] = {"kind": "routes", "prompt": prompt}
        for name, (prompt, _) in REQUESTS.items():
            cases[name] = {"kind": "request", "prompt": prompt}
        for name, case in SESSIONS.items():
            cases[name] = {"kind": "session", **{k: v for k, v in case.items() if k != "check"}}
        (cls.tmp / "cases.json").write_text(json.dumps(cases))
        env = {"PATH": "/usr/bin:/bin", "HOME": str(cls.tmp)}
        try:
            cls.results = run_node(ROUTER_RUNNER, [EXTENSIONS / "skill-router.ts", cls.tmp / "cases.json",
                                                   cls.agent, cls.partial], env, cls.tmp)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


def _check_route(self, case, result):
    self.assertEqual(case["expected"], result, case["name"])


def _check_request(self, case, result):
    self.assertEqual(case["expected"], result)


def _check_session(self, case, result):
    case["check"](self, result, self.partial if case.get("partial") else self.agent)


generate(SkillRouterTests, {p: {"name": p, "expected": e} for p, e in ROUTES.items()}, _check_route)
generate(SkillRouterTests, {n: {"expected": e} for n, (_, e) in REQUESTS.items()}, _check_request)
generate(SkillRouterTests, SESSIONS, _check_session)


# --------------------------------------------------------------------------
# todo
# --------------------------------------------------------------------------

# pi supplies these packages to an extension; only their shape is needed here.
TODO_STUBS = {
    "@earendil-works/pi-ai": "export const StringEnum = (values, options) => ({ enum: values, ...options });",
    "@earendil-works/pi-tui": (
        "export class Text { constructor(text, x, y) { this.text = text; } }\n"
        "export const matchesKey = (data, key) => (key === 'escape' && data === '\\x1b') || (key === 'ctrl+c' && data === '\\x03');\n"
        "export const truncateToWidth = (s, width) => s;\n"),
    "typebox": "const f = (...a) => ({ a }); export const Type = { Object: f, String: f, Optional: f, Number: f, Boolean: f };",
}

TODO_RUNNER = r"""
const [source, casesPath] = process.argv.slice(1);
const fs = await import("node:fs");
const mod = await import(source);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const theme = { fg: (c, s) => `<${c}>${s}</>`, bold: (s) => `[b]${s}[/b]` };
const snap = (x) => (x === undefined ? null : JSON.parse(JSON.stringify(x)));
const out = {};
for (const [id, c] of Object.entries(cases)) {
  const handlers = {}; let tool; const commands = {};
  mod.default({ on: (e, h) => { handlers[e] = h; }, registerTool: (t) => { tool = t; }, registerCommand: (n, d) => { commands[n] = d; } });
  const entries = c.entries ?? [];
  const ctx = { sessionManager: { getBranch: () => entries } };
  const now = []; const kept = [];
  for (const s of c.steps) {
    let r = null;
    if (s.op === "exec") { r = await tool.execute("id", s.params, undefined, undefined, ctx); kept.push(r); }
    else if (s.op === "start" || s.op === "tree") await handlers[s.op === "start" ? "session_start" : "session_tree"]({}, ctx);
    else if (s.op === "call") r = tool.renderCall(s.args, theme, {}).text;
    else if (s.op === "result") r = tool.renderResult(s.result, { expanded: !!s.expanded }, theme, {}).text;
    else if (s.op === "command") {
      const seen = { notes: [], lines: null, closed: false, same: null };
      const ui = {
        notify: (m, level) => seen.notes.push([m, level]),
        custom: async (factory) => {
          const component = factory({}, theme, {}, () => { seen.closed = true; });
          seen.lines = component.render(60);
          seen.same = component.render(60) === seen.lines;
          for (const key of s.keys ?? []) component.handleInput(key);
        },
      };
      await commands.todos.handler("", { mode: s.mode, ui });
      r = seen;
    }
    now.push(snap(r));
  }
  out[id] = { now, later: snap(kept), entries: snap(entries) };
}
console.log(JSON.stringify(out));
"""


def ex(action, **params):
    return {"op": "exec", "params": {"action": action, **params}}


def text_of(step):
    return step["content"][0]["text"]


def todo_entry(todos, next_id, tool="todo"):
    return {"type": "message", "message": {"role": "toolResult", "toolName": tool,
                                           "details": {"action": "add", "todos": todos, "nextId": next_id}}}


A1 = {"id": 1, "text": "a", "done": False}
B2 = {"id": 2, "text": "b", "done": False}

TODO = {
    "list of nothing says no todos": {
        "steps": [ex("list")],
        "check": lambda t, r: t.assertEqual(
            ({"type": "text", "text": "No todos"}, {"action": "list", "todos": [], "nextId": 1}),
            (r["now"][0]["content"][0], r["now"][0]["details"]))},
    "add returns the new todo and its id": {
        "steps": [ex("add", text="buy milk")],
        "check": lambda t, r: t.assertEqual(
            ("Added todo #1: buy milk", {"action": "add", "todos": [{"id": 1, "text": "buy milk", "done": False}], "nextId": 2}),
            (text_of(r["now"][0]), r["now"][0]["details"]))},
    "add without text is an error and changes nothing": {
        "steps": [ex("add", text="a"), ex("add")],
        "check": lambda t, r: t.assertEqual(
            ("Error: text required for add", {"action": "add", "todos": [A1], "nextId": 2, "error": "text required"}),
            (text_of(r["now"][1]), r["now"][1]["details"]))},
    "list shows each todo with a checkbox": {
        "steps": [ex("add", text="a"), ex("add", text="b"), ex("toggle", id=2), ex("list")],
        "check": lambda t, r: t.assertEqual("[ ] #1: a\n[x] #2: b", text_of(r["now"][3]))},
    "toggle completes": {
        "steps": [ex("add", text="a"), ex("toggle", id=1)],
        "check": lambda t, r: t.assertEqual(
            ("Todo #1 completed", [{"id": 1, "text": "a", "done": True}]),
            (text_of(r["now"][1]), r["now"][1]["details"]["todos"]))},
    "toggle twice uncompletes": {
        "steps": [ex("add", text="a"), ex("toggle", id=1), ex("toggle", id=1)],
        "check": lambda t, r: t.assertEqual(("Todo #1 uncompleted", False),
                                            (text_of(r["now"][2]), r["now"][2]["details"]["todos"][0]["done"]))},
    "toggle of an unknown id is not found": {
        "steps": [ex("add", text="a"), ex("toggle", id=9)],
        "check": lambda t, r: t.assertEqual(("Todo #9 not found", "#9 not found", [A1]),
                                            (text_of(r["now"][1]), r["now"][1]["details"]["error"], r["now"][1]["details"]["todos"]))},
    "toggle of id zero is not found rather than missing": {
        "steps": [ex("toggle", id=0)],
        "check": lambda t, r: t.assertEqual("Todo #0 not found", text_of(r["now"][0]))},
    "toggle without an id is an error": {
        "steps": [ex("toggle")],
        "check": lambda t, r: t.assertEqual(("Error: id required for toggle", "id required"),
                                            (text_of(r["now"][0]), r["now"][0]["details"]["error"]))},
    "clear counts and empties the list": {
        "steps": [ex("add", text="a"), ex("add", text="b"), ex("clear")],
        "check": lambda t, r: t.assertEqual(("Cleared 2 todos", {"action": "clear", "todos": [], "nextId": 1}),
                                            (text_of(r["now"][2]), r["now"][2]["details"]))},
    "ids start again at one after clear": {
        "steps": [ex("add", text="a"), ex("add", text="b"), ex("clear"), ex("add", text="c")],
        "check": lambda t, r: t.assertEqual("Added todo #1: c", text_of(r["now"][3]))},
    "an unknown action is reported as a list error": {
        "steps": [ex("add", text="a"), ex("remove", id=1)],
        "check": lambda t, r: t.assertEqual(
            ("Unknown action: remove", {"action": "list", "todos": [A1], "nextId": 2, "error": "unknown action: remove"}),
            (text_of(r["now"][1]), r["now"][1]["details"]))},
    # details.todos is a copy down to each Todo, so a later toggle does not
    # rewrite an earlier result in memory (or the branch rebuilt from it).
    "an earlier result is not changed by a later toggle": {
        "steps": [ex("add", text="a"), ex("toggle", id=1)],
        "check": lambda t, r: t.assertFalse(r["later"][0]["details"]["todos"][0]["done"])},
    # The rebuilt list is a copy, so add does not push into the stored entry.
    "a stored entry is not changed by adding after a rebuild": {
        "entries": [todo_entry([A1], 2)],
        "steps": [{"op": "tree"}, ex("add", text="b")],
        "check": lambda t, r: t.assertEqual([A1], r["entries"][0]["message"]["details"]["todos"])},
    "session start rebuilds the list from the branch": {
        "entries": [todo_entry([A1], 2), todo_entry([A1, B2], 3)],
        "steps": [{"op": "start"}, ex("list"), ex("add", text="c")],
        "check": lambda t, r: t.assertEqual(("[ ] #1: a\n[ ] #2: b", "Added todo #3: c"),
                                            (text_of(r["now"][1]), text_of(r["now"][2])))},
    "other tools results and entries are ignored on rebuild": {
        "entries": [todo_entry([A1], 2), todo_entry([B2], 7, tool="bash"), {"type": "label", "label": "x"},
                    {"type": "message", "message": {"role": "toolResult", "toolName": "todo"}}],
        "steps": [{"op": "start"}, ex("add", text="c")],
        "check": lambda t, r: t.assertEqual("Added todo #2: c", text_of(r["now"][1]))},
    "navigating the tree replaces the live list": {
        "steps": [ex("add", text="x"), ex("add", text="y"), {"op": "tree"}, ex("list")],
        "check": lambda t, r: t.assertEqual("No todos", text_of(r["now"][3]))},
    # renderCall and renderResult, through a theme that marks each colour.
    "render call shows the action and text": {
        "steps": [{"op": "call", "args": {"action": "add", "text": "buy milk"}}],
        "check": lambda t, r: t.assertEqual('<toolTitle>[b]todo [/b]</><muted>add</> <dim>"buy milk"</>', r["now"][0])},
    "render result without details shows the content": {
        "steps": [{"op": "result", "result": {"content": [{"type": "text", "text": "raw"}]}}],
        "check": lambda t, r: t.assertEqual("raw", r["now"][0])},
    "render result of an error": {
        "steps": [{"op": "result", "result": {"content": [], "details": {"action": "toggle", "todos": [], "nextId": 1, "error": "#9 not found"}}}],
        "check": lambda t, r: t.assertEqual("<error>Error: #9 not found</>", r["now"][0])},
    "render result of an empty list": {
        "steps": [{"op": "result", "result": {"content": [], "details": {"action": "list", "todos": [], "nextId": 1}}}],
        "check": lambda t, r: t.assertEqual("<dim>No todos</>", r["now"][0])},
    "render result of a long list shows five and counts the rest": {
        "steps": [{"op": "result", "result": {"content": [], "details": {"action": "list", "nextId": 8, "todos": [
            {"id": i, "text": f"t{i}", "done": i == 1} for i in range(1, 8)]}}}],
        "check": lambda t, r: t.assertEqual(
            "<muted>7 todo(s):</>\n<success>✓</> <accent>#1</> <dim>t1</>"
            + "".join(f"\n<dim>○</> <accent>#{i}</> <muted>t{i}</>" for i in range(2, 6)) + "\n<dim>... 2 more</>",
            r["now"][0])},
    "render result of add shows the last todo": {
        "steps": [{"op": "result", "result": {"content": [], "details": {"action": "add", "todos": [A1, B2], "nextId": 3}}}],
        "check": lambda t, r: t.assertEqual("<success>✓ Added </><accent>#2</> <muted>b</>", r["now"][0])},
    "render result of toggle repeats its message": {
        "steps": [{"op": "result", "result": {"content": [{"type": "text", "text": "Todo #1 completed"}],
                                              "details": {"action": "toggle", "todos": [A1], "nextId": 2}}}],
        "check": lambda t, r: t.assertEqual("<success>✓ </><muted>Todo #1 completed</>", r["now"][0])},
    # The /todos command.
    "todos command outside the tui only notifies": {
        "steps": [{"op": "command", "mode": "print"}],
        "check": lambda t, r: t.assertEqual(([["/todos requires interactive mode", "error"]], None),
                                            (r["now"][0]["notes"], r["now"][0]["lines"]))},
    "todos command with no todos says so": {
        "steps": [{"op": "command", "mode": "tui"}],
        "check": lambda t, r: t.assertEqual("  <dim>No todos yet. Ask the agent to add some!</>", r["now"][0]["lines"][3])},
    "todos command counts and lists": {
        "steps": [ex("add", text="a"), ex("add", text="b"), ex("toggle", id=1), {"op": "command", "mode": "tui"}],
        "check": lambda t, r: t.assertEqual(
            ["  <muted>1/2 completed</>", "", "  <success>✓</> <accent>#1</> <dim>a</>", "  <dim>○</> <accent>#2</> <text>b</>"],
            r["now"][3]["lines"][3:7])},
    "todos view closes on escape": {
        "steps": [{"op": "command", "mode": "tui", "keys": ["x", "\x1b"]}],
        "check": lambda t, r: t.assertEqual((True, True), (r["now"][0]["closed"], r["now"][0]["same"]))},
    "todos view stays open on other keys": {
        "steps": [{"op": "command", "mode": "tui", "keys": ["q", "\r"]}],
        "check": lambda t, r: t.assertFalse(r["now"][0]["closed"])},
}


class TodoTests(unittest.TestCase):
    """todo.ts: the tool's actions, state from the session, rendering, /todos."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        for package, source in TODO_STUBS.items():
            folder = cls.tmp / "node_modules" / package
            folder.mkdir(parents=True)
            (folder / "package.json").write_text(json.dumps({"name": package, "type": "module", "main": "index.js"}))
            (folder / "index.js").write_text(source)
        shutil.copy(EXTENSIONS / "todo.ts", cls.tmp / "todo.ts")
        cases = {name: {k: v for k, v in case.items() if k not in ("check", "bug")} for name, case in TODO.items()}
        (cls.tmp / "cases.json").write_text(json.dumps(cases))
        try:
            cls.results = run_node(TODO_RUNNER, [cls.tmp / "todo.ts", cls.tmp / "cases.json"],
                                   {"PATH": "/usr/bin:/bin", "HOME": str(cls.tmp)}, cls.tmp)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


generate(TodoTests, TODO, lambda self, case, result: case["check"](self, result))


# --------------------------------------------------------------------------
# view-outputs
# --------------------------------------------------------------------------


def png(width, height):
    raw = b"".join(b"\0" + bytes((200, 30, 30)) * width for _ in range(height))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def pdf(pages):
    """A minimal PDF with one line of text per page."""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>",
               "<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(f"{4 + 2 * i} 0 R" for i in range(pages)), pages),
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for i in range(pages):
        stream = f"BT /F1 24 Tf 30 150 Td (Spectrum page {i + 1}) Tj ET".encode()
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents {5 + 2 * i} 0 R "
                       "/Resources << /Font << /F1 3 0 R >> >> >>")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + (body if isinstance(body, bytes) else body.encode()) + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1) + b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)


def bmp(width, height):
    """24-bit uncompressed BMP."""
    row = bytes((30, 30, 200)) * width
    row += b"\0" * ((4 - len(row) % 4) % 4)
    data = row * height
    header = struct.pack("<2sIHHI", b"BM", 54 + len(data), 0, 0, 54)
    info = struct.pack("<IiiHHIIiiII", 40, width, height, 1, 24, 0, len(data), 2835, 2835, 0, 0)
    return header + info + data


def ppm(width, height):
    return b"P6\n%d %d\n255\n" % (width, height) + bytes((10, 200, 10)) * (width * height)


def tiff(width, height):
    """Baseline uncompressed RGB TIFF, little-endian, one strip."""
    data = bytes((200, 200, 30)) * (width * height)
    entries = 10
    ifd_at = 8
    bps_at = ifd_at + 2 + entries * 12 + 4
    data_at = bps_at + 6
    tags = [(256, 3, 1, width), (257, 3, 1, height), (258, 3, 3, bps_at), (259, 3, 1, 1), (262, 3, 1, 2),
            (273, 4, 1, data_at), (277, 3, 1, 3), (278, 3, 1, height), (279, 4, 1, len(data)), (284, 3, 1, 1)]
    out = b"II*\0" + struct.pack("<I", ifd_at) + struct.pack("<H", entries)
    for tag, kind, count, value in tags:
        out += struct.pack("<HHI", tag, kind, count) + (struct.pack("<HH", value, 0) if kind == 3 and count == 1
                                                        else struct.pack("<I", value))
    return out + struct.pack("<I", 0) + struct.pack("<HHH", 8, 8, 8) + data


def b64(data):
    return {"b64": base64.b64encode(data).decode()}


GIF = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
SMALL = b64(png(6, 6))
FAKE = b64(b"not really an image")
LIMIT = 64 * 1024 * 1024

VIEW_RUNNER = r"""
const [source, casesPath, scratch] = process.argv.slice(1);
const fs = await import("node:fs");
const { join, dirname } = await import("node:path");
const mod = await import(source);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const out = {};
const put = (cwd, files) => {
  for (const [name, spec] of Object.entries(files ?? {})) {
    const path = name.startsWith("/") ? name : join(cwd, name);
    fs.mkdirSync(dirname(path), { recursive: true });
    if (spec.sparse !== undefined) { fs.writeFileSync(path, ""); fs.truncateSync(path, spec.sparse); }
    else fs.writeFileSync(path, Buffer.from(spec.b64, "base64"));
    if (spec.age !== undefined) { const t = Date.now() / 1000 - spec.age; fs.utimesSync(path, t, t); }
  }
};
for (const [id, c] of Object.entries(cases)) {
  process.env.PATH = c.path;
  const cwd = c.cwd;
  fs.mkdirSync(cwd, { recursive: true });
  const handlers = {}; let tool;
  mod.default({ on: (e, h) => { (handlers[e] ??= []).push(h); }, registerTool: (t) => { tool = t; } });
  put(cwd, c.before);
  const steps = [];
  for (const [n, step] of c.steps.entries()) {
    const ctx = { cwd, model: { input: step.vision === false ? ["text"] : ["text", "image"] } };
    let result;
    if (step.kind === "view") result = await tool.execute("v", step.params, undefined, undefined, ctx);
    else {
      const callId = `${id}-${n}`;
      const tool = step.tool ?? "bash";
      if (!step.orphan) for (const h of handlers.tool_call) await h({ type: "tool_call", toolCallId: callId, toolName: tool, input: step.input ?? {} }, ctx);
      put(cwd, step.write);
      const event = { type: "tool_result", toolCallId: callId, toolName: tool, input: step.input ?? {},
                      content: [{ type: "text", text: step.output ?? "out" }], isError: !!step.isError, details: undefined };
      for (const h of handlers.tool_result) result = (await h(event, ctx)) ?? result;
    }
    const content = result?.content ?? [];
    steps.push({ isError: result?.isError ?? null, modified: result !== undefined,
                 texts: content.filter((p) => p.type === "text").map((p) => p.text),
                 images: content.filter((p) => p.type === "image").map((p) => p.mimeType) });
  }
  out[id] = { steps, leftovers: fs.readdirSync(scratch).filter((n) => n.startsWith("elm-pi-view-")) };
}
console.log(JSON.stringify(out));
"""

NO_VISION_TAIL = ". This model cannot see images: have the qwen sub-agent examine them before reporting on them."


def wrote(*names):
    return "[view-outputs] This command wrote " + ", ".join(names) + NO_VISION_TAIL


def blind(files, command="python3 plot.py", tool="bash", before=None, input=None):
    """One call by a text-only model: its note names exactly the files noticed."""
    return {"before": before or {}, "steps": [{"tool": tool, "vision": False, "write": files,
                                               "input": input or {"command": command}}]}


def note(step):
    return step["texts"][-1] if step["texts"] else None


def first_note(step):
    return next(t for t in step["texts"] if t.startswith("[view-outputs]"))


# Which files a text-only model is told about: the scan, without rendering.
DETECTED = {
    "png is noticed": (blind({"a.png": SMALL}), ["a.png"]),
    "jpeg spelled jpeg is noticed": (blind({"a.jpeg": FAKE}), ["a.jpeg"]),
    "tiff spelled tif is noticed": (blind({"a.tif": FAKE}), ["a.tif"]),
    "postscript is noticed": (blind({"a.ps": FAKE}), ["a.ps"]),
    "upper case extension is noticed": (blind({"FIG.PNG": SMALL}), ["FIG.PNG"]),
    "data files are not figures": (blind({"a.csv": FAKE, "a.npy": FAKE, "a.h5": FAKE, "a.root": FAKE, "a.mp4": FAKE}), None),
    "a backup of a figure is not a figure": (blind({"a.png.bak": SMALL}), None),
    "several are listed sorted": (blind({"z.pdf": FAKE, "b.png": SMALL, "figures/a.svg": FAKE}), ["b.png", "figures/a.svg", "z.pdf"]),
    "hidden folders are skipped": (blind({".cache/a.png": SMALL, ".git/b.png": SMALL, "c.png": SMALL}), ["c.png"]),
    "package and cache folders are skipped": (blind({"node_modules/a.png": SMALL, "__pycache__/b.png": SMALL, "venv/c.png": SMALL,
                                                    "lib/site-packages/d.png": SMALL, "lib/dist-packages/e.png": SMALL}), None),
    "six folders deep is scanned": (blind({"1/2/3/4/5/6/deep.png": SMALL}), ["1/2/3/4/5/6/deep.png"]),
    "seven folders deep is not": (blind({"1/2/3/4/5/6/7/deep.png": SMALL}), None),
    "an empty file is not shown": (blind({"empty.png": {"b64": ""}}), None),
    "a file at the size limit is shown": (blind({"huge.pdf": {"sparse": LIMIT}}), ["huge.pdf"]),
    "a file over the size limit is not": (blind({"huge.pdf": {"sparse": LIMIT + 1}}), None),
    "a figure from an hour ago is not new": (blind({}, before={"old.png": {**SMALL, "age": 3600}}), None),
    # Coarse filesystem clocks: 1.5 s of slack before the call started.
    "a figure from just before the call counts": (blind({}, before={"edge.png": {**SMALL, "age": 0.8}}), ["edge.png"]),
    "an absolute path the command names is noticed": (
        blind({"{out}/elsewhere.png": SMALL}, command="python3 plot.py --out {out}/elsewhere.png"), ["{out}/elsewhere.png"]),
    "an absolute path after equals and in quotes is noticed": (
        blind({"{out}/q.pdf": FAKE, "{out}/e.png": SMALL}, command="plot --pdf='{out}/q.pdf' --png={out}/e.png"),
        ["{out}/e.png", "{out}/q.pdf"]),
    "an absolute path the command does not name is not": (blind({"{out}/unnamed.png": SMALL}, command="python3 plot.py"), None),
    "a named path in a python cell is noticed": (
        blind({"{out}/cell.png": SMALL}, tool="python", input={"cells": [{"code": "x = 1"}, {"code": "fig.savefig('{out}/cell.png')"}]}),
        ["{out}/cell.png"]),
    "a tool other than bash or python is not watched": (blind({"a.png": SMALL}, tool="write"), None),
}


def vision(files, command="python3 plot.py", before=None, path="none", output="out"):
    return {"before": before or {}, "path": path, "steps": [{"input": {"command": command}, "write": files, "output": output}]}


ATTACH_NOTE = ("Examine every attached image before you report on it or build on it: does it show what was intended; "
               "are axes labelled with units, ranges and scales sensible, legends and text legible and not overlapping; "
               "are there empty, clipped or wrong panels; does a fit follow the data. Fix and regenerate what is wrong, "
               "and describe what each figure shows in your report.")

VIEW = {
    # Attached to a bash result for a model that can see.
    "a png is passed through as png": {
        **vision({"a.png": SMALL}),
        "check": lambda t, s: t.assertEqual(
            (["out", "[view-outputs] This command wrote 1 figure/document file(s). Attached below: a.png.\n" + ATTACH_NOTE, "a.png:"],
             ["image/png"]), (s[0]["texts"], s[0]["images"]))},
    "a jpeg mupdf cannot read is passed through as jpeg": {
        **vision({"a.jpg": FAKE}), "check": lambda t, s: t.assertEqual(["image/jpeg"], s[0]["images"])},
    "a gif is passed through as gif": {
        **vision({"a.gif": b64(GIF)}), "check": lambda t, s: t.assertEqual(["image/gif"], s[0]["images"])},
    "a bmp is rendered to png": {
        **vision({"a.bmp": b64(bmp(5, 4))}),
        "check": lambda t, s: t.assertEqual((["image/png"], "a.bmp:"), (s[0]["images"], s[0]["texts"][2]))},
    "a tiff is rendered to png": {
        **vision({"a.tiff": b64(tiff(4, 3))}), "check": lambda t, s: t.assertEqual(["image/png"], s[0]["images"])},
    "a one page pdf comes with its text layer": {
        **vision({"one.pdf": b64(pdf(1))}),
        "check": lambda t, s: t.assertEqual(["one.pdf:", "--- page 1 of 1 - text layer:\nSpectrum page 1"], s[0]["texts"][2:4])},
    "a long pdf shows four pages and says how to see the rest": {
        **vision({"six.pdf": b64(pdf(6))}),
        "check": lambda t, s: (
            t.assertEqual(4, len(s[0]["images"])),
            t.assertIn("Attached below: six.pdf (pages 1,2,3,4 of 6).", s[0]["texts"][1]),
            t.assertEqual('six.pdf: 6 pages, showing pages 1-4 - view it with pages "5-6" for the rest.', s[0]["texts"][2]))},
    "a pdf gets only the room left under eight images": {
        **vision({"a.pdf": b64(pdf(6)), **{f"p{i}.png": SMALL for i in range(7)}}),
        "check": lambda t, s: (
            t.assertEqual(8, len(s[0]["images"])),
            t.assertIn("Not attached here - p4.png; p5.png; p6.png. Look at what can be shown with the view tool.", s[0]["texts"][1]))},
    "three pngs then a pdf leave the pdf four pages": {
        **vision({"a.png": SMALL, "b.png": SMALL, "c.png": SMALL, "d.pdf": b64(pdf(6))}),
        "check": lambda t, s: (t.assertEqual(7, len(s[0]["images"])), t.assertIn("d.pdf (pages 1,2,3,4 of 6)", s[0]["texts"][1]))},
    "a broken pdf is named with its error and the output kept": {
        **vision({"bad.pdf": FAKE, "ok.png": SMALL}, output="saved"),
        "check": lambda t, s: (t.assertEqual("saved", s[0]["texts"][0]), t.assertEqual(["image/png"], s[0]["images"]),
                               t.assertIn("Not attached here - bad.pdf: ", s[0]["texts"][1]),
                               t.assertIn("Attached below: ok.png.", s[0]["texts"][1]))},
    "a changed figure is attached again": {
        "path": "none", "steps": [{"input": {"command": "a"}, "write": {"a.png": SMALL}},
                                  {"input": {"command": "b"}, "write": {"a.png": {**b64(png(7, 7)), "age": -5}}}],
        "check": lambda t, s: t.assertEqual([["image/png"], ["image/png"]], [x["images"] for x in s])},
    "a result without its call is left alone": {
        "path": "none", "steps": [{"orphan": True, "input": {"command": "x"}, "write": {"a.png": SMALL}}],
        "check": lambda t, s: t.assertFalse(s[0]["modified"])},
    "a figure already viewed is not attached again": {
        # Dated ahead, so it is new to every call: only having been viewed keeps it out.
        "path": "none", "steps": [{"kind": "view", "params": {"path": "v.png"}}, {"input": {"command": "ls"}}],
        "before": {"v.png": {**SMALL, "age": -30}},
        "check": lambda t, s: t.assertEqual((["image/png"], False), (s[0]["images"], s[1]["modified"]))},
    # Formats MuPDF cannot read, through whatever converter is on PATH.
    "eps without a converter names the tools that would do": {
        **vision({"fig.eps": FAKE}),
        "check": lambda t, s: t.assertIn("fig.eps: no converter for .eps on this machine (any of: gs, epstopdf, magick, pixi)."
                                         " Save the figure as PNG or PDF instead", s[0]["texts"][1])},
    "svg without a converter names five tools": {
        **vision({"fig.svg": FAKE}),
        "check": lambda t, s: t.assertIn("(any of: resvg, rsvg-convert, inkscape, magick, qlmanage)", s[0]["texts"][1])},
    "resvg is preferred to rsvg-convert": {
        **vision({"fig.svg": FAKE}, path="both"),
        "check": lambda t, s: (t.assertIn("Attached below: fig.svg (converted with resvg).", s[0]["texts"][1]),
                               t.assertEqual("fig.svg (converted with resvg):", s[0]["texts"][2]))},
    "a converter that fails hands on to the next": {
        **vision({"fig.svg": FAKE}, path="failing"),
        "check": lambda t, s: t.assertIn("fig.svg (converted with rsvg-convert)", s[0]["texts"][1])},
    "a converter that writes nothing hands on to the next": {
        **vision({"fig.svg": FAKE}, path="empty"),
        "check": lambda t, s: t.assertIn("fig.svg (converted with rsvg-convert)", s[0]["texts"][1])},
    "quick look output is found under its own name": {
        **vision({"fig.svg": FAKE}, path="quicklook"),
        "check": lambda t, s: (t.assertIn("fig.svg (converted with qlmanage)", s[0]["texts"][1]),
                               t.assertEqual(["image/png"], s[0]["images"]))},
    "postscript goes through epstopdf without ghostscript": {
        **vision({"fig.ps": FAKE}, path="epstopdf"),
        "check": lambda t, s: (t.assertIn("fig.ps (pages 1,2 of 2) (converted with epstopdf)", s[0]["texts"][1]),
                               t.assertEqual(2, len(s[0]["images"])))},
    "heic goes through sips": {
        **vision({"photo.heic": FAKE}, path="sips"),
        "check": lambda t, s: t.assertIn("photo.heic (converted with sips)", s[0]["texts"][1])},
    "a conversion leaves no temporary folder": {
        **vision({"fig.svg": FAKE, "fig.eps": FAKE}, path="both"),
        "check": lambda t, s, r: t.assertEqual([], r["leftovers"])},
    # The view tool.
    "view refuses for a model without vision": {
        "path": "none", "before": {"a.png": SMALL}, "steps": [{"kind": "view", "vision": False, "params": {"path": "a.png"}}],
        "check": lambda t, s: t.assertEqual((True, ["This model cannot see images. Ask the qwen sub-agent to view the file."]),
                                            (s[0]["isError"], s[0]["texts"]))},
    "view refuses a text file": {
        "path": "none", "before": {"data.csv": FAKE}, "steps": [{"kind": "view", "params": {"path": "data.csv"}}],
        "check": lambda t, s: t.assertEqual(["data.csv: not an image or PDF. Use read for text files."], s[0]["texts"])},
    "view of a missing file says so": {
        "path": "none", "steps": [{"kind": "view", "params": {"path": "nope.pdf"}}],
        "check": lambda t, s: t.assertEqual((True, ["nope.pdf: no such file."]), (s[0]["isError"], s[0]["texts"]))},
    "view refuses a file over the size limit": {
        "path": "none", "before": {"big.png": {"sparse": LIMIT + 1}}, "steps": [{"kind": "view", "params": {"path": "big.png"}}],
        "check": lambda t, s: t.assertEqual(["big.png: 67 MB is too large to render."], s[0]["texts"])},
    "view of a broken pdf is an error": {
        "path": "none", "before": {"bad.pdf": FAKE}, "steps": [{"kind": "view", "params": {"path": "bad.pdf"}}],
        "check": lambda t, s: (t.assertTrue(s[0]["isError"]), t.assertTrue(s[0]["texts"][0].startswith("bad.pdf: could not be shown: ")))},
    "view pages from a start to the end": {
        "path": "none", "before": {"p.pdf": b64(pdf(5))}, "steps": [{"kind": "view", "params": {"path": "p.pdf", "pages": "3-"}}],
        "check": lambda t, s: t.assertEqual(("p.pdf: 5 pages, showing pages 3-5.", 3), (s[0]["texts"][0], len(s[0]["images"])))},
    "view pages up to an end": {
        "path": "none", "before": {"p.pdf": b64(pdf(5))}, "steps": [{"kind": "view", "params": {"path": "p.pdf", "pages": "-2"}}],
        "check": lambda t, s: t.assertEqual('p.pdf: 5 pages, showing pages 1-2 - view it with pages "3-5" for the rest.', s[0]["texts"][0])},
    "view of pages past the end shows none": {
        "path": "none", "before": {"p.pdf": b64(pdf(5))}, "steps": [{"kind": "view", "params": {"path": "p.pdf", "pages": "9"}}],
        "check": lambda t, s: t.assertEqual((["p.pdf: 5 pages, showing no pages."], []), (s[0]["texts"], s[0]["images"]))},
    "view ignores a page spec that is not a number": {
        "path": "none", "before": {"p.pdf": b64(pdf(5))}, "steps": [{"kind": "view", "params": {"path": "p.pdf", "pages": "x,2"}}],
        "check": lambda t, s: t.assertEqual(["--- page 2 of 5 - text layer:\nSpectrum page 2"], s[0]["texts"][1:])},
    # The header names the pages shown, so "2,4" does not claim page 3.
    "view of scattered pages does not claim the gap": {
        "path": "none", "before": {"p.pdf": b64(pdf(5))}, "steps": [{"kind": "view", "params": {"path": "p.pdf", "pages": "2,4"}}],
        "check": lambda t, s: t.assertEqual('p.pdf: 5 pages, showing pages 2,4 - view it with pages "5" for the rest.',
                                            s[0]["texts"][0])},
    "view without the text layer": {
        "path": "none", "before": {"p.pdf": b64(pdf(1))}, "steps": [{"kind": "view", "params": {"path": "p.pdf", "text": False}}],
        "check": lambda t, s: t.assertEqual(["p.pdf:", "--- page 1 of 1 (no text layer)"], s[0]["texts"])},
    "view names a file outside the project by its full path": {
        "path": "none", "before": {"{out}/x.png": SMALL}, "steps": [{"kind": "view", "params": {"path": "{out}/x.png"}}],
        "check": lambda t, s, r, out: t.assertEqual([f"{out}/x.png:"], s[0]["texts"])},
    "view converts through the first working converter": {
        "path": "both", "before": {"fig.svgz": FAKE}, "steps": [{"kind": "view", "params": {"path": "fig.svgz"}}],
        "check": lambda t, s: t.assertEqual(["fig.svgz (converted with resvg):"], s[0]["texts"])},
    # read, for the formats pi's read cannot show.
    "read of a tiff is rendered": {
        "path": "none", "before": {"scan.tif": b64(tiff(4, 3))},
        "steps": [{"tool": "read", "orphan": True, "input": {"path": "scan.tif"}, "output": "binary"}],
        "check": lambda t, s: t.assertEqual((False, ["scan.tif:"], ["image/png"]), (s[0]["isError"], s[0]["texts"], s[0]["images"]))},
    "read of a png is left to read": {
        "path": "none", "before": {"a.png": SMALL},
        "steps": [{"tool": "read", "orphan": True, "input": {"path": "a.png"}}],
        "check": lambda t, s: t.assertFalse(s[0]["modified"])},
    "read of a missing pdf is left to read": {
        "path": "none", "steps": [{"tool": "read", "orphan": True, "input": {"path": "gone.pdf"}, "isError": True}],
        "check": lambda t, s: t.assertFalse(s[0]["modified"])},
}


class ViewOutputsTests(unittest.TestCase):
    """view-outputs.ts: the scan after each call, attachment, converters, view and read."""

    @classmethod
    def setUpClass(cls):
        mupdf = ROOT / "node_modules/mupdf"
        if not mupdf.exists():
            raise unittest.SkipTest("needs the installed mupdf package (run bootstrap.sh)")
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            cls._prepare(mupdf)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def _prepare(cls, mupdf):
        ext = cls.tmp / "ext"
        (ext / "node_modules/typebox").mkdir(parents=True)
        (ext / "node_modules/typebox/package.json").write_text('{"name":"typebox","type":"module","main":"index.js"}')
        (ext / "node_modules/typebox/index.js").write_text(
            "const f = (...a) => ({ a }); export const Type = { Object: f, String: f, Optional: f, Boolean: f };")
        (ext / "node_modules/mupdf").symlink_to(mupdf)
        shutil.copy(EXTENSIONS / "view-outputs.ts", ext / "view-outputs.ts")
        cls.out = cls.tmp / "outside"
        cls.out.mkdir()
        scratch = cls.tmp / "scratch"
        scratch.mkdir()
        (cls.tmp / "red.png").write_bytes(png(20, 20))
        (cls.tmp / "two.pdf").write_bytes(pdf(2))
        red, two = cls.tmp / "red.png", cls.tmp / "two.pdf"
        # Converter sets on PATH, each a folder of fake tools that copy a known file to the output.
        bins = {"none": {}, "both": {"resvg": f'/bin/cp "{red}" "$4"\n', "rsvg-convert": f'/bin/cp "{red}" "$4"\n',
                                     "gs": 'for a; do case "$a" in -sOutputFile=*) /bin/cp "%s" "${a#-sOutputFile=}" ;; esac; done\n' % two},
                "failing": {"resvg": "exit 1\n", "rsvg-convert": f'/bin/cp "{red}" "$4"\n'},
                "empty": {"resvg": ': > "$4"\n', "rsvg-convert": f'/bin/cp "{red}" "$4"\n'},
                "quicklook": {"qlmanage": f'/bin/cp "{red}" "$5/$(/usr/bin/basename "$6").png"\n'},
                "epstopdf": {"epstopdf": 'for a; do case "$a" in --outfile=*) /bin/cp "%s" "${a#--outfile=}" ;; esac; done\n' % two},
                "sips": {"sips": f'/bin/cp "{red}" "$6"\n'}}
        paths = {}
        for name, tools in bins.items():
            folder = cls.tmp / "bin" / name
            folder.mkdir(parents=True)
            for tool, script in tools.items():
                write_executable(folder / tool, script)
            paths[name] = str(folder)
        cases = {}
        for name, (case, _) in DETECTED.items():
            cases[name] = {**case, "path": paths["none"]}
        for name, case in VIEW.items():
            cases[name] = {k: v for k, v in case.items() if k not in ("check", "bug")}
            cases[name]["path"] = paths[case["path"]]
        for i, (name, case) in enumerate(cases.items()):
            case["cwd"] = str(cls.tmp / "projects" / f"p{i}")
        cases = fill(cases, out=cls.out)
        (cls.tmp / "cases.json").write_text(json.dumps(cases))
        env = {"PATH": paths["none"], "HOME": str(cls.tmp), "TMPDIR": str(scratch)}
        cls.results = run_node(VIEW_RUNNER, [ext / "view-outputs.ts", cls.tmp / "cases.json", scratch], env, cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


def _check_detected(self, case, result):
    step = result["steps"][0]
    expected = fill(case["expected"], out=self.out)
    if expected is None:
        self.assertFalse(step["modified"], step["texts"])
    else:
        self.assertEqual(["out", wrote(*expected)], step["texts"])


def _check_view(self, case, result):
    check = case["check"]
    arity = check.__code__.co_argcount
    args = [self, result["steps"], result, str(self.out)][:arity]
    check(*args)


generate(ViewOutputsTests, {n: {"expected": e} for n, (_, e) in DETECTED.items()}, _check_detected)
generate(ViewOutputsTests, VIEW, _check_view)


if __name__ == "__main__":
    unittest.main()
