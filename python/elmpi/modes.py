"""How much the agent may do without asking, and who decides.

    manual             nothing runs without your yes, beyond reading files in
                       the project and the tools in manualNoPrompt
    read-only-auto     manual, and shell commands that only read inside the
                       project run without asking
    auto               the permission gate's rules as written
    yolo               every ask answered yes, for this session only

The gate, patched by patch-pi.py --gate, reads PI_ELM_PERMISSION_MODE on every
decision; /mode (agent/extensions/permission-mode.ts) changes it inside a
session. A run's mode, in order:

  1. --manual/--auto/--yolo, for that run only: a flag never changes the default
  2. a sub-agent's: the mode of the session that started it. A yolo session's
     runs as auto and sends its asks to that session, which answers yes - yolo
     is never handed on, so nothing started from a session's shell inherits it
  3. this install's default: manual or auto, never yolo. agent/permission-mode
     holds what /mode saved, else permissionModes.default

Started from a shell, a PI_ELM_PERMISSION_MODE already in the environment can
make the run stricter, never looser: otherwise the agent could loosen a
session by setting it. read-only-auto is the gate's manual plus
PI_ELM_READ_AUTO, which switches on command-guard's reviewer - and
PI_ELM_READ_AUTO is set here from the mode and from nothing else, so one found
in a shell's environment is dropped unless it is consistent with the mode.
"""

import os

from elmpi.errors import Refusal

RANK = {"manual": 3, "read-only-auto": 2, "auto": 1, "yolo": 0}
KNOWN = frozenset(RANK)
SAVABLE = ("manual", "read-only-auto", "auto")
DEFAULT = "manual"

NO_GATE = "has no permission gate (made with --no-packages)"
UNPATCHED_GATE = ("has a permission gate that does not apply the permission modes "
                  "(--no-patch, or pi update --extensions patches it)")


class Resolution:
    """The mode this run runs in, the install's default, and what to say."""

    def __init__(self, mode, default, notes):
        self.mode = mode
        self.default = default
        self.notes = notes


def saved_mode(path):
    """What /mode last saved: the first line of agent/permission-mode."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            value = handle.readline()
    except OSError:
        return ""
    return "".join(value.split())


def read_default(env, saved):
    """The mode a new session starts in: the saved one, else the config's."""
    value = saved if saved in SAVABLE else env.get("ELM_PERMISSION_MODE_DEFAULT", DEFAULT)
    return value if value in SAVABLE else DEFAULT


def inherited(env):
    """PI_ELM_PERMISSION_MODE as found, with read-only-auto's second variable."""
    value = env.get("PI_ELM_PERMISSION_MODE")
    if value == "manual" and env.get("PI_ELM_READ_AUTO") == "1":
        return "read-only-auto"
    return value


def gate_problem(root):
    """Why the gate cannot apply a mode, or "" when it can.

    The gate is a package, and patch-pi.py adds two things to it. Asked for a
    mode the gate cannot apply, the launcher refuses rather than runs it as
    auto; as the default, on an install made with --no-patch or --no-packages,
    it runs as auto and says so.
    """
    package = os.path.join(root, "agent", "npm", "node_modules",
                           "@gotgenes", "pi-permission-system")
    if not os.path.isdir(package):
        return NO_GATE
    manager = os.path.join(package, "src", "policy", "permission-manager.ts")
    index = os.path.join(package, "src", "index.ts")
    if not (_contains(manager, 'PI_ELM_PERMISSION_MODE === "manual"')
            and _contains(index, 'PI_ELM_PERMISSION_MODE === "yolo"')):
        return UNPATCHED_GATE
    return ""


def _contains(path, needle):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return needle in handle.read()
    except OSError:
        return False


def resolve(flag, env, saved, child, problem, argv):
    """Decide this run's mode, with the lines to print about it.

    Refuses - rather than returns - when a mode was asked for by name and the
    gate cannot apply it: running it as auto would be doing something else.
    """
    default = read_default(env, saved)
    from_environment = inherited(env)
    notes = []

    if flag:
        mode = flag
    elif child and from_environment:
        # Anything but a known mode is read as the strictest: whoever set it
        # meant to restrict something.
        if from_environment in KNOWN and from_environment != "yolo":
            mode = from_environment
        elif from_environment == "yolo":
            mode = "auto"
        else:
            mode = "manual"
    else:
        mode = default

    if not child and from_environment:
        if from_environment not in KNOWN:
            from_environment = "manual"
        if RANK[from_environment] > RANK[mode]:
            if flag:
                notes.append("note: PI_ELM_PERMISSION_MODE=%s in the environment keeps this "
                             "run %s; --%s cannot loosen it."
                             % (from_environment, from_environment, flag))
            mode = from_environment
        elif from_environment != mode:
            notes.append("note: PI_ELM_PERMISSION_MODE=%s in the environment cannot loosen a "
                         "run; this one is %s (pi --%s to choose it)."
                         % (from_environment, mode, from_environment))

    if mode != "auto" and problem:
        if flag:
            # Said before the refusal, as bash prints it: the note explains
            # which mode was asked for and why it is not the one being refused.
            raise Refusal(*("    " + note for note in notes),
                          "pi: this install %s, so it cannot run in %s mode." % (problem, mode))
        if not child:
            notes.append("note: this install %s, so it runs in auto mode." % problem)
        mode = default = "auto"

    if not child:
        if mode == "yolo":
            notes.append("permission mode: yolo for this session only - every ask is answered "
                         "yes; denies still apply. New sessions start in %s." % default)
        elif mode != default:
            notes.append("permission mode: %s for this session; new sessions start in %s "
                         "(/mode %s can change that)." % (mode, default, mode))
        if mode in ("manual", "read-only-auto") and ("-p" in argv or "--print" in argv):
            notes.append("note: %s mode with -p: there is no one to ask, so commands and "
                         "edits are refused (pi --auto -p lets them run)." % mode)
    return Resolution(mode, default, notes)


def apply(env, resolution):
    """Put the decision where the gate and every child will read it."""
    if resolution.mode == "read-only-auto":
        env.set("PI_ELM_PERMISSION_MODE", "manual")
        env.set("PI_ELM_READ_AUTO", "1")
    else:
        env.set("PI_ELM_PERMISSION_MODE", resolution.mode)
        env.unset("PI_ELM_READ_AUTO")
    env.set("PI_ELM_PERMISSION_DEFAULT", resolution.default)
    # Always this install's list, never the caller's: a longer one would
    # loosen manual.
    manual = env.get("ELM_MANUAL_NO_PROMPT")
    approved = "auto" if env.get("ELM_APPROVED_AGENTS") == "auto" else "manual"
    # Before each child of a parallel or chain run starts, pi-subagents makes a
    # call of its own, `subagent_launch`, for permission extensions to see. In
    # manual every call asks, so a launch you had just allowed asked again for
    # each child (seen live, 2026-11-13). With approvedAgents auto, allowing
    # the launch is the permission for its children.
    if approved == "auto":
        manual = (manual + "," if manual else "") + "subagent_launch"
    env.set("PI_ELM_MANUAL_ALLOW", manual)
    env.set("PI_ELM_APPROVED_AGENTS", approved)
    # The switch to auto happens only in the process pi-subagents starts for a
    # launch you allowed, which sets PI_SUBAGENT_RUNNER_PID to its own pid. A
    # pi started through here is never that process, so it must not pass for
    # one: a manual session's shell could otherwise switch itself to auto.
    env.unset("PI_SUBAGENT_RUNNER_PID")
