"""Generated cases for the feature extensions, checked against invariants and reference models.

tests/test_feature_extensions.py, test_skill_router.py, test_view_outputs.py,
test_policy_extensions.py and test_shim.py hold hand-written tables. This file
generates its cases instead - cross products, seeded random sequences - and
checks each against a property or a small Python model of what the extension
should do, so a whole family of inputs is covered rather than one example:

- install-notes: every installer x every shell context it can sit in (prefix
  assignments, sudo/env/time, chains, pipes, newlines, subshells,
  redirections); every value-taking option of every installer, attached with
  `=` and separate; several installs in one command; the note and the
  installs.log line after success, and nothing after failure. Invariants: a
  note iff something was installed, every package named, no option value ever
  taken for a package, the undo naming exactly the packages.
- skill-router: for each skill, the same request in other casings,
  punctuation, wrappings, plurals and Unicode surroundings must route to it;
  the guarded topic words in software contexts must not route; routesFor never
  repeats a skill and keeps table order; the session message inlines at most
  two and names at most two more.
- todo: seeded random add/toggle/remove/clear/list sequences, with branch
  navigation and session rebuilds, against a reference model of the list.
- view-outputs: `pages` specs generated from the grammar, against a reference
  parser that follows JavaScript's Number(); the image budget across several
  files a command wrote. mupdf is a stub that records which pages were loaded,
  so only the extension's own logic is under test and nothing needs bootstrap.
- pinned-instructions: seeded pin/unpin/compact/start sequences against a
  model of the pin file and of the copy in the system prompt.
- elm-shim: the provider it registers (or the warning it gives) across health
  answers, ports, paths and interpreters, all on loopback.

Each extension's .ts is run under the bundled node (type stripping) against a
stub ExtensionAPI; one node process per TestCase class runs every case and
prints one JSON object; one test method is generated per case. Cases marked
expectedFailure are real bugs, named in a comment beside each.
"""

import hashlib
import json
import math
import os
import random
import re
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = ROOT / "templates/extensions"
SKILLS = ROOT / "templates/skills"


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


def run_node(script, args, env, cwd, timeout=180):
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
    text = text.replace("σ", "sigma").replace("χ²", "chi2").replace("\n", " nl ")
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:100]


def generate(cls, cases):
    """One test method per case: test_<slug>, calling case["check"](self, result)."""
    for name, case in cases.items():
        method = f"test_{slug(name)}"
        assert not hasattr(cls, method), f"duplicate case name: {name} ({method})"

        def test(self, name=name, case=case):
            case["check"](self, self.results[name])

        test.__name__ = method
        test.__doc__ = name
        if case.get("bug"):
            test = unittest.expectedFailure(test)
        setattr(cls, method, test)


def write_executable(path, script):
    path.write_text("#!/bin/sh\n" + script)
    path.chmod(0o755)


def stub_package(root, name, source):
    folder = root / "node_modules" / name
    folder.mkdir(parents=True)
    (folder / "package.json").write_text(json.dumps({"name": name, "type": "module", "main": "index.js"}))
    (folder / "index.js").write_text(source)


def closed_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ==========================================================================
# install-notes
# ==========================================================================

INSTALL_RUNNER = r"""
const [source, casesPath] = process.argv.slice(1);
const fs = await import("node:fs");
const { join } = await import("node:path");
const mod = await import(source);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const base = process.env.PI_CODING_AGENT_DIR;
const out = {};
for (const [id, c] of Object.entries(cases)) {
  process.env.PI_CODING_AGENT_DIR = c.agent ?? base;
  if (c.kind === "describe") { out[id] = mod.describe(c.command, "/proj"); continue; }
  let handler;
  mod.default({ on: (event, h) => { if (event === "tool_result") handler = h; } });
  const event = { toolName: "bash", isError: c.isError, input: { command: c.command }, content: [{ type: "text", text: "ok" }] };
  const returned = (await handler(event, { cwd: "/proj" })) ?? null;
  const log = join(c.agent, "installs.log");
  out[id] = { returned, log: fs.existsSync(log) ? fs.readFileSync(log, "utf8") : null };
}
console.log(JSON.stringify(out));
"""

BREW_WHERE = "Homebrew's prefix (`brew --prefix`), shared with everything else on this machine that uses Homebrew"


def pip_note(pkgs, python, reqs=(), target=None, prefix=None, root=None, user=False):
    """What describe() says for a pip-family install: the reference model of that branch."""
    names = " ".join(pkgs) or "<package>"
    what = ", ".join([*pkgs, *(f"the packages in {r}" for r in reqs)]) or "Python packages"
    if target:
        where, undo = (f"the folder {target}/ (--target), not a Python environment",
                       f"delete {names} from {target}/ (pip uninstall does not look there)")
    elif prefix:
        where, undo = (f"the prefix {prefix}/ (--prefix), outside the Python environment",
                       f"delete {names} from {prefix}/ (pip uninstall does not look there)")
    elif root:
        where, undo = (f"under {root}/ (--root), outside the Python environment",
                       f"delete {names} from {root}/ (pip uninstall does not look there)")
    elif user:
        where, undo = "your user site-packages (`python3 -m site --user-site`)", f"pip uninstall {names}"
    else:
        where = f"the Python environment of {python}" if python else "the environment uv chose"
        undo = f"pip uninstall {names}"
    return {"what": f"{what} from PyPI", "where": where, "undo": undo}


def uv_add_note(pkgs, reqs=(), project="/proj"):
    return {"what": f"{', '.join([*pkgs, *(f'the packages in {r}' for r in reqs)])} from PyPI, added to this "
                    "project's environment (uv add)",
            "where": f"{project}/pyproject.toml and {project}/.venv",
            "undo": f"uv remove {' '.join(pkgs) or '<package>'}"}


def pixi_add_note(pkgs, folder="/proj", manifest=None):
    manifest = manifest or f"{folder}/pixi.toml"
    return {"what": f"{', '.join(pkgs)} added to this project's pixi environment",
            "where": f"{manifest} and {manifest.rsplit('/', 1)[0]}/.pixi", "undo": f"pixi remove {' '.join(pkgs)}"}


def pixi_global_note(pkgs):
    return {"what": f"{', '.join(pkgs)} from conda-forge (pixi global install)",
            "where": "{agent}/pixi/envs, with its commands in {agent}/pixi/bin on PATH",
            "undo": f"pixi global uninstall {' '.join(pkgs)}"}


def pixi_exec_note(specs):
    return {"what": f"{', '.join(specs) or 'a package'} from conda-forge, run with pixi exec (nothing installed)",
            "where": "downloaded packages cached in {agent}/pixi/cache", "undo": "pixi clean cache"}


def image_note(name, tool):
    return {"what": f"the container image {name}", "where": f"{tool}'s image store", "undo": f"{tool} rmi {name}"}


def brew_note(pkgs):
    return {"what": f"{', '.join(pkgs)} (Homebrew)", "where": BREW_WHERE, "undo": f"brew uninstall {' '.join(pkgs)}"}


# installer -> (command, expected describe() entry). {bin} holds pip, pip3,
# python3 and python3.11; `python` is not on PATH. The working directory is /proj.
INSTALLERS = {
    "pip": ("pip install numpy 'scipy>=1.11'", pip_note(["numpy", "scipy>=1.11"], "{bin}/pip")),
    "pip3": ("pip3 install astropy", pip_note(["astropy"], "{bin}/pip3")),
    "python3 -m pip": ("python3 -m pip install emcee corner", pip_note(["emcee", "corner"], "{bin}/python3")),
    "python3.11 -m pip": ("python3.11 -m pip install h5py", pip_note(["h5py"], "{bin}/python3.11")),
    "python -m pip off PATH": ("python -m pip install uproot", pip_note(["uproot"], "python")),
    "python by path": ("/opt/conda/bin/python3 -m pip install iminuit", pip_note(["iminuit"], "/opt/conda/bin/python3")),
    "pip by relative path": (".venv/bin/pip install lmfit", pip_note(["lmfit"], ".venv/bin/pip")),
    "uv pip": ("uv pip install polars pyarrow", pip_note(["polars", "pyarrow"], None)),
    "uv add": ("uv add xarray netcdf4", uv_add_note(["xarray", "netcdf4"])),
    "pixi add": ("pixi add root hdf5", pixi_add_note(["root", "hdf5"])),
    "pixi global install": ("pixi global install ghostscript gnuplot", pixi_global_note(["ghostscript", "gnuplot"])),
    "pixi exec": ("pixi exec -s ghostscript -s imagemagick gs -v", pixi_exec_note(["ghostscript", "imagemagick"])),
    "docker pull": ("docker pull alpine:3.20", image_note("alpine:3.20", "docker")),
    "podman image pull": ("podman image pull docker.io/library/python:3.12",
                          image_note("docker.io/library/python:3.12", "podman")),
    "brew install": ("brew install pandoc gnuplot", brew_note(["pandoc", "gnuplot"])),
}

