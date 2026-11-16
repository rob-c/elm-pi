"""pi itself, and the extension packages: staged, patched, then swapped in.

Both trees are built in a sibling staging directory and moved into place only
once npm has finished and what was built has been checked, so a run that fails
halfway leaves the install it started with. The tree a run replaces is kept
until the whole run has verified (run.py puts it back otherwise).

The versions this repo last ran its checks against are in config/versions.json,
and every install takes them except --update - which is what `pi update` runs,
and takes whatever npm calls latest. PI_VERSION overrides pi itself for one
run. A pin is part of what each tree is stamped with, so a pull that moves one
rebuilds that tree at the next run; one that moves none leaves a tree on
whatever it has, `pi update`'s latest included.
"""

import os
import shutil
import tempfile

from elmboot import console, nodejs, settings

PI_PACKAGE = os.path.join("node_modules", "@earendil-works", "pi-coding-agent")
PI_CLI = os.path.join(PI_PACKAGE, "dist", "bundle", "cli.js")
STAMP = ".elm-pi-lock.sha256"
# The permission gate: the one package patch-pi.py patches (--gate).
GATE_PACKAGE = "@gotgenes/pi-permission-system"
NPM_FLAGS = ["--ignore-scripts", "--no-audit", "--no-fund", "--fetch-retries=5",
             "--fetch-retry-maxtimeout=60000", "--loglevel=error"]


def _pins(run, *arguments):
    return run.python([run.path("scripts", "pin_versions.py"), "--versions",
                       run.path("config", "versions.json")] + list(arguments))


def stage_manifest(run, manifest, stage, section):
    """Write `manifest` into `stage` with its section's tested versions applied."""
    command = _pins(run, "stage", run.path(manifest), os.path.join(stage, "package.json"), section)
    if run.options.update:
        command.append("--update")
    run.must(command + ["--pi-version", run.pi_version])


def manifest_digest(run, manifest, section, what):
    """What a tree was built from: its manifest and its section of versions.json."""
    status, digest = run.capture(_pins(run, "digest", run.path(manifest), section))
    if status != 0:
        console.die(what)
    return digest


def installed_pi(run):
    """The version of the pi in node_modules, or ""."""
    if not os.path.isfile(run.path(PI_PACKAGE, "package.json")):
        return ""
    return console.output(
        [run.node(), "-p",
         'require("./node_modules/@earendil-works/pi-coding-agent/package.json").version'],
        cwd=run.root, env=run.env)


