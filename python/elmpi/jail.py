"""The OS layer: only the proxy is reachable outbound while the mode says so.

The proxy decides *which hosts* a session may reach. This decides *whether it
can reach anything else at all*, and it is the layer a compromised plugin, an
attacking prompt or an MCP server cannot argue with:

* macOS: `sandbox-exec` with a profile that denies everything and allows
  outbound TCP only to this machine's own loopback - where the proxy and the
  Llama shim are, and the session's own servers - plus Unix sockets in the
  session's temporary and project folders. Denying by default is what closes
  DNS: the system resolver is reached over a socket
  that `network-outbound` governs, so name lookups fail (measured - a
  `deny default` profile makes `getaddrinfo` raise, while `allow default` plus
  `deny network-outbound` leaves it working through mDNSResponder). A process
  cannot widen the sandbox by running sandbox-exec again (measured: refused).
* Linux: a user and network namespace with *no route* - only loopback, brought
  up by hand - and a relay from a loopback port inside it to a Unix socket the
  host owns. There is no interface to the host, so there is nothing to route:
  no DNS, no raw sockets, no second namespace back. A separate reverse relay
  exposes exactly one jailed loopback web-preview port on host loopback; it
  supplies no outbound path. A nested `unshare` gets another empty namespace,
  not this one (measured). The proxy relays must answer the proxy health
  request end to end before pi starts, and all relays follow pi's lifetime.
* Anything else, and both of those when the tooling is missing: the session
  refuses to start rather than run unfenced, the same way it refuses to run
  without the egress proxy. `ELM_PI_NO_JAIL=1` is the one way past it, for a
  debugging run.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time

from elmpi import console, network
from elmpi.errors import Refusal, CANNOT_START

PACKAGE = os.path.dirname(os.path.realpath(__file__))
SANDBOX_EXEC = "/usr/bin/sandbox-exec"
RELAY_INTERVAL = 0.02
RELAY_TIMEOUT = 5.0
FENCED_ENV = network.FENCED_ENV
TRUE = "/usr/bin/true"
TRUE_LINUX = shutil.which("true") or "/bin/true"


class Plan:
    """What to put in front of pi's own command, and what to say about it."""

    def __init__(self, prefix, note, cleanup=()):
        self.prefix = list(prefix)
        self.note = note
        self.cleanup = list(cleanup)

    def __bool__(self):
        return bool(self.prefix)


def enabled(mode, env):
    """False for yolo, and for the debugging switch; otherwise the mode decides."""
    return mode.jail and not env.get("ELM_PI_NO_JAIL")


def plan(mode, root, env, proxy_port, python):
    """The argv prefix that fences this session in, or a plain Plan([])."""
    try:
        requested_preview = network.preview_port(env)
    except ValueError as problem:
        raise Refusal("pi: %s" % problem, code=CANNOT_START)
    preview_was_explicit = bool(env.get(network.PREVIEW_ENV))
    if not enabled(mode, env):
        network.publish_preview_port(env, requested_preview)
        return Plan([], "")
    # ELM_PI_NO_PROXY=1 is the documented "no proxy, for debugging" run; a fence
    # with nothing behind it would only turn that into a session that cannot
    # reach the model at all.
    if not proxy_port:
        network.publish_preview_port(env, requested_preview)
        return Plan([], "")
    if sys.platform == "darwin":
        network.publish_preview_port(env, requested_preview)
        fence = _macos(mode, env, proxy_port)
        _mark_fenced(env, proxy_port)
        return fence
    if sys.platform.startswith("linux"):
        fence = _linux(mode, env, proxy_port, python, requested_preview,
                       preview_was_explicit)
        _mark_fenced(env, proxy_port)
        return fence
    raise Refusal.about(
        "this system has no network jail for %s, and this mode will not run unfenced."
        % os.uname().sysname,
        "Sessions run fenced by the OS: only this install's proxy is reachable from inside.",
        "To run without the fence for one command: ELM_PI_NO_JAIL=1 pi ...",
        code=CANNOT_START,
    )


