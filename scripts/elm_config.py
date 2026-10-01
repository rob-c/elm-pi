#!/usr/bin/env python3
"""Render the small set of runtime values shared by shell, JSON and TypeScript."""

from __future__ import annotations

import argparse
import json
import os
import shlex
from pathlib import Path


TOKENS = {"qwen": "@QWEN_MODEL@", "llama": "@LLAMA_MODEL@"}


def load(root: Path) -> tuple[dict, dict]:
    config = json.loads((root / "config/elm-pi.json").read_text())
    state_path = root / "agent/model-ids.json"
    models = dict(config["models"])
    if state_path.exists():
        models.update(json.loads(state_path.read_text()))
    return config, models


def rendered(text: str, models: dict) -> str:
    for name, token in TOKENS.items():
        text = text.replace(token, models[name])
    return text


def render_file(root: Path, source: Path, destination: Path) -> None:
    _, models = load(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(rendered(source.read_text(), models))


def write_runtime(root: Path) -> None:
    config, models = load(root)
    values = {
        "ELM_QWEN_MODEL_ID": models["qwen"],
        "ELM_LLAMA_MODEL_ID": models["llama"],
        "ELM_ALLOWED_PROVIDERS": " ".join(config["allowedProviders"]),
        "ELM_BUILTIN_PROVIDERS": " ".join(config["builtinProviders"]),
        "ELM_PROVIDER_CREDENTIALS": " ".join(config["providerCredentials"]),
        "ELM_WEB_TOOLS": ",".join(config["webTools"]),
    }
    path = root / "agent/runtime.env"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"export {key}={shlex.quote(value)}\n" for key, value in values.items()))
    os.chmod(path, 0o600)


def replace_json(value, old: str, new: str):
    if isinstance(value, dict):
        return {replace_json(k, old, new): replace_json(v, old, new) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_json(v, old, new) for v in value]
    if isinstance(value, str):
        return value.replace(old, new)
    return value


def set_model(root: Path, name: str, model: str) -> None:
    config, current = load(root)
    old = current[name]
    current[name] = model
    state_path = root / "agent/model-ids.json"
    state_path.write_text(json.dumps(current, indent=2) + "\n")
    os.chmod(state_path, 0o600)

    # Update every generated runtime consumer, including dictionary keys such as
    # modelThinkingLevels. Hand-tuned unrelated values remain untouched.
    for rel in (
        "agent/models.json",
        "agent/settings.json",
        "agent/config/pi-task-models/config.json",
    ):
        path = root / rel
        if path.exists():
            data = json.loads(path.read_text())
            path.write_text(json.dumps(replace_json(data, old, model), indent=2) + "\n")
    for rel in ("agent/agents/qwen.md", "agent/agents/llama.md", "agent/extensions/elm-shim.ts"):
        path = root / rel
        if path.exists():
            path.write_text(path.read_text().replace(old, model))
    write_runtime(root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    render = sub.add_parser("render")
    render.add_argument("source", type=Path)
    render.add_argument("destination", type=Path)
    set_parser = sub.add_parser("set-model")
    set_parser.add_argument("name", choices=tuple(TOKENS))
    set_parser.add_argument("model")
    value = sub.add_parser("value")
    value.add_argument("key")
    args = parser.parse_args()
    root = args.root.resolve()

    if args.command == "init":
        config, models = load(root)
        state = root / "agent/model-ids.json"
        if not state.exists():
            state.parent.mkdir(parents=True, exist_ok=True)
            state.write_text(json.dumps(models, indent=2) + "\n")
            os.chmod(state, 0o600)
        write_runtime(root)
    elif args.command == "render":
        render_file(root, args.source, args.destination)
    elif args.command == "set-model":
        set_model(root, args.name, args.model)
    elif args.command == "value":
        config, models = load(root)
        if args.key == "nodeVersion":
            print(config[args.key])
        elif args.key in models:
            print(models[args.key])
        else:
            raise SystemExit(f"unknown key: {args.key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
