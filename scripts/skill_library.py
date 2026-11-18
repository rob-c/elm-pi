#!/usr/bin/env python3
"""The community skill library: fetched once, filtered, and kept out of the prompt.

    skill_library.py --root INSTALL sync [--force] [--cache DIR] [-- curl ...]
    skill_library.py --root INSTALL remove
    skill_library.py --root INSTALL pin

`sync` puts the library config/skill-library.json pins (K-Dense's
scientific-agent-skills) in agent/skills/kdense, one folder per skill, and is
what both installers run: bootstrap.bash and python/elmboot/skilllibrary.py
print the heading, this prints the rest, so the two cannot differ.

What it decides, and why:

* One commit, one checksum. The archive is GitHub's tarball of the pinned
  commit, verified against the sha256 in the config before a byte of it is
  unpacked, on a cache hit as on a download. A mismatch installs nothing.
* Only skills/<name>/ is unpacked, as plain files: no links, no devices,
  nothing with `..` in its path, nothing executable. The archive is 245 MB
  because of the pictures in its docs/; 24 MB of it is skills.
* A skill the config excludes is not installed, and neither is one whose name
  a skill in agent/skills already has: pi keeps the first of two skills with
  one name and warns at every start.
* Every installed SKILL.md gains `disable-model-invocation: true`. pi puts the
  name and description of every other skill in the system prompt of every
  session; for the 167 kept at the pinned commit that is 67,000 characters,
  measured. Hidden, they cost nothing until one is read: /skill:<name> loads one by hand, and the skill
  router names the ones a request mentions (agent/skills/kdense/index.json).
* It never fails an install: no network, a refused download or a wrong
  checksum is a warning, and the next run tries again.

Python 3.9, standard library only: it runs under the installer's interpreter.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

VERSION = 1   # of what this script writes: a new number re-installs an existing library
FOLDER = os.path.join("agent", "skills", "kdense")
MARKER = ".elm-pi-library"
HIDE = "disable-model-invocation: true"
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# More than the pinned commit holds by a wide margin, and far less than would
# fill a home directory: an archive that is not what it claims stops here.
MAX_FILES, MAX_BYTES = 20000, 200 * 1024 * 1024

YELLOW, RESET = "\033[33m", "\033[0m"


def note(message):
    print("    " + message)
    sys.stdout.flush()


def warn(message):
    """Yellow, on stdout: the installers' own `warn`."""
    print(YELLOW + "    " + message + RESET)
    sys.stdout.flush()


def load_config(root):
    with open(os.path.join(root, "config", "skill-library.json"), encoding="utf-8") as handle:
        config = json.load(handle)
    commit = config["commit"]
    if not re.match(r"^[0-9a-f]{40}$", commit) or not re.match(r"^[0-9a-f]{64}$", config["sha256"]):
        raise ValueError("config/skill-library.json: commit or sha256 is not a full hash")
    config["asset"] = "scientific-agent-skills-%s.tar.gz" % commit
    config["url"] = "%s/archive/%s.tar.gz" % (config["repository"].rstrip("/"), commit)
    return config


def recipe(config):
    """What decides the installed set besides the commit: a change re-installs."""
    text = json.dumps([VERSION, sorted(config.get("exclude", {}))])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_marker(folder):
    try:
        with open(os.path.join(folder, MARKER), encoding="utf-8") as handle:
            marker = json.load(handle)
        return marker if isinstance(marker, dict) else {}
    except (OSError, ValueError):
        return {}


# --- frontmatter ---------------------------------------------------------------

FRONT = re.compile(r"\A---\r?\n(.*?)\r?\n---[ \t]*(\r?\n|\Z)", re.S)


def scalar(front, key):
    """A top-level string value: plain, quoted, folded or literal, with its
    continuation lines. Enough YAML for a name and a description; pi's own
    parser is the judge of the file (tests/test_skill_library.py runs it)."""
    lines = front.replace("\r\n", "\n").split("\n")
    for number, line in enumerate(lines):
        if not line.startswith(key + ":"):
            continue
        first = line[len(key) + 1:].strip()
        rest = []
        for more in lines[number + 1:]:
            if more.strip() and not more.startswith((" ", "\t")):
                break
            rest.append(more.strip())
        if first[:1] in ("|", ">"):
            return " ".join(part for part in rest if part)
        value = " ".join([first] + [part for part in rest if part]).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value
    return ""


def hidden(text):
    """The SKILL.md with `disable-model-invocation: true` in its frontmatter,
    or None when it has no frontmatter to put it in."""
    match = FRONT.match(text)
    if not match:
        return None
    newline = "\r\n" if "\r\n" in match.group(0) else "\n"
    kept = [line for line in match.group(1).split(newline)
            if not line.startswith("disable-model-invocation:")]
    return "---" + newline + newline.join(kept + [HIDE]) + newline + "---" + newline + text[match.end():]


