"""Whether to draw the banner, and how.

Kept apart from the text (banner_text.py) because the decision has more cases
than it looks: a terminal on both ends, not a sub-agent child, not a run whose
output a program reads, and not PI_ELM_BANNER=0. It goes to stderr, above the
TUI pi draws inline, so it stays in the scrollback and never enters an answer.
"""

import os

from elmpi.banner_text import BANNER

WIDTH = 74
COLOUR_ON = "\033[0;1;38;5;22;48;5;255m"   # palette 22 on 255: fixed RGB everywhere
COLOUR_OFF = "\033[0m"


def wanted(argv, env, stdin_is_tty, stderr_is_tty):
    """True when this launch should open with the credit line."""
    if env.get("PI_ELM_CHILD") or env.get("PI_ELM_BANNER") == "0":
        return False
    if not (stdin_is_tty and stderr_is_tty):
        return False
    # Walked without skipping option values, as the reference launcher does: a "-p"
    # anywhere in the arguments is a one-shot run, and so is anything at all
    # after a --mode, whose value is a protocol rather than a screen.
    previous = ""
    for argument in argv:
        if argument in ("-p", "--print") or argument.startswith("--mode="):
            return False
        if previous == "--mode":
            return False
        previous = argument
    return True


def columns(env, fallback=80):
    """The terminal's width, then COLUMNS, then 80: `stty size` and its fallbacks.

    A terminal that reports no width is treated as a missing one, as `stty
    size` returning 0 is in the reference launcher - a pty with no size set, or one
    being resized.
    """
    try:
        width = os.get_terminal_size(2).columns
    except OSError:
        width = 0
    if width > 0:
        return width
    try:
        width = int(env.get("COLUMNS"))
    except ValueError:
        return fallback
    return width if width > 0 else fallback


def render(env, width):
    """The banner's lines, boxed in colour when the terminal can take it.

    With NO_COLOR, TERM=dumb or a terminal narrower than the box, it is the
    same text without the box rather than a box broken across lines.
    """
    coloured = not env.get("NO_COLOR") and env.get("TERM", "dumb") != "dumb" and width >= WIDTH
    lines = []
    for line in BANNER.splitlines():
        if coloured:
            lines.append(COLOUR_ON + "  " + line.ljust(WIDTH - 2) + COLOUR_OFF)
        else:
            lines.append("  " + line)
    return lines
