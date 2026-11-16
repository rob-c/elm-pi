"""This install, not this account: the environment and interpreter it runs on.

From here on nothing of the account's own toolchain is used - no conda or
virtualenv Python, no nvm/volta/Homebrew Node or npm, no ~/.npmrc or ~/.npm,
no PYTHON*/NODE_*/npm_config_*/GIT_* variables. lib/sandbox.sh has the list and
the reasons (an activated conda base put a 3.8 first on PATH and bootstrap died
on `str.removeprefix` halfway through); this is that list, in Python, and a test
reads the prefixes back out of lib/sandbox.sh so the two cannot drift.

Also here: the interpreter choice and the standalone CPython to fall back on,
the glibc-loader check that saves a NixOS install from failing three steps
later, the private TMPDIR jiti needs, the permissions on code and state, and
the disk-space estimate said before the first download rather than halfway
through it.
"""

import hashlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

from elmboot import console

# Removed by prefix, except ELM_SCRUB_KEEP: an institution's TLS-intercepting
# proxy needs its CA, and dropping it turns every download into a certificate
# error. install.sh carries an identical copy for the steps before this file
# has been downloaded; tests/test_sandbox.py fails if the two drift.
SCRUB_PREFIXES = (
    "PYTHON", "CONDA", "_CE_", "MAMBA", "VIRTUAL_ENV", "PIP_", "PYENV",
    "npm_config_", "NPM_CONFIG_", "NODE_", "NVM_", "VOLTA_", "FNM_", "ASDF_",
    "COREPACK_", "YARN_", "PNPM_", "BUN_", "GIT_",
)
# Removed by exact name: BASH_ENV/ENV are sourced by every non-interactive child
# bash, CDPATH makes `cd dir` print and land somewhere else, and the rest change
# how archives and TLS behave.
SCRUB_NAMES = ("BASH_ENV", "ENV", "CDPATH", "TAR_OPTIONS", "GZIP", "UNZIP",
               "UNZIPOPT", "GREP_OPTIONS", "CURL_HOME", "LD_PRELOAD", "LD_LIBRARY_PATH")
SCRUB_KEEP = ("NODE_EXTRA_CA_CERTS",)
CA_VARIABLES = ("SSL_CERT_FILE", "CURL_CA_BUNDLE", "REQUESTS_CA_BUNDLE",
                "NODE_EXTRA_CA_CERTS")

MIN_PYTHON = (3, 8)
STANDALONE_RELEASE = "20261003"
STANDALONE_VERSION = "3.12.15"
STANDALONE_DIGESTS = {
    "aarch64-apple-darwin": "316a463172740e71d8dca1f2730784e325f3f720941137b5d674d5801a632213",
    "x86_64-apple-darwin": "a8fd7a91852f19b6d959793ef41fad048631ccb2a334a9ecdf573255298f7978",
    "x86_64-unknown-linux-gnu": "f937814031eab4698ca6d07ec606ede1825768f3f3e99af76d9db3900bee03c5",
    "aarch64-unknown-linux-gnu": "95c01982c9fcb9d95b0acfdb5eb8a6e0099dd11edf062314a474228d93f2b765",
}
VERSION_MANAGER_MARKERS = ("/.pyenv/", "/.nvm/", "/.volta/", "/.fnm/",
                           "/fnm_multishells/", "/.asdf/", "/.npm-global",
                           "/node_modules/")
DISK_BASE_MB, DISK_PYTHON_MB, DISK_PYPI_KEPT_MB, DISK_PYPI_TEMP_MB = 1000, 1000, 400, 1000


# --- the environment --------------------------------------------------------

def scrub(env):
    """Drop every variable that redirects Python, conda, Node, npm, git or TLS."""
    for name in list(env):
        if name in SCRUB_KEEP:
            continue
        if name.startswith(SCRUB_PREFIXES):
            env.pop(name, None)
    for name in SCRUB_NAMES:
        env.pop(name, None)
    # A CA bundle that names a file which no longer exists - typically inside a
    # conda env since deleted - fails every TLS connection. One that exists is
    # the institution's and is kept.
    for name in CA_VARIABLES:
        if env.get(name) and not os.path.isfile(env[name]):
            env.pop(name, None)


