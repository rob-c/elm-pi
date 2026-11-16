"""The hand-over to pi.

pi.orig is the unwrapped CLI: this launcher is `pi`, and it hands over the way
a `mv thing thing.orig` wrapper always has. `exec` - not a child process -
because pi must own the terminal, the signals and Ctrl-C, and because everything
exported above (the key, PI_CODING_AGENT_DIR, the ELM-only policy, the proxy
address) is inherited across the exec while nothing of the launcher stays
behind to be noticed.
"""

import os
import signal
import sys

# The Bash reference uses this trusted file for the same OS-fenced hand-over.
if not __package__:
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from elmpi.console import is_terminal
from elmpi.errors import Refusal, CANNOT_START

PRINT_FLAGS = ("-p", "--print")

def hand_over(command):
    """exec, with the signal dispositions a program expects to start with.

    Python ignores SIGPIPE at startup, and an ignored signal is inherited
    across exec - and bash cannot un-ignore one it was started with. So under
    this launcher `pi setup` ran a bootstrap.sh in which `yes | head -1` left
    `yes` writing "Broken pipe" errors with status 1 instead of dying quietly
    with 141, which is not the script that was tested.
    """
    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except (AttributeError, ValueError, OSError):
        pass
    os.execv(command[0], command)


def print_mode(argv):
    """True for `pi -p`: pi reads stdin then, so the terminal must be closed."""
    return any(argument in PRINT_FLAGS for argument in argv)


def run(root, arguments, env, prefix=()):
    """Check pi is there, close a terminal stdin in print mode, then exec it."""
    original = os.path.join(root, "pi.orig")
    if not os.access(original, os.X_OK):
        raise Refusal("pi is not installed here: %s is missing. Run %s first."
                      % (original, os.path.join(root, "bootstrap.sh")), code=CANNOT_START)
    # Anything this process spawns is a child of ours; see preflight.
    env.set("PI_ELM_CHILD", "1")
    # In print mode pi reads stdin so you can pipe input to it. A pipe ends with
    # EOF and all is well; an interactive terminal never does, so `pi -p "..."`
    # typed at a prompt waits on stdin forever and looks hung.
    if print_mode(arguments) and is_terminal(sys.stdin):
        try:
            null = os.open(os.devnull, os.O_RDONLY)
            os.dup2(null, 0)
            os.close(null)
        except OSError:
            pass
    # The jail must execute pi, not become arguments pi interprets as a prompt.
    # Keep its own flags separate too: sandbox-exec's -p is not pi print mode.
    command = list(prefix) + [original] + list(arguments)
    hand_over(command)


FENCE_FALLBACK = 3


def fence_check(argv, console):
    """`launch.py --fence-check <mode>`: the Bash reference's question about a
    machine that cannot make the fence, answered by the code cli.py uses.

    Exit 0 and nothing: the fence can be made, or none is wanted. Exit 3 with
    the warning on stdout: start unfenced. Exit 1 with the refusal on stderr:
    offline, which does not start without one.
    """
    from elmpi import jail, network
    from elmpi.environ import Environment

    name = argv[0] if argv else network.DEFAULT
    if argv[1:2] == ["--asked-again"]:
        # `pi --offline` typed in a session that started without its fence: what
        # the machine says now, whatever that session's ELM_PI_NO_JAIL says.
        reason = jail.fence_problem()
    else:
        reason = jail.unavailable(network.Mode(name, "flag"), Environment())
    if not reason:
        return 0
    if name == network.OFFLINE:
        console.note(*jail.refusal(reason, "pi --offline"))
        return CANNOT_START
    console.say(*jail.warning(reason))
    return FENCE_FALLBACK


def main(argv):
    """The Bash reference's hand-over: install root, proxy port, pi arguments."""
    from elmpi import jail, network
    from elmpi.console import Console
    from elmpi.environ import Environment

    console = Console()
    if argv[:1] == ["--fence-check"]:
        return fence_check(argv[1:], console)
    if len(argv) < 2:
        console.note("pi: fenced launch needs an install root and proxy port")
        return CANNOT_START
    env = Environment()
    try:
        root, port = argv[0], int(argv[1])
        fence = jail.plan(network.resolve("", env), root, env, port, sys.executable)
        if fence.note:
            console.note("    " + fence.note)
        run(root, argv[2:], env, prefix=fence.prefix)
        return 0
    except Refusal as refusal:
        console.show(refusal)
        return refusal.code
    except (OSError, ValueError) as problem:
        console.note("pi: %s" % problem)
        return CANNOT_START


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