def _mark_fenced(env, proxy_port):
    """Tell everything this session starts that it is inside a fence."""
    if hasattr(env, "set"):
        env.set(FENCED_ENV, proxy_port)
    else:
        env[FENCED_ENV] = str(proxy_port)


def fenced(env):
    """True when this launch was started from inside a fenced session."""
    return bool(env.get(FENCED_ENV))


# --- macOS -------------------------------------------------------------------

def profile(socket_folders=(), sockets=()):
    """The Seatbelt profile, as measured to work for pi (and to close DNS).

    Denying by default is deliberate: with `(allow default)` and a network deny,
    the system resolver still answers, because mDNSResponder does the lookup
    outside the sandbox. Under `(deny default)` with `network-outbound` limited
    to loopback, pi runs (`--list-models` works) and `getaddrinfo` fails.

    File and process operations are left broad: this layer is about the network
    (the permission gate governs what the agent may write), and every allow
    removed here is another way pi fails to start.

    Loopback is open as a whole, and Unix sockets in `socket_folders` (the
    session's temporary folder and its project). Limited to the proxy's and the
    shim's ports, as it first was, a session could not reach what it had
    started itself (measured 2026-11-15): `curl` to its own server was refused,
    a Jupyter kernel never answered - the install ships ipykernel and nbconvert -
    and multiprocessing.Manager could not bind its socket. The Linux fence
    never had that limit, since a namespace has a loopback of its own. The
    cost, on macOS only: another program listening on this machine's loopback
    (a database, a local SOCKS proxy) is reachable from the session. Nothing
    off the machine is, and no socket outside those folders - ssh-agent's stays
    closed.

    `sockets` are single sockets the session may connect to and nothing more:
    the container engine's (engine_sockets). Closed with everything else at
    first, which left a session unable to run any `docker` command at all
    ("permission denied while trying to connect to the docker API", measured
    2026-11-17) though the install's own containers skill tells it to. Opened
    by the user's decision that day, for every session on a machine that has
    an engine: what a container may then do is the permission gate's and
    command-guard's to hold (no network but an internal one, the project
    folder only), as it was before there was a fence.
    """
    lines = [
        "(version 1)",
        "(deny default)",
        "(allow file-read*)",
        "(allow file-write*)",
        "(allow process*)",
        # Measured on macOS 27 with node under this profile, 2026-11-15: without
        # file-ioctl, process.stdin.setRawMode(true) is EPERM - pi's screen
        # cannot start; without signal, child.kill() is EPERM - a tool's
        # timeout or Esc leaves the command running. Signals stay inside the
        # sandbox: the session can stop what it started and nothing else.
        "(allow file-ioctl)",
        "(allow signal (target same-sandbox))",
        # multiprocessing.Lock() and pty.openpty(), which the agent's own
        # Python and any terminal tool need: EPERM and "out of pty devices".
        "(allow ipc-posix-sem)",
        "(allow pseudo-tty)",
        "(allow sysctl-read)",
        "(allow ipc-posix-shm)",
        "(allow mach-lookup)",
        # The proxy, the Llama shim and the session's own servers, all on
        # loopback. `network-bind` and `network-inbound` are what lets the shim
        # and a web preview listen and serve.
        "(allow network-bind (local ip \"localhost:*\"))",
        "(allow network-inbound (local ip \"localhost:*\"))",
        "(allow network-outbound (remote ip \"localhost:*\"))",
    ]
    for folder in socket_folders:
        quoted = folder.replace("\\", "\\\\").replace("\"", "\\\"")
        lines.append("(allow network-bind (local unix-socket (subpath \"%s\")))" % quoted)
        lines.append("(allow network-outbound (remote unix-socket (subpath \"%s\")))" % quoted)
    for path in sockets:
        quoted = path.replace("\\", "\\\\").replace("\"", "\\\"")
        lines.append("(allow network-outbound (remote unix-socket (path-literal \"%s\")))" % quoted)
    return "\n".join(lines + [""])