def clean_path(value, keep_environments=False):
    """`value` without relative entries, duplicates or foreign toolchains.

    `keep_environments` is the launcher's mode (drop only relative entries);
    the installer drops conda, virtualenv and version-manager entries too,
    recognised structurally - conda-meta or pyvenv.cfg beside the bin - rather
    than by name.
    """
    out = []
    for entry in value.split(os.pathsep):
        if not entry.startswith("/"):
            continue
        if entry.endswith("/"):
            entry = entry[:-1]
        if not entry or entry in out:
            continue
        if not keep_environments:
            if any(marker in entry for marker in VERSION_MANAGER_MARKERS):
                continue
            # entry/.. through the filesystem, as bash's `[ -d "$entry/../conda-meta" ]`:
            # the text's parent is the wrong folder for a PATH entry that is a
            # link to conda's bin, and that entry was kept.
            if os.path.isdir(os.path.join(entry, "..", "conda-meta")):
                continue
            if os.path.isfile(os.path.join(entry, "..", "pyvenv.cfg")):
                continue
        out.append(entry)
    return os.pathsep.join(out)


def install_environment(root, env):
    """The whole install-time environment, and the umask files are written with."""
    env["ELM_PI_USER_PATH"] = env.get("ELM_PI_USER_PATH") or env.get("PATH", "")
    scrub(env)
    env["PATH"] = clean_path("%s/.node/bin:/usr/bin:/bin:/usr/sbin:/sbin:%s"
                             % (root, env.get("PATH", "")))
    npm_environment(root, env)
    # npm fetches git dependencies with git, and nothing in ~/.gitconfig (url
    # rewrites, hooks paths, credential helpers) belongs in an install.
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
               GIT_TERMINAL_PROMPT="0")
    # Files the install writes are not writable by others whatever the
    # account's umask is; a 000 umask would let anyone edit pi's code.
    os.umask(0o022)
    env["ELM_PI_ROOT"] = root


def npm_environment(root, env):
    """npm confined to the install: its config, cache and global prefix.

    npm reads the command line, npm_config_* variables, the project .npmrc,
    ~/.npmrc and the global npmrc, in that order. The variables are dropped,
    and the files are replaced with this install's own.
    """
    for name in list(env):
        if re.match(r"npm_config_", name, re.I):
            env.pop(name, None)
    # npm refuses one file loaded as both the user and the global config.
    # `or`, not a default: set and empty is unset (bash's `:-`), and npm given
    # "" as its user config reads none of this install's.
    env["NPM_CONFIG_USERCONFIG"] = (env.get("ELM_PI_NPM_USERCONFIG")
                                    or os.path.join(root, "config", "npmrc"))
    env["NPM_CONFIG_GLOBALCONFIG"] = "/dev/null"
    env["NPM_CONFIG_CACHE"] = os.path.join(root, ".npm-cache")
    env["NPM_CONFIG_PREFIX"] = os.path.join(root, ".node")
    env["NPM_CONFIG_UPDATE_NOTIFIER"] = "false"
    for name in ("NODE_OPTIONS", "NODE_PATH", "NODE_ENV"):
        env.pop(name, None)


def curl_retry(env):
    """curl's retry flags, for every download below.

    Any failure is retried for public files; --retry-all-errors (curl 7.71) adds
    the non-transient ones, and AlmaLinux 8's curl lacks it, so it is used only
    where curl has it.
    """
    flags = ["--retry", "5", "--retry-connrefused", "--retry-max-time", "120"]
    help_text = console.output(["curl", "--help", "all"], env=env)
    if "--retry-all-errors" in help_text:
        flags.append("--retry-all-errors")
    return flags


