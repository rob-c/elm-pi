"""The launch, in the order it has to happen.

Each step is in `run()` in the order the reference launcher performs it, and the
order is not arbitrary:

* the deleted-folder check is first: nothing else can be trusted in a folder
  that has no path, and --help included
* --help comes before the key check, the load preflight and the proxy: an
  install that cannot start is exactly the one whose help you want to read
* the model policy comes before the key check, so a refusal does not wait on a
  key, and an install with none yet still refuses --model anthropic/...
* `pi update` and `pi setup` come before the proxy, because they need the
  network
* the permission mode, the transcript folder and the proxy come last, after
  everything that might end the launch early has had its chance
"""

import os
import signal
import sys

from elmpi import (argwalk, banner, credentials, extensions, flags, interpreter, jail, launch,
                   modes, network, paths, policy, preflight, proxy, runtime, state, toolchain,
                   tools, untrusted, updates, usage)
from elmpi.console import Console, is_terminal
from elmpi.environ import Environment, clean_path, load_dotenv
from elmpi.errors import Refusal, CANNOT_START

# Commands that do not contact the ELM inference endpoint: they stay usable
# when a key has expired or a fresh install still needs configuring, while
# ordinary sessions fail early with guidance.
NO_KEY_NEEDED = ("update", "setup", "--list-models", "--version", "-v")

SUBCOMMANDS = {
    "auth": (
        "`pi auth` is not available in this install.",
        "pi signs in to ELM with the key in {root}/.env, and offers no other provider",
        "({root}/LOCKDOWN.md). To change the key, edit .env and run {root}/configure.sh.",
    ),
    "mcp": (
        "`pi mcp` is not available in this install.",
        "pi's MCP support is switched off here: an MCP server is a program or a remote "
        "service",
        "outside the reviewed set and the egress policy ({root}/LOCKDOWN.md, -builtin:mcp).",
    ),
    "config": (
        "`pi config` is not available in this install.",
        "Which package resources load is set in {root}/templates/settings.json, which every",
        "bootstrap and `pi update` rebuilds agent/settings.json from, so a change made here",
        "would be undone at the next update (CONTRIBUTING.md).",
    ),
    "list": (
        "`pi list` is not available in this install.",
        "What is running: {root}/agent/installed-versions.json. The reviewed set:",
        "{root}/templates/packages.json. pi itself: pi --version.",
    ),
}
PACKAGE_COMMANDS_NAMES = frozenset({"install", "remove", "uninstall"})
PACKAGE_COMMANDS = (
    "`pi {command}` is not available in this install.",
    "Its packages are the reviewed set in {root}/templates/packages.json,",
    "which every bootstrap and `pi update` rebuilds agent/npm and agent/settings.json from,",
    "so a package added here would be removed again at the next update.",
    "To add one for good: list it in templates/packages.json and, as npm:<name>, in",
    "templates/settings.json \"packages\", then run {root}/bootstrap.sh (CONTRIBUTING.md).",
    "To try a local extension for one session: PI_ELM_UNLOCK=1 pi -e /path/to/extension.ts",
)