# Where a command sits in what the shell runs. None of these change what is installed.
CONTEXTS = {
    # VAR=x, time, sudo and env are skipped in any order.
    "after assignments time sudo and env": "PIP_NO_INPUT=1 LC_ALL=C time sudo env HTTPS_PROXY_UNUSED=1 {cmd}",
    "after cd and": "cd sub && {cmd}",
    "as an or fallback before a semicolon": "false || {cmd}; echo finished",
    "piped in a subshell on the second line": "echo start\n(set -e; {cmd} 2>&1 | tail -n 5)",
    "with output redirected": "{cmd} > install.log 2> errors.txt",
}

# `cd sub && pixi add x` changes sub/pixi.toml: a project-relative install
# follows a `cd` earlier in the chain.
CONTEXT_ENTRIES = {
    ("pixi add", "after cd and"): pixi_add_note(["root", "hdf5"], "/proj/sub"),
    ("uv add", "after cd and"): uv_add_note(["xarray", "netcdf4"], project="/proj/sub"),
}


def describe_case(command, expected):
    return {"input": {"kind": "describe", "command": command},
            "check": lambda t, r: t.assertEqual(t.names(expected), r, command)}


INSTALL_CASES = {}

for installer, (cmd, entry) in INSTALLERS.items():
    for context, template in CONTEXTS.items():
        INSTALL_CASES[f"{installer} {context}"] = describe_case(
            template.format(cmd=cmd), [CONTEXT_ENTRIES.get((installer, context), entry)])

# Every value-taking option, its value a decoy: the value must never be listed
# as a package, and the package after it must be. Options whose value changes
# the where (-t, --prefix, --root, --python) or adds a requirements file are
# modelled; tests/test_feature_extensions.py already has -i, --index-url=, -f,
# -t, --prefix, --root, -r and --requirement in their separate form.
PIP_VALUED = [
    "-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-t", "--target", "--platform",
    "--python-version", "--implementation", "--abi", "--root", "--prefix", "--src", "--upgrade-strategy",
    "-C", "--config-settings", "--global-option", "--no-binary", "--only-binary", "--progress-bar",
    "--root-user-action", "--report", "--group", "-i", "--index-url", "--extra-index-url", "-f", "--find-links",
    "--python", "--log", "--keyring-provider", "--proxy", "--retries", "--timeout", "--exists-action",
    "--trusted-host", "--cert", "--client-cert", "--cache-dir", "--use-feature", "--use-deprecated", "--resume-retries",
]
UV_PIP_ONLY = [
    "-p", "--requirements", "--constraints", "--overrides", "-b", "--build-constraints", "--extra", "-P",
    "--upgrade-package", "--reinstall-package", "--refresh-package", "--index", "--default-index", "--index-strategy",
    "--resolution", "--prerelease", "--exclude-newer", "--no-build-isolation-package", "--config-setting",
    "--link-mode", "--python-platform", "--torch-backend", "--color", "--allow-insecure-host", "--config-file",
    "--directory", "--project",
]
UV_ADD_VALUED = [
    "-r", "--requirements", "-c", "--constraints", "-m", "--marker", "--optional", "--group", "--rev", "--tag",
    "--branch", "--extra", "--package", "--script", "--bounds", "--index", "--default-index", "-i", "--index-url",
    "--extra-index-url", "-f", "--find-links", "--index-strategy", "--keyring-provider", "--resolution",
    "--prerelease", "--exclude-newer", "--no-build-isolation-package", "-C", "--config-setting", "--link-mode",
    "-P", "--upgrade-package", "--reinstall-package", "--refresh-package", "-p", "--python", "--cache-dir",
    "--color", "--allow-insecure-host", "--config-file", "--directory", "--project",
]
ALREADY_TABLED = {"-i", "-f", "-t", "--prefix", "--root", "-r", "--requirement"}
DECOY = "decoyval"


def opt(option):
    """An option as a test name: -C and -c, -P and -p must not share one."""
    return f"{option} upper" if len(option) == 2 and option[1].isupper() else option


def pip_expected(option, value, python, uv):
    """The note for `<pip> install <option> <value> numpy`."""
    reqs = [value] if option in ("-r", "--requirement") or (uv and option == "--requirements") else []
    kwargs = {"target": value if option in ("-t", "--target") else None,
              "prefix": value if option == "--prefix" else None,
              "root": value if option == "--root" else None}
    if option == "--python" or (uv and option == "-p"):
        python = value
    return pip_note(["numpy"], python, reqs, **kwargs)


# Long options alternate between the two shapes, so each is tested once and
# both shapes are tested throughout the list.
for i, option in enumerate(PIP_VALUED):
    if option.startswith("--") and (i % 2 or option in ALREADY_TABLED):
        # Attached with `=`, the option must not swallow the package after it.
        INSTALL_CASES[f"python3 -m pip value of {option} attached with equals"] = describe_case(
            f"python3 -m pip install {option}={DECOY} numpy", [pip_expected(option, DECOY, "{bin}/python3", False)])
    elif option not in ALREADY_TABLED:
        INSTALL_CASES[f"pip value of {opt(option)} given separately"] = describe_case(
            f"pip install {option} {DECOY} numpy", [pip_expected(option, DECOY, "{bin}/pip", False)])

for option in UV_PIP_ONLY:
    INSTALL_CASES[f"uv pip value of {opt(option)}"] = describe_case(
        f"uv pip install {option} {DECOY} numpy", [pip_expected(option, DECOY, None, True)])

# uv add's own list; the options it shares with pip's spelling are checked in pairs with equals.
for option in UV_ADD_VALUED:
    reqs = [DECOY] if option in ("-r", "--requirements") else []
    project = f"/proj/{DECOY}" if option in ("--project", "--directory") else "/proj"
    INSTALL_CASES[f"uv add value of {opt(option)}"] = describe_case(
        f"uv add {option} {DECOY} numpy", [uv_add_note(["numpy"], reqs, project)])

for option in ["-c", "--channel", "-f", "--feature", "--platform"]:
    INSTALL_CASES[f"pixi add value of {option}"] = describe_case(f"pixi add {option} {DECOY} numpy",
                                                                 [pixi_add_note(["numpy"])])
for option in ["--channel", "-e", "--environment", "-p", "--platform"]:
    INSTALL_CASES[f"pixi global value of {option}"] = describe_case(f"pixi global install {option} {DECOY} gdal",
                                                                    [pixi_global_note(["gdal"])])

