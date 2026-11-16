"""agent/: code is refreshed, config is kept.

Everything this repository owns - the ELM-only guard, the write protections,
the delegation rules, the agent definitions, the skills and prompt templates -
is rendered from templates/ on every run, because those are code and a
re-install should pick up whatever the repo now says. What you tune
(settings.json, models.json, web-search.json, the extension configs) is written
only when it is missing, with the keys this repo decides reapplied over the top
later (settings.py).

The two exceptions are visible rather than silent: a manifest under agent/ lists
the skills and prompt templates this repo installed, so a file it drops is
removed and one you added yourself is never touched.
"""

import os
import shutil

from elmboot import console, installenv

REQUIRED_SETS = ("agent/extensions/subagent", "agent/extensions/pi-permission-system",
                 "agent/config/pi-task-models", "agent/prompts", "agent/agents")


def render(root, env, source, destination):
    """Templates with @QWEN_MODEL@ and the like resolved, as installed."""
    installenv.elm_py(root, env, [os.path.join(root, "scripts", "elm_config.py"),
                                  "--root", root, "render",
                                  os.path.join(root, source), os.path.join(root, destination)])


def install_if_absent(root, env, source, destination):
    """A config someone has tuned is never clobbered."""
    live = os.path.join(root, destination)
    if os.path.isfile(live):
        console.note("keeping existing " + destination)
        return
    render(root, env, source, destination)
    console.note("wrote " + destination)


def refresh(root, options, env):
    """Write agent/ from templates/ - the phase bootstrap.sh calls 3."""
    for name in ("pi", os.path.join("python", "pi"), "pi.orig", "configure.sh"):
        try:
            path = os.path.join(root, name)
            os.chmod(path, os.stat(path).st_mode | 0o111)
        except OSError:
            pass
    console.say("agent configuration")
    for directory in REQUIRED_SETS:
        os.makedirs(os.path.join(root, directory), exist_ok=True)
    installenv.secure_install_state(root, env)
    # The launcher starts this interpreter rather than searching again on every
    # launch; the next install re-validates it.
    with open(os.path.join(root, "agent", "python-path"), "w", encoding="utf-8") as handle:
        handle.write(env["ELM_PI_PYTHON"] + "\n")
    installenv.elm_py(root, env, [os.path.join(root, "scripts", "elm_config.py"),
                                  "--root", root, "init"])

    required = _required_extensions(root, env)
    if not options.shim:
        # --no-shim removes the shim's extension here, before anything loads or
        # checks the set: it used to be rendered, loaded by the warm-up and
        # passed by the checks, and only then deleted.
        required = [name for name in required if name != "elm-shim.ts"]
        shim = os.path.join(root, "agent", "extensions", "elm-shim.ts")
        if os.path.exists(shim):
            os.remove(shim)
    for name in required:
        if os.path.isfile(os.path.join(root, "templates", "extensions", name)):
            render(root, env, "templates/extensions/" + name, "agent/extensions/" + name)
    console.note("refreshed required agent extensions (policy, protections, tools%s"
                 % (", shim)" if options.shim else "; no shim)"))
    for name in required:
        if not os.path.isfile(os.path.join(root, "agent", "extensions", name)):
            console.die("required policy extension was not installed: " + name)

    install_if_absent(root, env, "templates/extensions/subagent/config.json",
                      "agent/extensions/subagent/config.json")
    _permission_config(root)
    _agents(root, env)
    install_if_absent(root, env, "templates/config/pi-task-models/config.json",
                      "agent/config/pi-task-models/config.json")
    os.makedirs(os.path.join(root, "agent", "config", "pi-auto-compact"), exist_ok=True)
    install_if_absent(root, env, "templates/config/pi-auto-compact/config.json",
                      "agent/config/pi-auto-compact/config.json")
    install_if_absent(root, env, "templates/settings.json", "agent/settings.json")
    install_if_absent(root, env, "templates/models.json", "agent/models.json")

    render(root, env, "templates/AGENTS.md", "agent/AGENTS.md")
    _reference(root, env)
    os.makedirs(os.path.join(root, "agent", "shell"), exist_ok=True)
    shutil.copy2(os.path.join(root, "templates", "shell", "colour.sh"),
                 os.path.join(root, "agent", "shell", "colour.sh"))
    render(root, env, "templates/APPEND_SYSTEM.md", "agent/APPEND_SYSTEM.md")
    _skills(root, env)
    console.note("refreshed agent/AGENTS.md and agent/reference/")
    _prompts(root, env)
    install_if_absent(root, env, "templates/web-search.json", "agent/web-search.json")
    auth = os.path.join(root, "agent", "auth.json")
    if not os.path.exists(auth):
        with open(auth, "w", encoding="utf-8") as handle:
            handle.write("{}\n")
    _links(root, options, env)


