"""The egress proxy: one allowlisting CONNECT proxy on loopback.

Everything pi does leaves through this one process: the model requests, the web
tools, every sub-agent, the shim, and every command the agent runs that honours
proxy variables. HTTPS through a proxy starts with a plaintext CONNECT line, so
the destination host is checked without any certificate, interception or
decryption - see proxy/egress.py.

Deliberately started after the update intercept: `pi update` needs npm, GitHub
and nodejs.org, and it is the one operation that runs unproxied. Fail-closed:
if the proxy cannot start, pi does not start.

    ELM_PI_NO_PROXY=1 pi ...        run unfiltered, for debugging
    ELM_PI_PROXY_ALLOW=host,host    add hosts for a run

Two things learned in driven sessions, both implemented here:

* One compatible proxy per session. A sub-agent child inherits HTTPS_PROXY from
  its parent and used to chain through it repeatedly. It now adopts the parent
  only when the health document has the exact allowlist and upstream policy
  this run requires. A deliberately tighter child starts its own scoped proxy.
* The port stays fixed for the life of the session, and a replacement is bound
  to the same one: HTTPS_PROXY has already been exported into pi, into every
  child and into detached sub-agent runners, and none of them can renegotiate
  it afterwards. A watchdog replaces a proxy that dies, on the same port.
"""

import json
import os
import socket
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

from elmpi.errors import Refusal, CANNOT_START
from elmpi.network import FENCED_ENV

HEALTH_PATH = "/__elm_pi_egress__/health"
LOOPBACK = ("127.0.0.1", "localhost", "::1")
DEFAULT_BASE_URL = "https://elm.edina.ac.uk/api/v1"
STARTUP_POLLS = 250      # measured: the proxy listens ~125ms after python starts
STARTUP_INTERVAL = 0.02  # so poll tightly and cap at five seconds
HEARTBEAT_SECONDS = 1
FENCED_TRIES = 3         # health checks of a fenced session's proxy before giving up
FENCED_PAUSE = 0.5


def elm_host(env):
    """The gateway's host from ELM_BASE_URL - the same value the shim uses."""
    base = env.get("ELM_BASE_URL", DEFAULT_BASE_URL)
    try:
        parsed = urlsplit(base if "://" in base else "//" + base)
        return parsed.hostname or ""
    except ValueError:
        return ""


def allow_list(env, host):
    """The gateway, the hosts every session may reach, and this run's own.

    proxyAllow in config/elm-pi.json (runtime.env's ELM_PROXY_ALLOW) is PyPI
    and the container registries, so pip and uv can install what a task needs.
    """
    allowed = host
    for extra in (env.get("ELM_PROXY_ALLOW"), env.get("ELM_PI_PROXY_ALLOW")):
        if extra:
            allowed += "," + extra
    return allowed


def loopback_port(url):
    """The port of a loopback proxy URL, or None for anything else."""
    if not url:
        return None
    scheme, separator, rest = url.partition("://")
    if not separator or scheme.lower() not in ("http", "https"):
        return None
    authority = rest.split("/", 1)[0]
    host, _, port = authority.rpartition(":")
    if not host.startswith("[") and ":" in host:
        return None
    if host.strip("[]") not in LOOPBACK or not port.isdigit():
        return None
    number = int(port)
    return number if 0 < number < 65536 else None


def health(port, timeout=1.0):
    """The validated health document from our proxy, or None.

    A TCP connect proves only that something holds the port; this asks the
    proxy who it is, over its own local health route. A substring is not an
    identity: an HTTP error page can quote ``elm-pi-egress`` too.
    """
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as connection:
            connection.sendall(
                ("GET %s HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
                 % HEALTH_PATH).encode("ascii"))
            reply = b""
            while True:
                chunk = connection.recv(65536)
                if not chunk:
                    break
                reply += chunk
                if len(reply) > 131072:
                    return None
    except OSError:
        return None
    head, separator, body = reply.partition(b"\r\n\r\n")
    if not separator or not head.startswith(b"HTTP/1.1 200 "):
        return None
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(document, dict) or document.get("proxy") != "elm-pi-egress":
        return None
    if not isinstance(document.get("allow"), list) or not all(
            isinstance(item, str) for item in document["allow"]):
        return None
    if not isinstance(document.get("upstream"), bool):
        return None
    return document


