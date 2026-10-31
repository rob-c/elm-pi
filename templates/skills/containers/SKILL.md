---
name: containers
description: "Running software the machine does not have - a full TeX Live, pandoc, a toolchain - in a Docker or Podman container, offline: finding the engine, pulling an image, --network=none, mounting only the project, files owned by the user. Use when a tool is missing and pip cannot supply it, e.g. compiling LaTeX to PDF without TeX installed."
---

# Containers

## When

A tool the task needs is not installed (`command -v latexmk`), it is not a
Python package (those come from `pip install`, see `scientific-python`), and a
published image has it. Compiling LaTeX without a TeX installation is the
usual case. Use the machine's own tool when it has one.

## Which engine

```bash
docker info >/dev/null 2>&1 && echo docker
podman info >/dev/null 2>&1 && echo podman
```

The commands below are the same for both; use whichever answered. If neither
did, say so and stop: Docker Desktop has to be running on macOS, a Podman
machine started (`podman machine start`), and installing an engine needs an
administrator - it is the user's decision, not yours.

## The rules here

The permission gate enforces these; a command that breaks one is refused with
the reason.

- **Every `run` or `create` has `--network=none`.** A container's network does
  not go through this install's egress proxy, so a container may not have one.
  The software is in the image; the job does not need the internet.
- **Pulling is fine.** Images come from Docker Hub, GHCR or Quay. A first pull
  can be gigabytes: say how large before you start it.
- **Mount the project folder only, at its own path:** `-v "$PWD":"$PWD" -w
  "$PWD"`. Never mount home, `/`, or a folder with credentials in it - a mount
  bypasses the path protections the agent's own tools have. The same path
  inside matters too: a container path such as `/work` looks to the permission
  gate like a folder outside the project, and it asks for approval - which a
  sub-agent or a print-mode run cannot get - while paths in the error messages
  and the output match the user's own.
- **`--rm`**, so nothing is left behind.
- **Files the user owns.** Docker on Linux: `-u "$(id -u):$(id -g)"`. Podman:
  `--userns=keep-id`. Docker Desktop on macOS maps ownership itself.
- **No `push`, no `login`, no remote engine** (`-H`, `--context`,
  `podman --remote`): refused, because each sends data off this machine.
- **`build` asks the user first**: a Dockerfile's `RUN` steps have an open
  network. Prefer a published image that already has the software.

## Images

| Need | Image | Size (compressed) |
|---|---|---|
| LaTeX, everything | `texlive/texlive:latest` | ~2.7 GB |
| LaTeX, common packages | `texlive/texlive:latest-medium` | ~0.9 GB |
| pandoc with minimal LaTeX | `pandoc/latex` | ~0.2 GB |
| pandoc with fonts and extra LaTeX | `pandoc/extra` | ~0.6 GB |

For anything else, name the image you would use and its publisher, and ask
before pulling one that is not an official or the project's own image.

## Compiling LaTeX

```bash
docker run --rm --network=none -v "$PWD":"$PWD" -w "$PWD" texlive/texlive:latest-medium \
  latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

(`podman run` with the same arguments, plus `--userns=keep-id`.) Try
`latest-medium` first; a missing package (`! LaTeX Error: File 'x.sty' not
found`) means `latest`. The PDF lands in the project folder, where it is
attached to the command's result: look at it, and fix every error, overfull
box worth fixing and undefined reference before reporting.

## Reporting

Say which engine and image (with tag) produced the result and give the exact
command, so the user can run it again.
