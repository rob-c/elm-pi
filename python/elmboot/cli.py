"""The install, in the order it has to happen.

Each phase is a function in the module named for it, and `phases()` below is
the order bootstrap.bash ran them in. The order is not arbitrary:

* --help and an unknown option come before anything is looked at or changed
* the environment is scrubbed before the first program is run, and the tools
  the downloads need are asked for before the first download
* the options are recorded before any phase reads them, so a run that stops
  halfway is repeated with the same choices
* Node before pi, pi before agent/, agent/ before the packages that load its
  config, and every check after everything it checks
* the versions are recorded only after every check has passed

Idempotent: re-running never overwrites .env, sessions, memory or any config
you have edited. Nothing is installed system-wide; delete the folder and the
install is gone.
"""

import os
import re
import signal
import sys

from elmboot import (agentconfig, agentpython, checks, console, installenv, nodejs,
                     options as install_options, pirelease, settings, skilllibrary, tools)
from elmboot.run import Run, Stop, flush

REQUIRED_TOOLS = ("curl", "tar")


def prerequisites(env):
    """The tools every download needs, asked for before the first one.

    install.sh checks for these before it fetches the source, but the installer
    is also run on its own (a clone, `pi setup`, a copied tree). On Ubuntu
    26.04, which ships without curl, it got as far as "downloading node-..." and
    ended as "line 329: curl: command not found", exit 127 (measured
    2026-11-16). Silent when both are there.
    """
    import shutil
    missing = [tool for tool in REQUIRED_TOOLS if not shutil.which(tool, path=env.get("PATH", ""))]
    if not missing:
        return
    console.warn("missing required tool(s): " + " ".join(missing))
    if os.uname().sysname == "Darwin":
        console.warn("install the Apple command line tools:  xcode-select --install")
    else:
        console.warn("Debian/Ubuntu:  sudo apt install -y curl tar")
        console.warn("Fedora/RHEL:    sudo dnf install -y curl tar")
        console.warn("Arch:           sudo pacman -S --needed curl tar")
    console.die("install the tools above, then run %s again - nothing has been downloaded "
                "or changed" % os.path.join(env["ELM_PI_ROOT"], "bootstrap.sh"))


def choose_python(run):
    """Which interpreter the install records and runs its own Python on."""
    root, env = run.root, run.env
    # bootstrap.sh has said it already when it had to download an interpreter
    # before there was one to run this with.
    if env.pop("ELM_PI_BOOTSTRAP_SAID_PYTHON", "") != "1":
        console.say("Python")
    python = installenv.select_python(root, env)
    status, version = run.capture(run.python(["-c", "import platform; "
                                              "print(platform.python_version())"]))
    console.note("%s (%s)" % (python, version if status == 0 else ""))
    import shutil
    users = shutil.which("python3", path=env.get("ELM_PI_USER_PATH", "")) or ""
    if users and users != python:
        console.note("(not %s from your PATH: elm-pi always runs its own choice, isolated)"
                     % users)


def installer_settings(run):
    """The keys this repo decides, reapplied; hashline's and the workflows' too."""
    console.say("installer-owned settings")
    settings.merge_owned(run.root)
    # pi-hashline-edit-pro reads agent/hashline/config.json (the launcher
    # exports PI_HASHLINE_DIR). requirePath makes every anchor edit name its
    # file, which is what lets protected-paths.ts check it; copy and move are
    # off because a move's destination comes from an anchor, not from the path
    # it names.
    os.makedirs(run.path("agent", "hashline"), exist_ok=True)
    settings.hashline(run.root)
    console.say("workflow settings")
    settings.workflow(run.root)


def shim_note(run):
    """ELM's vLLM instance for Llama 3.3 was started without a tool-call parser,
    so any request carrying `tools` returns 400. The shim prompt-engineers tool
    calling on top of it, which is what makes cheap Llama sub-agents possible."""
    console.say("Llama tool-call shim")
    if run.options.shim:
        console.note("%s - shim will start on demand (127.0.0.1:8811)" % run.env["ELM_PI_PYTHON"])
    else:
        console.note("skipped (--no-shim): agent/extensions/elm-shim.ts was not installed")