def check_loader(env):
    """Linux only: without the system's glibc loader, none of the downloads run."""
    if os.uname().sysname != "Linux":
        return ""
    machine = os.uname().machine
    loader = {("x86_64", "amd64"): "/lib64/ld-linux-x86-64.so.2",
              ("aarch64", "arm64"): "/lib/ld-linux-aarch64.so.1"}.get(machine)
    if loader is None or os.path.exists(loader):
        return ""
    if os.path.exists("/etc/NIXOS") or os.path.isdir("/nix/store"):
        return ("this system has no %s, so the Node, Python and tools elm-pi downloads cannot run.\n"
                "    On NixOS, nix-ld provides it. Add\n"
                "      programs.nix-ld.enable = true;\n"
                "    to /etc/nixos/configuration.nix, run  sudo nixos-rebuild switch,  log out and back in\n"
                "    (that sets NIX_LD), then run the install again." % loader)
    return ("this system has no %s: elm-pi needs a glibc-based Linux (Debian, Ubuntu,\n"
            "    Fedora, RHEL, Alma, Rocky, Arch, SUSE...). The Node and tools it downloads cannot run on a\n"
            "    musl system such as Alpine." % loader)


# --- the interpreter --------------------------------------------------------

PROBE = """import os, sys
if sys.version_info[:2] < (%d, %d): sys.exit(10)
if os.path.isdir(os.path.join(sys.prefix, 'conda-meta')): sys.exit(11)
if os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(sys.executable))), 'pyvenv.cfg')): sys.exit(12)
""" % MIN_PYTHON


def python_check(path):
    """0 usable, 1 missing, 10 too old, 11 conda, 12 virtualenv, 13 a shim."""
    if not os.path.isabs(path) or not os.path.isfile(path) or not os.access(path, os.X_OK):
        return 1
    if any(marker in path for marker in ("/.pyenv/", "/.asdf/", "/shims/")):
        return 13
    if os.uname().sysname == "Darwin" and path.startswith("/usr/bin/"):
        # Without the Command Line Tools, /usr/bin/python3 is a stub that opens
        # an install dialog and fails. Never run one to find out.
        if console.run(["xcode-select", "-p"], capture=True, check=False).returncode != 0:
            return 1
    try:
        result = console.run([path, "-E", "-S", "-c", PROBE], capture=True, check=False)
    except OSError:
        # Executable and not a program (a corrupt download, a script with no
        # `#!`): a candidate that does not run, not the end of the search.
        return 1
    return 0 if result.returncode == 0 else result.returncode


def python_reason(code):
    return {10: "older than %d.%d" % MIN_PYTHON, 11: "conda", 12: "virtualenv",
            13: "version-manager shim"}.get(code, "does not run")


def python_candidates(root, env):
    """Interpreters worth trying, most preferred first, system ones before PATH."""
    found = []
    for directory in ("/usr/bin", "/usr/local/bin", "/opt/homebrew/bin",
                      "/Library/Frameworks/Python.framework/Versions/Current/bin"):
        for name in ("python3", "python3.14", "python3.13", "python3.12", "python3.11",
                     "python3.10", "python3.9", "python3.8"):
            path = os.path.join(directory, name)
            if os.access(path, os.X_OK):
                found.append(path)
    bundled = os.path.join(root, ".python", "bin", "python3")
    if os.access(bundled, os.X_OK):
        found.append(bundled)
    for directory in clean_path(env.get("ELM_PI_USER_PATH", env.get("PATH", ""))).split(os.pathsep):
        if directory and os.access(os.path.join(directory, "python3"), os.X_OK):
            found.append(os.path.join(directory, "python3"))
    return found


