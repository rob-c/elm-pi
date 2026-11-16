"""Which interpreter runs this install's Python, and how it is kept isolated.

An account with an activated conda base, a pyenv shim or a virtualenv has a
`python3` first on PATH that is not the machine's, and bootstrap died halfway
through an install that way once (conda's 3.8, and a `str.removeprefix`). So:

* one interpreter, chosen once and recorded in agent/python-path
* never conda, a virtualenv or a version-manager shim unless named explicitly
  with ELM_PI_PYTHON - then it is the caller's decision to make, and a shim is
  still refused because which Python it runs depends on the folder
* always run as `python -E -S`: no PYTHON* variable, no site-packages, no .pth
  file. Every Python file in this repository is stdlib-only, so nothing needs
  site-packages, and a check that cannot load one cannot be changed by one.

The launcher only ever validates in `fast` mode - a recorded interpreter that
is still executable is used without starting it, which is what keeps a
sub-agent's start cheap. `python/pi` makes the same choice in bash before any
Python runs; this is the full version, used when that has to fall back.
"""

import os
import subprocess

from elmpi.environ import clean_path, read_first_line
from elmpi.errors import Refusal, CANNOT_START

MIN_MAJOR, MIN_MINOR = 3, 8
RECORD = os.path.join("agent", "python-path")

SYSTEM_DIRS = (
    "/usr/bin",
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/Library/Frameworks/Python.framework/Versions/Current/bin",
)
VERSIONED = ("python3", "python3.14", "python3.13", "python3.12", "python3.11",
             "python3.10", "python3.9", "python3.8")

# Written to run under any Python at all, 2.x included, so that an old one
# reports "too old" rather than a syntax error.
PROBE = """import os, sys
if sys.version_info[:2] < (%d, %d): sys.exit(10)
if os.path.isdir(os.path.join(sys.prefix, 'conda-meta')): sys.exit(11)
if os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sys.executable))), 'pyvenv.cfg')): sys.exit(12)
""" % (MIN_MAJOR, MIN_MINOR)

OK, MISSING, TOO_OLD, CONDA, VIRTUALENV, SHIM = 0, 1, 10, 11, 12, 13

REASONS = {
    TOO_OLD: "older than %d.%d" % (MIN_MAJOR, MIN_MINOR),
    CONDA: "conda",
    VIRTUALENV: "virtualenv",
    SHIM: "version-manager shim",
    MISSING: "does not run",
}


def _is_macos_stub(path):
    """On a Mac without the Command Line Tools, /usr/bin/python3 is a stub that
    opens an install dialog and fails. Never run one to find out."""
    if os.uname().sysname != "Darwin" or not path.startswith("/usr/bin/"):
        return False
    try:
        return subprocess.run(["xcode-select", "-p"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode != 0
    except OSError:
        return False


def check(path):
    """0 usable, 1 missing or not runnable, 10 too old, 11 conda, 12 virtualenv,
    13 a version-manager shim."""
    if not os.path.isabs(path) or not os.path.isfile(path) or not os.access(path, os.X_OK):
        return MISSING
    if "/.pyenv/" in path or "/.asdf/" in path or "/shims/" in path:
        return SHIM
    if _is_macos_stub(path):
        return MISSING
    try:
        result = subprocess.run([path, "-E", "-S", "-c", PROBE], stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return MISSING
    return OK if result.returncode == 0 else result.returncode


def candidates(root, env):
    """Interpreters worth trying, most preferred first.

    System and package-manager locations come before anything on PATH, so an
    activated environment cannot change which one is picked; the standalone
    build bootstrap.sh can download into .python comes after them.
    """
    found = []
    for directory in SYSTEM_DIRS:
        for name in VERSIONED:
            path = os.path.join(directory, name)
            if os.access(path, os.X_OK):
                found.append(path)
    if root:
        bundled = os.path.join(root, ".python", "bin", "python3")
        if os.access(bundled, os.X_OK):
            found.append(bundled)
    for directory in clean_path(env.get("ELM_PI_USER_PATH", env.get("PATH"))).split(os.pathsep):
        path = os.path.join(directory, "python3")
        if directory and os.access(path, os.X_OK):
            found.append(path)
    return found


def select(root, env, mode=""):
    """Set ELM_PI_PYTHON to the interpreter to use, or raise Refusal."""
    explicit = env.get("ELM_PI_PYTHON")
    if explicit:
        # Named explicitly: conda or a virtualenv is the caller's decision.
        # Too old or not runnable is not, and there is no silent fallback.
        result = check(explicit)
        if result in (OK, CONDA, VIRTUALENV):
            env.set("ELM_PI_PYTHON", explicit)
            return explicit
        raise Refusal("pi: " + _explicit_error(explicit, result), code=CANNOT_START)

    recorded = read_first_line(os.path.join(root, RECORD)) if root else ""
    if recorded:
        if mode == "fast" and os.access(recorded, os.X_OK):
            env.set("ELM_PI_PYTHON", recorded)
            return recorded
        # Re-validated at install time and kept when it still passes, so a newly
        # installed Homebrew Python does not swap the interpreter under an install.
        if check(recorded) == OK:
            env.set("ELM_PI_PYTHON", recorded)
            return recorded

    rejected = []
    seen = set()
    for path in candidates(root, env):
        if path in seen:
            continue
        seen.add(path)
        result = check(path)
        if result == OK:
            env.set("ELM_PI_PYTHON", path)
            return path
        if result != MISSING:
            # A missing shared library or a wrapper can exit 127 (or any
            # status outside our probe's). The port used to raise KeyError
            # here instead of trying the next interpreter, unlike bash.
            rejected.append("\n      %s (%s)" % (path, REASONS.get(result, "does not run")))

    lines = [
        "pi: no usable Python %d.%d+ found. elm-pi does not use conda, virtualenv"
        % (MIN_MAJOR, MIN_MINOR),
        "    or pyenv interpreters, whatever is first on PATH.",
    ]
    if rejected:
        lines += ["    Rejected:" + "".join(rejected)]
    lines += [
        "    macOS:  xcode-select --install     (provides /usr/bin/python3)",
        "    Linux:  install python3 >= %d.%d from the system package manager"
        % (MIN_MAJOR, MIN_MINOR),
        "    Or name one explicitly:  ELM_PI_PYTHON=/absolute/path/to/python3",
    ]
    raise Refusal(*lines, code=CANNOT_START)


def _explicit_error(path, result):
    if result == SHIM:
        return ("ELM_PI_PYTHON=%s is a version-manager shim; name the real interpreter "
                "(e.g. `pyenv which python3`)" % path)
    if result == TOO_OLD:
        return "ELM_PI_PYTHON=%s is older than Python %d.%d" % (path, MIN_MAJOR, MIN_MINOR)
    return "ELM_PI_PYTHON=%s is not a runnable Python (it must be an absolute path)" % path