def alive(port, timeout=1.0):
    """True when the proxy on `port` returns a valid health document."""
    return health(port, timeout) is not None


def compatible(port, allowed, upstream, timeout=1.0):
    """True when an inherited proxy enforces exactly this run's policy."""
    document = health(port, timeout)
    expected = [item.strip().lower().strip(".") for item in allowed.split(",")
                if item.strip()]
    return bool(document and document["allow"] == expected
                and document["upstream"] is bool(upstream))


def ensure(root, env, mode=None):
    """Point pi's environment at a live proxy, starting one if needed.

    Returns the port it is reachable on, or None when this run is unfenced.
    """
    if env.get("ELM_PI_NO_PROXY") == "1":
        return None
    script = os.path.join(root, "proxy", "egress.py")
    if not os.path.isfile(script):
        raise _unproxied("proxy/egress.py is missing from this install.")
    host = elm_host(env)
    if not host:
        raise _unproxied("could not work out the ELM host from ELM_BASE_URL.")

    # Mode.hosts returns an inventory; the proxy CLI accepts one comma-separated
    # argument. Passing that list to Popen prevented every fresh guarded launch.
    allowed = ",".join(mode.hosts(env, host)) if mode is not None else allow_list(env, host)
    inherited = env.get("HTTPS_PROXY", env.get("https_proxy"))
    inherited_port = loopback_port(inherited)
    # A child sees our loopback proxy, not the corporate proxy behind it. Keep
    # the original so a child with a different allowlist can start a correctly
    # scoped proxy without silently routing around the site's proxy.
    upstream = (env.get("ELM_PI_UPSTREAM_PROXY") if inherited_port is not None
                else inherited)
    if upstream:
        # For agent/bin/brew, which runs an approved install past this proxy but
        # must still go through a campus one.
        env.set("ELM_PI_UPSTREAM_PROXY", upstream)

    port = None
    if inherited_port is not None and compatible(inherited_port, allowed, upstream):
        # Someone up the tree owns a compatible live proxy on this port and is
        # already heartbeating it. Use it and start nothing. A different mode
        # gets its own proxy: offline must never inherit trusted/yolo access.
        port = inherited_port
    if port is None and env.get(FENCED_ENV):
        port = _fenced(env, inherited_port, allowed, upstream)
    if port is None:
        port = _start_own(root, env, script, allowed, upstream)

    address = "http://127.0.0.1:%d" % port
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        env.set(name, address)
    # The Llama shim is on loopback, and so is the proxy itself. All three
    # spellings: a client that resolves localhost to ::1 and finds only the
    # other two in the list sends its loopback traffic to the proxy, which
    # refuses it.
    env.set("NO_PROXY", "127.0.0.1,localhost,::1")
    env.set("no_proxy", "127.0.0.1,localhost,::1")
    return port


def _fenced(env, inherited_port, allowed, upstream):
    """The session's proxy for a launch inside a fence, or a refusal - never a
    second proxy.

    A proxy started in here would be inside the fence too, and the fence lets
    it reach one thing: the session's own proxy. So `pi --offline -p x` from a
    session's shell started a proxy with no route out, and then ended as
    sandbox-exec's "sandbox_apply: Operation not permitted" on macOS, or as a
    run that started and could not reach the model on Linux (both measured,
    2026-11-15). The same happened to an ordinary sub-agent whenever the
    session's proxy missed one health check on a busy machine, so that case is
    asked again before it is believed.
    """
    session = env.get(FENCED_ENV)
    if inherited_port is None:
        raise Refusal.about(
            "this run is inside a session fenced to its proxy on 127.0.0.1:%s, and "
            "HTTPS_PROXY no longer names it." % session,
            "That proxy is the only route out of the session, so a run started in it has "
            "to use it.",
            "Leave HTTPS_PROXY as the session set it, or start this run from your own "
            "terminal.",
            code=CANNOT_START,
        )
    answered = False
    for attempt in range(FENCED_TRIES):
        if attempt:
            time.sleep(FENCED_PAUSE)
        if compatible(inherited_port, allowed, upstream):
            return inherited_port
        if alive(inherited_port):
            answered = True
            break
    if answered:
        raise Refusal.about(
            "this run asks for a network policy the session it is inside does not have.",
            "The session is fenced to its own proxy (127.0.0.1:%d), which is the only "
            "route out," % inherited_port,
            "so a run started in it keeps the session's network mode and hosts: drop",
            "--offline, --trusted-remote, --remote and ELM_PI_PROXY_ALLOW here, or start "
            "this run",
            "from your own terminal.",
            code=CANNOT_START,
        )
    raise Refusal.about(
        "the proxy of the session this run is inside (127.0.0.1:%d) is not answering."
        % inherited_port,
        "It is the only route out of the session, and the session restarts it within a "
        "few seconds",
        "if it has stopped: try again.",
        code=CANNOT_START,
    )


