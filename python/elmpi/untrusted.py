"""Folders a session must not start in.

The folder pi starts in is the project. The permission gate asks before the
agent touches anything outside it and nothing inside it, so started in home
the whole home folder is the project: every repository, document and dotfile
in it readable and writable without a prompt, and the agent's searches sweep
all of it. The trust guard keeps project trust off the same folders, and the
list is `untrustedFolders` in config/elm-pi.json.

Two kinds of entry:

* exact - containers, and only the folder itself counts (`/Users`, `~/Desktop`)
* tree  - credentials or system files, and everything under them counts (`~/.ssh`)

Home and every ancestor of home are refused without being listed, so a home
that moves does not need a config change.

Comparison is by device and inode where the folder exists, which is why no
spelling of a listed folder gets past it: `/tmp` for `/private/tmp`, a case
variant on macOS, a symlink into `~/.ssh`. A path that does not exist (an
argument, never the launcher's own folder) cannot be inside a folder that
does, so it is compared as canonical text, as pi does.
"""

import os

from elmpi.paths import canonical, same_folder, tilde_absolute

HOME_ITSELF = "your home folder"
HOME_CONTAINER = "a folder that contains your home folder"
CONTAINER = "%s, which holds far more than one project"
TREE = "inside %s, which holds credentials or system files"


def _entries(value):
    return [line for line in value.split("\n") if line]


def _walk_to(target, start):
    """True when `start` is `target` or inside it, by device and inode."""
    folder = start
    while True:
        if same_folder(folder, target):
            return True
        if folder == "/":
            return False
        folder = os.path.dirname(folder) or "/"


def _text_inside(folder, target):
    """The bash launcher's `case "$dir/" in "$up"/*)` - including its edge:
    target "/" gives the pattern "//*", which matches nothing."""
    return (folder + "/").startswith(target + "/" if target != "/" else "//")


def untrusted_folder(path, env, home=None, cwd=None):
    """Why `path` is not a folder a session may start in, or None.

    The returned text is the reason phrase the refusal puts after "not
    starting in <folder> - ".
    """
    folder = canonical(path, home, cwd)
    exists = os.path.exists(folder)
    home_path = canonical("~", home, cwd)

    if folder == home_path or (exists and same_folder(folder, home_path)):
        return HOME_ITSELF
    ancestor = home_path
    while ancestor != "/" and ancestor:
        ancestor = os.path.dirname(ancestor) or "/"
        if folder == ancestor or (exists and same_folder(folder, ancestor)):
            return HOME_CONTAINER

    for entry in _entries(env.get("ELM_UNTRUSTED_EXACT")):
        if exists:
            if not same_folder(folder, tilde_absolute(entry, home)):
                continue
        elif folder != canonical(entry, home, cwd):
            continue
        return CONTAINER % entry

    for entry in _entries(env.get("ELM_UNTRUSTED_TREE")):
        if exists:
            listed = tilde_absolute(entry, home)
            if not os.path.isdir(listed):
                continue
            if _walk_to(listed, folder):
                return TREE % canonical(entry, home, cwd)
        elif _text_inside(folder, canonical(entry, home, cwd)):
            return TREE % canonical(entry, home, cwd)
    return None
