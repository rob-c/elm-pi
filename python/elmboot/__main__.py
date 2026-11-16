"""The first Python the installer runs: make the import path safe, then hand over.

`bootstrap.sh` finds an interpreter - downloading a standalone one where the
machine has none it can use - and starts this file with it, isolated:

    python -E -s -S -B -u -X utf8 python/elmboot/__main__.py [flags]

Python puts the directory of the script it was given at the front of
`sys.path`. Here that is python/elmboot, and it is replaced by its parent
before anything else is imported, so that the only code importable beside the
standard library is this install's own two packages (elmboot, and elmpi for
the launcher's own answer about the fence) - whatever folder the installer was
started from, and whatever is in it.
"""

import os
import sys

MINIMUM = (3, 8)


def main(argv):
    if sys.version_info < MINIMUM:
        sys.stderr.write(
            "bootstrap: python %d.%d is too old for the installer; it needs %d.%d or newer.\n"
            "    Name another:  ELM_PI_PYTHON=/absolute/path/to/python3 ./bootstrap.sh\n"
            % (sys.version_info[0], sys.version_info[1], MINIMUM[0], MINIMUM[1]))
        return 1
    package = os.path.dirname(os.path.abspath(__file__))
    ours = os.path.realpath(package)
    sys.path[:] = [os.path.dirname(package)] + [
        entry for entry in sys.path
        if entry and os.path.isabs(entry) and os.path.realpath(entry) != ours]
    # What is said has to appear in the order it was said, between the lines of
    # the programs this runs: npm, uv, curl and pi write to the same terminal.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except (AttributeError, ValueError, OSError):
            pass

    # Python starts with SIGPIPE ignored, and an ignored signal is inherited by
    # everything this runs: configure.sh, npm and pi would be different
    # programs from the ones the bash installer ran (the launcher met this as
    # `yes | head -1` writing "Broken pipe" errors under `pi setup`).
    try:
        import signal
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError, OSError):
        pass

    from elmboot.cli import main as install

    # abspath, not realpath: every path the installer prints and records names
    # the install as the account spells it (~/src is not /Users/me/src on a Mac).
    return install(argv, root=os.path.dirname(os.path.dirname(package)))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