def socket_folders(env):
    """Where a fenced session may bind and reach Unix sockets: its temporary
    folder and its project, as the kernel spells them.

    A temporary folder that is not this account's alone is left out: on macOS
    /tmp holds launchd's ssh-agent socket, and the launcher has already pointed
    TMPDIR at a private folder (toolchain.private_tmpdir) wherever it could.
    """
    from elmpi.toolchain import is_private
    folders = []
    temporary = env.get("TMPDIR") or ""
    if temporary and is_private(temporary.rstrip("/") or "/"):
        folders.append(os.path.realpath(temporary))
    try:
        project = os.path.realpath(os.getcwd())
    except OSError:
        project = ""
    for folder in (project,):
        if folder and folder != "/" and folder not in folders:
            folders.append(folder)
    return folders


def engine_sockets(env):
    """The container engine's socket on this machine, each way it is spelled:
    where DOCKER_HOST points when that is a local socket, and where Docker
    Desktop, Colima, Rancher Desktop and OrbStack put theirs. Only what is
    there, and is a socket: a path that is not one opens nothing.
    """
    import stat
    home = env.get("HOME") or os.path.expanduser("~")
    candidates = []
    host = env.get("DOCKER_HOST") or ""
    if host.startswith("unix://"):
        candidates.append(host[len("unix://"):])
    candidates += ["/var/run/docker.sock"] + [os.path.join(home, rel) for rel in (
        ".docker/run/docker.sock", ".colima/default/docker.sock", ".rd/docker.sock",
        ".orbstack/run/docker.sock")]
    found = []
    for path in candidates:
        for spelling in (path, os.path.realpath(path)):
            try:
                is_socket = stat.S_ISSOCK(os.stat(spelling).st_mode)
            except OSError:
                is_socket = False
            if is_socket and os.path.isabs(spelling) and spelling not in found:
                found.append(spelling)
    return found


def _macos(mode, env, proxy_port):
    if not os.access(SANDBOX_EXEC, os.X_OK):
        raise Refusal.about(
            "sandbox-exec is missing, and this mode will not run unfenced.",
            "It is part of macOS; if it has been removed, run with ELM_PI_NO_JAIL=1 "
            "only on a machine you trust.",
            code=CANNOT_START,
        )
    if not proxy_port:
        raise Refusal.about("the network jail needs the egress proxy's port, and none is running.",
                            code=CANNOT_START)
    try:
        # Not in the profile - all of loopback is - but a session with a shim
        # port nothing can listen on is refused here, in a sentence.
        network.shim_port(env)
    except ValueError as problem:
        raise Refusal("pi: %s" % problem, code=CANNOT_START)
    if fenced(env) and _inside_a_sandbox():
        # Started from inside a fenced session: that fence is inherited and
        # cannot be left, and macOS applies a second profile only when it is
        # the first one again - from another folder, or with another TMPDIR,
        # it is not, and the launch ended as sandbox-exec's own "sandbox_apply:
        # Operation not permitted" (exit 71, measured 2026-11-15). The marker
        # alone is not believed: outside a sandbox the fence is applied as usual.
        return Plan([], "jail: the fence of the session this run was started in "
                        "(outbound only to this machine's loopback)")
    # `-p` takes the profile inline: no file to leak, nothing to clean up, and
    # the profile is parsed by sandbox-exec before it execs pi.
    return Plan([SANDBOX_EXEC, "-p", profile(socket_folders(env), engine_sockets(env))],
                "jail: sandbox-exec, outbound only to this machine's loopback, where the "
                "proxy is (127.0.0.1:%d)" % proxy_port)


def _inside_a_sandbox():
    """True when this process is already sandboxed: macOS then refuses to apply
    a profile that allows everything (measured; tests/test_network_modes.py
    holds it to that), and applies it anywhere else."""
    try:
        return subprocess.run([SANDBOX_EXEC, "-p", "(version 1)(allow default)", TRUE],
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=10).returncode != 0
    except (OSError, subprocess.SubprocessError):
        return False


