"""The command-line tools in agent/bin.

pi's find and grep tools shell out to fd and rg. It looks for them in agent/bin
first, then on PATH, and if it finds neither it downloads them from GitHub on
the first interactive launch - awaited before the prompt is drawn, which is
what made the first start crawl. Installing them here means the first launch
costs what the tenth does.

The rest of the list is for the agent's bash tool rather than for pi: the
things a model reaches for constantly and cannot rely on finding, on a Mac or
on a login node. All are a single static binary from the project's own GitHub
release, so the install stays one directory you can delete.

    fd          file finding               (pi's find tool)
    rg          content search             (pi's grep tool)
    jq          JSON on the command line   - macOS 15 ships it, most Linux does not
    yq          the same for YAML          - CI configs, k8s, conda envs
    shellcheck  lints shell before it runs
    ast-grep    structural search and rewrite by syntax tree, not by regex
    uv          Python interpreters, environments and packages - builds the
                agent's own Python, and installs into it later
    mlr         Miller: CSV/TSV/JSON reshaping, sorting and stats in one pass
    resvg       SVG to PNG with no system libraries, so view-outputs can show
                the agent an SVG figure on any host
    ruff        lints and formats Python, in milliseconds
    pixi        conda-forge packages without sudo, kept in agent/pixi

They are installed even when the machine already has them, so that every host
behaves the same: the launcher puts agent/bin at the front of PATH, so the
agent gets these versions and not whatever a login node last updated in 2019.

    --no-tools              install none of them; the system's own are used
    ELM_PI_TOOL_CACHE=/path where verified archives are kept between installs
                            (default ~/.cache/elm-pi/tools)
    ELM_PI_TOOLS=fd,rg,jq   install a subset
    FD_VERSION=10.5.2       pin any of them (checksums: templates/tools.sha256)
"""

import os
import re
import shutil
import tempfile

from elmboot import console, installenv

DEFAULT_SET = "fd,rg,jq,yq,shellcheck,ast-grep,uv,mlr,resvg,pixi,ruff"
GITHUB = "https://github.com"
# The tested version of each, by the variable that overrides it. fd is the
# exception, decided per machine below.
VERSIONS = (("RG_VERSION", "15.2.0"), ("JQ_VERSION", "1.8.2"), ("YQ_VERSION", "4.54.3"),
            ("SHELLCHECK_VERSION", "0.11.0"), ("ASTGREP_VERSION", "0.51.2"),
            ("UV_VERSION", "0.13.7"), ("MLR_VERSION", "6.22.0"), ("RESVG_VERSION", "0.49.0"),
            ("PIXI_VERSION", "0.84.2"), ("RUFF_VERSION", "0.17.4"))


def names_for_machine():
    """Three projects, three naming schemes: Rust triples, Go's os_arch, and
    jq's own spelling of macOS."""
    system, machine = os.uname().sysname, os.uname().machine
    if system == "Darwin":
        names = dict(rust_os="apple-darwin", gnu_os="apple-darwin", go_os="darwin",
                     jq_os="macos", resvg_os="macos", resvg_ext="zip")
    elif system == "Linux":
        names = dict(rust_os="unknown-linux-musl", gnu_os="unknown-linux-gnu", go_os="linux",
                     jq_os="linux", resvg_os="linux", resvg_ext="tar.gz")
    else:
        console.die("unsupported OS: %s" % system)
    if machine in ("x86_64", "amd64"):
        names.update(rust_arch="x86_64", go_arch="amd64")
    elif machine in ("arm64", "aarch64"):
        names.update(rust_arch="aarch64", go_arch="arm64")
    else:
        console.die("unsupported architecture: %s" % machine)
    # musl where it is offered: a static binary has no glibc version to match.
    # ast-grep's Linux builds are the glibc ones.
    names["triple"] = "%s-%s" % (names["rust_arch"], names["rust_os"])
    names["gnu_triple"] = "%s-%s" % (names["rust_arch"], names["gnu_os"])
    return names


def versions(env, triple):
    found = {name: env.get(name) or default for name, default in VERSIONS}
    # fd 10.4+ is built against a macOS SDK newer than the Intel Macs in the
    # estate. pi pins 10.3.0 there for the same reason; match it.
    found["FD_VERSION"] = env.get("FD_VERSION") or (
        "10.3.0" if triple == "x86_64-apple-darwin" else "10.5.2")
    return found