KEY_LINE = re.compile(r"^(export )?ELM_API_KEY=.+", re.M)
EMPTY_KEY_LINE = re.compile(r"^(export )?ELM_API_KEY=$", re.M)


def has_key(run):
    """True when .env supplies a key - not merely when there is a .env."""
    try:
        with open(run.path(".env"), encoding="utf-8", errors="replace") as handle:
            return KEY_LINE.search(handle.read()) is not None
    except OSError:
        return False


def _add_key(path, value):
    """The key into a .env that is already there: in place of its empty
    `ELM_API_KEY=` line, or at its end. Everything else in it is kept."""
    os.umask(0o077)
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    if EMPTY_KEY_LINE.search(text):
        text = EMPTY_KEY_LINE.sub(lambda _: "ELM_API_KEY=" + value, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += "ELM_API_KEY=%s\n" % value
    with open(path + ".tmp", "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path + ".tmp", 0o600)
    os.replace(path + ".tmp", path)


def _ask_for_key(prompt):
    sys.stdout.write(prompt)
    flush()
    typed = sys.stdin.readline().rstrip("\n").rstrip("\r")
    if not typed:
        console.die("no key given")
    return typed


def key(run):
    """Phase 5. ELM keys are issued on request through the ELM web UI, not self-service.

    A .env that is there and holds no key is not a key: a folder copied from a
    clone carries .env.example's empty `ELM_API_KEY=` line, and "keeping
    existing .env" then skipped the question and the install ended at the
    lockdown check with pi's advice to /login (a copied install in ~/sandbox,
    2026-11-16).
    """
    console.say("ELM API key")
    path = run.path(".env")
    given = run.env.get("ELM_API_KEY", "")
    asking = run.options.interactive and _stdin_is_a_terminal()
    if os.path.isfile(path):
        if has_key(run):
            console.note("keeping existing .env")
        elif given:
            _add_key(path, given)
            console.note(".env had no key: added ELM_API_KEY from the environment")
        elif asking:
            _add_key(path, _ask_for_key("    .env has no key - paste your ELM API key (elm-...): "))
            console.note("added the key to .env (mode 600)")
        else:
            console.warn(".env has no ELM_API_KEY - add it there before running ./pi")
        return

    def write(value):
        # The key's file is this account's alone, and so is everything the
        # rest of the run writes: the umask stays, as it did in bash.
        os.umask(0o077)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("ELM_API_KEY=%s\n" % value)
        os.chmod(path, 0o600)

    if given:
        write(given)
        console.note("wrote .env from the environment")
    elif asking:
        write(_ask_for_key("    paste your ELM API key (elm-...): "))
        console.note("wrote .env (mode 600)")
    else:
        import shutil
        shutil.copyfile(run.path(".env.example"), path)
        os.chmod(path, 0o600)
        console.warn("no key available - edit .env before running ./pi")


def _stdin_is_a_terminal():
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (OSError, ValueError):
        return False


def resolve_model(run):
    """Phase 6: ask the gateway which Qwen it serves, once there is a key to ask with."""
    if not has_key(run):
        # Without a key pi lists no models at all, so the lockdown check could
        # only fail, and with pi's own words about /login. Said as what it is.
        console.die("this install has no ELM key yet, so the ELM-only policy cannot be "
                    "verified. Everything else is installed: put ELM_API_KEY=elm-... in "
                    "%s and run %s again (nothing is downloaded twice)"
                    % (run.path(".env"), run.path("bootstrap.sh")))
    console.say("resolving the model id from the gateway")
    # stdin is left as it is for configure.sh, as it was.
    import subprocess
    flush()
    try:
        status = subprocess.call([run.path("configure.sh")], cwd=run.root, env=run.env)
    except OSError:
        status = 127
    if status != 0:
        console.warn("configure.sh failed - check the key and the gateway, then re-run "
                     "./configure.sh")


def done(run):
    console.say("done")
    root = run.root
    print("    Run it:        pi            (or %s/pi if it is not on your PATH yet)" % root)
    print("    Unwrapped:     %s/pi.orig   (vanilla CLI, no ELM config - debugging only)" % root)
    print("    Policy:        %s/LOCKDOWN.md   (/elm-policy inside pi)" % root)
    print('    Fast one-shot: %s/pi --fast -p "..."    (skips the npm packages)' % root)
    print("    Update it:     pi update      (elm-pi + pi from GitHub, then the pi packages)")
    print('    Verify:        see "Verify the install" in INSTALL.md')


def install(run):
    """Every phase, in order."""
    root, env = run.root, run.env
    installenv.install_environment(root, env)
    # Before anything is downloaded: on NixOS without nix-ld none of it would run.
    problem = installenv.check_loader(env)
    if problem:
        console.die(problem)
    prerequisites(env)
    run.retry = installenv.curl_retry(env)
    choose_python(run)

    install_options.inherit(root, run.options, env)
    install_options.write(root, run.options, env)
    node_version = nodejs.wanted_version(run)
    # PI_VERSION=1.4.0 installs exactly that pi, over both config/versions.json
    # and --update. Unset, the version comes from those.
    run.pi_version = env.get("PI_VERSION", "")
    installenv.check_disk(root, run.options, env)

    nodejs.ensure(run, node_version)
    pirelease.install_pi(run)
    agentconfig.refresh(root, run.options, env)
    tools.install(run)
    skilllibrary.install(run)
    agentpython.build(run)
    agentpython.pypi_index(run)
    installer_settings(run)
    pirelease.packages(run)
    # Whatever umask the account had when any of this was unpacked, code here
    # ends up writable by its owner only - shared deliberately
    # (ELM_PI_SHARED_STATE=1): owner and group.
    installenv.tighten_install_perms(root, env)
    checks.warm_cache(run)
    checks.everything_present(run)
    shim_note(run)
    # Existing installs may contain state created under the account's ordinary
    # 022 umask. Tighten only known private state; do not alter project files.
    installenv.secure_install_state(root, env)
    key(run)
    resolve_model(run)
    checks.lockdown(run)
    checks.record_versions(run)
    checks.fence(run)
    done(run)


def main(argv, root, env=None):
    """Run the installer in `root`; returns its exit status."""
    env = os.environ if env is None else env
    try:
        # "try: ./bootstrap.sh --help" names the command as it was typed.
        chosen = install_options.parse(argv, program=env.get("ELM_PI_BOOTSTRAP_NAME")
                                       or "./bootstrap.sh")
    except SystemExit as stop:
        flush()
        return stop.code if isinstance(stop.code, int) else 1
    os.chdir(root)
    run = Run(root, env, chosen)

    def terminated(number, _frame):
        raise Stop(128 + number)

    previous = {}
    for number in (signal.SIGTERM, signal.SIGHUP):
        try:
            previous[number] = signal.signal(number, terminated)
        except (ValueError, OSError):
            pass
    status = 1
    try:
        install(run)
        status = 0
    except console.Failure as failure:
        flush()
        sys.stderr.write(console.RED + "ERROR: %s" % failure + console.RESET + "\n")
    except Stop as stop:
        status = stop.code
    except KeyboardInterrupt:
        status = 130
    except BrokenPipeError:
        status = 141
    except (OSError, ValueError, KeyError) as problem:
        # A file that is not what it should be - a config that is not JSON, a
        # folder that cannot be written. Said in a line, as a failed command
        # said it in bash, rather than as a traceback.
        flush()
        sys.stderr.write(console.RED + "ERROR: %s: %s" % (type(problem).__name__, problem)
                         + console.RESET + "\n")
    finally:
        flush()
        run.finish(failed=status != 0)
        for number, handler in previous.items():
            try:
                signal.signal(number, handler)
            except (ValueError, OSError):
                pass
    return status