class Launcher:
    """One launch, from the caller's arguments to pi's."""

    def __init__(self, argv, root, console=None, env=None):
        self.argv = list(argv)
        self.root = root
        self.console = console if console is not None else Console()
        self.env = env if env is not None else Environment()

    # -- the sequence ---------------------------------------------------------

    def run(self):
        self._refuse_deleted_folder()
        self._install_environment()
        if argwalk.has_flag(self.argv, "-h", "--help"):
            return self._help()

        runtime.load(self.root, self.env)
        load_dotenv(os.path.join(self.root, ".env"), self.env, self.console)
        # Relative PATH entries out: with "." on PATH, a repository's own ./git
        # or ./fd runs whenever pi looks that command up in it. The rest of
        # PATH - conda included - is the researcher's, and the agent's shell
        # needs it.
        self.env.set("PATH", clean_path(self.env.get("PATH"), relative_only=True))
        interpreter.select(self.root, self.env, mode="fast")
        self._toolchain()

        switches = flags.parse(self.argv, self.env)
        if flags.conflict(switches):
            raise Refusal.about("--llama and --mistral each choose the model for the run; "
                                "give one of them.")
        self._refuse_pi_subcommand(switches.rest)
        self._apply_model_policy(switches.rest)
        sessions = self._needs_key(switches.rest)
        self._require_key(sessions)
        self._refuse_untrusted_folder(sessions)
        # After the three above, as in the reference: a mistyped PI_ELM_NETWORK
        # used to be reported first, so `--model anthropic/x` was answered with
        # a line about the network, and an install with no key exited 2, not 1.
        saved = network.saved_mode(self.root)
        try:
            self.network = network.resolve(switches.network_flag, self.env, saved)
        except ValueError as problem:
            raise Refusal("pi: %s" % problem)
        self.env.set(network.ENV, self.network.name)
        self.env.set(network.DEFAULT_ENV, saved or network.DEFAULT)
        self._draw_banner(sessions, switches.rest)
        self._apply_network(switches, sessions)

        before_pi = []
        before_pi += self._computer_use(switches)
        before_pi += extensions.plan(self.root, switches)
        before_pi += self._choose_model(switches)
        switches.rest, exclusions = tools.plan(
            self.env, switches, switches.rest, bool(self.env.get("PI_SUBAGENT_CHILD")))
        before_pi += exclusions

        self._go_offline(switches.rest)
        outcome = updates.intercept(switches.rest, self.root, self.env, self.console)
        if outcome is not None:
            return outcome
        # Not for a sub-agent child: it would install into the install its
        # parent is already running from, mid-session (the bash launcher's
        # `[ -z "${PI_ELM_CHILD:-}" ]` in the same condition).
        if switches.with_all and not self.env.get("PI_ELM_CHILD"):
            updates.with_all(self.argv, self.root, self.env, self.console)
        self._permission_mode(switches, switches.rest)

        # Transcripts hold every file the agent read, so the folder they go in
        # is made private before pi can write one.
        state.ensure_gitignore(os.getcwd())
        directory = state.session_dir(self.root, self.env, switches.rest, os.getcwd())
        state.secure(self.root, directory, self.env)

        proxy_port = proxy.ensure(self.root, self.env, self.network)
        for line in preflight.note(self.env):
            self.console.note(line)
        self._note_inside_install(sessions)

        fence = jail.plan(self.network, self.root, self.env, proxy_port, sys.executable)
        if fence.note:
            self.console.note("    " + fence.note)
        launch.run(self.root, before_pi + switches.rest, self.env, prefix=fence.prefix)
        return 0

    # -- where the launch is --------------------------------------------------

    def _refuse_deleted_folder(self):
        """A shell keeps its folder open after it is deleted, and pi started
        there would have every write fail: sessions and memory going nowhere,
        and node's process.cwd() throwing at whatever first asks."""
        try:
            os.getcwd()
            return
        except OSError:
            pass
        typed = self.env.get("PWD")
        if typed.startswith("/"):
            lines = ["pi: the folder this shell is in has been deleted (%s)." % typed]
            if os.path.isdir(typed):
                lines.append("    A new folder exists at that path; the shell is still in the "
                             "old one. Run: cd \"%s\"" % typed)
            else:
                lines.append("    cd to a folder that exists, then run pi again.")
        else:
            lines = ["pi: the folder this shell is in has been deleted.",
                     "    cd to a folder that exists - cd \"$PWD\" in your shell if it was "
                     "recreated - then run pi again."]
        raise Refusal(*lines)

    def _install_environment(self):
        """The environment every path below builds on."""
        managed = os.path.join(self.root, "agent", "bin")
        node = os.path.join(self.root, ".node", "bin")
        self.env.set("PATH", managed + ":" + node + ":" + self.env.get("PATH"))
        # Telemetry is off, and not a knob: it reports the install to pi.dev.
        self.env.set("PI_TELEMETRY", "0")
        # Nothing on this list belongs in a locked install: where /share points,
        # and pi's switch for unreleased features.
        self.env.unset("PI_SHARE_VIEWER_URL", "PI_EXPERIMENTAL")
        # Copies (/copy, Ctrl+X) also go to the terminal as OSC 52, so they reach
        # the clipboard of the machine you are sitting at when pi runs on another
        # one. Locally it is a second write of the same text; write-only.
        self.env.set_default("PI_CLIPBOARD_OSC52", "1")
        # __pycache__ beside every module the agent imports leaves directories
        # nobody asked for in the project: a batch of coding problems put one
        # into each project folder. Set here, everything the agent runs
        # inherits it. Before Python 3.11 any value means "do not write", so 0
        # is passed on as unset.
        self.env.set_default("PYTHONDONTWRITEBYTECODE", "1")
        if self.env.get("PYTHONDONTWRITEBYTECODE") == "0":
            self.env.unset("PYTHONDONTWRITEBYTECODE")
        # keep config, sessions and credentials inside this directory, not ~/.pi
        self.env.set("PI_CODING_AGENT_DIR", os.path.join(self.root, "agent"))
        self._matplotlib_backend()

    def _matplotlib_backend(self):
        """Figures go to files, which view-outputs shows the model; nothing the
        agent runs should open a window - on macOS a plt.show() with the GUI
        backend can hang the command, the persistent python kernel included.

        Not MPLBACKEND: a Jupyter kernel picks its inline backend only when that
        is unset, and with it set to Agg a notebook's plots came out as a
        warning and no image. A matplotlibrc saying Agg ranks below both, so
        notebooks keep inline figures and scripts get Agg. Only where the
        researcher has no matplotlib setup of their own.
        """
        home = paths.home_dir()
        configured = self.env.get("MPLCONFIGDIR")
        candidates = [
            (configured + "/matplotlibrc") if configured else "/matplotlibrc",
            os.path.join(self.env.get("XDG_CONFIG_HOME", os.path.join(home, ".config")),
                         "matplotlib", "matplotlibrc"),
            os.path.join(home, ".matplotlib", "matplotlibrc"),
        ]
        ours = os.path.join(self.root, "config", "matplotlibrc")
        if (not self.env.get("MPLBACKEND") and not self.env.get("MATPLOTLIBRC")
                and not any(os.path.isfile(path) for path in candidates)
                and os.path.isfile(ours)):
            self.env.set("MATPLOTLIBRC", ours)

    def _toolchain(self):
        try:
            toolchain.arrange(self.root, self.env)
        except toolchain.PrivateTmpRefusal as problem:
            raise Refusal("pi: %s is not a private directory owned by you (a symlink, or "
                          "someone else's?) - set TMPDIR to one that is" % problem.directory,
                          code=CANNOT_START)

    # -- --help ---------------------------------------------------------------

    def _help(self):
        """This launcher's help, then pi's own, on an install that may not run."""
        self.console.say(usage.USAGE.rstrip("\n"))
        original = os.path.join(self.root, "pi.orig")
        if not os.access(original, os.X_OK):
            return 0
        self.console.say()
        # pi's half gets what a session gets, as far as an install that may not
        # start allows: this agent/, no startup network work, and no provider
        # credentials.
        self.env.set("PI_OFFLINE", "1")
        self.env.set("PI_SKIP_VERSION_CHECK", "1")
        if os.path.isfile(runtime.path(self.root)):
            runtime.load(self.root, self.env)
        else:
            self.env.set("ELM_PROVIDER_CREDENTIALS",
                         " ".join(runtime.credential_names(self.root)))
        if self.env.get("PI_ELM_UNLOCK") != "1":
            credentials.scrub(self.env)
        launch.hand_over([original, "--help"])
        return 0

    # -- what this install refuses -------------------------------------------

    def _refuse_pi_subcommand(self, argv):
        """pi's own subcommands, each with what to do instead.

        pi dispatches a subcommand only as its first argument, and this launcher
        adds options in front of the caller's, so a subcommand that got past
        here would never reach pi as one: `pi auth login x` became a prompt to
        the model.
        """
        if not argv:
            return
        command = argv[0]
        if command in PACKAGE_COMMANDS_NAMES:
            template = PACKAGE_COMMANDS
        else:
            template = SUBCOMMANDS.get(command)
        if template is None:
            return
        lines = [line.format(root=self.root, command=command) for line in template]
        raise Refusal("pi: " + lines[0], *("    " + line for line in lines[1:]))

    def _apply_model_policy(self, argv):
        if self.env.get("PI_ELM_UNLOCK") == "1":
            return
        credentials.scrub(self.env)
        problem = policy.check_args(argv, self.env)
        if problem:
            raise Refusal.about(
                problem,
                "This install is restricted to the University's self-hosted ELM models.",
                "Why, and how to lift it: %s" % os.path.join(self.root, "LOCKDOWN.md"),
            )

    def _needs_key(self, argv):
        return not (argv and argv[0] in NO_KEY_NEEDED)

    def _require_key(self, sessions):
        if sessions and not self.env.get("ELM_API_KEY"):
            raise Refusal(
                "ELM_API_KEY is not set. Copy %s to %s and add your ELM key."
                % (os.path.join(self.root, ".env.example"), os.path.join(self.root, ".env")),
                "Run %s if this install has not been set up yet."
                % os.path.join(self.root, "bootstrap.sh"),
                code=CANNOT_START,
            )

    def _refuse_untrusted_folder(self, sessions):
        if not sessions or self.env.get("PI_FORCE") == "1" or self.env.get("PI_ELM_CHILD"):
            return
        folder = self.env.get("PWD") or os.getcwd()
        reason = untrusted.untrusted_folder(folder, self.env)
        if reason:
            raise Refusal.about(
                "not starting in %s - %s." % (folder, reason),
                "The folder pi starts in is the project it works on, and nothing inside it is",
                "asked about. cd to a project folder first (mkdir ~/scratch for a quick "
                "question),",
                "or start here anyway with PI_FORCE=1. Why: %s"
                % os.path.join(self.root, "LOCKDOWN.md"),
            )

    # -- what this run offers -------------------------------------------------

    def _draw_banner(self, sessions, argv):
        if not sessions:
            return
        if not banner.wanted(argv, self.env, is_terminal(sys.stdin), is_terminal(sys.stderr)):
            return
        self.console.note(*banner.render(self.env, banner.columns(self.env)))
        self.console.note()

    def _apply_network(self, switches, sessions=True):
        """What this run may reach, in the three modes network.py names.

        The mode decides three things at once, which is why it is one decision:
        whether the model's web tools are offered, which hosts the egress proxy
        will connect to, and whether the OS fences the session to that proxy.
        """
        mode = self.network
        # A machine that cannot make the fence: offline is refused, anything
        # else starts without one and says so (jail.warning has the request).
        # A session started from this one inherits ELM_PI_NO_JAIL, so it is
        # neither asked nor warned again.
        if not self.env.get("PI_ELM_CHILD"):
            self.env.unset(network.UNFENCED_ENV)      # this launch's own answer, not a shell's
        elif (self.env.get(network.UNFENCED_ENV) == "fallback" and mode.name == network.OFFLINE
              and mode.source == "flag"):
            # `pi --offline` typed in a session that started without its fence. The
            # ELM_PI_NO_JAIL it inherits is the launcher's, not a request, and it
            # made this the one way to get an unfenced offline run without asking
            # for one (the Ubuntu VM, 2026-11-16). Asked again: refused if the
            # machine still has no fence, fenced if it now has.
            if jail.fence_problem():
                raise Refusal(*jail.refusal(jail.fence_problem(), "pi --offline"),
                              code=CANNOT_START)
            self.env.unset("ELM_PI_NO_JAIL", network.UNFENCED_ENV)
        reason = jail.unavailable(mode, self.env)
        warn = []
        if reason:
            if mode.name == network.OFFLINE:
                raise Refusal(*jail.refusal(reason, "pi --offline"), code=CANNOT_START)
            self.env.set("ELM_PI_NO_JAIL", "1")
            self.env.set(network.UNFENCED_ENV, "fallback")
            warn = jail.warning(reason) if sessions else []
        if mode.web:
            self.env.set("PI_ELM_WEB", "1")
            # remote-research.ts reads this, here and in sub-agents, which inherit it
            self.env.set("PI_ELM_REMOTE", "1")
        else:
            self.env.unset("PI_ELM_WEB", "PI_ELM_REMOTE")
        self.console.note("    " + network.describe(mode, self.env))
        if warn:
            self.console.note(*warn)
        if mode.wildcard:
            existing = self.env.get("ELM_PI_PROXY_ALLOW")
            self.env.set("ELM_PI_PROXY_ALLOW", (existing + "," if existing else "") + "*")
            # The one mode that gives up the proxy as a gate: say so, every time.
            self.console.raw(
                "pi: --remote/--yolo - the egress proxy is recording rather than gating,",
                "    and no OS fence is applied. Models are unchanged: ELM only.",
                "    Destinations: agent/egress.log",
            )
            # Lifting the exclusion does nothing if there is no package behind
            # it, and a silent nothing is worse than a line of text.
            if not os.path.isdir(os.path.join(self.root, "agent", "npm", "node_modules",
                                              "pi-web-access")):
                self.console.note("    note: pi-web-access is not installed, so there are no "
                                  "web tools to enable.")

    def _computer_use(self, switches):
        """Computer use, with --remote only.

        A logged-in browser reaches anything, past the egress proxy entirely, so
        the extension loads only in a run that has already opened the network,
        and sub-agent children never get it.
        """
        extension = os.path.join(self.root, "agent", "npm", "node_modules", "@injaneity",
                                 "pi-computer-use", "extensions", "computer-use.ts")
        # Asked for with this run (--remote, PI_ELM_NETWORK), not by a default
        # /network saved: a browser the agent drives is not something every
        # new session should come with.
        if (self.network.wildcard and self.network.source != "saved" and switches.computer_use
                and not self.env.get("PI_ELM_CHILD") and os.path.isfile(extension)):
            helpers = os.path.join(self.root, "agent", "helpers")
            self.env.set("PI_COMPUTER_USE_HELPER_APP_PATH",
                         os.path.join(helpers, "pi-computer-use.app"))
            self.env.set("PI_COMPUTER_USE_LINUX_HELPER_PATH",
                         os.path.join(helpers, "linux-bridge"))
            self.env.set("PI_COMPUTER_USE_WINDOWS_HELPER_PATH",
                         os.path.join(helpers, "windows-bridge.exe"))
            self.env.set("PI_COMPUTER_USE_CODESIGN_IDENTITY", "-")
            # remote-research.ts adds how to drive Safari and hand the screen back.
            self.env.set("PI_ELM_COMPUTER_USE", "1")
            self.console.note("    computer use is on for this run: the agent can see the "
                              "screen and drive apps.")
            return ["-e", extension]
        # A sub-agent inherits the parent's environment but never gets computer
        # use, so it must not get the instructions for it either.
        self.env.unset("PI_ELM_COMPUTER_USE")
        return []

    def _choose_model(self, switches):
        """--llama or --mistral picks the model, unless the caller already chose.

        A --model or --provider among pi's options means the caller decided; the
        same words inside the prompt or an option's value do not.
        """
        kind = switches.model_flag
        if not kind:
            return []
        if kind == "mistral":
            identifier = self.env.get("ELM_MISTRAL_MODEL_ID")
            if not identifier:
                # runtime.env names Mistral from the bootstrap that first served it on.
                raise Refusal(
                    "pi: --mistral needs this install's Mistral model id, which %s"
                    % os.path.join(self.root, "agent", "runtime.env"),
                    "    does not have yet. Run %s once, then try again."
                    % os.path.join(self.root, "bootstrap.sh"),
                    code=CANNOT_START,
                )
            model = "elm/" + identifier
        else:
            model = "elm-shim/" + self.env.get("ELM_LLAMA_MODEL_ID")
        if _model_chosen(switches.rest):
            return []
        return ["--model", model]

    def _go_offline(self, argv):
        """No update work at launch: pi otherwise downloads fd and ripgrep, runs
        `npm view` per package, asks pi.dev for a newer pi and refreshes the
        remote model catalogue - four network operations before the prompt
        appears. `pi update` needs the network by definition, so it is exempt."""
        if argv and argv[0] in ("update", "setup"):
            return
        if self.env.get("PI_ELM_STARTUP_CHECKS") == "1":
            return
        self.env.set_default("PI_OFFLINE", "1")
        self.env.set_default("PI_SKIP_VERSION_CHECK", "1")

    # -- the session's own settings ------------------------------------------

    def _permission_mode(self, switches, argv):
        saved = modes.saved_mode(os.path.join(self.root, "agent", "permission-mode"))
        resolution = modes.resolve(switches.mode, self.env, saved,
                                   bool(self.env.get("PI_ELM_CHILD")),
                                   modes.gate_problem(self.root), argv)
        for line in resolution.notes:
            self.console.note("    " + line)
        modes.apply(self.env, resolution)

    def _note_inside_install(self, sessions):
        """Started in the install itself, a session writes its work among the
        installer's files: one replaced this repository's README.md with its own
        and left thirty files in the install root. Warned, not refused."""
        if not sessions or self.env.get("PI_FORCE") == "1" or self.env.get("PI_ELM_CHILD"):
            return
        if not paths.is_inside(os.getcwd(), self.root):
            return
        self.console.note(
            "pi: this session is starting inside the elm-pi install (%s)." % self.root,
            "    The agent cannot change the install it runs on: its writes here are refused "
            "(only .pi/ is",
            "    open). For your own work, cd to a project directory first; to work on elm-pi "
            "itself, clone",
            "    it (git clone %s ~/src/elm-pi) and start pi there - its AGENTS.md says how."
            % self.root,
        )


