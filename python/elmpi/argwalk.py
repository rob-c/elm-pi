"""How pi reads its own arguments, and who has to read them the same way.

pi takes the value of some options with `args[++i]` whatever the next argument
is, `--` and other options included; the rest it takes only when the value does
not start with `-`. A walker that does not know which is which reads
`--name -- --model x` as prompt text where pi reads a model choice, and that
exact mistake - the argument guard passing something pi acted on - is why the
list below exists as one list rather than as a `case` in each block.

`classify()` is the walk every block uses: it says, for each argument, whether
it is an option, the value an option consumed, or prompt text after `--`. A
block that needs more (the tool exclusions rebuild the list) builds its own
loop on the same two rules.
"""

OPTION = "option"   # an option, or `--` itself
VALUE = "value"     # the argument the option before it consumed
TEXT = "text"       # prompt text: everything after `--`

# pi 1.5.0's parser (dist/cli/args.js) reads these with args[++i]. The others
# that take a value take it only when it does not start with "-".
VALUE_OPTIONS = frozenset({
    "--provider", "--model", "--api-key", "--system-prompt", "--append-system-prompt",
    "--name", "-n", "--session", "--session-id", "--fork", "--session-dir", "--models",
    "--tools", "-t", "--exclude-tools", "-xt", "--thinking", "--export", "--extension",
    "-e", "--skill", "--prompt-template", "--theme",
})


def takes_value(token):
    """True when pi takes the argument after `token` as its value."""
    return token in VALUE_OPTIONS


def classify(argv):
    """Yield `(index, argument, kind)` for each argument, in order."""
    taken = False
    prompt = False
    for index, argument in enumerate(argv):
        if prompt:
            yield index, argument, TEXT
            continue
        if taken:
            taken = False
            yield index, argument, VALUE
            continue
        if argument == "--":
            prompt = True
            yield index, argument, OPTION
            continue
        yield index, argument, OPTION
        if takes_value(argument):
            taken = True


def joined_value(argv, name):
    """The last value pi will use for `--name`, from either spelling, or None.

    `--session-dir a --session-dir=b` is pi's last one, as it is here. A
    trailing `--name` with no value is not reported: that is pi's to complain
    about, and the launcher must not swallow an argument to look tidy.
    """
    found = None
    wanted = False
    for _, argument, kind in classify(argv):
        if kind == VALUE:
            if wanted:
                found = argument
            wanted = False
        elif kind == OPTION:
            wanted = argument == name
            if argument.startswith(name + "="):
                found = argument[len(name) + 1:]
    return found


def has_flag(argv, *flags):
    """True when one of `flags` is an option - not an option's value, not text."""
    return any(argument in flags for _, argument, kind in classify(argv) if kind == OPTION)
