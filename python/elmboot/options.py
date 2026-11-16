"""The installer's flags, and the record of what this install was made with.

Flags describe the install, not one run: `pi update` and `pi update
--extensions` call the installer without them, so an update used to quietly
install the packages, the shim and the tools someone had declined, and re-lock
auth.json. They are recorded in agent/install-options, with ELM_PI_TOOLS and
the branch and repository install.sh fetched, and every later run repeats them.
Flags on the command line are added to the record; --reset-options starts it
again from this run's flags alone, which is the way to take one back.

Read as data - key=value lines, nothing is sourced - for the same reason .env
is: a file in the install must not be able to run code. bootstrap.sh reads it
with sed; this reads it with str.partition, and the two write the same file.
"""

import os
import re

from elmboot import console

OPTIONS_FILE = os.path.join("agent", "install-options")

# The flags that describe the install. Each replaces its opposite in the record;
# the two groups below are what makes `pi setup --no-python` and
# `pi setup --python` take each other back.
RECORDED = ("--no-shim", "--no-packages", "--no-auth-lock", "--no-tools", "--no-patch",
            "--with-python", "--with-pypi-index", "--no-python")
OPPOSITES = {
    "--no-python": ("--with-python", "--with-pypi-index"),
    "--with-python": ("--no-python",),
    "--with-pypi-index": ("--no-python",),
}
DEFAULTS = {
    "shim": True, "packages": True, "interactive": True, "update": False,
    "auth_lock": True, "force": False, "with_tools": True, "patch": True,
    "python": True, "pypi_index": False, "force_packages": False,
}
# What each recorded flag sets. --with-all is recorded as the two parts it
# stands for, so --no-pypi-index can take one back.
APPLY = {
    "--no-shim": {"shim": False},
    "--no-packages": {"packages": False},
    "--no-auth-lock": {"auth_lock": False},
    "--no-tools": {"with_tools": False},
    "--no-patch": {"patch": False},
    "--with-python": {"python": True},
    "--with-pypi-index": {"pypi_index": True, "python": True},
    "--no-python": {"python": False, "pypi_index": False},
}


class Options:
    """Everything one run of the installer decided, and what it inherits."""

    def __init__(self):
        for name, value in DEFAULTS.items():
            setattr(self, name, value)
        self.given = []      # the flags this record will hold, in order
        self.dropped = []    # the flags a later --with-*/--no-* took back
        self.reset_options = False
        self.tools = ""      # ELM_PI_TOOLS, possibly from the record
        self.branch = ""
        self.repo = ""
        self.repeated = ""   # the record's flags this run repeated, for the note
        self.source = ""     # where they came from, for the note

    def apply(self, flag):
        for name, value in APPLY[flag].items():
            setattr(self, name, value)


def usage_or_exit(argv):
    """`--help` wins over everything, including a typo earlier in the line."""
    if any(argument in ("-h", "--help") for argument in argv):
        print_usage()
        raise SystemExit(0)


def print_usage():
    from elmboot.usage import USAGE
    print(USAGE.rstrip("\n"))


def parse(argv, program="./bootstrap.sh"):
    """First pass: this run's own flags, with the record's added on."""
    options = Options()
    usage_or_exit(argv)
    for argument in argv:
        if argument == "--with-all":
            # Recorded as the parts it stands for.
            for part in ("--with-python", "--with-pypi-index"):
                _remember(options, part)
            options.dropped.append("--no-python")
        elif argument in OPPOSITES:
            _remember(options, argument)
            options.dropped += OPPOSITES[argument]
        elif argument == "--no-pypi-index":
            options.dropped.append("--with-pypi-index")
        elif argument in RECORDED:
            _remember(options, argument)
        elif argument == "--non-interactive":
            options.interactive = False
        elif argument == "--update":
            options.update = True
        elif argument == "--force":
            options.force = True
        elif argument == "--force-packages":
            options.force_packages = True
        elif argument == "--reset-options":
            options.reset_options = True
        else:
            print("unknown option: %s" % argument, file=console.sys.stderr)
            print("try: %s --help" % program, file=console.sys.stderr)
            raise SystemExit(2)
    return options


def _remember(options, flag):
    if flag not in options.given:
        options.given.append(flag)


def saved(root, key):
    """The last `key=value` line of the record, or "" - `sed -n "s/^key=//p"`."""
    path = os.path.join(root, OPTIONS_FILE)
    value = ""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.rstrip("\n")
                if line.startswith(key + "="):
                    value = line[len(key) + 1:]
    except OSError:
        return ""
    return value