def _model_chosen(argv):
    """True when the caller picked the model among pi's own options."""
    previous = ""
    for argument in argv:
        if previous == "value":
            previous = ""
            continue
        if argument == "--":
            break
        if argument in ("--model", "--provider") or argument.startswith("--model="):
            return True
        if argwalk.takes_value(argument):
            previous = "value"
    return False


def main(argv, package_dir=None, install_root=None, console=None, env=None):
    """Run one launch, printing any refusal and returning its exit code."""
    console = console if console is not None else Console()
    if install_root is None:
        if package_dir is None:
            package_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        install_root = paths.install_root(package_dir)
    launcher = Launcher(argv, install_root, console=console, env=env)
    try:
        return launcher.run()
    except Refusal as refusal:
        console.show(refusal)
        return refusal.code
    except KeyboardInterrupt:
        # Ctrl-C while the launcher is still working (`pi update`, a slow
        # proxy start): end as a program stopped by SIGINT does, which is what
        # the calling shell expects - not with twenty lines of traceback.
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGINT)
        return 130
    except BrokenPipeError:
        # `pi --help | head`: the reader has gone. Nothing to report to it.
        try:
            sys.stdout.close()
        except OSError:
            pass
        return 0
    except (OSError, ValueError) as problem:
        # A launcher that cannot run something says which thing and why; a
        # traceback on a user's terminal says neither. ValueError is what the
        # OS interface raises for a value it cannot hold (a NUL byte).
        console.note("pi: %s" % problem)
        return CANNOT_START