def catalogue(env, names):
    """(binary, version, asset, url, checksum url or "") for every tool, in order."""
    v = versions(env, names["triple"])
    t, g = names["triple"], names["gnu_triple"]
    go_os, go_arch, arch = names["go_os"], names["go_arch"], names["rust_arch"]

    def release(project, tag, asset, sums=""):
        base = "%s/%s/releases/download/%s/" % (GITHUB, project, tag)
        return base + asset, (base + sums) if sums else ""

    rows = []

    def add(binary, version, asset, project, tag, sums=""):
        url, sums_url = release(project, tag, asset, sums)
        rows.append((binary, version, asset, url, sums_url))

    fd = "fd-v%s-%s.tar.gz" % (v["FD_VERSION"], t)
    add("fd", v["FD_VERSION"], fd, "sharkdp/fd", "v" + v["FD_VERSION"])
    rg = "ripgrep-%s-%s.tar.gz" % (v["RG_VERSION"], t)
    add("rg", v["RG_VERSION"], rg, "BurntSushi/ripgrep", v["RG_VERSION"], rg + ".sha256")
    add("jq", v["JQ_VERSION"], "jq-%s-%s" % (names["jq_os"], go_arch), "jqlang/jq",
        "jq-" + v["JQ_VERSION"], "sha256sum.txt")
    add("yq", v["YQ_VERSION"], "yq_%s_%s" % (go_os, go_arch), "mikefarah/yq", "v" + v["YQ_VERSION"])
    add("shellcheck", v["SHELLCHECK_VERSION"],
        "shellcheck-v%s.%s.%s.tar.xz" % (v["SHELLCHECK_VERSION"], go_os, arch),
        "koalaman/shellcheck", "v" + v["SHELLCHECK_VERSION"])
    # The zip also contains `sg`, which is a real command on Linux
    # (shadow-utils). Only ast-grep is installed; shadowing `sg` would be rude.
    add("ast-grep", v["ASTGREP_VERSION"], "app-%s.zip" % g, "ast-grep/ast-grep",
        v["ASTGREP_VERSION"])
    # The archive also has uvx, which is only `uv tool run`.
    uv = "uv-%s.tar.gz" % t
    add("uv", v["UV_VERSION"], uv, "astral-sh/uv", v["UV_VERSION"], uv + ".sha256")
    add("mlr", v["MLR_VERSION"], "miller-%s-%s-%s.tar.gz" % (v["MLR_VERSION"], go_os, go_arch),
        "johnkerl/miller", "v" + v["MLR_VERSION"], "miller-%s-checksums.txt" % v["MLR_VERSION"])
    # resvg publishes no build for 64-bit ARM Linux before 0.49; pinned below
    # that, it is skipped there with a warning and view-outputs falls back to
    # the system's tools. The Linux build links glibc, like ast-grep's.
    add("resvg", v["RESVG_VERSION"],
        "resvg-%s-%s.%s" % (names["resvg_os"], arch, names["resvg_ext"]),
        "linebender/resvg", "v" + v["RESVG_VERSION"])
    pixi = "pixi-%s.tar.gz" % t
    add("pixi", v["PIXI_VERSION"], pixi, "prefix-dev/pixi", "v" + v["PIXI_VERSION"],
        pixi + ".sha256")
    ruff = "ruff-%s.tar.gz" % t
    add("ruff", v["RUFF_VERSION"], ruff, "astral-sh/ruff", v["RUFF_VERSION"], ruff + ".sha256")
    return rows


def is_version(text, version):
    """The version as a whole word, so 0.17.10 is not taken for a pin of 0.17.1."""
    pattern = r"(^|[^0-9.])%s([^0-9.]|\.([^0-9]|$)|$)" % re.escape(version)
    return re.search(pattern, text, re.M) is not None


def published_checksum(text, asset):
    """ "hash  asset", sha256sum's binary-mode "hash *asset", or a bare hash."""
    for line in text.splitlines():
        fields = line.split()
        if not fields:
            continue
        if len(fields) >= 2 and fields[1].lstrip("*") == asset:
            return fields[0]
        if len(fields) == 1:
            return fields[0]
    return ""


def pinned_checksum(root, binary, version, asset):
    wanted = "%s/%s/%s" % (binary, version, asset)
    try:
        with open(os.path.join(root, "templates", "tools.sha256"), encoding="utf-8",
                  errors="replace") as handle:
            for line in handle:
                fields = line.split()
                if len(fields) >= 2 and fields[1] == wanted:
                    return fields[0]
    except OSError:
        pass
    return ""