def _infer_old_install(root):
    """An install from before the record existed: what its flags left behind.

    Unambiguous for four of them; --no-patch and a tool subset are not inferred.
    """
    flags = []
    settings = os.path.join(root, "agent", "settings.json")
    try:
        with open(settings, encoding="utf-8", errors="replace") as handle:
            if '"packages": []' in handle.read():
                flags.append("--no-packages")
    except OSError:
        pass
    if (os.path.isdir(os.path.join(root, "agent", "extensions"))
            and not os.path.isfile(os.path.join(root, "agent", "extensions", "elm-shim.ts"))):
        flags.append("--no-shim")
    auth = os.path.join(root, "agent", "auth.json")
    if os.path.isfile(auth) and os.access(auth, os.W_OK):
        flags.append("--no-auth-lock")
    binaries = os.path.join(root, "agent", "bin")
    if os.path.isdir(binaries):
        if not any(os.access(os.path.join(binaries, tool), os.X_OK)
                   for tool in ("fd", "rg", "jq", "yq", "shellcheck", "ast-grep")):
            flags.append("--no-tools")
    return flags


def inherit(root, options, env):
    """Read the record, add the flags this run did not contradict, and report."""
    path = os.path.join(root, OPTIONS_FILE)
    saved_flags, saved_tools = "", ""
    if os.path.isfile(path):
        saved_flags, saved_tools = saved(root, "flags"), saved(root, "tools")
        options.source = OPTIONS_FILE
    elif os.path.isfile(os.path.join(root, "agent", "settings.json")):
        saved_flags = " ".join(_infer_old_install(root))
        options.source = "this install (it has no agent/install-options yet)"

    if options.reset_options:
        if saved_flags or saved_tools:
            console.note("--reset-options: not repeating %s%s"
                         % (saved_flags, (" ELM_PI_TOOLS=" + saved_tools) if saved_tools else ""))
        saved_flags, saved_tools = "", ""

    repeated = []
    for flag in saved_flags.split():
        if flag not in RECORDED:
            continue
        if flag in options.given or flag in options.dropped:
            continue
        options.given.append(flag)
        repeated.append(flag)
    for flag in options.given:
        options.apply(flag)

    # A tools list is words and commas; anything else in that line is not one.
    if re.search(r"[^a-z,-]", saved_tools):
        saved_tools = ""
    if not env.get("ELM_PI_TOOLS") and saved_tools:
        env["ELM_PI_TOOLS"] = saved_tools
        repeated.append("ELM_PI_TOOLS=" + saved_tools)
    options.tools = env.get("ELM_PI_TOOLS", "")

    _say_record(options, repeated)
    # An install made while the agent's Python was opt-in gains it on its next
    # run; say so, because it is a gigabyte.
    if (options.python and options.source
            and not os.access(os.path.join(root, "agent", "python", "env", "bin", "python"),
                              os.X_OK)):
        console.note("the agent's Python (agent/python, ~1 GB) is part of every install now, "
                     "and is built below;",
                     "to leave it out: pi setup --no-python")
    return options


def _say_record(options, repeated):
    console.say("install options")
    if repeated:
        console.note("repeating %s, from %s" % (" ".join(repeated), options.source))
        console.note("(to drop one: re-run with --reset-options and only the flags you want)")
    console.note("this install: %s%s" % (" ".join(options.given) or "the defaults",
                                         (", ELM_PI_TOOLS=" + options.tools)
                                         if options.tools else ""))


def write(root, options, env):
    """Record this run's options, and the branch and repository install.sh fetched."""
    os.makedirs(os.path.join(root, "agent"), exist_ok=True)
    # install.sh passes the branch and repository it fetched; any other run
    # keeps what was recorded. Whitespace in a value is not a branch or a URL.
    branch = env.get("ELM_PI_BRANCH") or saved(root, "branch")
    repo = env.get("ELM_PI_REPO") or saved(root, "repo")
    branch = "" if re.search(r"\s", branch) else branch
    repo = "" if re.search(r"\s", repo) else repo
    options.branch, options.repo = branch, repo
    text = (
        "# The options this install was made with. Written by bootstrap.sh and repeated\n"
        "# by every later run (pi update, pi update --extensions, the installer).\n"
        "# To change them: ./bootstrap.sh --reset-options [the flags you want]\n"
        "flags=%s\n"
        "tools=%s\n"
        "branch=%s\n"
        "repo=%s\n"
    ) % (" ".join(options.given), options.tools, branch, repo)
    target = os.path.join(root, OPTIONS_FILE)
    with open(target + ".tmp", "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(target + ".tmp", target)
