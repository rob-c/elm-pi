"""What an install has to show before it is called done.

The warm-up that is also the load check, the list of what pi is told to load
against what is on disk, and then the lockdown itself, asked of the launcher a
person will run: commercial providers gone, Qwen listed by its id, the config
valid against this pi's schemas, the patches in place, the module guard firing,
the web tools excluded, and `--model anthropic/...` refused.
"""

import json
import os
import re
import shutil
import tempfile

from elmboot import console, installenv, pirelease, settings

LOAD_FAILURE = "Failed to load extension"
GUARD_PROBE = '''
let blocked = 0;
try { require("elm-pi-guard-probe"); } catch (e) { if (/elm-pi: refusing/.test(e.message)) blocked++; }
import("elm-pi-guard-probe").catch((e) => { if (/elm-pi: refusing/.test(e.message)) blocked++; })
  .then(() => console.log(blocked));'''


# --- warm the module cache ---------------------------------------------------

def warm_cache(run):
    """Transpile the packages once, and find the extension that does not load.

    The packages ship raw TypeScript. pi transpiles them with jiti, which
    caches the result in $TMPDIR/jiti and reuses it on every later launch:
    measured here, ~21s of CPU cold against ~3.3s warm. The first launch after
    an install pays it otherwise, and so does the first after a tmp cleaner
    sweeps the cache. Paying it here means the install finishes slow and the
    agent starts fast, which is the right way round.

    This is also the load check. scripts/check-extensions.mjs loads every
    extension with pi's own resource loader, exactly as a session does, and
    reports each one that fails. A failure is repaired by reinstalling the
    packages once; if it still fails, the install stops with the error. It runs
    under lib/node-guard.mjs, as pi does, so an extension that would take a
    package from a node_modules outside this install fails here, by name.
    """
    if not (run.options.packages and os.path.isdir(run.path("agent", "npm", "node_modules"))):
        return
    console.say("warming the module cache")
    console.note("transpiling the packages once so the first launch does not have to")
    # The same private directory the launcher will use, or the warm cache would
    # land somewhere pi never looks.
    installenv.private_tmpdir(run.env)
    cache = run.env.get("TMPDIR", "").rstrip("/") + "/jiti"
    handle, log = tempfile.mkstemp()
    os.close(handle)
    run.temp(log)

    def warm():
        env = dict(run.env, ELM_PI_INSTALL_DIR=run.root,
                   PI_CODING_AGENT_DIR=run.path("agent"), PI_OFFLINE="1")
        import subprocess
        with open(log, "w", encoding="utf-8") as out:
            return subprocess.call(
                [run.node(), "--import", run.path("lib", "node-guard.mjs"),
                 run.path("scripts", "check-extensions.mjs")],
                cwd=run.root, env=env, stdin=subprocess.DEVNULL, stdout=out,
                stderr=subprocess.STDOUT) == 0

    def failures():
        with open(log, encoding="utf-8", errors="replace") as text:
            return [line.rstrip("\n") for line in text if LOAD_FAILURE in line]

    worked = warm()
    if failures():
        console.warn("pi could not load an extension - reinstalling the packages once:")
        for line in failures()[:5]:
            print("      " + line)
        run.package_digest = pirelease.manifest_digest(
            run, os.path.join("templates", "packages.json"), "packages",
            "cannot hash the package manifest")
        pirelease.install_packages(run)
        worked = warm()
        if failures():
            for line in failures()[:5]:
                print("      " + line)
            console.die("extensions still fail to load after reinstalling (above)")
    if worked:
        with open(log, encoding="utf-8", errors="replace") as text:
            lines = text.read().splitlines()
        console.note("%s - cached in %s" % ((lines[-1] if lines else "").lstrip(" "), cache))
    else:
        console.warn("warm-up failed; the first launch will transpile instead (slow, not fatal)")