# --manifest-path: a .toml names the manifest, anything else the folder holding it.
INSTALL_CASES.update({
    "pixi add manifest path folder": describe_case("pixi add --manifest-path tools ruff",
                                                   [pixi_add_note(["ruff"], manifest="/proj/tools/pixi.toml")]),
    "pixi add manifest path absolute toml with equals": describe_case(
        "pixi add --manifest-path=/work/env/pixi.toml ruff", [pixi_add_note(["ruff"], manifest="/work/env/pixi.toml")]),
    "pixi add manifest path pyproject": describe_case(
        "pixi add --manifest-path svc/pyproject.toml ruff", [pixi_add_note(["ruff"], manifest="/proj/svc/pyproject.toml")]),
    "pixi add manifest path dotdot is resolved": describe_case(
        "pixi add --manifest-path ../shared ruff", [pixi_add_note(["ruff"], manifest="/shared/pixi.toml")]),
    "uv add project with equals is resolved": describe_case(
        "uv add --project=../lib numpy", [uv_add_note(["numpy"], project="/lib")]),
    "uv add first of project and directory wins": describe_case(
        "uv add --directory a --project b numpy", [uv_add_note(["numpy"], project="/proj/a")]),
    "uv add two requirements files": describe_case(
        "uv add -r a.txt --requirements=b.txt", [uv_add_note([], ["a.txt", "b.txt"])]),
    "pip first target of two wins": describe_case(
        "pip install -t one --target=two numpy", [pip_note(["numpy"], None, target="one")]),
    "pip target outranks prefix root and user": describe_case(
        "pip install --user --root /r --prefix /p -t vend numpy", [pip_note(["numpy"], None, target="vend")]),
    "pip prefix outranks root and user": describe_case(
        "pip install --user --root /r --prefix /p numpy", [pip_note(["numpy"], None, prefix="/p")]),
    "pip root outranks user": describe_case("pip install --user --root /r numpy",
                                            [pip_note(["numpy"], None, root="/r")]),
    "uv pip python with equals names the interpreter": describe_case(
        "uv pip install --python=/opt/py/bin/python numpy", [pip_note(["numpy"], "/opt/py/bin/python")]),
    "pip requirement and constraint files": describe_case(
        "pip install -r a.txt -c pins.txt --requirement=b.txt",
        [pip_note([], "{bin}/pip", ["a.txt", "b.txt"])]),
    "podman pull platform": describe_case("podman pull --platform linux/arm64 alpine", [image_note("alpine", "podman")]),
    "docker image pull platform with equals": describe_case(
        "docker image pull --platform=linux/amd64 -q nginx", [image_note("nginx", "docker")]),
    "docker pull with no image": describe_case("docker pull", [image_note("an image", "docker")]),
    "brew install flags are not packages": describe_case(
        "brew install --formula --quiet -v jq", [brew_note(["jq"])]),
})

# Several installs in one command: one entry per install, in command order.
_rng = random.Random(1729)
_SEPARATORS = [" && ", "; ", " || ", "\n", " | "]
for i in range(6):
    picked = _rng.sample(sorted(INSTALLERS), _rng.choice([2, 3]))
    seps = [_rng.choice(_SEPARATORS) for _ in picked[1:]]
    command = INSTALLERS[picked[0]][0] + "".join(s + INSTALLERS[p][0] for s, p in zip(seps, picked[1:]))
    INSTALL_CASES[f"chain {i + 1} of {' then '.join(picked)}"] = describe_case(
        command, [INSTALLERS[p][1] for p in picked])

# Not installs, whatever the context: no note.
for command in ["pip show numpy && pip check", "uv pip list | grep numpy", "pixi global list; pixi info",
                "docker images && podman image ls", "brew info pandoc || brew search pandoc",
                "pip wheel numpy -w dist", "uv pip compile requirements.in -o requirements.txt"]:
    INSTALL_CASES[f"not an install {command}"] = describe_case(command, [])

# Installs once missed, option values once taken for packages, and notes once
# given for what installs nothing.
INSTALL_EDGES = {
    # A pip named with its Python version (pip3.11, as python.org and Homebrew install it).
    "versioned pip3.11": ("pip3.11 install numpy", [pip_note(["numpy"], "pip3.11")]),
    # pip's general options may come before the subcommand.
    "pip option before install": ("pip -q install numpy", [pip_note(["numpy"], "{bin}/pip")]),
    "python -m pip option before install": ("python3 -m pip --disable-pip-version-check install numpy",
                                            [pip_note(["numpy"], "{bin}/python3")]),
    # sudo's own options are skipped with it.
    "sudo with an option": ("sudo -H pip install numpy", [pip_note(["numpy"], "{bin}/pip")]),
    # A short option with its value attached (-tvendor) is read.
    "pip target attached to the short option": ("pip install -tvendor requests", [pip_note(["requests"], None, target="vendor")]),
    # pixi add's --git and --branch take values: the URL and branch are not packages.
    "pixi add git url and branch": ("pixi add --pypi --git https://github.com/mahmoud/boltons.git boltons --branch main",
                                    [pixi_add_note(["boltons"])]),
    # podman pull --arch takes a value; it is not the image.
    "podman pull arch value": ("podman pull --arch arm64 alpine", [image_note("alpine", "podman")]),
    # pixi exec --spec=name is read.
    "pixi exec spec with equals": ("pixi exec --spec=ghostscript gs -v", [pixi_exec_note(["ghostscript"])]),
    # An && inside quotes does not separate commands: a commit message mentioning an install is not one.
    "install named inside a quoted argument": ('git commit -m "docs: say to run && pip install numpy"', []),
    # --dry-run installs nothing.
    "pip dry run": ("pip install --dry-run numpy", []),
    "uv pip dry run": ("uv pip install --dry-run polars", []),
    # `pip install --help` prints help and exits 0, installing nothing.
    "pip install help": ("pip install --help", []),
    # Only the --spec/-s before the command are pixi's: rg -s is case-sensitive search.
    "pixi exec option of the command run": ("pixi exec -s ripgrep rg -s TODO src", [pixi_exec_note(["ripgrep"])]),
}
for name, (command, expected) in INSTALL_EDGES.items():
    INSTALL_CASES[name] = describe_case(command, expected)

# The handler: after success the note and the log line name exactly what
# describe() does; after failure, nothing at all.
NOTE_HEAD = ("[install-notes] This command installed software. Tell the user in your report - what, where it lives, "
             "and how to remove it (also logged in {agent}/installs.log):\n")
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def _handler_success(entry):
    def check(t, r):
        e = t.names(entry)
        note = t.names(NOTE_HEAD) + f"- {e['what']}\n  where: {e['where']}\n  remove: {e['undo']}"
        t.assertEqual([{"type": "text", "text": "ok"}, {"type": "text", "text": note}], r["returned"]["content"])
        fields = r["log"].rstrip("\n").split("\t")
        t.assertRegex(fields[0], STAMP)
        t.assertEqual(["/proj", e["what"], e["where"], f"remove: {e['undo']}"], fields[1:])
    return check


for installer, (cmd, entry) in INSTALLERS.items():
    INSTALL_CASES[f"handler notes and logs {installer}"] = {
        "input": {"kind": "handler", "command": cmd, "isError": False}, "check": _handler_success(entry)}
for installer in ["uv add", "pixi exec", "podman image pull"]:
    INSTALL_CASES[f"handler is silent when {installer} fails"] = {
        "input": {"kind": "handler", "command": INSTALLERS[installer][0], "isError": True},
        "check": lambda t, r: t.assertEqual({"returned": None, "log": None}, r)}


