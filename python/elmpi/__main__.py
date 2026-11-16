"""The first Python that runs: make the import path safe, then hand over.

Python puts the directory of the script it was given at the front of
`sys.path`. Here that directory is `python/elmpi`, and before it existed the
launcher's helpers were stdin snippets started from `/` for exactly this
reason: a `json.py`, `os.py` or `sitecustomize.py` in the folder the agent is
working on must never be importable by the code that decides what the agent may
do. The same care applies to `sys.path[0]` itself - it is the one entry whose
value depends on how and from where the launcher was started.

So before anything else is imported, `sys.path[0]` is replaced by this
package's parent. Everything else is then exactly what `-E -s -S` selected:
the stdlib of the interpreter `python/pi` chose. Two entries at most are ever
ours, and both are inside the install.
"""

import os
import sys


def _import_root(module_dir):
    """The directory `elmpi` is imported from, with the script's own removed."""
    ours = os.path.realpath(module_dir)
    stdlib = [
        entry for entry in sys.path
        if entry and os.path.isabs(entry) and os.path.realpath(entry) != ours
    ]
    return [os.path.dirname(module_dir)] + stdlib


MINIMUM = (3, 8)


def main(argv):
    if sys.version_info < MINIMUM:
        sys.stderr.write(
            "pi: python %d.%d is too old for this launcher; it needs %d.%d or newer.\n"
            "    python/pi chooses the interpreter from agent/python-path, ELM_PI_PYTHON\n"
            "    or PATH; run bootstrap.sh to record a newer one.\n"
            % (sys.version_info[0], sys.version_info[1], MINIMUM[0], MINIMUM[1]))
        return 1
    # abspath, not realpath: the install is known here by the path python/pi
    # resolved, which keeps the spelling the account uses (~/src is not
    # /Users/me/src on a Mac). Every message the launcher prints names a path
    # this install is at, and the reference launcher prints the same spelling.
    module_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path[:] = _import_root(module_dir)

    from elmpi.cli import main as launch

    package_dir = os.path.dirname(module_dir)
    return launch(argv, package_dir=package_dir, install_root=os.path.dirname(package_dir))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