def everything_present(run):
    """Packages, required local extensions and skills, checked on every run.

    Anything missing here is not something a reinstall of the npm packages
    fixes, so it stops the install with the list.
    """
    console.say("checking the installed extensions, skills and tools")
    if run.call(run.python([run.path("scripts", "verify_install.py"), "--root", run.root])) != 0:
        console.die("the install is incomplete (above)")
    console.note("all packages, extensions, skills and tools present")


# --- the lockdown ------------------------------------------------------------

def _indented(text, stream):
    for line in text.split("\n"):
        stream.write("    " + line + "\n")


def lockdown(run):
    """Phase 7: ask the launcher itself."""
    import sys
    root, env = run.root, run.env
    console.say("verifying the ELM-only policy")
    handle, errors_file = tempfile.mkstemp(prefix=".elm-pi-verify.", dir=root)
    os.close(handle)
    run.temp(errors_file)
    # In auto mode whatever .env asks for: this probes the ELM policy, not the modes.
    probe = dict(env, PI_FORCE="1", PI_OFFLINE="1", ELM_PI_NO_PROXY="1",
                 ANTHROPIC_API_KEY="probe-should-be-ignored",
                 OPENAI_API_KEY="probe-should-be-ignored", PI_ELM_PERMISSION_MODE="")
    import subprocess
    from elmboot.run import flush
    flush()
    with open(errors_file, "w", encoding="utf-8") as errors:
        result = subprocess.run([run.path("pi"), "--auto", "--list-models"], cwd=root, env=probe,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors,
                                universal_newlines=True, errors="replace")
    listed = result.stdout.rstrip("\n")
    with open(errors_file, encoding="utf-8", errors="replace") as errors:
        said = errors.read()

    def show_pi_messages():
        for line in said.splitlines():
            sys.stderr.write("    " + line + "\n")

    if result.returncode != 0:
        show_pi_messages()
        _indented(listed, sys.stderr)
        console.die("pi --list-models failed (exit %d); the ELM-only policy could not be "
                    "verified (pi's messages above)" % result.returncode)
    if re.search(r"^(anthropic|openai|google) ", listed, re.M):
        console.die("commercial providers are still visible - the credential scrub in ./pi is "
                    "not working")
    # Qwen by its id, not "any elm row": pi drops a provider whose models.json
    # entry it rejects, and when 1.4.0 rejected Qwen's, elm-shim alone still
    # matched the old pattern and the install passed with its main model gone.
    # pi says why only on stderr, which this used to discard.
    qwen = installenv.config_value(root, env, "qwen")
    if not any(line.split()[:2] == ["elm", qwen] for line in listed.split("\n")):
        show_pi_messages()
        # With an empty .env, pi explains "No models available" on stdout, not stderr.
        _indented(listed, sys.stderr)
        console.die("pi did not list elm/%s (pi's own messages above) - check that .env supplies "
                    "ELM_API_KEY, then agent/models.json, runtime.env and elm-only.ts" % qwen)
    if "errors loading models.json" in said:
        show_pi_messages()
        console.die("pi reported errors in agent/models.json (above)")
    _indented(listed, sys.stdout)

    config_check = [run.path("scripts", "check_config.py"), "--root", root]
    # The same files against the schemas this pi release ships. A value pi
    # stopped accepting fails the run, and the previous pi is put back. A theme
    # it rejects only costs a warning at every launch, so that is a warning here.
    if run.call(run.python(config_check + ["--config"])) == 0:
        console.note("config: agent/models.json and agent/settings.json match pi %s's schemas"
                     % pirelease.installed_pi(run))
    else:
        console.die("agent/models.json or agent/settings.json has values this pi rejects (above)")
    # The gate keeps a config the user edited, so a rule it would read
    # differently from how it is written only warns.
    if run.call(run.python(config_check + ["--rules"])) == 0:
        console.note("permission rules: each applies in the order and sense written")
    else:
        console.warn("pi-permission-system applies the rules above differently from how they "
                     "read (see scripts/check_config.py) - rewrite them in "
                     "agent/extensions/pi-permission-system/config.json")
    if run.options.packages:
        if run.call(run.python(config_check + ["--themes"])) == 0:
            console.note("themes: every theme the packages load is valid")
        else:
            console.warn("pi will skip the themes above with a warning at every launch - exclude "
                         "them in templates/settings.json")

    _child_launcher(run)
    _patches(run)
    _module_guard(run)
    if not web_tools(root):
        console.warn("could not check the web-tool exclusion list")
    _excluded_tools(run)
    _argument_guard(run)