class InstallNotesGeneratedTests(unittest.TestCase):
    """install-notes.ts: describe() over generated commands, and its handler."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            cls.bin = cls.tmp / "bin"
            cls.bin.mkdir()
            for tool in ("pip", "pip3", "python3", "python3.11"):
                write_executable(cls.bin / tool, "exit 0\n")
            cls.agent = cls.tmp / "agent"
            cls.agent.mkdir()
            inputs = {}
            for i, (name, case) in enumerate(INSTALL_CASES.items()):
                inputs[name] = dict(case["input"])
                if inputs[name]["kind"] == "handler":
                    agent = cls.tmp / f"agent{i}"
                    agent.mkdir()
                    inputs[name]["agent"] = str(agent)
            cls.inputs = inputs
            (cls.tmp / "cases.json").write_text(json.dumps(inputs))
            env = {"PATH": str(cls.bin), "HOME": str(cls.tmp), "PI_CODING_AGENT_DIR": str(cls.agent)}
            cls.results = run_node(INSTALL_RUNNER, [EXTENSIONS / "install-notes.ts", cls.tmp / "cases.json"], env, cls.tmp)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def names(self, value):
        """Fill {bin} and {agent} into an expected value (agent is the case's own for the handler)."""
        agent = self.inputs[self._testMethodDoc]["agent"] if "agent" in self.inputs.get(self._testMethodDoc, {}) \
            else self.agent
        text = json.dumps(value).replace("{bin}", str(self.bin)).replace("{agent}", str(agent))
        return json.loads(text)


generate(InstallNotesGeneratedTests, INSTALL_CASES)


# ==========================================================================
# skill-router
# ==========================================================================

ROUTER_RUNNER = r"""
const [source, casesPath, agent] = process.argv.slice(1);
const fs = await import("node:fs");
process.env.PI_CODING_AGENT_DIR = agent;
const mod = await import(source);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const out = {};
for (const [id, c] of Object.entries(cases)) {
  if (c.kind === "routes") { out[id] = mod.routesFor(c.prompt); continue; }
  const handlers = {};
  mod.default({ on: (e, h) => { handlers[e] = h; }, registerMessageRenderer: () => {} });
  const ctx = { sessionManager: { buildContextEntries: () => c.context ?? [], getBranch: () => [] } };
  const r = await handlers.before_agent_start({ type: "before_agent_start", prompt: c.prompt, messageType: "user" }, ctx);
  out[id] = r ? r.message.details : null;
}
console.log(JSON.stringify(out));
"""

# The table's order, which is the order routesFor returns skills in.
SKILL_ORDER = ["data-fitting", "statistics-and-significance", "uncertainty-propagation", "histogram-analysis",
               "derivation-checks", "numerical-methods", "physical-constants", "physics-documents",
               "scientific-cpp", "scientific-python", "installing-software", "containers"]

# skill -> (a request that routes to it alone, the same request in the plural).
REQUESTS = {
    "data-fitting": ("fit the peak in this spectrum", "fit the peaks in these spectra"),
    "statistics-and-significance": ("what is the p-value of this excess", "what are the p-values of these excesses"),
    "uncertainty-propagation": ("estimate the systematic uncertainty", "estimate the systematic uncertainties"),
    "histogram-analysis": ("make a histogram of the energies", "make histograms of the energies"),
    "derivation-checks": ("check the derivation in section two", "check the derivations in section two"),
    "numerical-methods": ("solve this ODE with an adaptive step", "solve these ODEs with an adaptive step"),
    "physical-constants": ("look up the physical constant", "look up the physical constants"),
    "physics-documents": ("write the lab report", "write the lab reports"),
    "scientific-cpp": ("port the loop to C++", "port the loops to C++"),
    "scientific-python": ("make a plot of the residues", "make plots of the residues"),
    "installing-software": ("the module is not installed", "the modules are not installed"),
    "containers": ("run the build in a podman container", "run the builds in podman containers"),
}

# The same request reworded around its keywords; none of these may change the route.
TRANSFORMS = {
    "upper case": str.upper,
    "title case as a question": lambda s: f"Could you {s.title()}?",
    "polite in curly quotes": lambda s: f"“Please, {s}... thanks!”",
    "task prefix then a paragraph": lambda s: f"Task: Some background first.\n\n{s}\n",
    "among unicode words": lambda s: f"Voilà — {s} — merci, café ☕",
}

ROUTER_CASES = {}


def route_case(prompt, expected, bug=None):
    return {"input": {"kind": "routes", "prompt": prompt},
            "check": lambda t, r: t.assertEqual(expected, r, prompt), "bug": bug}


for skill, (singular, plural) in REQUESTS.items():
    ROUTER_CASES[f"{skill} plain"] = route_case(singular, [skill])
    ROUTER_CASES[f"{skill} plural"] = route_case(plural, [skill])
    for name, transform in TRANSFORMS.items():
        ROUTER_CASES[f"{skill} {name}"] = route_case(transform(singular), [skill])

# A keyword glued to letters of another script is not a word: the boundary is Unicode-aware.
ROUTER_CASES.update({
    "keyword glued to greek letters is not a word": route_case("αβhistogramγ of it", []),
    "keyword glued to cjk is not a word": route_case("请histogram", []),
    "keyword before cjk punctuation is a word": route_case("请画 histogram。", ["histogram-analysis"]),
    "keyword beside an emoji is a word": route_case("📊histogram📊", ["histogram-analysis"]),
    "keyword after an accented word is a word": route_case("déjà histogramme histogram", ["histogram-analysis"]),
    "sigma with a decimal significance": route_case("a 2.5σ tension", ["statistics-and-significance"]),
    "sigma glued to a letter is not a significance": route_case("a 5σx run", []),
})

# The guarded words, in everyday software use: no route, in any of three casings.
SOFTWARE = [
    "the dress fits her perfectly", "does the table fit on one page", "make Panel derive from Widget",
    "simulate a slow network in the test suite", "integrate with the payment gateway",
    "make the retry count a constant", "raise the upper limit on uploads", "list the root files in the repo",
    "record a root macro in the editor", "improve the efficiency of the query", "calibrate the monitor colours",
    "report the bug to the vendor", "the lifetime of the cache entry", "propagate the error to the caller",
    "the bins in the kitchen are full",
]
for prompt in SOFTWARE:
    ROUTER_CASES[f"software {prompt}"] = route_case(prompt, [])
    ROUTER_CASES[f"software upper {prompt}"] = route_case(prompt.upper(), [])
# CERN's ROOT is told apart by its capitals alone, with the rest of the phrase in lower case.
ROUTER_CASES.update({
    "capital ROOT files route to histograms": route_case("list the ROOT files in the repo", ["histogram-analysis"]),
    "capital ROOT macro routes to cpp": route_case("record a ROOT macro in the editor", ["scientific-cpp"]),
})

# Invariants of routesFor: each skill once, in table order, however often and
# in whatever order the request names it.
ROUTER_CASES.update({
    "both histogram entries give one histogram skill": route_case(
        "open the ROOT file and make a histogram", ["histogram-analysis"]),
    "both cpp entries give one cpp skill": route_case("a ROOT macro in C++", ["scientific-cpp"]),
    "a request repeated gives its skill once": route_case(
        "make a plot; make a plot; make a plot", ["scientific-python"]),
})
_rng = random.Random(42)
for i in range(10):
    picked = _rng.sample(SKILL_ORDER, _rng.randint(2, 6))
    joined = ". ".join(REQUESTS[s][_rng.randint(0, 1)] for s in picked)
    ROUTER_CASES[f"combination {i + 1} of {len(picked)} comes back in table order"] = route_case(
        joined, [s for s in SKILL_ORDER if s in picked])


# The session message: of the skills routed and not yet present, the first two
# are inlined and the next two named, never more.
def message_case(picked, present=()):
    prompt = ". ".join(REQUESTS[s][0] for s in picked)
    context = [{"type": "custom_message", "customType": "skill-routing",
                "details": {"inlined": list(present), "named": []}}] if present else []
    left = [s for s in SKILL_ORDER if s in picked and s not in present][:4]
    expected = {"inlined": left[:2], "named": left[2:]} if left else None
    return {"input": {"kind": "message", "prompt": prompt, "context": context},
            "check": lambda t, r: t.assertEqual(expected, r)}


for k in (1, 2, 3, 4, 5, 7, 12):
    ROUTER_CASES[f"message for {k} matching skills"] = message_case(SKILL_ORDER[-k:])
ROUTER_CASES["message skips two present and caps the rest"] = message_case(
    SKILL_ORDER[:7], present=SKILL_ORDER[:2])
ROUTER_CASES["message skips a present skill in the middle"] = message_case(
    SKILL_ORDER[3:8], present=[SKILL_ORDER[5]])
ROUTER_CASES["message with every match present is nothing"] = message_case(
    SKILL_ORDER[2:4], present=SKILL_ORDER[2:4])


class SkillRouterGeneratedTests(unittest.TestCase):
    """skill-router.ts: generated requests through routesFor and before_agent_start."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            skills = cls.tmp / "agent/skills"
            skills.mkdir(parents=True)
            for skill in SKILLS.iterdir():
                (skills / skill.name).symlink_to(skill)
            (cls.tmp / "cases.json").write_text(json.dumps({n: c["input"] for n, c in ROUTER_CASES.items()}))
            cls.results = run_node(ROUTER_RUNNER, [EXTENSIONS / "skill-router.ts", cls.tmp / "cases.json",
                                                   cls.tmp / "agent"],
                                   {"PATH": "/usr/bin:/bin", "HOME": str(cls.tmp)}, cls.tmp)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


generate(SkillRouterGeneratedTests, ROUTER_CASES)


# ==========================================================================
# todo
# ==========================================================================

TODO_STUBS = {
    "@earendil-works/pi-ai": "export const StringEnum = (values, options) => ({ enum: values, ...options });",
    "@earendil-works/pi-tui": (
        "export class Text { constructor(text, x, y) { this.text = text; } }\n"
        "export const matchesKey = (data, key) => false;\n"
        "export const truncateToWidth = (s, width) => s;\n"),
    "typebox": "const f = (...a) => ({ a }); export const Type = { Object: f, String: f, Optional: f, Number: f, Boolean: f };",
}

# Runs each sequence against one fresh instance. The branch is the session:
# each result is appended to it, `tree` cuts it back to its first n entries
# (navigating to an earlier point) and `start` rebuilds from it as a resume does.
TODO_RUNNER = r"""
const [source, casesPath] = process.argv.slice(1);
const fs = await import("node:fs");
const mod = await import(source);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const theme = { fg: (c, s) => `<${c}>${s}</>`, bold: (s) => s };
const out = {};
for (const [id, steps] of Object.entries(cases)) {
  const handlers = {}; let tool; const commands = {};
  mod.default({ on: (e, h) => { handlers[e] = h; }, registerTool: (t) => { tool = t; }, registerCommand: (n, d) => { commands[n] = d; } });
  let branch = [];
  const ctx = { sessionManager: { getBranch: () => branch } };
  const got = [];
  for (const s of steps) {
    if (s.op === "exec") {
      const r = await tool.execute("id", s.params, undefined, undefined, ctx);
      branch.push({ type: "message", message: { role: "toolResult", toolName: "todo", details: r.details } });
      got.push({ text: r.content[0].text, details: JSON.parse(JSON.stringify(r.details)) });
    } else if (s.op === "noise") {
      branch.push({ type: "message", message: { role: "toolResult", toolName: "bash", details: { todos: [], nextId: 99 } } });
      branch.push({ type: "label", label: "x" });
    } else if (s.op === "tree") {
      branch = branch.slice(0, s.keep);
      await handlers.session_tree({}, ctx);
    } else if (s.op === "start") {
      await handlers.session_start({}, ctx);
    }
  }
  let lines = null;
  await commands.todos.handler("", { mode: "tui", ui: { custom: async (factory) => { lines = factory({}, theme, {}, () => {}).render(40); } } });
  out[id] = { got, lines };
}
console.log(JSON.stringify(out));
"""


class TodoModel:
    """The list as the tool should keep it."""

    def __init__(self):
        self.todos, self.next = [], 1

    def details(self, action, error=None):
        d = {"action": action, "todos": [dict(t) for t in self.todos], "nextId": self.next}
        if error:
            d["error"] = error
        return d

    def apply(self, params):
        action = params["action"]
        if action == "list":
            text = "\n".join(f"[{'x' if t['done'] else ' '}] #{t['id']}: {t['text']}" for t in self.todos) or "No todos"
            return text, self.details("list")
        if action == "add":
            if not params.get("text"):
                return "Error: text required for add", self.details("add", "text required")
            self.todos.append({"id": self.next, "text": params["text"], "done": False})
            self.next += 1
            return f"Added todo #{self.next - 1}: {params['text']}", self.details("add")
        if action == "toggle":
            if "id" not in params:
                return "Error: id required for toggle", self.details("toggle", "id required")
            todo = next((t for t in self.todos if t["id"] == params["id"]), None)
            if not todo:
                return f"Todo #{params['id']} not found", self.details("toggle", f"#{params['id']} not found")
            todo["done"] = not todo["done"]
            return f"Todo #{todo['id']} {'completed' if todo['done'] else 'uncompleted'}", self.details("toggle")
        if action == "clear":
            count, self.todos, self.next = len(self.todos), [], 1
            return f"Cleared {count} todos", self.details("clear")
        return f"Unknown action: {action}", self.details("list", f"unknown action: {action}")

    def lines(self):
        head = "<borderMuted>───</><accent> Todos </><borderMuted>" + "─" * 30 + "</>"
        body = ["  <dim>No todos yet. Ask the agent to add some!</>"] if not self.todos else [
            f"  <muted>{sum(t['done'] for t in self.todos)}/{len(self.todos)} completed</>", "",
            *(f"  {'<success>✓</>' if t['done'] else '<dim>○</>'} <accent>#{t['id']}</> "
              f"{'<dim>' if t['done'] else '<text>'}{t['text']}</>" for t in self.todos)]
        return ["", head, "", *body, "", "  <dim>Press Escape to close</>", ""]


TEXTS = ["write the abstract", "fit run 7", "plot χ² vs mass", "check units", "  spaced  ", "naïve café",
         "a #hash", "", "[x] fake box"]


def todo_sequence(rng, length):
    """Random steps and what the model predicts for each exec, replayed with branch cuts."""
    steps = []
    for _ in range(length):
        roll = rng.random()
        if roll < 0.38:
            text = rng.choice(TEXTS)
            steps.append({"op": "exec", "params": {"action": "add", **({"text": text} if text or rng.random() < 0.5 else {})}})
        elif roll < 0.62:
            params = {"action": "toggle"}
            if rng.random() > 0.08:
                params["id"] = rng.randint(0, 6)
            steps.append({"op": "exec", "params": params})
        elif roll < 0.70:
            steps.append({"op": "exec", "params": {"action": "remove", "id": rng.randint(1, 3)}})
        elif roll < 0.76:
            steps.append({"op": "exec", "params": {"action": "clear"}})
        elif roll < 0.84:
            steps.append({"op": "exec", "params": {"action": "list"}})
        elif roll < 0.88:
            steps.append({"op": "noise"})
        elif roll < 0.95:
            steps.append({"op": "tree", "keep": None})  # filled in below, once the branch length is known
        else:
            steps.append({"op": "start"})
    # Replay against the model: the branch holds each result's details.
    model, branch, expected = TodoModel(), [], []
    for s in steps:
        if s["op"] == "exec":
            text, details = model.apply(s["params"])
            branch.append(("todo", details))
            expected.append({"text": text, "details": details})
        elif s["op"] == "noise":
            branch += [("bash", None), ("label", None)]
        else:
            if s["op"] == "tree":
                s["keep"] = rng.randint(0, len(branch))
                branch = branch[:s["keep"]]
            model = TodoModel()
            for tool, details in branch:
                if tool == "todo":
                    model.todos, model.next = [dict(t) for t in details["todos"]], details["nextId"]
    return steps, expected, model.lines()


TODO_CASES = {}
_rng = random.Random(2718)
for i in range(32):
    steps, expected, lines = todo_sequence(_rng, _rng.randint(5, 16))
    ops = "".join(s["params"]["action"][0] if s["op"] == "exec" else {"noise": "N", "tree": "T", "start": "S"}[s["op"]]
                  for s in steps)
    TODO_CASES[f"sequence {i + 1:02d} {ops}"] = {
        "input": steps,
        "check": lambda t, r, expected=expected, lines=lines: (
            t.assertEqual(expected, r["got"]), t.assertEqual(lines, r["lines"]))}


class TodoGeneratedTests(unittest.TestCase):
    """todo.ts: random action sequences with branch cuts, against TodoModel."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            for package, source in TODO_STUBS.items():
                stub_package(cls.tmp, package, source)
            shutil.copy(EXTENSIONS / "todo.ts", cls.tmp / "todo.ts")
            (cls.tmp / "cases.json").write_text(json.dumps({n: c["input"] for n, c in TODO_CASES.items()}))
            cls.results = run_node(TODO_RUNNER, [cls.tmp / "todo.ts", cls.tmp / "cases.json"],
                                   {"PATH": "/usr/bin:/bin", "HOME": str(cls.tmp)}, cls.tmp)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


generate(TodoGeneratedTests, TODO_CASES)


# ==========================================================================
# view-outputs
# ==========================================================================

# A stand-in for the mupdf package. A file's text says what it is: "PDF <pages>"
# or "IMG <width> <height>". Every page loaded is recorded, so a test sees which
# pages the extension chose, not only how many images came back.
MUPDF_STUB = r"""
const words = (bytes) => Buffer.from(bytes).toString("utf8").trim().split(/\s+/);
globalThis.__loaded = [];
export class Image {
  constructor(bytes) { const w = words(bytes); if (w[0] !== "IMG") throw new Error("not an image"); this.w = +w[1]; this.h = +w[2]; }
  getWidth() { return this.w; } getHeight() { return this.h; } destroy() {}
}
export const Document = {
  openDocument(bytes, name) {
    const w = words(bytes);
    const pages = w[0] === "PDF" ? +w[1] : 1;
    return {
      countPages: () => pages,
      loadPage: (i) => {
        globalThis.__loaded.push(i);
        return {
          getBounds: () => [0, 0, 300, 200],
          toPixmap: () => ({ asPNG: () => new Uint8Array([i]), asJPEG: () => new Uint8Array([i]), destroy() {} }),
          toStructuredText: () => ({ asText: () => `words on page ${i + 1}` }),
          destroy() {},
        };
      },
      destroy() {},
    };
  },
};
export const Matrix = { scale: (a, b) => [a, 0, 0, b, 0, 0] };
export const ColorSpace = { DeviceRGB: "rgb" };
"""

VIEW_RUNNER = r"""
const [source, casesPath, base] = process.argv.slice(1);
const fs = await import("node:fs");
const mod = await import(source);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const out = {};
let n = 0;
for (const [id, c] of Object.entries(cases)) {
  const cwd = `${base}/case${++n}`;
  fs.mkdirSync(cwd);
  const handlers = {}; let tool;
  mod.default({ on: (e, h) => { handlers[e] = h; }, registerTool: (t) => { tool = t; } });
  const ctx = { cwd, model: { input: ["text", "image"] } };
  globalThis.__loaded = [];
  let result;
  if (c.kind === "view") {
    fs.writeFileSync(`${cwd}/doc.pdf`, `PDF ${c.count}`);
    const params = { path: "doc.pdf", ...(c.pages !== null ? { pages: c.pages } : {}), ...(c.text === false ? { text: false } : {}) };
    result = await tool.execute("v", params, undefined, undefined, ctx);
  } else {
    await handlers.tool_call({ toolCallId: "b", toolName: "bash", input: { command: "make figures" } }, ctx);
    for (const [name, body] of Object.entries(c.files)) fs.writeFileSync(`${cwd}/${name}`, body);
    result = await handlers.tool_result({ toolCallId: "b", toolName: "bash", input: { command: "make figures" },
      content: [{ type: "text", text: "made" }], isError: false }, ctx);
  }
  const content = result?.content ?? [];
  out[id] = { texts: content.filter((x) => x.type === "text").map((x) => x.text),
              images: content.filter((x) => x.type === "image").length, loaded: globalThis.__loaded };
}
console.log(JSON.stringify(out));
"""


def js_number(text):
    """JavaScript's Number() of a trimmed, dash-free string."""
    s = text.strip()
    if s == "":
        return 0.0
    for prefix, radix, digits in (("0x", 16, "0-9a-f"), ("0o", 8, "0-7"), ("0b", 2, "01")):
        if re.fullmatch(f"{prefix}[{digits}]+", s, re.IGNORECASE):
            return float(int(s[2:], radix))
    if re.fullmatch(r"\+?(\d+\.?\d*|\.\d+)([eE][+]?\d+)?", s):
        return float(s)
    if s in ("Infinity", "+Infinity"):
        return math.inf
    return math.nan


def page_list(spec, count):
    """Reference for pageList(): the 0-based pages a `pages` spec selects, sorted."""
    if spec is None or not spec.strip():
        return list(range(count))
    out = set()
    for part in spec.split(","):
        pieces = [p.strip() for p in part.split("-")]
        a, b = pieces[0], pieces[1] if len(pieces) > 1 else None
        if a == "" and b is None:
            continue  # "3," means page 3: an empty part selects nothing
        start = js_number(a) if a else 1
        end = start if b is None else (js_number(b) if b else count)
        if not all(math.isfinite(x) and float(x).is_integer() for x in (start, end)):
            continue
        out.update(range(max(1, int(start)) - 1, min(count, int(end))))
    return sorted(out)


def spans(pages):
    parts, i = [], 0
    while i < len(pages):
        j = i
        while j + 1 < len(pages) and pages[j + 1] == pages[j] + 1:
            j += 1
        parts.append(str(pages[i]) if i == j else f"{pages[i]}-{pages[j]}")
        i = j + 1
    return ",".join(parts)


def header(name, count, shown):
    """Reference for header(); shown is 1-based."""
    if count <= 1:
        return f"{name}:"
    if not shown:
        return f"{name}: {count} pages, showing no pages."
    more = f' - view it with pages "{spans(list(range(shown[-1] + 1, count + 1)))}" for the rest' if shown[-1] < count else ""
    return f"{name}: {count} pages, showing {'pages' if len(shown) > 1 else 'page'} {spans(shown)}{more}."


def view_case(count, spec, text=True):
    shown = page_list(spec, count)[:12]
    page_texts = [f"--- page {i + 1} of {count}" + (f" - text layer:\nwords on page {i + 1}" if text else " (no text layer)")
                  for i in shown]
    expected = {"texts": [header("doc.pdf", count, [i + 1 for i in shown]), *page_texts],
                "images": len(shown), "loaded": shown}
    return {"input": {"kind": "view", "count": count, "pages": spec, "text": text},
            "check": lambda t, r: t.assertEqual(expected, r, f"pages={spec!r} of {count}")}


VIEW_CASES = {}
_rng = random.Random(31415)


def _spec_part(rng, count):
    a, b = rng.randint(0, count + 2), rng.randint(0, count + 2)
    return rng.choice([f"{a}", f"{a}-{b}", f"{a}-", f"-{b}", "-", f" {a} - {b} ", f"{a}.5", f"{a}.0",
                       f"0x{a:x}", f"{a}e0", "x", f"{a}-{b}-{a}", f"+{a}", "Infinity"])


for i in range(32):
    count = _rng.choice([1, 4, 9, 15, 20])
    spec = ",".join(_spec_part(_rng, count) for _ in range(_rng.randint(1, 3)))
    VIEW_CASES[f"pages spec {i + 1:02d} {spec!r} of {count}"] = view_case(count, spec, text=_rng.random() > 0.25)
for count in (15, 20):
    VIEW_CASES[f"no spec on {count} pages shows twelve"] = view_case(count, None)
    VIEW_CASES[f"blank spec on {count} pages shows twelve"] = view_case(count, "  ")
VIEW_CASES["a page twice is shown once"] = view_case(9, "3,3,2-3")
VIEW_CASES["a reversed range shows nothing"] = view_case(9, "7-2")
# An empty part of a list ("3," or "2,,5") selects nothing: page 1 is not shown unless asked for.
for spec in ("3,", "2,,5", " ,4"):
    VIEW_CASES[f"an empty part in {spec!r} selects nothing"] = view_case(9, spec)


def auto_case(files):
    """files: name -> pages (an .png is one small image). The model of the eight-image budget."""
    images, lines, skipped, headers = 0, [], [], []
    for name in sorted(files):
        room = 8 - images
        if room <= 0:
            skipped.append(name)
            continue
        if name.endswith(".png"):
            images += 1
            lines.append(name)
            headers.append(f"{name}:")
            continue
        count = files[name]
        shown = list(range(1, min(count, room, 4) + 1))
        images += len(shown)
        lines.append(name + (f" (pages {','.join(map(str, shown))} of {count})" if count > 1 else ""))
        headers.append(header(name, count, shown))
    first = f"[view-outputs] This command wrote {len(files)} figure/document file(s). Attached below: {'; '.join(lines)}."
    last = f"Not attached here - {'; '.join(skipped)}. Look at what can be shown with the view tool." if skipped else None
    bodies = {n: ("IMG 120 80" if n.endswith(".png") else f"PDF {p}") for n, p in files.items()}

    def check(t, r):
        note = r["texts"][1].split("\n")
        t.assertEqual(first, note[0])
        t.assertEqual(last, note[2] if len(note) > 2 else None)
        t.assertEqual(images, r["images"])
        t.assertEqual(headers, [x for x in r["texts"][2:] if not x.startswith("--- page")])
    return {"input": {"kind": "auto", "files": bodies}, "check": check}


_rng = random.Random(161803)
for i in range(12):
    files = {}
    for j in range(_rng.randint(2, 6)):
        if _rng.random() < 0.4:
            files[f"fig{j}.png"] = 1
        else:
            files[f"doc{j}.pdf"] = _rng.randint(1, 9)
    VIEW_CASES[f"budget {i + 1:02d} " + " ".join(f"{n}={p}" for n, p in sorted(files.items()))] = auto_case(files)


class ViewOutputsGeneratedTests(unittest.TestCase):
    """view-outputs.ts: page specs against page_list(), and the image budget against auto_case()."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            ext = cls.tmp / "ext"
            ext.mkdir()
            stub_package(ext, "typebox", "const f = (...a) => ({ a }); "
                                         "export const Type = { Object: f, String: f, Optional: f, Boolean: f };")
            stub_package(ext, "mupdf", MUPDF_STUB)
            shutil.copy(EXTENSIONS / "view-outputs.ts", ext / "view-outputs.ts")
            (cls.tmp / "work").mkdir()
            (cls.tmp / "cases.json").write_text(json.dumps({n: c["input"] for n, c in VIEW_CASES.items()}))
            cls.results = run_node(VIEW_RUNNER, [ext / "view-outputs.ts", cls.tmp / "cases.json", cls.tmp / "work"],
                                   {"PATH": "/usr/bin:/bin", "HOME": str(cls.tmp), "TMPDIR": str(cls.tmp)}, cls.tmp)
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


generate(ViewOutputsGeneratedTests, VIEW_CASES)


# ==========================================================================
# pinned-instructions
# ==========================================================================

PINNED_RUNNER = r"""
const [source, casesPath] = process.argv.slice(1);
const fs = await import("node:fs");
const mod = await import(source);
const cases = JSON.parse(fs.readFileSync(casesPath, "utf8"));
const out = {};
for (const [id, c] of Object.entries(cases)) {
  const handlers = {}; const tools = {};
  mod.default({ on: (e, h) => { handlers[e] = h; }, registerTool: (t) => { tools[t.name] = t; } });
  const ctx = { cwd: c.cwd };
  const got = [];
  for (const s of c.steps) {
    if (s.op === "pin") got.push((await tools.pin_instruction.execute("i", { instruction: s.arg }, undefined, undefined, ctx)).content[0].text);
    else if (s.op === "unpin") got.push((await tools.unpin_instruction.execute("i", { number: s.arg }, undefined, undefined, ctx)).content[0].text);
    else if (s.op === "start" || s.op === "compact") { await handlers[`session_${s.op}`]({}, ctx); got.push(null); }
    else if (s.op === "prompt") {
      const event = { systemPromptOptions: { sections: { tools: "t" } } };
      handlers.before_agent_start(event, ctx);
      got.push(event.systemPromptOptions.sections.pinned_instructions ?? null);
    }
  }
  out[id] = got;
}
console.log(JSON.stringify(out));
"""


def render_pins(pins):
    return "\n".join(["# Pinned instructions", "",
                      "Standing instructions the user gave for this project. They hold for the whole",
                      "session and outrank anything a summary of earlier conversation says:", "",
                      *[f"{i + 1}. {pin}" for i, pin in enumerate(pins)]])


def js_num(x):
    return str(int(x)) if float(x).is_integer() else repr(x)


class PinModel:
    """The pin file, and the copy of it in the system prompt (None until first read)."""

    def __init__(self):
        self.file, self.prompt = [], None

    def step(self, op, arg):
        if op == "pin":
            text = " ".join(arg.split())
            if not text:
                return "Nothing to pin: the instruction is empty."
            if len(text) > 400:
                return "Not pinned: keep a pin under 400 characters - one sentence."
            if text in self.file:
                return f"Already pinned:\n{render_pins(self.file)}"
            self.file = [*self.file, text]
            return f"Pinned - it holds from now on, through compaction.\n{render_pins(self.file)}"
        if op == "unpin":
            index = math.trunc(arg) - 1
            if index < 0 or index >= len(self.file):
                return f"No pinned instruction {js_num(arg)}." + (f"\n{render_pins(self.file)}" if self.file else "")
            removed = self.file[index]
            self.file = self.file[:index] + self.file[index + 1:]
            self.prompt = list(self.file)
            return f"Removed: {removed}" + (f"\n{render_pins(self.file)}" if self.file else "\nNo instructions pinned.")
        if op in ("start", "compact"):
            self.prompt = list(self.file)
            return None
        if self.prompt is None:
            self.prompt = list(self.file)
        return render_pins(self.prompt) if self.prompt else None


INSTRUCTIONS = ["use natural units", "run7.csv is the calibrated file", "do not touch analysis/",
                "  use   natural units ", "quote errors to two significant figures", "", "   ", "x" * 401,
                "plots in PDF only", "use\tnatural\nunits"]

PINNED_CASES = {}
_rng = random.Random(1123)
for i in range(16):
    model, steps, expected = PinModel(), [], []
    for _ in range(_rng.randint(6, 14)):
        roll = _rng.random()
        if roll < 0.4:
            step = ("pin", _rng.choice(INSTRUCTIONS))
        elif roll < 0.6:
            step = ("unpin", _rng.choice([-1, 0, 1, 1, 2, 3, 4, 1.7, 2.5]))
        elif roll < 0.7:
            step = ("compact", None)
        elif roll < 0.75:
            step = ("start", None)
        else:
            step = ("prompt", None)
        steps.append({"op": step[0], "arg": step[1]})
        expected.append(model.step(*step))
    PINNED_CASES[f"sequence {i + 1:02d} " + "".join(s["op"][0:2] for s in steps)] = {
        "input": {"steps": steps},
        "check": lambda t, r, expected=expected: t.assertEqual(expected, r)}


class PinnedInstructionsGeneratedTests(unittest.TestCase):
    """pinned-instructions.ts: random pin/unpin/compact/prompt sequences against PinModel."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            stub_package(cls.tmp, "typebox", "const f = (o) => o ?? {}; "
                                             "export const Type = { Object: f, String: f, Number: f };")
            shutil.copy(EXTENSIONS / "pinned-instructions.ts", cls.tmp / "pinned-instructions.ts")
            inputs = {}
            for i, (name, case) in enumerate(PINNED_CASES.items()):
                project = cls.tmp / f"project{i}"
                project.mkdir()
                inputs[name] = {**case["input"], "cwd": str(project)}
            (cls.tmp / "cases.json").write_text(json.dumps(inputs))
            cls.results = run_node(PINNED_RUNNER, [cls.tmp / "pinned-instructions.ts", cls.tmp / "cases.json"],
                                   {"PATH": "/usr/bin:/bin", "HOME": str(cls.tmp),
                                    "PI_CODING_AGENT_DIR": str(cls.tmp / "agent")}, cls.tmp)
            # Each project's pins went to its own file under agent/pinned.
            cls.files = sorted(p.name for p in (cls.tmp / "agent/pinned").iterdir()) \
                if (cls.tmp / "agent/pinned").exists() else []
            cls.keys = sorted(hashlib.sha256(v["cwd"].encode()).hexdigest()[:16] + ".md" for v in inputs.values())
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_pin_file_is_one_of_the_projects(self):
        # Only projects that ever pinned have a file, and every file is a project's hash.
        self.assertTrue(set(self.files) <= set(self.keys), (self.files, self.keys))


