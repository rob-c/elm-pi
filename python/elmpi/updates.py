"""The parts of the install that change: `pi update`, `pi setup`, optional parts.

All three run before the egress proxy starts, because all three need the
network by definition: install.sh fetches the source, bootstrap.sh fetches pi,
the extension packages, a standalone Python and the PyPI index. Every other
launch is offline by default (see cli.py), and these are the exemption.

`pi update` on its own means "update this install": one command, in the order
the pieces depend on each other - the repository and pi first, then the
extension packages pi itself manages. Doing only the first leaves pi-subagents
and the rest on whatever npm resolved at install time, which is the
half-updated state this used to produce. `pi update --extensions` is the
recorded set instead, for going back.
"""

import os
import subprocess

from elmpi import launch, usage
from elmpi.errors import Refusal, CANNOT_START, REFUSED
from elmpi.paths import entry_point

SETUP_FLAGS = {
    "--python": "--with-python",
    "--pypi-index": "--with-pypi-index",
    "--all": "--with-all",
    "--no-python": "--no-python",
    "--no-pypi-index": "--no-pypi-index",
}


def intercept(argv, root, env, console):
    """Handle a subcommand this launcher owns. Returns its exit code, or None."""
    if not argv:
        return None
    if argv[0] == "update":
        return _update(argv, root, env, console)
    if argv[0] == "setup":
        return _setup(argv[1:], root, env, console)
    return None


def _update(argv, root, env, console):
    extensions = "--extensions" in argv
    if "--models" in argv:
        # pi's own: it refreshes the providers' catalogues. ELM's models are
        # agent/models.json, which configure.sh refreshes from the gateway, and
        # every other provider is stripped.
        raise Refusal.about(
            "`pi update --models` is not available in this install.",
            "ELM's models are agent/models.json; %s refreshes them from the gateway."
            % os.path.join(root, "configure.sh"),
        )
    if not extensions:
        console.note(
            "pi: updating this install.",
            "    source, then pi and the extension packages at their latest versions;",
            "    if the new versions fail the install's checks, the current ones are put back.",
            "    To go back to the tested versions instead: pi update --extensions",
            "    The options this install was made with (agent/install-options) are kept.",
            "",
        )
        # The launch-time offline default must not follow us into an update.
        env.unset("PI_OFFLINE", "PI_SKIP_VERSION_CHECK")
        # install.sh reads the branch and repository from agent/install-options,
        # and bootstrap.sh the --no-* flags, so neither needs repeating here.
        child = dict(os.environ)
        child.update(ELM_PI_PREFIX=root, ELM_PI_NO_PATH="1", ELM_PI_NO_LINK="1")
        result = subprocess.run(
            [os.path.join(root, "install.sh"), "--update", "--no-path", "--no-link"],
            env=child)
        if result.returncode != 0:
            # install.sh and bootstrap.sh have said what was put back and what
            # was not; this only must not claim more than they did.
            raise Refusal("pi: the update did not complete - see above for what was rolled back.",
                          code=CANNOT_START)
        return 0

    # "The tested versions" means the tested set: --force-packages also returns
    # pi to config/versions.json's pin when a `pi update` moved it on, since the
    # packages were tested against that pi.
    console.note(
        "pi: reinstalling the extension packages at the tested versions "
        "(config/versions.json),",
        "    and pi itself if it is not at its tested version.",
    )
    env.unset("PI_OFFLINE", "PI_SKIP_VERSION_CHECK")
    result = subprocess.run([os.path.join(root, "bootstrap.sh"), "--force-packages",
                             "--non-interactive"])
    return result.returncode


def _setup(argv, root, env, console):
    flags = []
    for argument in argv:
        mapped = SETUP_FLAGS.get(argument)
        if mapped is None:
            console.note("pi setup: unknown option: %s" % argument)
            _print_optional_parts(console)
            return REFUSED
        flags.append(mapped)
    if not flags:
        _print_optional_parts(console)
        return REFUSED
    env.unset("PI_OFFLINE", "PI_SKIP_VERSION_CHECK")
    bootstrap = os.path.join(root, "bootstrap.sh")
    launch.hand_over([bootstrap, "--non-interactive"] + flags)
    return REFUSED


def _print_optional_parts(console):
    console.note(*usage.optional_parts_section())


def with_all(argv, root, env, console):
    """Run the optional parts' setup once, then start again with everything.

    The installed extras are built by bootstrap.sh (as `pi setup --all` would),
    recorded so `pi update` keeps them, and then the launcher starts again from
    the top, since the agent's Python is put on PATH earlier on a second run.
    ELM_PI_WITH_ALL_SET_UP stops a part that will not build from turning into a
    loop of re-installs.
    """
    python = os.path.join(root, "agent", "python", "env", "bin", "python")
    index = os.path.join(root, "agent", "pypi-index.db")
    if os.access(python, os.X_OK) and os.path.isfile(index) and os.path.getsize(index) > 0:
        return
    if env.get("ELM_PI_WITH_ALL_SET_UP"):
        console.note("pi: --with-all: some optional parts did not build (see above); "
                     "starting without them.")
        return
    console.note(
        "pi: --with-all - setting up the optional parts first: the agent's Python and the",
        "    offline PyPI index (~2GB to download, once). Recorded, so pi update keeps them.",
    )
    env.unset("PI_OFFLINE", "PI_SKIP_VERSION_CHECK")
    result = subprocess.run([os.path.join(root, "bootstrap.sh"), "--non-interactive",
                             "--with-all"])
    if result.returncode != 0:
        raise Refusal("pi: setting up the optional parts failed - see above. Without them: "
                      "pi (no --with-all).", code=CANNOT_START)
    env.set("ELM_PI_WITH_ALL_SET_UP", "1")
    entry = entry_point(root)
    launch.hand_over([entry] + list(argv))