def _child_launcher(run):
    """agent/bin/pi is how a sub-agent child finds this launcher: say whether it does."""
    link = run.path("agent", "bin", "pi")
    resolved = ""
    if os.access(link, os.X_OK) and os.path.islink(link):
        target = os.readlink(link)
        if not os.path.isabs(target):
            target = os.path.join(run.root, target)
        # The folder as it is spelled, links kept: `cd dir && pwd`.
        resolved = os.path.join(os.path.normpath(os.path.dirname(target)),
                                os.path.basename(target))
    if resolved == run.path("pi"):
        console.note("sub-agent launcher: agent/bin/pi resolves to the launcher")
    else:
        console.warn("agent/bin/pi is missing or points elsewhere - sub-agents may fail to start")


def _patches(run):
    if not run.options.patch:
        return
    if run.call(run.python([run.path("patch-pi.py"), "--check"])) != 0:
        console.warn("/share, /bug and pi's subcommands are NOT disabled in this install")
    gate = run.path("agent", "npm", "node_modules", pirelease.GATE_PACKAGE)
    if os.path.isdir(gate):
        if run.call(run.python([run.path("patch-pi.py"), "--gate", gate, "--check"])) != 0:
            console.warn("the permission gate does not apply the permission modes: pi --manual "
                         "and pi --yolo will refuse to start")


def _module_guard(run):
    """The module guard is only worth having if it fires. Plant a package
    outside the install and ask the guarded node for it, through require and
    import."""
    probe = tempfile.mkdtemp()
    try:
        package = os.path.join(probe, "node_modules", "elm-pi-guard-probe")
        os.makedirs(package)
        with open(os.path.join(package, "index.js"), "w", encoding="utf-8") as handle:
            handle.write('module.exports = "loaded";\n')
        _, out = run.capture([run.node(), "--import", run.path("lib", "node-guard.mjs"), "-e",
                              GUARD_PROBE], cwd=probe, merge=True)
    finally:
        shutil.rmtree(probe, ignore_errors=True)
    if out == "2":
        console.note("module guard: packages outside the install are refused (require and import)")
    else:
        console.warn("module guard did not refuse a package outside the install (%s)" % out)


def web_tools(root):
    """The launcher hides pi-web-access's tools by naming them in
    --exclude-tools, and pi ignores an exclusion for a tool that does not exist -
    so a version that adds a fifth tool would leave it live in the default mode,
    silently. Compare the two lists rather than trusting that they still agree.
    False when the lists disagree or cannot be read."""
    package = os.path.join(root, "agent", "npm", "node_modules", "pi-web-access")
    if not os.path.isdir(package):
        print("    web tools: pi-web-access is not installed, nothing to exclude")
        return True
    # Every top-level source file, not index.ts alone: 0.37 moved the names
    # into web-tool-core.ts and added a loader tool, web_enable, that switches
    # the others on - which a check reading index.ts could not see.
    parts = []
    for name in sorted(os.listdir(package)):
        if name.endswith(".ts"):
            with open(os.path.join(package, name), encoding="utf-8", errors="replace") as handle:
                parts.append(handle.read())
    source = "\n".join(parts)
    block = re.search(r"const DEFAULT_TOOL_NAMES[^=]*=\s*\{(.*?)\}", source, re.S)
    registers = set(re.findall(r'"([a-z][a-z0-9_]*)"', block.group(1))) if block else set()
    registers |= set(re.findall(r'const LOADER_NAME\s*=\s*"([a-z][a-z0-9_]*)"', source))
    # config/elm-pi.json is the source of truth. The launcher passes the list
    # as "$ELM_WEB_TOOLS", so scraping ./pi for a literal list finds nothing.
    with open(os.path.join(root, "config", "elm-pi.json"), encoding="utf-8") as handle:
        excluded = set(json.load(handle).get("webTools") or [])
    if not registers or not excluded:
        print("    web tools: could not read one of the two lists - check\n"
              "          config/elm-pi.json and pi-web-access by hand")
        return False
    missing = registers - excluded
    if missing:
        print("    web tools: %s registered but NOT excluded - live in the default mode"
              % ", ".join(sorted(missing)))
        return False
    stale = excluded - registers
    print("    web tools: %d registered, all excluded by default (pi --remote enables them)"
          % len(registers))
    if stale:
        print("    web tools: %s excluded but no longer registered - harmless, tidy when convenient"
              % ", ".join(sorted(stale)))
    return True