generate(PinnedInstructionsGeneratedTests, PINNED_CASES)


# ==========================================================================
# elm-shim
# ==========================================================================

# Health stubs run inside the node process, on loopback ports. A case names a
# stub (or a closed port) and its environment; the module is imported afresh
# per case because it reads the environment at import. For `spawn` cases the
# "python" is a script that records its arguments; the stub on that port starts
# answering once the record exists, as a real shim would once started.
SHIM_RUNNER = r"""
import { createServer } from "node:http";
import { existsSync, readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const [source, casesPath] = process.argv.slice(1);
const cases = JSON.parse(readFileSync(casesPath, "utf8"));
const listen = (handler, port = 0) => new Promise((done) => { const s = createServer(handler); s.listen(port, "127.0.0.1", () => done(s)); });
const reply = (status, body, type = "application/json") => (req, res) => { res.writeHead(status, { "content-type": type }); res.end(body); };
const STUBS = {
  ok: reply(200, JSON.stringify({ shim: "elm-pi", pid: 1 })),
  okExtra: reply(200, JSON.stringify({ shim: "elm-pi", version: 7, upstream: "x" })),
  upper: reply(200, JSON.stringify({ shim: "ELM-PI" })),
  other: reply(200, JSON.stringify({ shim: "elm-pi-legacy" })),
  empty: reply(200, "{}"),
  nullBody: reply(200, "null"),
  array: reply(200, JSON.stringify(["elm-pi"])),
  text: reply(200, "elm-pi", "text/plain"),
  notFound: reply(404, JSON.stringify({ shim: "elm-pi" })),
  unavailable: reply(503, JSON.stringify({ shim: "elm-pi" })),
  html: reply(200, "<html>elm-pi</html>", "text/html"),
};
const servers = {};
for (const [name, handler] of Object.entries(STUBS)) servers[name] = await listen(handler);
const out = {};
const KEYS = ["ELM_SHIM_PORT", "ELM_SHIM_PATH", "ELM_LLAMA_MODEL_ID", "PI_CODING_AGENT_DIR", "ELM_PI_PYTHON", "MARK"];
let n = 0;
for (const [id, c] of Object.entries(cases)) {
  for (const key of KEYS) delete process.env[key];
  const port = c.stub ? servers[c.stub].address().port : c.port;
  Object.assign(process.env, c.env, { ELM_SHIM_PORT: String(port) });
  let late, poll, seenAt = null;
  const t0 = Date.now();
  if (c.spawn) poll = setInterval(async () => {
    if (!late && existsSync(c.env.MARK)) { seenAt = Date.now() - t0; late = true; late = await listen(STUBS.ok, port); }
  }, 20);
  const mod = await import(pathToFileURL(source).href + "?" + ++n);
  const providers = [], notes = [], handlers = {};
  await mod.default({ registerProvider: (pid, config) => providers.push({ id: pid, config }), on: (e, h) => { handlers[e] = h; } });
  if (handlers.session_start) await handlers.session_start({}, { ui: { notify: (m, level) => notes.push([m, level]) } });
  if (poll) clearInterval(poll);
  if (late && late.close) late.close();
  // Not started within the extension's wait: allow a loaded machine a few seconds more, to tell late from never.
  for (let i = 0; c.spawn && seenAt === null && i < 60 && !existsSync(c.env.MARK); i++) await new Promise((r) => setTimeout(r, 50));
  out[id] = { providers, notes, port, seenAt, elapsed: Date.now() - t0,
              record: c.spawn && existsSync(c.env.MARK) ? readFileSync(c.env.MARK, "utf8") : null };
}
for (const s of Object.values(servers)) s.close();
console.log(JSON.stringify(out));
"""