def problem_with(name, text):
    """Why pi would not load this SKILL.md as the skill `name`, or ""."""
    match = FRONT.match(text)
    if not match:
        return "no frontmatter"
    declared = scalar(match.group(1), "name")
    description = scalar(match.group(1), "description")
    if declared != name:
        return "its name is %r" % declared
    if not description:
        return "no description"
    if len(description) > 1024:
        return "its description is %d characters (1024 at most)" % len(description)
    return ""


# --- the archive -----------------------------------------------------------------

def unpack(archive, destination):
    """skills/<name>/** and the licence, as plain files. Returns the skill names found."""
    found, files, size = set(), 0, 0
    with tarfile.open(archive, "r:*") as tar:
        for member in tar:
            parts = member.name.split("/")
            if len(parts) < 2 or any(part in ("", ".", "..") or "\\" in part or "\0" in part
                                     for part in parts):
                continue
            if len(parts) == 2 and parts[1] in ("LICENSE.md", "LICENSE") and member.isfile():
                target = os.path.join(destination, "LICENSE.md")
            elif len(parts) >= 4 and parts[1] == "skills" and member.isfile():
                if not NAME.match(parts[2]) or len(parts[2]) > 64:
                    continue
                found.add(parts[2])
                target = os.path.join(destination, *parts[2:])
            else:
                continue          # directories are made as needed; links and devices never
            files += 1
            size += member.size
            if files > MAX_FILES or size > MAX_BYTES:
                raise ValueError("the archive holds more than a skill library does")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            source = tar.extractfile(member)
            with open(target, "wb") as out:
                shutil.copyfileobj(source, out)
            os.chmod(target, 0o644)
    return found


def taken_names(root):
    """Skills this install already has by name: the repository's and the user's own."""
    names = set()
    for base in (os.path.join(root, "agent", "skills"), os.path.join(root, "templates", "skills")):
        try:
            for entry in os.listdir(base):
                if os.path.isfile(os.path.join(base, entry, "SKILL.md")):
                    names.add(entry)
        except OSError:
            pass
    return names