def _required_extensions(root, env):
    import json
    with open(os.path.join(root, "config", "elm-pi.json"), encoding="utf-8") as handle:
        return list(json.load(handle)["requiredExtensions"])


def _permission_config(root):
    """The gate's policy: written once, then kept - people tune it.

    `permission` is reapplied from templates/ later (settings.py), so a rule
    added to the template reaches installs that already exist. @AGENT_DIR@ marks
    this install as pi's own infrastructure, so reading its node_modules does
    not trip the outside-cwd prompt.
    """
    live = os.path.join(root, "agent", "extensions", "pi-permission-system", "config.json")
    if os.path.isfile(live):
        console.note("keeping existing agent/extensions/pi-permission-system/config.json")
        return
    with open(os.path.join(root, "templates", "extensions", "pi-permission-system",
                           "config.json"), encoding="utf-8") as handle:
        text = handle.read()
    text = text.replace("@AGENT_DIR@", os.path.join(root, "agent")).replace("@INSTALL_DIR@", root)
    with open(live, "w", encoding="utf-8") as handle:
        handle.write(text)
    console.note("wrote agent/extensions/pi-permission-system/config.json")


def _agents(root, env):
    """Agent definitions are code: pi-subagents discovers them in agent/agents."""
    source_dir = os.path.join(root, "templates", "agents")
    for name in sorted(os.listdir(source_dir)) if os.path.isdir(source_dir) else []:
        source = os.path.join(source_dir, name)
        if not os.path.isfile(source):
            continue
        destination = os.path.join(root, "agent", "agents", name)
        render(root, env, "templates/agents/" + name, "agent/agents/" + name)
        with open(destination, encoding="utf-8") as handle:
            text = handle.read()
        with open(destination + ".tmp", "w", encoding="utf-8") as handle:
            handle.write(text.replace("@AGENT_DIR@", os.path.join(root, "agent")))
        os.replace(destination + ".tmp", destination)
    console.note("refreshed agent/agents/*.md (model pinning, tools, delegation briefs)")


def _reference(root, env):
    """Detail AGENTS.md points at rather than carries, replaced whole each run."""
    destination = os.path.join(root, "agent", "reference")
    shutil.rmtree(destination, ignore_errors=True)
    os.makedirs(destination, exist_ok=True)
    source_dir = os.path.join(root, "templates", "reference")
    for name in sorted(os.listdir(source_dir)) if os.path.isdir(source_dir) else []:
        if name.endswith(".md"):
            render(root, env, "templates/reference/" + name, "agent/reference/" + name)


def _skills(root, env):
    """Skills: refreshed every run, and a skill this repo drops is removed.

    agent/skills/.elm-pi-managed lists the ones this repo owns, so one the
    template set drops is removed here and one you added yourself is never
    touched. pi lists each skill's name and description in the system prompt and
    loads the body only when a task calls for it.
    """
    base = os.path.join(root, "agent", "skills")
    manifest = os.path.join(base, ".elm-pi-managed")
    os.makedirs(base, exist_ok=True)
    for old in _manifest_lines(manifest):
        if "/" in old or old.startswith("."):
            continue
        if not os.path.isdir(os.path.join(root, "templates", "skills", old)):
            shutil.rmtree(os.path.join(base, old), ignore_errors=True)
    installed = []
    source_dir = os.path.join(root, "templates", "skills")
    for name in sorted(os.listdir(source_dir)) if os.path.isdir(source_dir) else []:
        source = os.path.join(source_dir, name)
        if not os.path.isfile(os.path.join(source, "SKILL.md")):
            continue
        destination = os.path.join(base, name)
        shutil.rmtree(destination, ignore_errors=True)
        os.makedirs(destination, exist_ok=True)
        for entry in sorted(os.listdir(source)):
            item = os.path.join(source, entry)
            if os.path.isdir(item):
                shutil.copytree(item, os.path.join(destination, entry))
            else:
                shutil.copy2(item, os.path.join(destination, entry))
        render(root, env, "templates/skills/%s/SKILL.md" % name,
               "agent/skills/%s/SKILL.md" % name)
        installed.append(name)
    _write_manifest(manifest, installed)
    console.note("refreshed agent/skills (%d skills)" % len(installed))