# --- Linux -------------------------------------------------------------------

def _linux(mode, env, proxy_port, python, preview_port=None, preview_explicit=None):
    unshare = shutil.which("unshare")
    if not unshare:
        raise Refusal.about(
            "unshare is missing, and this mode will not run unfenced.",
            "It is part of util-linux. On a distribution that restricts unprivileged user "
            "namespaces (Ubuntu 23.10+ does), allow them, or run with ELM_PI_NO_JAIL=1 only "
            "on a machine you trust.",
            code=CANNOT_START,
        )
    if not proxy_port:
        raise Refusal.about("the network jail needs the egress proxy's port, and none is running.",
                            code=CANNOT_START)
    problem = _namespace_problem(unshare)
    if problem:
        # Asked before the relays start and before the exec, after which only
        # unshare's own words are left: on Ubuntu 26.04, whose AppArmor keeps
        # user namespaces from unprivileged programs, every default launch
        # ended as "unshare: write failed /proc/self/uid_map: Operation not
        # permitted" and nothing of ours (measured 2026-11-16).
        raise Refusal(*refusal(namespace_reason(problem)), code=CANNOT_START)
    if preview_port is None:
        try:
            preview_port = network.preview_port(env)
        except ValueError as problem:
            raise Refusal("pi: %s" % problem, code=CANNOT_START)
    if preview_explicit is None:
        preview_explicit = bool(env.get(network.PREVIEW_ENV))
    # The one thing that crosses a network namespace is a filesystem: a Unix
    # socket the host owns, relayed to the proxy, and a relay inside the new
    # namespace that offers it as a loopback port. The namespace itself has no
    # interface to the host, so there is no DNS and no route to lose.
    runtime = env.get("TMPDIR", "/tmp").rstrip("/") or "/tmp"
    socket_path = os.path.join(runtime, "elm-pi-netns-%d.sock" % os.getpid())
    # sun_path holds 107 bytes on Linux. Past that the relay could not bind,
    # said so to /dev/null, and six seconds later the launch ended with "the
    # relay did not reach the proxy" - true, and no help with a long TMPDIR.
    if len(os.fsencode(socket_path)) > 107:
        raise Refusal.about(
            "TMPDIR is too long for the network jail's socket (%s)." % socket_path,
            "A Unix socket path holds 107 bytes. Set TMPDIR to a shorter private folder.",
            code=CANNOT_START,
        )
    host_relay = [python, "-E", "-S", os.path.join(PACKAGE, "relay.py"),
                  "--unix-listen", socket_path,
                  "--tcp-connect", str(proxy_port),
                  "--parent-pid", str(os.getpid())]
    try:
        relay_process = subprocess.Popen(
            host_relay, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True)
    except OSError as problem:
        raise Refusal.about("could not start the jail's relay: %s" % problem,
                            code=CANNOT_START)
    if not _wait_for_relay(socket_path):
        relay_process.terminate()
        try:
            os.unlink(socket_path)
        except OSError:
            pass
        raise Refusal.about(
            "the jail's host relay did not reach the egress proxy.",
            "Refusing to start a session whose only permitted route is unavailable.",
            code=CANNOT_START,
        )
    try:
        preview_process, preview_port, preview_socket = _preview_bridge(
            runtime, python, preview_port, preview_explicit)
    except Refusal:
        relay_process.terminate()
        try:
            os.unlink(socket_path)
        except OSError:
            pass
        raise
    network.publish_preview_port(env, preview_port, bridged=True)
    # No --fork: with it unshare stays as this pid, the session becomes its
    # child, and unshare blocks SIGINT and SIGTERM while it waits - so a
    # timeout's or a parent's `kill <pid>` did nothing at all, and SIGKILL left
    # the session running with no owner (measured, util-linux 2.39.3,
    # 2026-11-15). A user and a network namespace need no fork; without one the
    # pid the launcher was started as is pi's, which is what the proxy's
    # watchdog and both relays already assume.
    prefix = [
        unshare, "--user", "--map-root-user", "--net", "--",
        python, "-E", "-S", os.path.join(PACKAGE, "netns.py"),
        "--port", str(proxy_port), "--socket", socket_path,
        "--preview-port", str(preview_port), "--preview-socket", preview_socket, "--",
    ]
    return Plan(prefix,
                ("jail: user+net namespace with no route; only 127.0.0.1:%d reaches the proxy; "
                 "preview http://127.0.0.1:%d/ is bridged to the host")
                % (proxy_port, preview_port),
                cleanup=[relay_process, preview_process])


