"""Session transcripts and memory: where they go, and how they are protected.

A transcript holds every file the agent read and everything pasted in. Two
things follow, and both are done here:

* `.pi/` ignores itself. pi writes session transcripts to `.pi/sessions` in the
  working directory, and in a git repository that sits in the tree a
  `git push` would publish. A `.gitignore` inside `.pi` matching `*` covers the
  `.gitignore` too, so the directory is invisible to git rather than merely
  untracked: `git add -A` cannot stage anything in it, no project's own
  `.gitignore` has to know about it, and it survives being copied.
* the directories are mode 700 and the transcripts 600, set directly rather
  than with a process-wide umask - the agent's bash tool inherits a umask, and
  ordinary project files should stay 0644.
"""

import json
import os
import shutil
import subprocess

from elmpi.argwalk import joined_value
from elmpi.errors import Refusal, CANNOT_START
from elmpi.paths import normalize_session_dir

DEFAULT = ".pi/sessions"


def ensure_gitignore(cwd, which=shutil.which, run=subprocess.run):
    """Make `.pi` invisible to git, in a work tree only."""
    if not which("git"):
        return
    inside = run(["git", "rev-parse", "--is-inside-work-tree"], cwd=cwd,
                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if inside.returncode != 0:
        return
    marker = os.path.join(cwd, ".pi", ".gitignore")
    if os.path.isfile(marker):
        return
    try:
        os.makedirs(os.path.join(cwd, ".pi"), exist_ok=True)
        with open(marker, "w", encoding="utf-8") as handle:
            handle.write("*\n")
    except OSError:
        pass


def configured_session_dir(root):
    """settings.json's sessionDir, or pi's default when it says nothing."""
    try:
        with open(os.path.join(root, "agent", "settings.json"),
                  encoding="utf-8", errors="replace") as handle:
            value = json.load(handle).get("sessionDir", DEFAULT)
    except (OSError, ValueError, AttributeError):
        value = DEFAULT
    return value if isinstance(value, str) and value else DEFAULT


def session_dir(root, env, argv, cwd):
    """The directory pi will write transcripts to, resolved and made safe."""
    value = configured_session_dir(root)
    if env.get("PI_CODING_AGENT_SESSION_DIR"):
        value = env.get("PI_CODING_AGENT_SESSION_DIR")
    from_arguments = joined_value(argv, "--session-dir")
    if from_arguments is not None:
        value = from_arguments
    try:
        return normalize_session_dir(value, cwd)
    except ValueError:
        raise Refusal.about("could not resolve the session directory safely.",
                            code=CANNOT_START) from None


def secure(root, directory, env):
    """Harden the session directory and this install's own state."""
    if env.get("ELM_PI_SHARED_STATE") == "1":
        return
    _secure_session_dir(directory)
    _chmod(os.path.join(root, "agent"), 0o700)
    _secure_tree(os.path.join(root, "agent", "projects-memory"))
    _chmod(os.path.join(root, "agent", "egress.log"), 0o600)


def _chmod(path, mode):
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _chmod_own(path, mode):
    """chmod, but never through a link: `find -type f` in the reference does not
    match one, and os.chmod follows it - a repository shipping
    .pi/sessions/a.jsonl -> ../../tool.sh had tool.sh made 0600 at launch."""
    if not os.path.islink(path):
        _chmod(path, mode)


def _secure_session_dir(directory):
    if not os.path.isdir(directory):
        # makedirs gives its mode to the last folder only, so a new project's
        # .pi/ was 0755 around a 0700 sessions/: the names of everything in it
        # listable. The reference makes the whole chain under umask 077; the
        # umask is put back at once, because the agent's shell inherits it.
        previous = os.umask(0o077)
        try:
            os.makedirs(directory, mode=0o700, exist_ok=True)
        except OSError:
            pass
        finally:
            os.umask(previous)
    _chmod(directory, 0o700)
    # SessionManager writes JSONL transcripts, in subdirectories once a project
    # has several sessions. Recursive, as the reference launcher's `find
    # "$dir" -type f -name '*.jsonl'` is - but only those files: a mistaken
    # `--session-dir .` must not rewrite the modes of a whole project.
    for base, _, files in os.walk(directory):
        for name in files:
            if name.endswith(".jsonl"):
                _chmod_own(os.path.join(base, name), 0o600)


def _secure_tree(directory):
    if not os.path.isdir(directory):
        return
    _chmod(directory, 0o700)
    for base, folders, files in os.walk(directory):
        for name in folders:
            _chmod_own(os.path.join(base, name), 0o700)
        for name in files:
            _chmod_own(os.path.join(base, name), 0o600)
