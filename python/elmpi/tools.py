"""Tools that are not sent to the model, and the caller's own exclusions.

Every tool's definition goes with every request, so a rarely used tool costs
its length on all of them. Three groups are left out:

* web tools, unless PI_ELM_WEB=1 or --remote brought them back: they send the
  model's queries out, fetch arbitrary pages, and then treat what comes back
  as input - the one leak path that needs nobody to do anything wrong
* notebook edits with simple substitutes, always (they are in runtime.env)
* the workflow tools, unless the run asks for them

pi keeps only the last --exclude-tools it is given, so the caller's own list
used to replace this one and turn the web tools back on. The caller's lists are
folded into this one instead, as a single flag. An explicit --tools allowlist
is left alone: naming a web tool there is asking for it.
"""

from elmpi.argwalk import takes_value

BG_WAIT = "bg_wait"
EXCLUDE_OPTIONS = ("--exclude-tools", "-xt")
ALLOW_OPTIONS = ("--tools", "-t")


def _drop_comma(value):
    return value[:-1] if value.endswith(",") else value


def _add(value, extra):
    """`${value:+"$value,"}$extra`: no separator for an empty list."""
    return (value + "," if value else "") + extra


def wakes_on_its_own(argv):
    """True for a run that ends when its reply does: `pi -p`, --mode json/print.

    bg_wait is only useful where nothing else wakes the session. An interactive
    session is woken by each run's notices, and wait-guard refused the tool
    there - yet the model kept calling it: four times in a row in a driven
    session on 2026-11-13, each one a turn of ~50k input tokens. Not offered,
    it is not called. A sub-agent child does not get it either: pi-subagents
    sets PI_SUBAGENT_CHILD in every child, and the launcher's own condition
    (`... || [ -n "$PI_SUBAGENT_CHILD" ] || add bg_wait`) leaves it out there.
    """
    previous = ""
    for argument in argv:
        if argument in ("-p", "--print", "--mode=json", "--mode=print"):
            return True
        if previous == "--mode" and argument in ("json", "print"):
            return True
        previous = argument
    return False


def built_in(env, with_all, workflows):
    """The exclusions this install always adds, before the caller's."""
    value = "" if with_all else env.get("ELM_EXCLUDED_TOOLS")
    if env.get("PI_ELM_WEB") != "1":
        value = _add(value, env.get("ELM_WEB_TOOLS"))
    if not workflows:
        value = _add(value, env.get("ELM_WORKFLOW_TOOLS"))
    return _drop_comma(value)


def merge(argv, exclusions):
    """Fold the caller's -xt/--exclude-tools into `exclusions`.

    Returns `(arguments for pi, flags to put in front of them)`. With an
    explicit --tools/-t allowlist, both are returned unchanged: the caller has
    said which tools it wants, and an exclusion would contradict that.
    """
    rebuilt = []
    caller = []
    allowlist = False
    previous = ""
    for argument in argv:
        if previous == "stop":
            rebuilt.append(argument)
            continue
        if previous == "value":
            caller.append(argument)
            previous = ""
            continue
        if previous == "other":
            rebuilt.append(argument)
            previous = ""
            continue
        if argument == "--":
            previous = "stop"
            rebuilt.append(argument)
        elif argument in EXCLUDE_OPTIONS:
            previous = "value"
        elif argument in ALLOW_OPTIONS:
            allowlist = True
            previous = "other"
            rebuilt.append(argument)
        else:
            rebuilt.append(argument)
            if takes_value(argument):
                previous = "other"
    # A trailing flag with no value is pi's to report, not ours to swallow.
    if previous == "value":
        rebuilt.append("--exclude-tools")
    if allowlist:
        return list(argv), []
    # An empty -xt value contributes nothing, as bash's `${VAR:+$VAR,}$value`
    # does: `pi -xt ""` must not leave a trailing comma in the list.
    named = ",".join(value for value in caller if value)
    combined = exclusions + ("," + named if named else "")
    return rebuilt, ["--exclude-tools", combined]


def plan(env, switches, argv, child):
    """The exclusion flag this run needs, and pi's arguments after the merge."""
    excluded = built_in(env, switches.with_all, switches.workflows)
    if not wakes_on_its_own(argv) and not switches.with_all and not child:
        excluded = _add(excluded, BG_WAIT)
    excluded = _drop_comma(excluded)
    if not excluded:
        # --with-all --remote leaves no exclusions. Keep the arguments in the
        # same slot as merge(): swapping them bypassed update/setup dispatch
        # and hid --session-dir from transcript permission handling.
        return list(argv), []
    return merge(argv, excluded)
