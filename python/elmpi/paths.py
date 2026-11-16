"""What a folder's path is, and where this install's pieces live.

Almost every decision the launcher makes is about a path: which folder the
session starts in, whether that folder is home, which directory the transcripts
go in, whether an executable under `agent/` is this install's. A shell spells
paths two ways - what was typed, and what the kernel says - and the difference
is not academic: on macOS `~/Downloads` and `~/downloads` are the same folder,
so a comparison made against the typed spelling lets a session start in
Downloads and take the whole folder as its project. `canonical()` below is the
bash launcher's `elm_policy_canonical`, including its `/bin/pwd -P` step, done
with `os.getcwd()` instead of a process: three system calls instead of a fork,
on a path that runs at every session start.

A path that does not exist cannot be compared with one that does, so it is
resolved as text to the deepest folder that does exist, and the rest is kept.
"""

import os
from urllib.parse import unquote, urlsplit

# The installed command, which is how this launcher is reached again:
# `--with-all` re-executes it once the optional parts are built, and sub-agent
# children are pointed at it so they get this launcher's policy, not whichever
# `pi` happens to be on PATH. It is the bash hand-over to python/pi, so a child
# started from a session is the same command a person runs.
ENTRY_NAME = "pi"


def entry_point(root):
    """The install's own `pi`, for re-exec and for sub-agent children."""
    return os.path.join(root, ENTRY_NAME)


def install_root(package_dir):
    """The folder that holds `agent/`, `config/`, `pi.orig` and `python/`."""
    return os.path.dirname(package_dir)


def home_dir():
    """The account's home folder, for every comparison made against it.

    Not `os.path.expanduser("~")`: with `HOME=` (set, and empty) that is the
    empty string, which made `~` the root folder and switched off the home
    refusals - `cd ~/.ssh; HOME= pi` started a session there, where the bash
    launcher refused. An empty or relative HOME is not a folder, so the
    account's own record is asked; with neither, the folder the launch is in
    stands in, which refuses the launch as "your home folder" - the bash
    launcher's answer too, since its `~` was `$PWD` there.
    """
    home = os.environ.get("HOME", "")
    if home.startswith("/"):
        return home
    try:
        import pwd
        home = pwd.getpwuid(os.getuid()).pw_dir
    except (ImportError, KeyError, OSError):
        home = ""
    if home.startswith("/"):
        return home
    try:
        return os.getcwd()
    except OSError:
        return "/"


def tilde_absolute(value, home=None):
    """`~` and `~/...` replaced by home. A literal `~` from the config, not one
    for a shell to expand: the folder lists in runtime.env are single-quoted."""
    home = home_dir() if home is None else home
    if value == "~":
        return home
    if value.startswith("~/"):
        return os.path.join(home, value[2:])
    return value


def lexical(value, cwd=None):
    """`value` made absolute against `cwd` and resolved as text, the way `cd`
    resolves it: repeated slashes and `.` dropped, `..` taking off the name
    before it. Symlinks are not followed."""
    cwd = os.getcwd() if cwd is None else cwd
    rest = value + "/" if value.startswith("/") else os.path.join(cwd, value) + "/"
    out = ""
    for part in rest.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            out = out.rsplit("/", 1)[0] if "/" in out else ""
            continue
        out += "/" + part
    return out or "/"


def kernel_spelling(path):
    """The folder's own path: symlinks followed, and the spelling the disk has.

    `os.path.realpath` resolves the links but keeps the case that was typed;
    the kernel does not. Asking the kernel means being in the folder, so this
    changes directory for the length of one `getcwd()` and changes back. The
    launcher is single-threaded and holds no relative path across this call,
    which is what makes that safe; the alternative, a `/bin/pwd` process per
    folder, is what the reference launcher does and is 40 forks at startup.
    """
    try:
        saved = os.open(".", os.O_RDONLY)
    except OSError:
        # No way back, so no going: in a folder the account may enter but not
        # read (a drop box, mode 300) the chdir below was never undone, and a
        # session asked for there started in the home folder instead, with its
        # .pi/ written there. The links are still resolved; only the disk's own
        # spelling of the name is not asked for.
        return os.path.realpath(path)
    try:
        os.chdir(path)
        return os.getcwd()
    except OSError:
        return os.path.realpath(path)
    finally:
        try:
            os.fchdir(saved)
        except OSError:
            pass
        finally:
            os.close(saved)


def canonical(value, home=None, cwd=None):
    """`value` as the folder it names, or as text for one that does not exist."""
    path = lexical(tilde_absolute(value, home), cwd)
    tail = ""
    while path != "/" and not os.path.isdir(path):
        path, name = path.rsplit("/", 1)
        tail = "/" + name + tail
        path = path or "/"
    return lexical(kernel_spelling(path) + tail, cwd)


def same_folder(first, second):
    """True when both name the same folder by device and inode.

    `[ -ef ]` in the reference launcher: it follows symlinks, so no spelling of a
    listed folder gets past it.
    """
    try:
        return os.path.samefile(first, second)
    except OSError:
        return False


def is_inside(folder, parent):
    """True when `folder` is `parent` or somewhere under it, both resolved."""
    folder, parent = os.path.realpath(folder), os.path.realpath(parent)
    return folder == parent or folder.startswith(parent.rstrip(os.sep) + os.sep)


def normalize_session_dir(value, cwd=None, home=None):
    """A session directory as pi will read it: `~`, `file://` and relative
    paths resolved against the folder the session starts in.

    pi accepts all three spellings on the command line, the environment and in
    settings.json, and the launcher has to harden the same directory pi will
    write to - so it resolves them the way pi does, before anything is created.
    """
    cwd = os.getcwd() if cwd is None else cwd
    home = home_dir() if home is None else home
    if value == "~":
        value = home
    elif value.startswith("~/"):
        value = os.path.join(home, value[2:])
    if value.startswith("file://"):
        parsed = urlsplit(value)
        if parsed.netloc not in ("", "localhost"):
            raise ValueError("unsupported non-local session file URL: %s" % value)
        value = unquote(parsed.path)
    if not os.path.isabs(value):
        value = os.path.join(cwd, value)
    return os.path.abspath(value)
