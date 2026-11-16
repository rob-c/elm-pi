"""Which extensions load when pi's own discovery is off, and why each one.

pi loads `agent/extensions/` by itself. Two things switch that off: `--fast`
(quick, local starts) and the caller's own `--no-extensions`/`-ne`. The policy
extensions have to be loaded either way - the two used to differ, and `-ne`
then ran with the model policy alone: no permission gate, no write protection,
no trust guard, no pinned instructions. One list now serves both.

The permission gate ships as a package, so it is named by path. A release that
moves its entry point must not quietly drop the gate: a gate package without
its entry point stops the launch instead.
"""

import os

from elmpi.argwalk import classify
from elmpi.errors import Refusal, CANNOT_START

POLICY_EXTENSIONS = (
    "elm-only", "protected-paths", "trust-guard", "pinned-instructions", "command-guard",
)

# Conveniences on top of the policy for --fast: cheap, local, and what makes a
# quick start still feel like this install.
FAST_CONVENIENCES = (
    "todo", "network", "skill-router", "remote-research", "permission-mode", "claim-guard",
    "repeat-guard", "server-reaper", "report-guard", "date-note",
)

GATE_PACKAGE = os.path.join("agent", "npm", "node_modules",
                            "@gotgenes", "pi-permission-system")
GATE_ENTRY = os.path.join(GATE_PACKAGE, "src", "index.ts")


def wants_shim(argv, llama):
    """True when this run wants the tool-call shim, for Llama.

    `--llama` asks for it, and so does naming elm-shim in --model or
    --provider: either spelling has the shim in the value pi will use.
    """
    if llama:
        return True
    joined = " " + " ".join(argv) + " "
    return " elm-shim" in joined or "elm-shim/" in joined


def discovery_disabled(argv):
    """True when the caller turned pi's own extension discovery off."""
    for _, argument, kind in classify(argv):
        if kind != "option":
            continue
        if argument == "--":
            return False
        if argument in ("--no-extensions", "-ne"):
            return True
    return False


def _policy_arguments(root):
    """The `-e` arguments of the policy set, or a refusal that says what to do."""
    arguments = []
    for name in POLICY_EXTENSIONS:
        path = os.path.join(root, "agent", "extensions", name + ".ts")
        if not os.path.isfile(path):
            raise Refusal.about(
                "agent/extensions/%s.ts is missing, and with extension discovery off "
                "nothing else loads it." % name,
                "Run %s to put it back." % os.path.join(root, "bootstrap.sh"),
                code=CANNOT_START,
            )
        arguments += ["-e", path]
    package = os.path.join(root, GATE_PACKAGE)
    if os.path.isdir(package):
        entry = os.path.join(root, GATE_ENTRY)
        if not os.path.isfile(entry):
            raise Refusal.about(
                "the permission gate is installed but %s is not there." % entry,
                "Not starting without it. If @gotgenes/pi-permission-system moved its "
                "entry point,",
                "GATE_ENTRY in %s needs the new path; otherwise: pi update --extensions"
                % os.path.join(root, "python", "elmpi", "extensions.py"),
                code=CANNOT_START,
            )
        arguments += ["-e", entry]
    return arguments


def plan(root, switches):
    """The `-e`/`--no-extensions` arguments to put in front of pi's own."""
    arguments = []
    if switches.fast:
        arguments.append("--no-extensions")
        arguments += _policy_arguments(root)
        for name in FAST_CONVENIENCES:
            path = os.path.join(root, "agent", "extensions", name + ".ts")
            if os.path.isfile(path):
                arguments += ["-e", path]
        shim = os.path.join(root, "agent", "extensions", "elm-shim.ts")
        if wants_shim(switches.rest, switches.llama) and os.path.isfile(shim):
            arguments += ["-e", shim]
    elif discovery_disabled(switches.rest):
        arguments += _policy_arguments(root)
    return arguments