def provider(port, model):
    return {"id": "elm-shim", "config": {
        "name": "ELM (tool-shim)", "baseUrl": f"http://127.0.0.1:{port}", "apiKey": "$ELM_API_KEY",
        "api": "openai-completions",
        "models": [{"id": model, "name": "Llama 3.3 70B (ELM, tool-shim)", "reasoning": False, "input": ["text"],
                    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, "contextWindow": 128000,
                    "maxTokens": 8192, "samplingParams": {"temperature": 0.6, "top_p": 0.9}}]}}


def registers(model):
    def check(t, r):
        t.assertEqual(([provider(r["port"], model)], []), (r["providers"], r["notes"]))
    return check


def warns(shim):
    """No provider, and one warning naming the shim path (filled from the case dir) and the port."""
    def check(t, r):
        path = shim.replace("{dir}", str(t.tmp))
        t.assertEqual(([], [[f"elm-shim: could not start {path} on :{r['port']} - Llama sub-agents unavailable", "warn"]]),
                      (r["providers"], r["notes"]))
    return check


# A path no process has on its command line, so the stale-shim pgrep finds nothing to stop.
MISSING = "{dir}/never-started/shim.py"
SHIM_CASES = {}
for stub, model in [("ok", "Llama-3.3-70B-Instruct"), ("okExtra", "meta/llama-3.3:latest")]:
    SHIM_CASES[f"health {stub} registers the provider"] = {
        "input": {"stub": stub, "env": {"ELM_SHIM_PATH": MISSING, "ELM_LLAMA_MODEL_ID": model}},
        "check": registers(model)}
