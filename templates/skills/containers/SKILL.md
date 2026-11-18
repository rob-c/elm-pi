---
name: containers
description: "Run software the machine lacks (TeX Live, pandoc, toolchains) in Docker or Podman, offline, with --network=none. Use when a tool is missing and pip cannot supply it."
---

# Containers

## When

A tool the task needs is not installed (`command -v latexmk`), it is not a
Python package (those come from `pip install`, see `scientific-python`), and a
published image has it. Compiling LaTeX without a TeX installation is the
usual case. Use the machine's own tool when it has one.

## Which engine

Check first, with the bash tool's `timeout` set to 20 (seconds):

```bash
docker info >/dev/null 2>&1 && echo docker
podman info >/dev/null 2>&1 && echo podman
```

Never skip this and never run it without the time limit. A Docker Desktop that
is installed but still starting holds every `docker` command until it is up: a
session here sat 13 minutes on a `docker run` before it said the daemon was not
running. The commands below are the same for both engines; use whichever
answered. If neither did within the limit, say so and stop: Docker Desktop has
to be running on macOS, a Podman machine started (`podman machine start`), and
installing an engine needs an administrator - it is the user's decision, not
yours.

Give every later `docker`/`podman` call a `timeout` too: 1800 for a first
`pull` (say the image's size before it), 600 for a run such as a LaTeX build.
A command that hits the limit is reported as that, not retried blind.

## The rules here

The permission gate enforces these; a command that breaks one is refused with
the reason.

- **Every `run` or `create` has `--network=none`.** A container's network does
  not go through this install's egress proxy, so a container may not have one.
  The software is in the image; the job does not need the internet. The one
  exception is containers that must reach each other: an internal network (below).
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

## Several containers that talk to each other

A cluster, a service and its database, a head node and its workers:

```bash
docker network create --internal labnet          # reaches nothing but its own containers
docker run -d --name head   --hostname head   --network labnet IMAGE ...
docker run -d --name node1  --hostname node1  --network labnet IMAGE ...
docker exec head some-command                     # how you, and the user, reach a service inside
```

- A network of its own: `docker network ls` first, then a new one for this
  job. Do not join a network that is already there - someone else's
  containers are on it, with host names that may be yours too.
- The network must be made with `--internal`: any other is refused, and so is
  `network connect`. Containers on it find each other by `--name`; give each
  the same `--hostname`, since most cluster software checks its own.
- Nothing inside can install packages (no internet): everything the containers
  need is in the image. If no published image has it, a `build` is the way,
  and it asks the user first.
- A port published with `-p` must be `127.0.0.1:HOST:CONTAINER`, and on an
  internal network it does not reach this machine anyway: use `docker exec`.
- Wait for a service to be up before using it - poll its own status command in
  a loop with a limit, do not `sleep` and hope - and read `docker logs NAME`
  when it is not.
- These run with `-d`, not `--rm`: say what you started, and stop and remove
  it (`docker rm -f head node1; docker network rm labnet`) when the user is
  done or asks - never leave a cluster running unmentioned.

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
box worth fixing and undefined reference before reporting. No engine, or a
build that fails and cannot be fixed: the document is not built, and the report
says so (see `physics-documents`).

## Reporting

Say which engine and image (with tag) produced the result and give the exact
command, so the user can run it again.
