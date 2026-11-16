"""The install's own tools, ahead of whatever the machine has.

The agent's bash tool inherits this PATH, so what is on it is what the agent's
commands run. Four things are arranged here:

* the agent's Python (agent/python/env), built by bootstrap.sh with the analysis
  stack - but only when the researcher did not start pi from an environment of
  their own: an active venv, or a conda env other than base, stays first,
  because that is the one their project uses
* pixi and the tools it installs, kept inside the install rather than in ~/.pixi
* a private TMPDIR: jiti transpiles pi's extensions into $TMPDIR/jiti and the
  result is executed on every later launch, so on a Linux login node (where
  TMPDIR is usually unset, meaning /tmp) whoever creates that directory first
  would decide what pi runs
* the paths the extensions read: hashline's store, the shim, pi's hosted
  gateway (pointed at a closed port, see below), and the launcher children use
"""

import os
import stat
import subprocess

from elmpi.paths import entry_point

# /bug uploads report.json, diagnostics.json and session.jsonl - the entire
# transcript - to radius.pi.dev, and /share tries the same host before falling
# back to a GitHub gist. patch-pi.py removes both commands from the release;
# pointing the gateway at a closed local port is the belt to that pair of
# braces, and unlike the patch it survives someone running npm install by hand.
RADIUS_GATEWAY = "http://127.0.0.1:1"


def arrange(root, env):
    """Put the install's toolchain in the environment pi will inherit."""
    _agent_python(root, env)
    _pixi(root, env)
    if env.get("ELM_PI_OWN_TMP") == "1":
        tmp = os.path.join(root, "agent", "tmp")
        env.set("TMPDIR", tmp)
        os.makedirs(tmp, exist_ok=True)
    private_tmpdir(env)
    env.set("PI_HASHLINE_DIR", os.path.join(root, "agent", "hashline"))
    env.set_default("ELM_SHIM_PATH", os.path.join(root, "shim", "shim.py"))
    env.set_default("PI_RADIUS_GATEWAY", RADIUS_GATEWAY)
    env.set_default("PI_SUBAGENT_PI_BINARY", entry_point(root))


def _in_front(path, first, second):
    """`first:second:` ahead of `path`, without adding either twice."""
    rest = path[len(first) + 1:] if path.startswith(first + ":") else path
    return first + ":" + second + ":" + rest


def _agent_python(root, env):
    environment = os.path.join(root, "agent", "python", "env")
    if not os.access(os.path.join(environment, "bin", "python"), os.X_OK):
        return
    env.set("ELM_PI_AGENT_PYTHON", os.path.join(environment, "bin", "python"))
    env.set("UV_PYTHON_INSTALL_DIR", os.path.join(root, "agent", "python", "interpreters"))
    env.set("UV_CACHE_DIR", os.path.join(root, "agent", "python", "cache"))
    if env.get("VIRTUAL_ENV"):
        return
    if env.get("CONDA_DEFAULT_ENV") not in ("", "base"):
        return
    binary = os.path.join(environment, "bin")
    if ":" + binary + ":" in ":" + env.get("PATH") + ":":
        return
    env.set("PATH", _in_front(env.get("PATH"), os.path.join(root, "agent", "bin"), binary))


def _pixi(root, env):
    if not os.access(os.path.join(root, "agent", "bin", "pixi"), os.X_OK):
        return
    home = os.path.join(root, "agent", "pixi")
    env.set("PIXI_HOME", home)
    env.set("PIXI_CACHE_DIR", os.path.join(home, "cache"))
    tools = os.path.join(home, "bin")
    if ":" + tools + ":" in ":" + env.get("PATH") + ":":
        return
    env.set("PATH", _in_front(env.get("PATH"), os.path.join(root, "agent", "bin"), tools))


def private_tmpdir(env):
    """Point TMPDIR at a directory only this account can write."""
    base = (env.get("TMPDIR", "/tmp") or "/tmp").rstrip("/") or "/tmp"
    if is_private(base):
        return
    directory = os.path.join(base, "elm-pi-%d" % os.getuid())
    if not os.path.exists(directory):
        try:
            os.mkdir(directory, 0o700)
        except OSError:
            pass
    if not is_private(directory):
        raise PrivateTmpRefusal(directory)
    env.set("TMPDIR", directory)


class PrivateTmpRefusal(Exception):
    """TMPDIR is shared and cannot be made private for this account."""

    def __init__(self, directory):
        self.directory = directory
        super().__init__(directory)


def is_private(path):
    """A real directory, not a symlink, owned by this account, writable by nobody else."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        return False
    if info.st_uid != os.geteuid():
        return False
    return not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)


def run_count():
    """How many sub-agent runners are live, without pgrep -c (procps only)."""
    try:
        result = subprocess.run(["pgrep", "-f", "pi-subagents/runner-peer-preload"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                universal_newlines=True)
    except OSError:
        return 0
    return len([line for line in result.stdout.splitlines() if line.strip()])