def select_python(root, env):
    """Choose the interpreter for everything below, and export it."""
    explicit = env.get("ELM_PI_PYTHON", "")
    if explicit:
        code = python_check(explicit)
        if code in (0, 11, 12):
            env["ELM_PI_PYTHON"] = explicit
            return explicit
        if code == 13:
            console.die("ELM_PI_PYTHON=%s is a version-manager shim; name the real interpreter "
                        "(e.g. `pyenv which python3`)" % explicit)
        if code == 10:
            console.die("ELM_PI_PYTHON=%s is older than Python %d.%d"
                        % ((explicit,) + MIN_PYTHON))
        console.die("ELM_PI_PYTHON=%s is not a runnable Python (it must be an absolute path)"
                    % explicit)

    recorded = ""
    try:
        with open(os.path.join(root, "agent", "python-path"), encoding="utf-8") as handle:
            recorded = handle.readline().strip()
    except OSError:
        pass
    if recorded and python_check(recorded) == 0:
        env["ELM_PI_PYTHON"] = recorded
        return recorded

    rejected = []
    seen = set()
    for path in python_candidates(root, env):
        if path in seen:
            continue
        seen.add(path)
        code = python_check(path)
        if code == 0:
            env["ELM_PI_PYTHON"] = path
            return path
        if code != 1:
            rejected.append("\n      %s (%s)" % (path, python_reason(code)))
    lines = ["no usable Python %d.%d+ found. elm-pi does not use conda, virtualenv\n"
             "    or pyenv interpreters, whatever is first on PATH." % MIN_PYTHON]
    if rejected:
        lines.append("    Rejected:" + "".join(rejected))
    lines.append("    macOS:  xcode-select --install     (provides /usr/bin/python3)\n"
                 "    Linux:  install python3 >= %d.%d from the system package manager\n"
                 "    Or name one explicitly:  ELM_PI_PYTHON=/absolute/path/to/python3" % MIN_PYTHON)
    console.die("\n".join(lines))


def standalone_asset():
    """The pinned CPython build for this machine, as (asset, sha256)."""
    triple = {
        ("Darwin", "arm64"): "aarch64-apple-darwin",
        ("Darwin", "x86_64"): "x86_64-apple-darwin",
        ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
        ("Linux", "amd64"): "x86_64-unknown-linux-gnu",
        ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
        ("Linux", "arm64"): "aarch64-unknown-linux-gnu",
    }.get((os.uname().sysname, os.uname().machine))
    if triple is None:
        return None
    return ("cpython-%s+%s-%s-install_only.tar.gz" % (STANDALONE_VERSION, STANDALONE_RELEASE, triple),
            STANDALONE_DIGESTS[triple])


def elm_py(root, env, argv, cwd=None, capture=False, check=True):
    """Run this install's Python isolated: no PYTHON* variable, no site-packages."""
    python = env["ELM_PI_PYTHON"]
    command = [python, "-E", "-S"] + list(argv)
    return console.run(command, cwd=cwd or root, env=env, capture=capture, check=check)


def config_value(root, env, name):
    """One value scripts/elm_config.py renders from config/elm-pi.json."""
    result = elm_py(root, env, [os.path.join(root, "scripts", "elm_config.py"),
                                "--root", root, "value", name], capture=True)
    return result.stdout.strip()


# --- space, tmp, permissions, state -----------------------------------------

def disk_plan(root, options):
    """What this run downloads and keeps, in MB, and the parts for the message."""
    keep, temporary, parts = 0, 0, []
    if not os.path.isdir(os.path.join(root, "node_modules")) and not os.path.isdir(
            os.path.join(root, ".node")):
        keep += DISK_BASE_MB
        parts.append("Node, pi, its packages and the command-line tools (~1.0 GB)")
    if options.python and not os.access(os.path.join(root, "agent", "python", "env", "bin", "python"),
                                        os.X_OK):
        keep += DISK_PYTHON_MB
        parts.append("the agent's Python (~1.0 GB)")
    index = os.path.join(root, "agent", "pypi-index.db")
    if options.pypi_index and not (os.path.isfile(index) and os.path.getsize(index) > 0):
        keep += DISK_PYPI_KEPT_MB
        temporary = DISK_PYPI_TEMP_MB
        parts.append("the offline PyPI index (~0.4 GB, after a ~1 GB download deleted once it is built)")
    return keep, temporary, parts


