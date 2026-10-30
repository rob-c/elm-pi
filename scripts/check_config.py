#!/usr/bin/env python3
"""Check this install's pi configuration against the schemas pi itself ships.

pi validates models.json, settings.json and every theme it loads, and a value
it no longer accepts costs more than a warning: an invalid models.json drops
the whole provider it belongs to. pi 1.4.0 did exactly that to the elm
provider over "thinkingFormat": "reasoning_effort" - Qwen vanished and only
Llama was left - and rejected one of awesome-pi-themes' themes on every
launch. Both were visible only once the new release was already active.

So bootstrap.sh runs this against the pi it has just installed, before the
previous release is thrown away, and tests/ runs it against templates/. The
schemas come from the release under test (--schemas), never from pi.dev.

    check_config.py --root DIR [--schemas DIR] [--config] [--themes]

--config checks agent/models.json and agent/settings.json; --themes checks the
theme files the configured packages would load. With neither, both. Prints
one line per problem and exits 1 if there are any. Standard library only, and
only the JSON Schema keywords pi's schemas use: an unknown keyword is a
problem in this script, reported rather than silently passed.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

PI_SCHEMAS = "node_modules/@earendil-works/pi-coding-agent/schemas"

# Keywords that carry no constraint, and the ones validate() implements.
ANNOTATIONS = {"$schema", "$id", "$comment", "title", "description", "default", "deprecated", "$defs"}
HANDLED = {"$ref", "anyOf", "const", "enum", "type", "minLength", "pattern", "minimum", "maximum",
           "exclusiveMinimum", "items", "maxItems", "required", "properties", "patternProperties",
           "additionalProperties"}

TYPES = {
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    # bool is an int in Python and never a number in JSON
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "null": lambda v: v is None,
}


def validate(value, schema, root: dict, path: str, problems: list[str]) -> None:
    if schema is True:
        return
    if schema is False:
        problems.append(f"{path}: not allowed here")
        return
    unknown = set(schema) - ANNOTATIONS - HANDLED
    if unknown:
        problems.append(f"{path}: schema keyword(s) {sorted(unknown)} not understood by check_config.py")
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            problems.append(f"{path}: cannot resolve $ref {ref}")
            return
        target = root
        for part in ref[2:].split("/"):
            target = target[part]
        validate(value, target, root, path, problems)
    if "anyOf" in schema:
        branches = schema["anyOf"]
        if not any(_passes(value, branch, root) for branch in branches):
            consts = [b["const"] for b in branches if isinstance(b, dict) and "const" in b]
            if len(consts) == len(branches):
                problems.append(f"{path}: {json.dumps(value)} is not one of {', '.join(json.dumps(c) for c in consts)}")
            else:
                problems.append(f"{path}: {_brief(value)} matches none of the allowed forms")
    if "const" in schema and value != schema["const"]:
        problems.append(f"{path}: must be {json.dumps(schema['const'])}, not {_brief(value)}")
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: {_brief(value)} is not one of {schema['enum']}")
    if "type" in schema:
        allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(TYPES[t](value) for t in allowed):
            problems.append(f"{path}: expected {' or '.join(allowed)}, not {_brief(value)}")
            return
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            problems.append(f"{path}: shorter than {schema['minLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            problems.append(f"{path}: {json.dumps(value)} does not match {schema['pattern']}")
    if TYPES["number"](value):
        if "minimum" in schema and value < schema["minimum"]:
            problems.append(f"{path}: below the minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            problems.append(f"{path}: above the maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            problems.append(f"{path}: must be greater than {schema['exclusiveMinimum']}")
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            problems.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for index, item in enumerate(value):
                validate(item, schema["items"], root, f"{path}[{index}]", problems)
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                problems.append(f"{path}: missing required {key}")
        properties = schema.get("properties", {})
        patterns = schema.get("patternProperties", {})
        for key, item in value.items():
            matched = False
            if key in properties:
                validate(item, properties[key], root, f"{path}.{key}", problems)
                matched = True
            for pattern, sub in patterns.items():
                if re.search(pattern, key):
                    validate(item, sub, root, f"{path}.{key}", problems)
                    matched = True
            if not matched and "additionalProperties" in schema:
                extra = schema["additionalProperties"]
                if extra is False:
                    problems.append(f"{path}: unknown key {key}")
                else:
                    validate(item, extra, root, f"{path}.{key}", problems)


def _passes(value, schema, root: dict) -> bool:
    found: list[str] = []
    validate(value, schema, root, "", found)
    return not found


def _brief(value) -> str:
    text = json.dumps(value)
    return text if len(text) <= 40 else text[:37] + "..."


def check_file(path: Path, schema_path: Path) -> list[str]:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        return [f"{path.name}: does not parse ({error})"]
    schema = json.loads(schema_path.read_text())
    problems: list[str] = []
    validate(value, schema, schema, path.name, problems)
    return problems


def config_problems(config_dir: Path, schemas: Path) -> list[str]:
    problems = []
    for name in ("models.json", "settings.json"):
        if (config_dir / name).is_file():
            problems += check_file(config_dir / name, schemas / name.replace(".json", ".schema.json"))
    return problems


def _selected(rel: str, filters: list[str] | None) -> bool:
    """pi's per-package resource filter: omitted loads everything, [] loads
    nothing, "!glob" and "-path" exclude, a bare or "+" entry includes."""
    if filters is None:
        return True
    includes = [f.lstrip("+") for f in filters if not f.startswith(("!", "-"))]
    if not filters or (includes and not any(fnmatch.fnmatch(rel, p) for p in includes)):
        return False
    for entry in filters:
        if entry.startswith("!") and fnmatch.fnmatch(rel, entry[1:]):
            return False
        if entry.startswith("-") and rel == entry[1:]:
            return False
    return True


def theme_files(root: Path) -> list[Path]:
    settings = json.loads((root / "agent/settings.json").read_text())
    files = []
    for spec in settings.get("packages", []):
        filters = spec.get("themes") if isinstance(spec, dict) else None
        source = spec["source"] if isinstance(spec, dict) else spec
        pkg = root / "agent/npm/node_modules" / (source[4:] if source.startswith("npm:") else source)
        try:
            manifest = json.loads((pkg / "package.json").read_text()).get("pi") or {}
        except (OSError, ValueError):
            continue  # verify_install.py reports a missing package
        for entry in manifest.get("themes") or ([] if manifest else ["themes"]):
            base = pkg / entry
            candidates = sorted(base.glob("*.json")) if base.is_dir() else sorted(pkg.glob(entry))
            files += [f for f in candidates if _selected(f.relative_to(pkg).as_posix(), filters)]
    return files


def theme_problems(root: Path, schemas: Path) -> list[str]:
    problems = []
    for path in theme_files(root):
        found = check_file(path, schemas / "theme.schema.json")
        if found:
            rel = path.relative_to(root / "agent/npm/node_modules").as_posix()
            problems.append(f"theme {rel}: " + "; ".join(p.split(": ", 1)[1] for p in found))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--schemas", type=Path, help=f"default: <root>/{PI_SCHEMAS}")
    parser.add_argument("--config", action="store_true", help="agent/models.json and agent/settings.json")
    parser.add_argument("--themes", action="store_true", help="the themes the packages would load")
    args = parser.parse_args()
    root = args.root.resolve()
    schemas = (args.schemas or root / PI_SCHEMAS).resolve()
    if not (schemas / "models.schema.json").is_file():
        print(f"    no pi schemas at {schemas}")
        return 1
    both = not (args.config or args.themes)
    problems = []
    if args.config or both:
        problems += config_problems(root / "agent", schemas)
    if args.themes or both:
        problems += theme_problems(root, schemas)
    for problem in problems:
        print(f"    {problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
