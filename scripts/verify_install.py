#!/usr/bin/env python3
"""Check that everything pi is told to load is installed and loadable on disk.

bootstrap.sh runs this on every install and update, and reinstalls the
extension packages when it fails. It checks, for the install at --root:

- every package listed in agent/settings.json "packages": its directory, its
  package.json, and every extension and skill path its "pi" manifest declares;
- every required local extension in config/elm-pi.json, except one an
  install option in agent/install-options leaves out (--no-shim);
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
        # pi's object form narrows a package's resources; the name is its source
        if isinstance(spec, dict):
            spec = spec["source"]
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


def install_flags(root: Path) -> list[str]:
    """The --no-* flags recorded in agent/install-options by bootstrap.sh."""
    path = root / "agent/install-options"
    flags: list[str] = []
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.startswith("flags="):
                flags = line[len("flags="):].split()
    return flags


# Required extensions an install option leaves out on purpose.
OPTIONAL_UNDER = {"elm-shim.ts": "--no-shim"}


def extension_problems(root: Path) -> list[str]:
    config = json.loads((root / "config/elm-pi.json").read_text())
    flags = install_flags(root)
    return [
        f"required extension {name} is missing from agent/extensions"
        for name in config.get("requiredExtensions", [])
        if not (root / "agent/extensions" / name).is_file()
        and OPTIONAL_UNDER.get(name) not in flags
    ]


# pi's frontmatter: from an opening --- to the first line that starts with ---.
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---", re.S)
# A mapping entry (not a "- " list item; quoted keys are not read). The key runs
# to the first colon that ends the line or has a space after it, as in YAML:
# "ratio 1:2" is text, "a: b: c" a nested mapping.
ENTRY = re.compile(r"""(?!-(?:\s|$))([^\s#"'].*?)[ \t]*:(?:[ \t]+(.*))?$""")
BLOCK = re.compile(r"([|>])([-+1-9]{0,2})(?:[ \t]+#.*)?")
# Plain scalars YAML's core schema reads as null, a boolean or a number.
NOT_TEXT = re.compile(r"~|null|Null|NULL|true|True|TRUE|false|False|FALSE|[-+]?(\.[0-9]+|[0-9]+(\.[0-9]*)?)([eE][-+]?[0-9]+)?"
                      r"|0o[0-7]+|0x[0-9a-fA-F]+|[-+]?\.(inf|Inf|INF)|\.(nan|NaN|NAN)")


def frontmatter(text: str) -> dict[str, str] | None:
    """The two fields pi needs, read the way pi's YAML parser (the yaml package)
    reads a skill's frontmatter. None where that parser fails on any line, since
    pi then skips the whole skill; a name or description that is not a string
    is left out. This covers what frontmatter is written in - one level of
    `key: value` with plain, quoted, multi-line and block scalars, and lists or
    mappings under other keys - not all of YAML."""
    # pi strips a byte-order mark and normalises line endings before parsing
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    match = FRONTMATTER.match(text)
    if not match:
        return None
    try:
        entries = _mapping(match.group(1).split("\n"))
    except ValueError:
        return None
    return {key: entries[key] for key in ("name", "description") if isinstance(entries.get(key), str)}


def _is_comment(line: str) -> bool:
    return line.lstrip(" ").startswith("#")


def _mapping(lines: list[str]) -> dict:
    """A block mapping, each value a string or None for any other kind of value.
    Raises ValueError where YAML would."""
    entries: dict = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or _is_comment(line):
            continue
        entry = ENTRY.match(line)
        # yaml refuses a duplicate key too
        if not entry or entry.group(1) in entries:
            raise ValueError(line)
        # the value goes on over every line indented under its key, and a
        # list may start at the key's own indent
        start = i
        while i < len(lines) and (not lines[i].strip() or lines[i].startswith(" ")
                                  or not entry.group(2) and (lines[i] == "-" or lines[i].startswith("- "))):
            i += 1
        entries[entry.group(1)] = _value(entry.group(2) or "", lines[start:i])
    return entries


def _value(first: str, more: list[str]) -> str | None:
    """FIRST is the text after "key:", MORE the lines indented under the key."""
    block = BLOCK.fullmatch(first)
    if block:
        return _block_scalar(block.group(1), block.group(2), more)
    content = [line.lstrip(" ") for line in more if line.strip() and not _is_comment(line)]
    if not first:
        if not content:
            return None
        if content[0] == "-" or content[0].startswith("- ") or ENTRY.match(content[0]):
            _nested(more, content[0])
            return None
    lines = [line.strip() for line in [first, *more]]
    while not lines[0]:
        lines.pop(0)
    while not lines[-1]:
        lines.pop()
    return _scalar(lines)


def _scalar(lines: list[str]) -> str | None:
    head = lines[0]
    if head[0] in "\"'":
        text = _fold(lines)
        if head[0] == '"':
            # YAML's double-quoted escapes are JSON's and a few more
            value, end = json.JSONDecoder(strict=False).raw_decode(text)
        else:
            quoted = re.match(r"'((?:[^']|'')*)'", text)
            if not quoted:
                raise ValueError(text)
            value, end = quoted.group(1).replace("''", "'"), quoted.end()
        if text[end:].strip() and not re.match(r"\s+#", text[end:]):
            raise ValueError(text)
        return value
    if head[0] in "@`|>%" or head in ("-", "?") or head.startswith(("- ", "? ")):
        raise ValueError(head)
    # a flow list or mapping, an alias, a tagged value
    if head[0] in "[{&*!":
        return None
    words = []
    for i, line in enumerate(lines):
        word = "" if line.startswith("#") else re.split(r"[ \t]#", line, maxsplit=1)[0].rstrip()
        # what pi's parser reports as "Nested mappings are not allowed in compact mappings"
        if ": " in word or word.endswith(":"):
            raise ValueError(line)
        words.append(word)
        if word != line:
            # a comment ends a plain scalar; nothing may follow it
            if any(rest and not rest.startswith("#") for rest in lines[i + 1:]):
                raise ValueError(line)
            break
    text = _fold(words).strip()
    return None if NOT_TEXT.fullmatch(text) else text


def _nested(more: list[str], head: str) -> None:
    """A mapping or list indented under a key: checked, its value not needed."""
    first = next(line for line in more if line.lstrip(" ") == head)
    indent = " " * (len(first) - len(head))
    lines = []
    for line in more:
        if not line.strip() or _is_comment(line):
            lines.append("")
        elif line.startswith(indent):
            lines.append(line[len(indent):])
        else:
            raise ValueError(line)
    if not ENTRY.match(head):
        # a list, read as a mapping with a key of its own before each "- item"
        as_mapping = []
        for n, line in enumerate(lines):
            if line == "-" or line.startswith("- "):
                as_mapping += [f"{n}:", " " + line[1:]]
            elif line and not line.startswith(" "):
                raise ValueError(line)
            else:
                as_mapping.append(line)
        lines = as_mapping
    _mapping(lines)


def _block_scalar(style: str, flags: str, more: list[str]) -> str:
    """A | (literal) or > (folded) scalar; - strips the final newline, + keeps
    the blank lines after it."""
    head = next((line for line in more if line.strip()), None)
    if head is None:
        return ""
    indent = " " * (len(head) - len(head.lstrip(" ")))
    lines = []
    for line in more:
        if line.strip() and not line.startswith(indent):
            raise ValueError(line)
        lines.append(line[len(indent):] if line.strip() else "")
    text = "\n".join(lines) if style == "|" else _fold(lines)
    if "-" in flags:
        return text.rstrip("\n")
    if "+" in flags:
        return text + "\n"
    return text.rstrip("\n") + "\n"


def _fold(lines: list[str]) -> str:
    """Lines joined as YAML folds them: by a space, or by a newline per blank line.
    A more-indented line in a > scalar keeps its line breaks."""
    text = previous = ""
    for line in lines:
        if not line:
            text += "\n"
        elif text and not text.endswith("\n"):
            text += ("\n" if line[0] == " " or previous[0] == " " else " ") + line
        else:
            text += line
        previous = line
    return text


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