def check_disk(root, options, env):
    """Say the estimate, then refuse if the filesystem cannot hold it."""
    keep, temporary, parts = disk_plan(root, options)
    if keep <= 0:
        return
    if not env.get("ELM_PI_DISK_NOTED"):
        console.say("disk space")
        console.note("This run downloads and keeps about %.1f GB in %s:" % (keep / 1000.0, root))
        for part in parts:
            print("      - " + part)
        if temporary:
            console.note("and needs about %.1f GB more while it runs." % (temporary / 1000.0))
    try:
        stats = os.statvfs(root)
        free_kb = (stats.f_bavail * stats.f_frsize) // 1024
    except OSError:
        free_kb = None
    if free_kb is not None and free_kb < (keep + temporary) * 1024:
        free_gb = free_kb / 1024.0 / 1000.0
        wanted = (keep + temporary) / 1000.0
        if env.get("ELM_PI_IGNORE_DISK_SPACE") == "1":
            console.warn("only %.1f GB free here; going ahead (ELM_PI_IGNORE_DISK_SPACE=1)" % free_gb)
        else:
            console.die("only %.1f GB free on this filesystem, and this run needs about %.1f GB. "
                        "Free some space, install elsewhere (ELM_PI_PREFIX), or go ahead anyway "
                        "with ELM_PI_IGNORE_DISK_SPACE=1" % (free_gb, wanted))


