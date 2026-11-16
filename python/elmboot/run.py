"""One run of the installer: what it must undo, and how it runs a command.

bootstrap.bash had `set -e` and an EXIT trap. The first meant a command that
failed ended the run with that command's own words and status; the second put
back the pi release and the extension tree the run had replaced, and removed
its temporary folders, however the run ended. This module is those two things.

The pi release and the extension tree a run replaces are kept until the run
has finished and verified, and put back if it fails - so an update whose pi
cannot load this install's config leaves the previous working pair in place
rather than a broken one. Files a run rewrote under agent/ are not rolled back.
"""

import os
import shutil
import subprocess
import sys


class Stop(Exception):
    """`set -e`: a command failed, it has said why, and the run ends with its status."""

    def __init__(self, code):
        self.code = code if code else 1
        super().__init__("exit %d" % self.code)


class Run:
    """The state one run carries from phase to phase."""

    def __init__(self, root, env, options=None):
        self.root = root
        self.env = env
        self.options = options
        self.retry = []          # curl's retry flags, once curl has been asked
        self.temporary = []      # removed however the run ends
        self.core_old = ""       # the pi release this run replaced
        self.packages_old = ""   # the extension tree this run replaced
        self.pi_version = ""     # PI_VERSION, when this run was given one
        self.chosen = []         # the packages pi is told to load
        self.package_digest = ""

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def temp(self, path):
        """Remember a folder or file to remove when the run ends."""
        self.temporary.append(path)
        return path

    def forget(self, path):
        if path in self.temporary:
            self.temporary.remove(path)

    # -- commands -------------------------------------------------------------

    def must(self, argv, cwd=None, env=None, quiet=False):
        """Run a command that has to work; its failure ends the run, as `set -e` did."""
        code = self.call(argv, cwd=cwd, env=env, quiet=quiet)
        if code != 0:
            raise Stop(code)

    def call(self, argv, cwd=None, env=None, quiet=False):
        """Run a command with the installer's own streams; returns its status.

        `quiet` hides stdout only (`>/dev/null`): what a command says on stderr
        is still for the person watching.
        """
        flush()
        try:
            status = subprocess.call(argv, cwd=cwd or self.root,
                                     env=self.env if env is None else env,
                                     stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL if quiet else None)
        except OSError as problem:
            sys.stderr.write("%s: %s\n" % (argv[0], problem.strerror or problem))
            return 127
        # Ended by a signal: 128 + its number, as a shell reports it. Python's
        # own -15 left the installer exiting 241 when npm was killed.
        return 128 - status if status < 0 else status

    def capture(self, argv, cwd=None, env=None, merge=False):
        """`$(command)`: (status, stdout without its trailing newlines).

        stderr goes where the installer's goes, or into the text with `merge`.
        """
        flush()
        try:
            result = subprocess.run(argv, cwd=cwd or self.root,
                                    env=self.env if env is None else env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT if merge else None,
                                    universal_newlines=True, errors="replace")
        except OSError as problem:
            return 127, str(problem)
        return result.returncode, result.stdout.rstrip("\n")

    def python(self, argv, **kwargs):
        """This install's interpreter, isolated: `elm_py`."""
        return [self.env["ELM_PI_PYTHON"], "-E", "-S"] + list(argv)

    def node(self):
        return self.path(".node", "bin", "node")

    # -- the end of the run ---------------------------------------------------

    def finish(self, failed):
        """The EXIT trap: put back what a failed run replaced, remove what any run made."""
        if failed:
            _restore(self.core_old, self.path("node_modules"), self.root)
            _restore(self.packages_old, self.path("agent", "npm", "node_modules"), self.root)
        for path in self.temporary + [self.core_old, self.packages_old]:
            if path:
                _remove(path)


def _restore(kept, target, root):
    if not kept or not os.path.isdir(kept):
        return
    try:
        _remove(target)
        os.rename(kept, target)
    except OSError:
        return
    sys.stderr.write("    put back the previous %s\n" % os.path.relpath(target, root))


def _remove(path):
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)
    except OSError:
        pass


def flush():
    """Before anything else writes to the same terminal: what was said so far."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (AttributeError, ValueError, OSError):
            pass