def keep_or_drop(config, staged, found, taken):
    """Apply the config to an unpacked library. Returns (kept, {dropped: reason})."""
    kept, dropped = [], {}
    excluded = config.get("exclude", {})
    for name in sorted(found):
        folder = os.path.join(staged, name)
        path = os.path.join(folder, "SKILL.md")
        reason = ""
        if name in excluded:
            reason = "excluded"
        elif name in taken:
            reason = "this install has its own skill of that name"
        elif not os.path.isfile(path):
            reason = "no SKILL.md"
        else:
            with open(path, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            reason = problem_with(name, text)
            if not reason:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(hidden(text))
        if reason:
            dropped[name] = reason
            shutil.rmtree(folder, ignore_errors=True)
        else:
            kept.append(name)
    return kept, dropped


def words_for(config, name):
    """What a request calls this skill: its name, and the aliases the config adds."""
    if name in config.get("notRouted", []):
        return []
    return [name] + list(config.get("aliases", {}).get(name, []))


def write_index(config, folder, names):
    """index.json for the skill router, INDEX.md for a reader."""
    entries = []
    for name in names:
        with open(os.path.join(folder, name, "SKILL.md"), encoding="utf-8", errors="replace") as handle:
            match = FRONT.match(handle.read())
        description = scalar(match.group(1), "description") if match else ""
        entries.append({"name": name, "description": description, "match": words_for(config, name)})
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8") as handle:
        json.dump({"library": config["title"], "tag": config["tag"], "skills": entries}, handle,
                  indent=1, ensure_ascii=False)
        handle.write("\n")
    lines = ["# %s %s" % (config["title"], config["tag"]), "",
             "%d skills from %s," % (len(entries), config["repository"]),
             "commit %s. Each is `<name>/SKILL.md` in this folder; read one" % config["commit"][:12],
             "before using the tool it covers. They are a community",
             "library, written for other agents: where one says to install software, to",
             "set an API key or to call another AI service, this install's own rules",
             "decide, not the skill.", ""]
    for entry in entries:
        # maxsplit by name: Python 3.13 and later warn about it by position, on stderr,
        # which an install shows.
        first = re.split(r"(?<=[.!?])\s", entry["description"], maxsplit=1)[0]
        lines.append("- `%s` - %s" % (entry["name"], first[:200]))
    with open(os.path.join(folder, "INDEX.md"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


# --- sync --------------------------------------------------------------------------

def fetch(config, cache, curl, force, scratch):
    """The verified archive's path, or "" with a warning said."""
    asset, want = config["asset"], config["sha256"]
    cached = os.path.join(cache, "kdense-skills", config["commit"], asset) if cache else ""
    if cached and not force and os.path.isfile(cached) and os.path.getsize(cached) > 0:
        if sha256_of(cached) == want:
            note("%s from the tool cache" % asset)
            return cached
        warn("the cached %s does not match its checksum - fetching it again" % asset)
        try:
            os.remove(cached)
        except OSError:
            pass
    fetched = os.path.join(scratch, asset)
    note("downloading %s %s (%d MB once, kept in the tool cache; the skills are about a tenth of it)"
         % (config["title"], config["tag"], config.get("downloadMB", 0)))
    try:
        status = subprocess.call(list(curl) + ["-o", fetched, config["url"]], stdin=subprocess.DEVNULL)
    except OSError as problem:
        status = 127
        sys.stderr.write("%s: %s\n" % (curl[0], problem.strerror or problem))
    if status != 0:
        warn("could not download %s - the skill library is not installed; the next run tries again"
             % asset)
        return ""
    if sha256_of(fetched) != want:
        warn("checksum mismatch for %s - the skill library is not installed" % asset)
        return ""
    if cached:
        try:                     # a cache that cannot be written is not worth failing over
            os.makedirs(os.path.dirname(cached), exist_ok=True)
            shutil.copyfile(fetched, cached)
        except OSError:
            pass
    return fetched


def prune(root, config, folder, installed):
    """Skills that this install has since gained a namesake of: removed, and said."""
    taken = taken_names(root)
    for name in [name for name in installed if name in taken]:
        shutil.rmtree(os.path.join(folder, name), ignore_errors=True)
        installed.remove(name)
        note("removed kdense/%s: this install has its own skill of that name" % name)
    return installed


def sync(root, cache, curl, force):
    config = load_config(root)
    folder = os.path.join(root, FOLDER)
    marker = read_marker(folder)
    current = (marker.get("commit") == config["commit"] and marker.get("recipe") == recipe(config)
               and isinstance(marker.get("skills"), list))
    if current and not force:
        installed = [name for name in marker["skills"]
                     if os.path.isfile(os.path.join(folder, name, "SKILL.md"))]
        if installed:
            before = len(installed)
            installed = prune(root, config, folder, installed)
            if before != len(installed) or before != len(marker["skills"]):
                write_marker(config, folder, installed)
            write_index(config, folder, installed)
            note("%s %s already in agent/skills/kdense (%d skills)"
                 % (config["title"], config["tag"], len(installed)))
            return 0
    os.makedirs(os.path.dirname(folder), exist_ok=True)
    scratch = tempfile.mkdtemp(prefix=".kdense-", dir=os.path.dirname(folder))
    try:
        archive = fetch(config, cache, curl, force, scratch)
        if not archive:
            return 0
        staged = os.path.join(scratch, "kdense")
        os.makedirs(staged)
        try:
            found = unpack(archive, staged)
        except (tarfile.TarError, OSError, EOFError, ValueError) as problem:
            warn("could not unpack %s (%s) - the skill library is not installed" % (config["asset"], problem))
            return 0
        kept, dropped = keep_or_drop(config, staged, found, taken_names(root))
        if not kept:
            warn("%s holds no skill this install can use - the skill library is not installed"
                 % config["asset"])
            return 0
        write_marker(config, staged, kept)
        write_index(config, staged, kept)
        if os.path.lexists(folder):
            if os.path.isdir(folder) and not os.path.islink(folder):
                shutil.rmtree(folder)
            else:
                os.remove(folder)
        os.rename(staged, folder)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    excluded = sorted(name for name, reason in dropped.items() if reason == "excluded")
    others = sorted(name for name in dropped if name not in excluded)
    note("%s %s -> agent/skills/kdense (%d skills, hidden from the prompt until one is read)"
         % (config["title"], config["tag"], len(kept)))
    if excluded:
        note("left out, as config/skill-library.json says: " + ", ".join(excluded))
    for name in others:
        note("left out %s: %s" % (name, dropped[name]))
    return 0


def write_marker(config, folder, names):
    with open(os.path.join(folder, MARKER), "w", encoding="utf-8") as handle:
        json.dump({"commit": config["commit"], "tag": config["tag"], "recipe": recipe(config),
                   "skills": sorted(names)}, handle, indent=1)
        handle.write("\n")


def remove(root):
    folder = os.path.join(root, FOLDER)
    if os.path.isdir(folder) and not os.path.islink(folder):
        shutil.rmtree(folder, ignore_errors=True)
        note("removed agent/skills/kdense")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="The community skill library in agent/skills/kdense.")
    parser.add_argument("--root", required=True, help="the install")
    commands = parser.add_subparsers(dest="command")
    fetching = commands.add_parser("sync", help="install or refresh the pinned library")
    fetching.add_argument("--force", action="store_true", help="download and unpack it again")
    fetching.add_argument("--cache", default="", help="where verified archives are kept")
    fetching.add_argument("curl", nargs="*", help="after --: the download command and its flags")
    commands.add_parser("remove", help="take the library out")
    commands.add_parser("pin", help="print the tag, commit, url and sha256")
    options = parser.parse_args(argv)
    root = os.path.abspath(options.root)
    if options.command == "sync":
        return sync(root, options.cache, options.curl or ["curl", "-q", "-fsSL"], options.force)
    if options.command == "remove":
        return remove(root)
    if options.command == "pin":
        config = load_config(root)
        print("\n".join([config["tag"], config["commit"], config["url"], config["sha256"]]))
        return 0
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as problem:
        # A config that is not what it should be, a folder that cannot be written.
        sys.stderr.write("skill_library.py: %s: %s\n" % (type(problem).__name__, problem))
        sys.exit(1)