SHIM_CASES["health ok without a model id keeps the template token"] = {
    "input": {"stub": "ok", "env": {"ELM_SHIM_PATH": MISSING}}, "check": registers("@LLAMA_MODEL@")}
for stub in ["upper", "other", "empty", "nullBody", "array", "text", "notFound", "unavailable", "html"]:
    # Something answers on the port but is not this install's shim: left alone, and reported.
    SHIM_CASES[f"health {stub} is not our shim"] = {
        "input": {"stub": stub, "env": {"ELM_SHIM_PATH": MISSING, "ELM_LLAMA_MODEL_ID": "m"}}, "check": warns(MISSING)}
# Nothing listening and no shim to start: the default path is beside the agent dir.
for agent, shim in [("/srv/pi/agent", "/srv/pi/shim/shim.py"), ("/srv/pi/agent/", "/srv/pi/shim/shim.py"),
                    ("rel/agent", "rel/shim/shim.py"), (None, "../shim/shim.py")]:
    env = {"PI_CODING_AGENT_DIR": agent} if agent else {}
    shown = f"{agent} with a trailing slash" if agent and agent.endswith("/") else agent
    SHIM_CASES[f"no listener default shim path from agent dir {shown}"] = {
        "input": {"port": None, "env": env}, "check": warns(shim)}
