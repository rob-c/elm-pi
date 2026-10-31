#!/usr/bin/env python3
"""Apply config/versions.json, the versions this repo last tested, to a manifest.

Both manifests (package.json for pi, templates/packages.json for the extension
packages) ask for "latest". Every install takes the tested versions instead,
except --update, which is what `pi update` runs. One place decides that, for
bootstrap.sh and for CI:

  stage   MANIFEST DEST SECTION   write MANIFEST to DEST with SECTION's pins applied
                                  (none with --update; PI_VERSION overrides pi)
  digest  MANIFEST SECTION        what a tree built from MANIFEST was built from:
                                  the manifest and SECTION's pins. bootstrap.sh
                                  stamps each tree with it, so a pull that changes
                                  only config/versions.json still rebuilds it.
  pinned  SECTION NAME            the tested version of NAME, or nothing
  dev     MANIFEST                MANIFEST with the core pins applied and every
                                  @earendil-works/* devDependency moved to the same
                                  version as pi - what CI installs, so its tests
                                  run against the tested pi rather than npm's latest

Standard library only; runs on the interpreter bootstrap.sh selected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

PI = "@earendil-works/pi-coding-agent"


def load_pins(versions: str, section: str) -> dict:
    if not os.path.exists(versions):
        return {}
    with open(versions) as fh:
        return dict(json.load(fh).get(section, {}))


def stage(manifest: str, dest: str, section: str, versions: str, update: bool, pi_version: str) -> str:
    with open(manifest) as fh:
        data = json.load(fh)
    deps = data.get("dependencies", {})
    pins = {} if update else load_pins(versions, section)
    if pi_version and section == "core":
        pins[PI] = pi_version
    pinned = sorted(name for name in deps if name in pins)
    for name in pinned:
        deps[name] = pins[name]
    with open(dest, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    if not pinned:
        return "    versions: the latest of each" + (", as --update asks" if update else "")
    if len(pinned) == len(deps):
        return "    versions: all %d at the tested versions" % len(deps)
    return "    versions: %d of %d at the tested versions, the rest latest" % (len(pinned), len(deps))


def digest(manifest: str, section: str, versions: str) -> str:
    with open(manifest, "rb") as fh:
        raw = fh.read()
    pins = json.dumps(load_pins(versions, section), sort_keys=True).encode()
    return hashlib.sha256(raw + b"\0" + pins).hexdigest()


def dev(manifest: str, versions: str) -> dict:
    with open(manifest) as fh:
        data = json.load(fh)
    pins = load_pins(versions, "core")
    deps = data.get("dependencies", {})
    for name in deps:
        if name in pins:
            deps[name] = pins[name]
    # pi depends on its sibling packages at exactly its own version; a dev copy at
    # "latest" would be hoisted over them and the tests would read that instead.
    if PI in pins:
        for name in data.get("devDependencies", {}):
            if name.startswith("@earendil-works/"):
                data["devDependencies"][name] = pins[PI]
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--versions", required=True, help="path to config/versions.json")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("stage")
    p.add_argument("manifest")
    p.add_argument("dest")
    p.add_argument("section", choices=("core", "packages"))
    p.add_argument("--update", action="store_true")
    p.add_argument("--pi-version", default="")
    p = sub.add_parser("digest")
    p.add_argument("manifest")
    p.add_argument("section", choices=("core", "packages"))
    p = sub.add_parser("pinned")
    p.add_argument("section", choices=("core", "packages"))
    p.add_argument("name")
    p = sub.add_parser("dev")
    p.add_argument("manifest")
    args = parser.parse_args()

    if args.command == "stage":
        print(stage(args.manifest, args.dest, args.section, args.versions, args.update, args.pi_version))
    elif args.command == "digest":
        print(digest(args.manifest, args.section, args.versions))
    elif args.command == "pinned":
        version = load_pins(args.versions, args.section).get(args.name)
        if version:
            print(version)
    elif args.command == "dev":
        json.dump(dev(args.manifest, args.versions), sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
