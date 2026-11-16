"""The installer's output: the headings, the warnings, and the way it stops.

bootstrap.sh's `say`, `warn` and `die`, with their exact escape sequences -
the heading is bold, a warning yellow, an error red on stderr - because people
read this output once, at the moment something is wrong, and the shape is how
they find the line that matters.
"""

import subprocess
import sys

BOLD = "\033[1m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


class Failure(Exception):
    """`die`: print and stop the run. Nothing after it happens."""


def say(heading):
    """The `==> heading` that opens each phase."""
    print("\n" + BOLD + "==> " + heading + RESET)


def note(*lines):
    """An indented line of progress, the installer's ordinary output."""
    for line in lines:
        print("    " + line)


def warn(message):
    """Something the run continues through, in yellow, on stdout as bash has it."""
    print(YELLOW + "    " + message + RESET)


def die(message):
    raise Failure(message)


def run(argv, cwd=None, env=None, capture=False, check=True, stdin=None):
    """Run one command, the way the shell ran it.

    `capture` returns the output as text (bash's `$( )`); without it the
    command's own streams go where the installer's go, as they did in bash.
    """
    result = subprocess.run(
        argv, cwd=cwd, env=env,
        stdin=subprocess.DEVNULL if stdin is None else stdin,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        universal_newlines=True,
    )
    if check and result.returncode != 0:
        raise Failure("command failed: %s" % " ".join(argv))
    return result


def output(argv, cwd=None, env=None, default=""):
    """The command's stdout stripped, or `default` when it cannot run.

    bash's `$(cmd 2>/dev/null || true)`: a probe that fails is an answer, not
    a failure, in the places this is used.
    """
    try:
        result = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                universal_newlines=True)
    except OSError:
        return default
    return result.stdout.strip() if result.returncode == 0 else default


def stderr_of(argv, cwd=None, env=None):
    """Combined stdout and stderr of a command that is allowed to fail."""
    try:
        result = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True)
    except OSError as problem:
        return str(problem)
    return result.stdout