def namespace_reason(problem, release=None):
    """Why this system will not make the fence's namespace, and what would
    let it: lines for a refusal or a warning to be built around.

    WSL 1 is told apart by its kernel's name, because the advice differs: it
    has no namespaces at all ("unshare failed: Invalid argument", measured
    2026-11-16), and no sysctl will give it any.
    """
    release = os.uname().release if release is None else release
    lines = ["this system does not let an unprivileged program make the user and network "
             "namespace the session's fence needs.",
             "unshare said: %s" % problem]
    if release.endswith("-Microsoft"):
        lines += ["This is WSL 1, which has no namespaces. From Windows, convert the "
                  "distribution:",
                  "    wsl --set-version <distribution> 2"]
    else:
        lines += ["Ubuntu 23.10 and later restrict these through AppArmor; an administrator "
                  "can allow them with",
                  "    sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0",
                  "(elsewhere: user.max_user_namespaces and kernel.unprivileged_userns_clone "
                  "must not be 0)."]
    return lines


def fence_problem():
    """Why this machine cannot fence a session, as lines, or [] when it can."""
    if sys.platform == "darwin":
        return [] if os.access(SANDBOX_EXEC, os.X_OK) else [
            "sandbox-exec, which is part of macOS, is missing from this machine."]
    if not sys.platform.startswith("linux"):
        return ["elm-pi has no network fence for %s." % os.uname().sysname]
    unshare = shutil.which("unshare")
    if not unshare:
        return ["unshare, which is part of util-linux, is missing from this machine."]
    problem = _namespace_problem(unshare)
    return namespace_reason(problem) if problem else []


def unavailable(mode, env):
    """Why the fence this launch wants cannot be made, as lines, or [].

    Asked early, by both launchers, so that a machine without a fence is a
    decision rather than a failed exec: offline is refused (refusal()), and
    any other mode starts unfenced with a warning (warning()). Nothing is
    asked when no fence is wanted - yolo, ELM_PI_NO_JAIL, ELM_PI_NO_PROXY - or
    when this launch is inside a session that already has one.
    """
    if not enabled(mode, env) or env.get("ELM_PI_NO_PROXY") == "1" or fenced(env):
        return []
    return fence_problem()


def refusal(reason, what="this mode"):
    """A launch that will not run unfenced: `pi --offline` promises that
    nothing but the gateway is reachable, and without the fence that is only
    as true as each program's regard for proxy settings."""
    return (["pi: %s needs the OS fence, and this machine cannot make one:" % what]
            + ["    " + line for line in reason]
            + ["    To run it without the fence, the proxy still filtering, on a machine you "
               "trust: ELM_PI_NO_JAIL=1 pi ..."])


def warning(reason):
    """What a session started without its fence is told, once, at the start.

    Asked for on 2026-11-16: on Ubuntu 26.04 and WSL 1 every default launch was
    a refusal, which is a worse first hour than a session that says plainly
    what it lacks. Not printed when the person chose to run unfenced
    (ELM_PI_NO_JAIL, --remote/--yolo): they know.
    """
    return (["pi: ⚠  WARNING - this session is NOT fenced by the OS."]
            + ["    " + line for line in reason]
            + ["    It starts anyway. This install's proxy still filters what well-behaved "
               "programs reach,",
               "    but a program that ignores proxy settings can reach whatever this account "
               "can.",
               "    Without this warning: ELM_PI_NO_JAIL=1 pi ...   "
               "pi --offline is refused until the fence works."])