def _stamp(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read().rstrip("\n")
    except OSError:
        return None


def need_pi(options, installed, asked, tested, stamp, digest):
    """Whether pi is rebuilt this run, and the line that says why (or "").

    `installed` is the version in node_modules, `asked` is PI_VERSION, `tested`
    the pin in config/versions.json, `stamp` what the tree was built from (None
    when it has none) and `digest` what it would be built from now.
    """
    if options.force or options.update or not installed:
        return True, ""
    if asked and asked != installed:
        return True, "%s -> %s" % (installed, asked)
    if options.force_packages and tested and tested != installed:
        return True, "%s -> %s, the tested version (--force-packages)" % (installed, tested)
    if stamp != digest:
        return True, "dependency list changed"
    return False, ""


def install_pi(run):
    """Phase 2: pi, rebuilt only when something changed.

    Reinstalling pi is the slowest step of an install. The digest catches an
    edited dependency list or a moved pin in config/versions.json; nothing can
    catch "latest" moving on the registry, which is what --update and --force
    are for. --force-packages (`pi update --extensions`) means "back to the
    tested set", and extension packages tested against one pi are not a tested
    set beside another: so it also brings pi back to its pin when `pi update`
    moved it on.
    """
    console.say("pi coding agent")
    options = run.options
    installed = installed_pi(run)
    digest = manifest_digest(run, "package.json", "core", "cannot hash package.json")
    status, tested = run.capture(_pins(run, "pinned", "core", "@earendil-works/pi-coding-agent"))
    if status != 0:
        console.die("cannot read config/versions.json")

    need, why = need_pi(options, installed, run.pi_version, tested,
                        _stamp(run.path("node_modules", STAMP)), digest)
    if why:
        console.note(why)

    if need:
        _build_pi(run, digest)
    else:
        console.note("pi %s, dependency list and pins unchanged (pi update moves to the latest "
                     "release)" % installed)

    console.note(console.output([run.node(), run.path(PI_CLI), "--version"], cwd=run.root,
                                env=run.env, default="installed"))
    # /share publishes the session as a GitHub gist and /bug POSTs the whole
    # transcript to radius.pi.dev. pi has no way to disable a built-in command,
    # so they are patched out of the release here, on every install and every
    # update, with pi's own subcommands (auth, mcp, config, install, ...), which
    # manage what this install manages itself.
    #
    # Fatal by design. If a pi release moves the code the patch anchors to, this
    # stops the install rather than leaving an unpatched pi behind a message
    # nobody reads - and `pi update` then stops before touching the extension
    # packages. Re-derive the anchors in patch-pi.py, or re-run with --no-patch
    # if you have decided you want those commands.
    if options.patch:
        if run.call(run.python([run.path("patch-pi.py")])) != 0:
            console.die("could not patch pi (/share, /bug, its subcommands, retry jitter) - "
                        "see patch-pi.py")
    else:
        console.warn("--no-patch: /share and /bug are live, and both upload the whole session "
                     "off-site; so are pi's subcommands")


def _build_pi(run, digest):
    stage = run.temp(tempfile.mkdtemp(prefix=".elm-pi-stage-core.", dir=run.root))
    stage_manifest(run, "package.json", stage, "core")
    nodejs.npm(run, ["install", "--omit=dev"] + NPM_FLAGS, cwd=stage)
    staged_bundle = os.path.join(stage, PI_PACKAGE, "dist", "bundle")
    if run.options.patch:
        if run.call(run.python([run.path("patch-pi.py"), "--bundle", staged_bundle])) != 0:
            console.die("could not patch the staged pi release (/share, /bug, its subcommands, "
                        "retry jitter) - see patch-pi.py")
    if run.call([run.node(), os.path.join(staged_bundle, "cli.js"), "--version"], quiet=True) != 0:
        console.die("the staged pi release does not start")
    with open(os.path.join(stage, "node_modules", STAMP), "w", encoding="utf-8") as handle:
        handle.write(digest + "\n")
    run.core_old = _swap(run, os.path.join(stage, "node_modules"), run.path("node_modules"),
                         ".elm-pi-old-core.", "could not activate the staged pi release")
    shutil.rmtree(stage, ignore_errors=True)
    run.forget(stage)


def _swap(run, staged, live, old_prefix, failure):
    """Move `staged` to `live`, keeping what was there; returns where it was kept."""
    kept = run.path("%s%d" % (old_prefix, os.getpid()))
    had = os.path.isdir(live)
    if had:
        os.rename(live, kept)
    try:
        os.rename(staged, live)
    except OSError:
        if had and os.path.isdir(kept):
            os.rename(kept, live)
        console.die(failure)
    return kept


# --- the extension packages -------------------------------------------------

def install_packages(run):
    """Build the extension tree in a staging directory and swap it in once npm
    has finished and every listed package is present."""
    stage = run.temp(tempfile.mkdtemp(prefix=".elm-pi-stage-packages.", dir=run.root))
    stage_manifest(run, os.path.join("agent", "npm", "package.json"), stage, "packages")
    # Package scripts stay disabled. Transitive packages still ship install
    # scripts (esbuild, protobufjs, tree-sitter-bash); none of them run.
    nodejs.npm(run, ["install"] + NPM_FLAGS, cwd=stage)
    for name in run.chosen:
        if not os.path.isdir(os.path.join(stage, "node_modules", name)):
            console.die("staged package is missing: " + name)
    # The permission modes are applied by the gate, patched before it goes live
    # like pi's bundle is: a gate that moved under patch-pi.py stops the install
    # rather than running a manual session as an auto one.
    staged_gate = os.path.join(stage, "node_modules", GATE_PACKAGE)
    if run.options.patch and os.path.isdir(staged_gate):
        if run.call(run.python([run.path("patch-pi.py"), "--gate", staged_gate])) != 0:
            console.die("could not add the permission modes to the staged permission gate - "
                        "see patch-pi.py")
    with open(os.path.join(stage, "node_modules", STAMP), "w", encoding="utf-8") as handle:
        handle.write(run.package_digest + "\n")
    run.packages_old = _swap(run, os.path.join(stage, "node_modules"),
                             run.path("agent", "npm", "node_modules"), ".elm-pi-old-packages.",
                             "could not activate the staged extension packages")
    shutil.rmtree(stage, ignore_errors=True)
    run.forget(stage)
    console.note("installed into agent/npm/node_modules")


def _verify_packages(run, quiet=False):
    return run.call(run.python([run.path("scripts", "verify_install.py"), "--root", run.root,
                                "--packages-only"]), quiet=quiet) == 0


def packages(run):
    """The pi packages, or none of them (--no-packages)."""
    if not run.options.packages:
        settings.disable_packages(run.root)
        return
    console.say("pi packages (sub-agents, web access, anchor editing)")
    os.makedirs(run.path("agent", "npm"), exist_ok=True)
    # Two lists, and they are not the same list. templates/packages.json is
    # what npm installs; templates/settings.json is what pi loads.
    shutil.copyfile(run.path("templates", "packages.json"),
                    run.path("agent", "npm", "package.json"))
    run.chosen = settings.package_list(run.root)

    # Packages are reinstalled when the reviewed manifest changes, when forced,
    # and whenever what is on disk does not match what pi is told to load: every
    # run checks each listed package and every extension and skill its pi
    # manifest declares (scripts/verify_install.py). A broken or half-installed
    # tree is repaired here rather than discovered as a silently missing tool.
    run.package_digest = manifest_digest(run, os.path.join("templates", "packages.json"),
                                         "packages", "cannot hash the package manifest")
    options = run.options
    stamp = _stamp(run.path("agent", "npm", "node_modules", STAMP))
    need = (options.force or options.update or options.force_packages or stamp is None
            or stamp != run.package_digest)
    if not need and not _verify_packages(run, quiet=True):
        console.note("installed packages do not match agent/settings.json - reinstalling:")
        _verify_packages(run)
        need = True
    if need:
        install_packages(run)
    else:
        console.note("packages match the reviewed manifest and are complete (use --force to "
                     "reinstall)")
    # Still incomplete after a fresh install means npm resolved something that
    # does not contain what it declares: stop rather than run without it.
    if not _verify_packages(run):
        console.die("extension packages are incomplete even after reinstalling (above); "
                    "re-run with --force")
    # And on a tree that was not reinstalled: an install from before the modes
    # gets them on its next run.
    patch_gate(run)


def patch_gate(run):
    gate = run.path("agent", "npm", "node_modules", GATE_PACKAGE)
    if run.options.patch and os.path.isdir(gate):
        if run.call(run.python([run.path("patch-pi.py"), "--gate", gate])) != 0:
            console.die("could not add the permission modes to the permission gate - "
                        "see patch-pi.py")
