"""Node, bundled inside the install, and npm confined to it.

No brew, no system Node, no version conflict. On an Intel Mac `brew install
node` has no bottle and compiles V8 from source (over an hour); the official
prebuilt tarball takes seconds. It is checked against nodejs.org's published
SHASUMS256.txt, and run once before anything relies on it: a Node that cannot
start here used to surface three steps later as "npm is not isolated to this
install".
"""

import os
import re
import shutil
import tempfile

from elmboot import console, installenv
from elmboot.run import Stop

NPM_REGISTRY = "https://registry.npmjs.org/"
NPM_CLI = os.path.join(".node", "lib", "node_modules", "npm", "bin", "npm-cli.js")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def wanted_version(run):
    """The Node this install runs on.

    Not NODE_VERSION: official Node container images and some CI runners
    export that for their own Node, without the leading v, and it used to be
    read here.
    """
    version = run.env.get("ELM_PI_NODE_VERSION") or installenv.config_value(
        run.root, run.env, "nodeVersion")
    if not re.match(r"^v[0-9].*\.[0-9].*\.[0-9]", version):
        console.die('Node version "%s" is not of the form v24.1.0' % version)
    return version


def platform():
    """nodejs.org's names for this machine: (os, arch)."""
    system, machine = os.uname().sysname, os.uname().machine
    names = {"Darwin": "darwin", "Linux": "linux"}
    if system not in names:
        console.die("unsupported OS: %s" % system)
    if machine in ("x86_64", "amd64"):
        return names[system], "x64"
    if machine in ("arm64", "aarch64"):
        return names[system], "arm64"
    console.die("unsupported architecture: %s" % machine)


def installed_version(run):
    return console.output([run.node(), "--version"], env=run.env)


def ensure(run, version):
    """Phase 1: the pinned Node in .node, and npm proved to be this install's."""
    fetch(run, version)
    confirm(run)


def fetch(run, version):
    """The pinned Node, downloaded unless it is the one already there."""
    console.say("Node " + version)
    if os.access(run.node(), os.X_OK) and installed_version(run) == version:
        console.note("already present: " + installed_version(run))
    else:
        _download(run, version)


def confirm(run):
    """node and npm are this install's, asked rather than assumed."""
    # install_environment already put .node/bin first; prove it rather than assume it.
    found = shutil.which("node", path=run.env.get("PATH", "")) or ""
    if found != run.node():
        console.die("node resolves to %s, not the bundled %s" % (found, run.node()))
    if not os.path.isfile(run.path(NPM_CLI)):
        console.die("the bundled npm is missing from .node - delete .node and re-run")
    problem = npm_problem(run)
    if problem:
        console.die("npm is not isolated to this install: " + problem)
    console.note("npm: config/npmrc, cache .npm-cache, global prefix .node "
                 "(nothing from ~/.npmrc or ~/.npm)")


def _download(run, version):
    system, arch = platform()
    archive = "node-%s-%s-%s.tar.gz" % (version, system, arch)
    folder = run.temp(tempfile.mkdtemp())
    console.note("downloading " + archive)
    base = "https://nodejs.org/dist/%s/" % version
    for name in (archive, "SHASUMS256.txt"):
        run.must(["curl", "-q", "-fsSL"] + run.retry + ["-o", os.path.join(folder, name),
                                                       base + name])
    # The exact file's line - not the .tar.xz beside it.
    want = ""
    with open(os.path.join(folder, "SHASUMS256.txt"), encoding="utf-8", errors="replace") as sums:
        for line in sums:
            fields = line.split()
            if len(fields) >= 2 and fields[1].lstrip("*") == archive:
                want = fields[0]
                break
    got = installenv.sha256_of(os.path.join(folder, archive))
    if not want or want != got:
        console.die("checksum mismatch for " + archive)
    target = run.path(".node")
    shutil.rmtree(target, ignore_errors=True)
    os.makedirs(target)
    run.must(["tar", "-xzf", os.path.join(folder, archive), "-C", target, "--strip-components=1"])
    # Run it before anything relies on it.
    status, says = run.capture([run.node(), "--version"], merge=True)
    if status != 0:
        console.die("the downloaded Node does not run on this system: " + says)
    console.note("installed " + says)


def npm(run, arguments, cwd=None):
    """The bundled npm, by the bundled node, by path: never an `npm` found on
    PATH, whose `#!/usr/bin/env node` line would pick up whichever node comes
    first. A failure ends the run with npm's own message."""
    run.must([run.node(), run.path(NPM_CLI)] + list(arguments), cwd=cwd)


def npm_problem(run):
    """Why npm is not confined to this install, or "".

    Asked of npm rather than trusted from the variables. cache, prefix and
    userconfig are "protected" and npm will not print them, so the global
    prefix is checked through `npm prefix -g` instead.
    """
    command = [run.node(), run.path(NPM_CLI)]
    prefix = console.output(command + ["prefix", "-g"], cwd=run.root, env=run.env, default=None)
    if prefix is None:
        return "npm does not run"
    # npm prints UUID-shaped path segments as *** (it redacts them as possible
    # tokens), so compare with the same redaction applied to what we expect.
    if UUID.sub("***", prefix) != UUID.sub("***", run.path(".node")):
        return "npm global prefix is %s, not %s" % (prefix, run.path(".node"))
    listed = console.output(command + ["config", "list", "-l", "--json"], cwd=run.root,
                            env=run.env, default=None)
    if listed is None:
        return "npm config does not load"
    import json
    try:
        config = json.loads(listed)
    except ValueError:
        return "npm config does not load"
    for key, value in (("registry", NPM_REGISTRY), ("ignore-scripts", True),
                       ("globalconfig", "/dev/null")):
        if config.get(key) != value:
            return "npm %s is %r, not %r" % (key, config.get(key), value)
    return ""


__all__ = ["ensure", "npm", "npm_problem", "wanted_version", "installed_version", "Stop"]