def _namespace_problem(unshare):
    """What unshare says when it cannot make the fence's namespace, or ""."""
    try:
        result = subprocess.run(
            [unshare, "--user", "--map-root-user", "--net", "--", TRUE_LINUX],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            universal_newlines=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as problem:
        return str(problem)
    if result.returncode == 0:
        return ""
    said = " ".join(result.stderr.split())
    return said or "exit status %d" % result.returncode


def _preview_bridge(runtime, python, requested_port, explicit):
    """Expose one jailed loopback server on host loopback, never on the LAN."""
    parent = os.getpid()
    socket_path = os.path.join(runtime, "elm-pi-preview-%d.sock" % parent)
    port_file = os.path.join(runtime, "elm-pi-preview-%d.port" % parent)
    if len(os.fsencode(socket_path)) > 107:
        raise Refusal.about(
            "TMPDIR is too long for the preview bridge's socket (%s)." % socket_path,
            "A Unix socket path holds 107 bytes. Set TMPDIR to a shorter private folder.",
            code=CANNOT_START,
        )
    for path in (socket_path, port_file):
        try:
            os.unlink(path)
        except OSError:
            pass
    # An unset default uses an ephemeral host port so two elm-pi sessions can
    # both serve previews. An explicit value is honoured or refused clearly.
    listen_port = requested_port if explicit else 0
    command = [python, "-E", "-S", os.path.join(PACKAGE, "relay.py"),
               "--tcp-listen", str(listen_port), "--unix-connect", socket_path,
               "--port-file", port_file, "--parent-pid", str(parent)]
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True)
    except OSError as problem:
        raise Refusal.about("could not start the local preview bridge: %s" % problem,
                            code=CANNOT_START)
    actual = _wait_for_port_file(port_file)
    if actual is None:
        process.terminate()
        for path in (socket_path, port_file):
            try:
                os.unlink(path)
            except OSError:
                pass
        if explicit:
            raise Refusal.about(
                "%s=%d is unavailable on host loopback." %
                (network.PREVIEW_ENV, requested_port),
                "Choose another port, or unset it to let elm-pi choose a free one.",
                code=CANNOT_START,
            )
        raise Refusal.about("the local web-preview bridge did not start.",
                            code=CANNOT_START)
    return process, actual, socket_path


def _wait_for_port_file(path):
    deadline = time.monotonic() + RELAY_TIMEOUT
    while time.monotonic() < deadline:
        try:
            with open(path, encoding="ascii") as handle:
                value = handle.read().strip()
        except OSError:
            value = ""
        if value.isdigit() and 0 < int(value) < 65536:
            return int(value)
        time.sleep(RELAY_INTERVAL)
    return None


def _wait_for_relay(path):
    """Prove the host Unix relay reaches our proxy, not merely that it bound."""
    request = ("GET /__elm_pi_egress__/health HTTP/1.0\r\n"
               "Host: 127.0.0.1\r\nConnection: close\r\n\r\n").encode("ascii")
    deadline = time.monotonic() + RELAY_TIMEOUT
    while time.monotonic() < deadline:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(min(0.5, max(0.01, deadline - time.monotonic())))
        try:
            connection.connect(path)
            connection.sendall(request)
            reply = b""
            while True:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                reply += chunk
                if len(reply) > 131072:
                    break
            head, separator, body = reply.partition(b"\r\n\r\n")
            if separator and head.startswith(b"HTTP/1.1 200 "):
                document = json.loads(body.decode("utf-8"))
                if isinstance(document, dict) and document.get("proxy") == "elm-pi-egress":
                    return True
        except (OSError, UnicodeDecodeError, ValueError):
            pass
        finally:
            connection.close()
        if time.monotonic() < deadline:
            time.sleep(RELAY_INTERVAL)
    return False