def install_tool(run, toolset, cache, scratch, binary, version, asset, url, sums_url):
    """One binary into agent/bin: from the cache or the network, checksummed either way."""
    destination = run.path("agent", "bin", binary)
    cached = os.path.join(cache, binary, version, asset)
    if binary not in toolset:
        console.note("%s skipped (not in ELM_PI_TOOLS)" % binary)
        return
    # Already the pinned version? Then there is nothing to update. These are
    # pinned here, not tracked upstream, so --update means "match the pin" - it
    # does not mean "fetch 105MB again". Only a changed pin, a missing binary,
    # or one that will not run gets a download; --force gets one regardless.
    force = run.options.force
    if not force and os.access(destination, os.X_OK):
        if is_version(console.output([destination, "--version"], env=run.env), version):
            console.note("%s %s already in agent/bin" % (binary, version))
            return
    fetched = os.path.join(scratch, asset)
    from_cache = False
    if not force and os.path.isfile(cached) and os.path.getsize(cached) > 0:
        # --force deliberately bypasses the cache: it means "fetch it again".
        console.note("%s from the tool cache" % asset)
        shutil.copyfile(cached, fetched)
        from_cache = True
    else:
        console.note("downloading " + asset)
        if run.call(["curl", "-q", "-fsSL"] + run.retry + ["-o", fetched, url]) != 0:
            console.warn("could not download %s - %s not installed" % (asset, binary))
            return
    # Pinned versions are checksummed here, the way the Node tarball is. A
    # version someone pinned by hand falls back to the project's own published
    # checksum, and installs with a warning when there is none to be had.
    want = pinned_checksum(run.root, binary, version, asset)
    if not want and sums_url:
        sums = console.output(["curl", "-q", "-fsSL"] + run.retry + [sums_url], env=run.env,
                              default=None)
        if sums is None:
            console.warn("could not fetch the published checksum " + sums_url)
        else:
            want = published_checksum(sums, asset)
    got = installenv.sha256_of(fetched)
    if want:
        if want != got:
            console.die("checksum mismatch for " + asset)
    else:
        console.warn("no published checksum for %s - installing unverified (%s)" % (asset, got))
    # Verified: keep it for the next install. A cache we cannot write is not
    # worth failing over.
    if not from_cache:
        try:
            os.makedirs(os.path.dirname(cached), exist_ok=True)
            shutil.copyfile(fetched, cached)
        except OSError:
            pass

    unpacked = os.path.join(scratch, "x")
    shutil.rmtree(unpacked, ignore_errors=True)
    os.makedirs(unpacked)
    _unpack(run, fetched, unpacked, binary)
    found = installenv.find_binary(unpacked, binary)
    if not found:
        console.warn("could not unpack %s from %s - %s not installed" % (binary, asset, binary))
        return
    if os.path.lexists(destination):
        os.remove(destination)
    shutil.move(found, destination)
    os.chmod(destination, 0o755)
    if console.output([destination, "--version"], env=run.env, default=None) is None:
        os.remove(destination)
        console.warn("the downloaded %s does not run on this machine - %s not installed"
                     % (binary, binary))
        return
    console.note("%s %s -> agent/bin/%s" % (binary, version, binary))


def _unpack(run, archive, destination, binary):
    """The system's tar or unzip first, then Python's own tarfile and zipfile:
    GNU tar needs an `xz` binary for a .tar.xz and cannot read a zip at all, and
    minimal Linux installs (AlmaLinux, Arch, Ubuntu's container images) have
    neither xz nor unzip. Without the second, ast-grep was missing from every
    Linux install tested, and shellcheck too where xz was."""
    import subprocess

    def quiet(argv):
        try:
            return subprocess.call(argv, env=run.env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
        except OSError:
            return False

    if archive.endswith((".tar.gz", ".tar.xz", ".tgz")):
        if not quiet(["tar", "-xf", archive, "-C", destination]):
            _python_extract(archive, destination)
    elif archive.endswith(".zip"):
        if not (quiet(["unzip", "-q", archive, "-d", destination])
                or quiet(["tar", "-xf", archive, "-C", destination])):
            _python_extract(archive, destination)
    else:   # a bare binary, no archive
        shutil.move(archive, os.path.join(destination, binary))


def _python_extract(archive, destination):
    try:
        installenv.extract(archive, destination)
    except Exception:       # a truncated or foreign archive: "could not unpack", below
        pass


def disk_usage(run, path):
    """`du -sh`'s own figure, as it was printed before."""
    text = console.output(["du", "-sh", path], env=run.env)
    return text.split()[0] if text else ""


def install(run):
    """Phase 3b."""
    if not run.options.with_tools:
        console.say("command-line tools")
        console.note("skipped (--no-tools): the system's own fd/rg/jq/... are used instead")
        return
    env = run.env
    listed = env.get("ELM_PI_TOOLS") or DEFAULT_SET
    toolset = listed.split(",")
    console.say("command-line tools (%s)" % listed.replace(",", ", "))
    names = names_for_machine()
    # Archives are cached per user, keyed tool/version/asset, so a second
    # install - a new prefix, another machine account, a rebuilt install -
    # extracts what is already on disk instead of fetching 105MB again. Cache
    # hits are checksummed on every reuse, exactly like a fresh download, so a
    # corrupted or tampered entry fails the same way.
    cache = env.get("ELM_PI_TOOL_CACHE") or os.path.join(
        env.get("XDG_CACHE_HOME") or os.path.join(env.get("HOME", ""), ".cache"),
        "elm-pi", "tools")
    scratch = run.temp(tempfile.mkdtemp())
    for row in catalogue(env, names):
        install_tool(run, toolset, cache, scratch, *row)
    console.note("agent/bin is %s, cache %s in %s"
                 % (disk_usage(run, run.path("agent", "bin")), disk_usage(run, cache) or "0B",
                    cache))