def _excluded_tools(run):
    """The other excluded tools (excludedTools): the same failure mode - pi
    ignores an exclusion for a tool that does not exist, so a package that
    renamed one would put it back in every request with nothing said."""
    modules = run.path("agent", "npm", "node_modules")
    if not os.path.isdir(modules):
        return
    with open(run.path("config", "elm-pi.json"), encoding="utf-8") as handle:
        excluded = json.load(handle)["excludedTools"]
    names = list(excluded["always"]) + list(excluded["workflows"])
    import subprocess
    from elmboot.run import flush
    flush()
    missing = []
    for name in names:
        found = subprocess.call(["grep", "-rqsF", "--include=*.ts", "--include=*.js",
                                 '"%s"' % name, os.path.join("agent", "npm", "node_modules")],
                                cwd=run.root, env=run.env, stdin=subprocess.DEVNULL) == 0
        if not found:
            missing.append(name)
    if missing:
        console.warn("excluded tools that no installed package registers: %s - a renamed tool "
                     "is back in every request; update excludedTools in config/elm-pi.json"
                     % " ".join(missing))
    else:
        console.note("other excluded tools: all %d still registered, left out by default (the "
                     "workflow tools only with pi --no-workflows)" % len(names))


def _argument_guard(run):
    """Match the sentence both refusal paths share. The launcher says "is not
    available" for --provider and "is outside the allowed providers" for
    --model, so probing for the first reported a working guard as broken. It
    checks arguments before it looks for the key, so on an install with no key
    yet this still probes the guard rather than the key check."""
    _, said = run.capture([run.path("pi"), "--model", "anthropic/claude-opus-5", "-p", "x"],
                          env=dict(run.env, PI_FORCE="1", ELM_PI_NO_PROXY="1"), merge=True)
    if "restricted to the University" in said:
        console.note("argument guard: --model anthropic/... refused")
    else:
        console.warn("argument guard did not refuse --model anthropic/... - check the launcher")


def fence(run):
    """The checks above run pi unfenced, so an install on a machine that cannot
    fence a session passed them all: Ubuntu 26.04 (AppArmor keeps user
    namespaces from unprivileged programs) and WSL 1 (measured 2026-11-16).
    Sessions there start unfenced, with a warning each time; said here too,
    with what to do."""
    try:
        from elmpi import jail
        problem = jail.fence_problem()
    except Exception:           # a check that cannot run never fails an install
        return
    if not problem:
        return
    console.say("this machine cannot fence a session yet")
    console.warn("pi is installed and will start, but its sessions run WITHOUT the OS fence "
                 "(each one says so),")
    console.warn("and pi --offline is refused, until this is put right:")
    for line in problem:
        console.warn(line)


def record_versions(run):
    """Recorded only after every check above has passed."""
    settings.installed_versions(run.root)
