"""The launcher's own environment: read, set, scrub, and inherit.

Everything the launcher decides has to reach pi, and pi is reached by `exec`,
so every change here is made on the real process environment. A subprocess
(the proxy, git, the installer) inherits the same environment, as it does in
the reference launcher.

Two rules carried over from there because they were learned the hard way:

* The agent's shell keeps the researcher's PATH, conda included - it needs it
  for real work. Only relative entries are dropped, because `.` on PATH makes a
  repository's own `./git` run whenever pi looks that command up.
* `.env` is read as data, never sourced. It used to be sourced as shell, which
  made it a script anything could append a `PYTHONPATH` or a command to.
"""

import os
import re

# Directory names that mark a PATH entry as belonging to a version manager,
# a virtualenv or a package manager's private bin: never elm-pi's, except when
# a script asks for the whole account PATH (elm_clean_path without a mode).
VERSION_MANAGER_MARKERS = (
    "/.pyenv/", "/.nvm/", "/.volta/", "/.fnm/", "/fnm_multishells/",
    "/.asdf/", "/.npm-global", "/node_modules/",
)

# Only ELM_* keys: the key itself, the install's policy, its hosts. A line
# that is anything else is reported and ignored - there is no shell here to
# run it, which is the point.
DOTENV_KEY = re.compile(r"^ELM_[A-Z0-9_]+$")


class Environment:
    """A view of the process environment, with the launcher's conventions."""

    def __init__(self, mapping=None):
        self.mapping = os.environ if mapping is None else mapping

    def get(self, name, default=""):
        """`${NAME:-$default}`: unset and empty are the same thing."""
        value = self.mapping.get(name)
        return default if value is None or value == "" else value

    def set(self, name, value):
        self.mapping[name] = str(value)

    def set_default(self, name, value):
        """`export NAME="${NAME:-value}"`."""
        if not self.get(name):
            self.set(name, value)

    def unset(self, *names):
        for name in names:
            self.mapping.pop(name, None)

    def names(self):
        return list(self.mapping)


def clean_path(value, relative_only=False):
    """`value` without relative entries, duplicates or foreign toolchains.

    With `relative_only` - what the launcher uses - only the entries that are
    not absolute go, and the rest of the account's PATH is kept as it is.
    Without it, install-time work also drops conda, virtualenv and version
    manager entries, recognised structurally (conda-meta or pyvenv.cfg beside
    the bin) rather than by name.
    """
    out = []
    for entry in value.split(os.pathsep):
        if not entry.startswith("/"):
            continue
        if entry.endswith("/"):
            entry = entry[:-1]
        if not entry or entry in out:
            continue
        if not relative_only:
            if any(marker in entry for marker in VERSION_MANAGER_MARKERS):
                continue
            base = os.path.dirname(entry)
            if os.path.isdir(os.path.join(base, "conda-meta")):
                continue
            if os.path.isfile(os.path.join(base, "pyvenv.cfg")):
                continue
        out.append(entry)
    return os.pathsep.join(out)


def load_dotenv(path, env, console):
    """The ELM key from `.env`, as KEY=value data.

    One key per line, an optional `export `, optional matching quotes, no
    expansion and nothing executed. Any other line is reported with its number
    and ignored, so a mistake in the file is visible rather than silently read
    as part of the key.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return
    for number, line in enumerate(text.split("\n"), 1):
        if line.endswith("\r"):
            line = line[:-1]
        line = line.lstrip()
        if not line or line.startswith("#"):
            continue
        if "\0" in line:
            # No environment can hold one: setting it was a traceback.
            console.note("elm-pi: ignoring line %d of %s - it holds a NUL byte" % (number, path))
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, separator, value = line.partition("=")
        if not separator or not DOTENV_KEY.match(key):
            console.note("elm-pi: ignoring line %d of %s - only ELM_*=value lines are read"
                         % (number, path))
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        env.set(key, value)


def read_first_line(path):
    """`head -n 1`: a recorded value, or "" when there is no file."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.readline().strip()
    except OSError:
        return ""