def is_private(path):
    """A real directory, not a symlink, owned by this account, writable by nobody else."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid():
        return False
    return not info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)


def private_tmpdir(env):
    """Point TMPDIR at a directory only this account can write.

    jiti transpiles pi's extensions into $TMPDIR/jiti and the result is executed
    on every later launch. On a Linux login node TMPDIR is usually unset, which
    means /tmp, shared by every account: whoever creates that directory first
    would decide what pi runs.
    """
    base = (env.get("TMPDIR") or "/tmp").rstrip("/") or "/tmp"
    if is_private(base):
        return
    directory = os.path.join(base, "elm-pi-%d" % os.geteuid())
    if not os.path.exists(directory):
        try:
            os.mkdir(directory, 0o700)
        except OSError:
            pass
    if not is_private(directory):
        console.die("%s is not a private directory owned by you (a symlink, or someone "
                    "else's?) - set TMPDIR to one that is" % directory)
    env["TMPDIR"] = directory


def tighten_install_perms(root, env):
    """Every code tree in the install: owner-writable only, unless shared."""
    # Shared: the group keeps its write access and everyone else loses theirs
    # (bash's o-w). This was 0o020 - the reverse.
    mask = 0o002 if env.get("ELM_PI_SHARED_STATE") == "1" else 0o022
    paths = [".node", ".python", "node_modules", "agent/npm", "agent/bin",
             "agent/extensions", "agent/agents", "lib", "config", "templates", "proxy",
             "shim", "scripts", "python", "patch-pi.py", "pi", "pi.bash", "pi.orig",
             "bootstrap.sh", "bootstrap.bash", "install.sh", "configure.sh"]
    # The install folder itself, and not what is in it: sessions, memory and
    # the key have their own rules (secure_install_state), and walking the
    # whole install rewrote every transcript's mode.
    _unwritable(root, mask)
    for relative in paths:
        target = os.path.join(root, relative)
        if not os.path.exists(target):
            continue
        if os.path.isdir(target) and not os.path.islink(target):
            for base, folders, files in os.walk(target):
                for name in folders:
                    _unwritable(os.path.join(base, name), mask)
                for name in files:
                    _unwritable(os.path.join(base, name), mask)
        _unwritable(target, mask)


def _unwritable(path, mask):
    try:
        status = os.lstat(path)
        if stat.S_ISLNK(status.st_mode):
            # chmod follows a link: with the link's own mode (0755) applied to
            # its target, a 0600 file outside the install became world-readable.
            return
        os.chmod(path, status.st_mode & ~mask)
    except OSError:
        pass


def secure_install_state(root, env):
    """Known private state at mode 700/600, without touching project files."""
    if env.get("ELM_PI_SHARED_STATE") == "1":
        return
    _chmod(os.path.join(root, "agent"), 0o700)
    _tree(os.path.join(root, "agent", "projects-memory"))
    _chmod(os.path.join(root, "agent", "egress.log"), 0o600)


def auth_mode(path, writable):
    """`/login` writes here; read-only is how a commercial subscription is refused."""
    if not os.path.exists(path):
        return
    _chmod(path, 0o600 if writable else 0o400)


def _chmod(path, mode):
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _tree(directory):
    if not os.path.isdir(directory):
        return
    _chmod(directory, 0o700)
    for base, folders, files in os.walk(directory):
        for name in folders:
            _chmod(os.path.join(base, name), 0o700)
        for name in files:
            _chmod(os.path.join(base, name), 0o600)


def sha256_of(path):
    """The file's sha256, or a refusal when no hashing tool exists.

    hashlib rather than sha256sum/shasum: bootstrap.sh has to pick between them
    and says so when it finds neither; here the tool cannot be missing.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def extract(archive, destination):
    """Unpack a .tar.gz/.tar.xz/.zip with the standard library, inside `destination`.

    GNU tar needs an `xz` binary for a .tar.xz and cannot read a zip at all, and
    minimal Linux installs have neither xz nor unzip: without this, ast-grep was
    missing from every Linux install tested, and shellcheck too where xz was.

    Nothing may be written outside `destination`. tarfile's own `data` filter
    does that, but it only exists from the security releases of 2023 onwards,
    and the interpreter this installer records may be older (macOS 11 ships
    3.9.6, which has neither the filter nor ZipFile's traversal guard). So the
    members are checked here as well, on every version: an archive is a remote
    file, and a downloaded tool is not a reason to trust one.
    """
    os.makedirs(destination, exist_ok=True)
    root = os.path.realpath(destination)
    if archive.endswith((".tar.gz", ".tgz", ".tar.xz")):
        with tarfile.open(archive) as bundle:
            members = [member for member in bundle.getmembers()
                       if _safe_member(member, root, archive)]
            kwargs = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
            bundle.extractall(destination, members=members, **kwargs)
        return True
    if archive.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(archive) as bundle:
            members = [name for name in bundle.namelist() if _safe_name(name, root, archive)]
            bundle.extractall(destination, members=members)
        return True
    return False


def _inside(root, path):
    resolved = os.path.realpath(path)
    return resolved == root or resolved.startswith(root + os.sep)


def _safe_name(name, root, archive):
    """A member's name, when extracting it stays inside `root`."""
    name = name.replace("\\", "/")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in name.split("/"):
        console.warn("refusing %s in %s: it names a path outside the destination"
                     % (name, os.path.basename(archive)))
        return False
    if not _inside(root, os.path.join(root, name)):
        console.warn("refusing %s in %s: it resolves outside the destination"
                     % (name, os.path.basename(archive)))
        return False
    return True


def _safe_member(member, root, archive):
    if not _safe_name(member.name, root, archive):
        return False
    if member.issym() or member.islnk():
        # A link inside the archive is a way out of it: check what it points at.
        target = os.path.join(os.path.dirname(os.path.join(root, member.name)), member.linkname)
        if os.path.isabs(member.linkname) or not _inside(root, target):
            console.warn("refusing the link %s in %s: it points outside the destination"
                         % (member.name, os.path.basename(archive)))
            return False
    return True


def find_binary(directory, name):
    """The first file called `name` under `directory`, as `find -type f | head -1`."""
    for base, _, files in os.walk(directory):
        for candidate in sorted(files):
            if candidate == name:
                return os.path.join(base, candidate)
    return ""