def _unproxied(problem):
    return Refusal.about(
        problem,
        "This install refuses to run unproxied. See LOCKDOWN.md.",
        "To run without the filter for one command: ELM_PI_NO_PROXY=1 pi ...",
        code=CANNOT_START,
    )


def _start_own(root, env, script, allowed, upstream):
    """Start this session's proxy, wait for it, and keep it alive."""
    # $$ survives the exec into pi - exec replaces the image, not the pid - so
    # the watchdog and the proxy's own both follow pi itself.
    parent = os.getpid()
    port_file = os.path.join(env.get("TMPDIR", "/tmp"), "elm-pi-egress-%d.port" % parent)
    try:
        os.unlink(port_file)
    except OSError:
        pass

    def spawn(port):
        argv = [
            env.get("ELM_PI_PYTHON", sys.executable), "-E", "-S", script,
            "--allow", allowed,
            "--port", str(port),
            "--port-file", port_file,
            "--log", os.path.join(root, "agent", "egress.log"),
            "--parent-pid", str(parent),
        ]
        if upstream:
            argv += ["--upstream", upstream]
        try:
            # Ctrl-C at the terminal goes to every process in the foreground
            # group. pi takes it as "stop this turn" and lives; the proxy took
            # it as "exit", and the session went on with no route out. bash
            # starts its `&` jobs with these two ignored; so does this.
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True,
                             preexec_fn=_ignore_keyboard_signals)
        except OSError:
            pass

    spawn(0)
    port = _wait_for_port(port_file)
    if port is None:
        raise _unproxied("the egress proxy did not come up.")
    _watchdog(parent, port, spawn)
    return port


def _ignore_keyboard_signals():
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGQUIT, signal.SIG_IGN)


def _wait_for_port(port_file):
    for _ in range(STARTUP_POLLS):
        try:
            with open(port_file, encoding="ascii") as handle:
                value = handle.read().strip()
        except OSError:
            value = ""
        if value.isdigit() and 0 < int(value) < 65536:
            return int(value)
        time.sleep(STARTUP_INTERVAL)
    return None


def _watchdog(parent, port, spawn):
    """Follow the session in a child process, replacing the proxy if it dies.

    One process a second, no interpreter start and no network: affordable all
    night at an interval short enough that nothing notices the gap. Two
    consecutive misses before rebinding - one miss can be a proxy busy enough
    to miss a health check, and rebinding a working port would cut the tunnels
    it is carrying.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (AttributeError, ValueError):
            pass
    try:
        child = os.fork()
    except OSError:
        return
    if child:
        return
    try:
        _ignore_keyboard_signals()      # the watchdog outlives a Ctrl-C too
        # Captured Python launches hung after pi exited: this fork kept their
        # output pipes open while its parent waited for EOF before reaping pi.
        # Match the bash watchdog's redirected streams, including stdin so a
        # background heartbeat cannot retain a caller's input pipe or terminal.
        null = os.open(os.devnull, os.O_RDWR)
        try:
            for descriptor in (0, 1, 2):
                os.dup2(null, descriptor)
        finally:
            if null > 2:
                os.close(null)
        _heartbeat(parent, port, spawn)
    finally:
        os._exit(0)


def _heartbeat(parent, port, spawn):
    failures = 0
    while _running(parent):
        if alive(port):
            failures = 0
        else:
            if not _running(parent):
                break
            failures += 1
            if failures >= 2:
                spawn(port)
                failures = 0
                time.sleep(HEARTBEAT_SECONDS)
        time.sleep(HEARTBEAT_SECONDS)


def _running(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True