SHIM_CASES["no listener the shim path outranks the agent dir"] = {
    "input": {"port": None, "env": {"PI_CODING_AGENT_DIR": "/srv/pi/agent", "ELM_SHIM_PATH": MISSING}},
    "check": warns(MISSING)}


def spawned(model, python):
    """The shim was started as `<python> -E -S <shim>` with SHIM_PORT, then registered."""
    def check(t, r):
        t.assertEqual(f"{python.replace('{dir}', str(t.tmp))}\n-E\n-S\n{t.tmp}/spawnshim/shim.py\n{r['port']}\n", r["record"])
        if not r["providers"] and (r["seenAt"] is None or r["seenAt"] > 4000):
            # The extension waits ~5 s for a shim it started; here the interpreter itself ran later than that.
            t.skipTest(f"machine too loaded: the interpreter ran {r['seenAt'] or 'after'} ms in, past the extension's wait")
        t.assertEqual(([provider(r["port"], model)], []), (r["providers"], r["notes"]))
    return check


for label, python_env, python in [("named interpreter", "{dir}/py/fakepython", "{dir}/py/fakepython"),
                                  ("python3 on PATH", None, "{dir}/pathbin/python3"),
                                  ("empty interpreter falls back to python3", "", "{dir}/pathbin/python3")]:
    env = {"ELM_SHIM_PATH": "{dir}/spawnshim/shim.py", "ELM_LLAMA_MODEL_ID": "spawned-llama", "MARK": f"{{dir}}/mark-{slug(label)}"}
    if python_env is not None:
        env["ELM_PI_PYTHON"] = python_env
    SHIM_CASES[f"spawn with {label}"] = {"input": {"port": None, "spawn": True, "env": env},
                                         "check": spawned("spawned-llama", python)}


class ElmShimGeneratedTests(unittest.TestCase):
    """elm-shim.ts: provider or warning across health answers, paths and interpreters."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            shutil.copy(EXTENSIONS / "elm-shim.ts", cls.tmp / "elm-shim.ts")
            (cls.tmp / "package.json").write_text('{"type": "module"}')
            (cls.tmp / "spawnshim").mkdir()
            (cls.tmp / "spawnshim/shim.py").write_text("# never run: the interpreter below only records how it was called\n")
            # Records "$0", each argument and SHIM_PORT, one per line, then exits (builtins only: quick to start).
            recorder = 'printf "%s\\n" "$0" "$@" "$SHIM_PORT" > "$MARK"\n'
            for folder, name in (("py", "fakepython"), ("pathbin", "python3")):
                (cls.tmp / folder).mkdir()
                write_executable(cls.tmp / folder / name, recorder)
            # cwd is a folder of its own, so the relative default ../shim/shim.py does not exist.
            (cls.tmp / "cwd").mkdir()
            inputs = {}
            for name, case in SHIM_CASES.items():
                c = json.loads(json.dumps(case["input"]).replace("{dir}", str(cls.tmp)))
                if not c.get("stub"):
                    c["port"] = closed_port()
                inputs[name] = c
            (cls.tmp / "cases.json").write_text(json.dumps(inputs))
            cls.results = run_node(SHIM_RUNNER, [cls.tmp / "elm-shim.ts", cls.tmp / "cases.json"],
                                   {"PATH": f"{cls.tmp}/pathbin:/usr/bin:/bin", "HOME": str(cls.tmp),
                                    "NO_PROXY": "*"}, cls.tmp / "cwd")
        except BaseException:
            shutil.rmtree(cls.tmp, ignore_errors=True)
            raise

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)


generate(ElmShimGeneratedTests, SHIM_CASES)


if __name__ == "__main__":
    unittest.main()