def _prompts(root, env):
    """Prompt templates become /commands; same manifest rule as the skills."""
    base = os.path.join(root, "agent", "prompts")
    manifest = os.path.join(base, ".elm-pi-managed")
    os.makedirs(base, exist_ok=True)
    managed = _manifest_lines(manifest)
    for old in managed:
        # "" too: a blank line in the manifest named the folder itself, and
        # removing that was a PermissionError where bash skipped the line.
        if not old or "/" in old or old.startswith("."):
            continue
        if not os.path.isfile(os.path.join(root, "templates", "prompts", old)):
            try:
                os.remove(os.path.join(base, old))
            except OSError:
                pass    # rm -f: already deleted by its owner is not a failed install
    installed = []
    source_dir = os.path.join(root, "templates", "prompts")
    for name in sorted(os.listdir(source_dir)) if os.path.isdir(source_dir) else []:
        if not name.endswith(".md") or not os.path.isfile(os.path.join(source_dir, name)):
            continue
        if os.path.lexists(os.path.join(base, name)) and name not in managed:
            # The researcher's own prompt of the same name: never replaced, and
            # never listed as ours (bootstrap.sh has the same rule).
            console.note("kept your own agent/prompts/%s (elm-pi's template of that name "
                         "is not installed)" % name)
            continue
        render(root, env, "templates/prompts/" + name, "agent/prompts/" + name)
        installed.append(name)
    _write_manifest(manifest, installed)
    console.note("refreshed agent/prompts (%d templates)" % len(installed))


def _manifest_lines(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return [line.rstrip("\n") for line in handle]
    except OSError:
        return []


def _write_manifest(path, names):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("".join(name + "\n" for name in names))


def _links(root, options, env):
    """agent/bin: pi's managed-binary directory, and what children find there.

    pi prepends it to PATH for every child, and pi-subagents falls back to a
    bare `pi` PATH lookup when it cannot resolve the CLI: the link makes that
    fallback land on this launcher, keeping the ELM-only policy and the .env key
    in force for children.
    """
    binaries = os.path.join(root, "agent", "bin")
    os.makedirs(binaries, exist_ok=True)
    for name, target in (("pi", os.path.join(root, "pi")),
                         ("workflow-check", os.path.join(root, "scripts", "workflow-check")),
                         ("conda-search", os.path.join(root, "scripts", "conda-search"))):
        link = os.path.join(binaries, name)
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(target, link)
    console.note("agent/bin/pi -> %s (sub-agent children)" % os.path.join(root, "pi"))

    # brew: the machine's Homebrew, with approved installs run past the egress
    # proxy. Linked only where Homebrew exists, so `command -v brew` keeps
    # telling the agent the truth.
    brew_link = os.path.join(binaries, "brew")
    if os.path.lexists(brew_link):
        os.remove(brew_link)
    search = clean_dirs(env) + ["/opt/homebrew/bin", "/usr/local/bin",
                                "/home/linuxbrew/.linuxbrew/bin"]
    for directory in search:
        if directory and os.access(os.path.join(directory, "brew"), os.X_OK):
            os.symlink(os.path.join(root, "scripts", "brew"), brew_link)
            console.note("agent/bin/brew -> scripts/brew (Homebrew at %s)" % directory)
            break

    # /login writes the credential it obtains here. Read-only means that write
    # fails, so a commercial subscription cannot be attached to this install
    # even by someone who has one; normal startup and ELM use are unaffected.
    auth = os.path.join(root, "agent", "auth.json")
    installenv.auth_mode(auth, not options.auth_lock)
    console.note("agent/auth.json is %s"
                 % ("read-only (/login cannot store credentials)" if options.auth_lock
                    else "writable (--no-auth-lock)"))


def clean_dirs(env):
    """The account's PATH entries, then the standard places Homebrew lives."""
    return installenv.clean_path(env.get("ELM_PI_USER_PATH") or env.get("PATH", "")).split(os.pathsep)
