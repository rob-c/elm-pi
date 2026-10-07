#!/usr/bin/env python3
"""Check that everything pi is told to load is installed and loadable on disk.

bootstrap.sh runs this on every install and update, and reinstalls the
extension packages when it fails. It checks, for the install at --root:

- every package listed in agent/settings.json "packages": its directory, its
  package.json, and every extension and skill path its "pi" manifest declares;
- every required local extension in config/elm-pi.json;
- every skill in agent/skills: a SKILL.md whose frontmatter parses and whose
  name matches its directory (pi drops a skill whose frontmatter is invalid).

Prints one line per problem and exits 1 if there are any. Standard library
only, so it runs on the interpreter bootstrap.sh selected.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path


def package_problems(root: Path) -> list[str]:
    settings = json.loads((root / "agent/settings.json").read_text())
    problems = []
    for spec in settings.get("packages", []):
        name = spec[4:] if spec.startswith("npm:") else spec
        pkg = root / "agent/npm/node_modules" / name
        manifest = pkg / "package.json"
        if not manifest.is_file():
            problems.append(f"package {name}: not installed ({pkg})")
            continue
        try:
            meta = json.loads(manifest.read_text())
        except ValueError as error:
            problems.append(f"package {name}: package.json does not parse ({error})")
            continue
        pi = meta.get("pi")
        if not isinstance(pi, dict):
            # a package without a pi manifest is loaded by convention
            # (extensions/, skills/ ...); nothing more to check here
            continue
        for kind in ("extensions", "skills", "prompts", "themes"):
            for entry in pi.get(kind) or []:
                pattern = str(pkg / entry)
                if not (glob.glob(pattern) if glob.has_magic(pattern) else os.path.exists(pattern)):
                    problems.append(f"package {name}: declared {kind[:-1]} {entry} is missing")
    return problems


def extension_problems(root: Path) -> list[str]:
    config = json.loads((root / "config/elm-pi.json").read_text())
    return [
        f"required extension {name} is missing from agent/extensions"
        for name in config.get("requiredExtensions", [])
        if not (root / "agent/extensions" / name).is_file()
    ]


FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def frontmatter(text: str) -> dict[str, str] | None:
    """The two fields pi needs, parsed the way YAML would see them. An unquoted
    value containing ': ' is a YAML error, which pi reports and skips."""
    match = FRONTMATTER.match(text)
    if not match:
        return None
    fields = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if not sep or key.strip() not in ("name", "description"):
            continue
        value = value.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                return None
        elif ": " in value:
            return None
        fields[key.strip()] = value
    return fields


def skill_problems(root: Path) -> list[str]:
    problems = []
    skills = root / "agent/skills"
    manifest = skills / ".elm-pi-managed"
    names = manifest.read_text().split() if manifest.is_file() else []
    for name in names:
        skill = skills / name / "SKILL.md"
        if not skill.is_file():
            problems.append(f"skill {name}: SKILL.md is missing")
            continue
        fields = frontmatter(skill.read_text())
        if fields is None or not fields.get("description"):
            problems.append(f"skill {name}: frontmatter does not parse or has no description")
        elif fields.get("name") != name:
            problems.append(f"skill {name}: frontmatter name {fields.get('name')!r} does not match its directory")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--packages-only", action="store_true",
                        help="check only what reinstalling the packages can fix")
    args = parser.parse_args()
    root = args.root.resolve()
    problems = package_problems(root)
    if not args.packages_only:
        problems += extension_problems(root) + skill_problems(root)
    for problem in problems:
        print(f"    {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
