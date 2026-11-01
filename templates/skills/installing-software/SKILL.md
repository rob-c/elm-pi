---
name: installing-software
description: "When something the task needs is not installed - search the package indexes, install the isolated way (pip, pixi, containers), Homebrew with approval, apt/dnf for the user, and report what went where."
---

# Installing software

Prefer what already exists over writing it, and what changes the least over
what changes more. Stop at the first step that works.

## 1. Is it already here?

```bash
command -v <tool>; ls "$PI_CODING_AGENT_DIR/bin"     # this install's own tools
python3 -c "import <module>"                          # a Python package
module avail <name> 2>&1 | head                       # HPC clusters: environment modules
pixi global list                                      # what was installed with pixi before
```

`agent/bin` has fd, rg, jq, yq, shellcheck, ast-grep, uv, mlr (CSV/JSON),
resvg (SVG to PNG) and pixi. On a cluster, `module load <name>` is how its
administrators provide software: use it before anything below.

## 2. Search for an existing solution

Before installing - or writing a tool yourself - find what is published. All of
these work in a normal session:

| Looking for | Command | Searches |
|---|---|---|
| a Python package for a job | `pypi-search <words>` | name, summary, keywords - when `command -v pypi-search` finds it (an offline snapshot) |
| a Python package's versions | `pip index versions <name>` | live PyPI, exact name |
| a program or library (C/C++/Fortran, CLI tools, R, ...) | `conda-search <name-fragment>` | conda-forge package names, with summaries |
| its versions for this machine | `pixi search '*<name>*' -p <platform>` | conda-forge builds, by exact name or glob; the platform is the `Platform:` line of `pixi info` (`osx-64`, `osx-arm64`, `linux-64`, `linux-aarch64`) |
| a container image | `docker search <term>` (or `podman search`) | Docker Hub (Podman: Quay too) |
| a Homebrew formula | `brew info <name>`, `brew search <name>` | Homebrew |
| a Linux system package | `apt-cache search <term>`, `dnf search <term>` | the distribution (to suggest to the user) |

Start a conda-forge search with `conda-search`, which matches part of a name and
shows what each package is; `pixi search` then gives exact versions. Every index
here searches names (PyPI's snapshot adds summaries): try the
field's own terms and the library's real name (`libnetcdf`, `hdf5`, `gdal`,
`root`), not a description. Prefer a package that is maintained and widely used;
say which you chose and why.

## 3. Install it the isolated way

Nothing outside the project or this install changes.

- **A Python package**: into the project's environment, or this install's
  (`$ELM_PI_AGENT_PYTHON` set): `pip install <package>` - see
  `scientific-python`.
- **Anything on conda-forge**, with pixi - no sudo, everything in
  `agent/pixi`:
  - once, without installing: `pixi exec --spec <package> <command> ...`
    (e.g. `pixi exec --spec ghostscript gs ...`), cached for the next time;
  - a tool for later sessions: `pixi global install <package>` - on PATH from
    the next command, removed with `pixi global uninstall <package>`;
  - a library a project builds against: a project environment
    (`pixi init` and `pixi add <package>` write `pixi.toml` and `.pixi/` into
    the project) - only when the user agrees to those files in their project.
  conda-forge only: another channel (`-c`/`--channel`) asks the user.
- **A large program or a whole toolchain** - TeX Live, a full compiler suite -
  in a container with `--network=none`: the `containers` skill.

## 4. Homebrew, with the user's approval

When none of that fits and `command -v brew` finds Homebrew: `brew install
<formula>`. The user is asked to approve every install, upgrade or removal;
say first what it is for and roughly how large it is (`brew info <formula>`).
Core formulae only: casks, third-party taps and formula files are refused.

## 5. Linux system packages: the user runs them

Never run apt, dnf, yum, zypper, pacman or apk - they need an administrator, and
the permission gate refuses them. Give the user the command for this system:

```bash
. /etc/os-release; echo "$ID $ID_LIKE"   # debian/ubuntu, rhel/fedora/centos/rocky, suse, arch, alpine
```

| `ID`/`ID_LIKE` | Command for the user |
|---|---|
| debian, ubuntu | `sudo apt-get install -y <package>` |
| fedora, rhel, centos, rocky, almalinux | `sudo dnf install -y <package>` (`yum` before EL8; some need EPEL) |
| suse, opensuse | `sudo zypper install -y <package>` |
| arch | `sudo pacman -S <package>` |
| alpine | `sudo apk add <package>` |

Package names differ between families (`libhdf5-dev` on Debian is
`hdf5-devel` on Fedora). On a shared cluster users usually cannot do this at
all: suggest asking its administrators, and use pixi or a container meanwhile.

## 6. Tell the user - every time

Before installing anything, say in one line what you are about to install,
with which tool, and why. In the report, list each thing installed:

- **what** (name and version) and **with what** (`pip`, `pixi exec`,
  `pixi global install`, `docker pull`, `brew`);
- **where it lives**: `agent/python/env` (pip into this install's Python),
  `agent/pixi` (pixi), the project's own `.venv`/`.pixi`, the container
  engine's image store, or Homebrew's prefix (`brew --prefix`);
- **whether it stays**: `pixi exec` and `--rm` containers leave only a cache;
  the rest is permanent until removed;
- **how to remove it**: `pip uninstall <name>`, `pixi global uninstall
  <name>`, `docker rmi <image>`, `brew uninstall <formula>`.

Anything you could not install: finish everything it does not block, and end
with what is missing and the exact command that would provide it.
