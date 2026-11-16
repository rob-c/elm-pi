"""The launcher's two streams, flushed where it matters.

The launcher runs subprocesses (git, pgrep, the proxy, the installer) that
inherit its standard streams, and it ends by replacing itself with pi. Text
left in a buffer would appear after a child's output or after pi's screen.
Every write here is therefore flushed at once, which is also what makes the
order of a banner, a note and pi's first line the order a reader sees.
"""

import sys


def is_terminal(stream):
    """`[ -t N ]`. A stream that was closed before the launcher started is
    None in Python, not a file that says no: `pi -p x <&-` was a traceback."""
    try:
        return stream is not None and stream.isatty()
    except (OSError, ValueError):
        return False


class Console:
    """stdout for what the caller asked for, stderr for everything else."""

    def __init__(self, out=None, err=None):
        self.out = out if out is not None else sys.stdout
        self.err = err if err is not None else sys.stderr

    def say(self, *lines):
        """Print to stdout: `--help`, and the help's own section slices.

        With no arguments, one blank line - `echo`, as the reference launcher writes it.
        """
        self._write(self.out, lines or ("",))

    def note(self, *lines):
        """Print to stderr: why the launcher is doing what it is doing."""
        self._write(self.err, lines or ("",))

    def raw(self, *lines):
        """Print to stderr exactly as given - a message already formatted."""
        self._write(self.err, lines or ("",))

    def show(self, refusal):
        """Print a refusal exactly as it was built."""
        self._write(self.err, refusal.lines)

    @staticmethod
    def _write(stream, lines):
        if stream is None:      # closed by the caller (`pi --help >&-`): nowhere to say it
            return
        for line in lines:
            stream.write(line + "\n")
        stream.flush()
