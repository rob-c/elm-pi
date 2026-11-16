"""What this session may reach, and which mode it is in.

Three modes, and the default is the middle one:

    offline          the ELM gateway and nothing else: no web tools, no PyPI,
                     no package registries, no second host. The proxy refuses
                     every other destination and the OS jail allows no packet
                     beyond the proxy.
    trusted-remote   the gateway, the package sources this install needs, and
                     the hosts named for research - still only through the
                     proxy, and still inside the OS jail. The default: a
                     session that needs a page or a package has it, and a
                     compromised plugin has nowhere else to go.
    yolo             anything, any protocol, no jail. `--remote` is now this,
                     because "let this run reach the internet" was always the
                     same decision as "stop asking": both are one session's
                     deliberate choice, and neither is a default.

The split of duties is the design: the OS jail guarantees that only the
loopback proxy is reachable (and, on Linux, that there is no route at all);
the proxy decides which hosts that proxy may reach (proxy/egress.py, one
CONNECT line at a time); and this module is the single place both read the
mode from. Nothing else should decide it.
"""

import os

OFFLINE = "offline"
TRUSTED = "trusted-remote"
YOLO = "yolo"
MODES = (OFFLINE, TRUSTED, YOLO)
DEFAULT = TRUSTED
ENV = "PI_ELM_NETWORK"

# The Llama shim on loopback: a local service, not a way out.
SHIM_PORT = 8811
# A user-visible local web preview. Linux replaces this default with a free
# host port when the variable was not explicitly set, so concurrent sessions
# do not fight over one listener.
PREVIEW_PORT = 8765
PREVIEW_ENV = "ELM_PI_PREVIEW_PORT"
# Set to the proxy's port in every fenced session, and inherited by whatever it
# starts - as the fence itself is. A launch that finds it is already inside a
# fence: its only route out is that session's proxy (proxy.py), and macOS will
# apply no second profile there unless it is the same one (jail.py; measured
# 2026-11-15, when such a launch ended as "sandbox-exec: sandbox_apply:
# Operation not permitted", exit 71, and nothing of ours). An internal marker,
# not a setting.
FENCED_ENV = "ELM_PI_FENCED"
# Why a session that would be fenced is not: "fallback" when this machine could
# not make the fence and the launcher started the session without one, with a
# warning. For the extensions that show the network mode (network.ts); an
# internal marker, not a setting.
UNFENCED_ENV = "ELM_PI_UNFENCED"
# The mode new sessions start in, when /network saved one: a file beside
# agent/permission-mode, and the variable that tells a session what it is.
SAVED_FILE = "network-mode"
DEFAULT_ENV = "PI_ELM_NETWORK_DEFAULT"


def shim_port(env):
    """The configured loopback shim port, with a useful error for bad input."""
    value = env.get("ELM_SHIM_PORT", str(SHIM_PORT))
    if value.isdigit() and 0 < int(value) < 65536:
        return int(value)
    raise ValueError("ELM_SHIM_PORT=%s is not a TCP port from 1 to 65535." % value)


def preview_port(env):
    """The requested host-loopback preview port, with a clear bad-value error."""
    value = env.get(PREVIEW_ENV, str(PREVIEW_PORT))
    if value.isdigit() and 0 < int(value) < 65536:
        return int(value)
    raise ValueError("%s=%s is not a TCP port from 1 to 65535."
                     % (PREVIEW_ENV, value))


def publish_preview_port(env, port, bridged=False):
    """Export the port the agent should bind and whether Linux bridges it."""
    if hasattr(env, "set"):
        env.set(PREVIEW_ENV, port)
        env.set("ELM_PI_PREVIEW_BRIDGED", "1" if bridged else "0")
    else:
        env[PREVIEW_ENV] = str(port)
        env["ELM_PI_PREVIEW_BRIDGED"] = "1" if bridged else "0"


class Mode:
    """This session's network policy, as the rest of the launcher reads it."""

    def __init__(self, name, source):
        self.name = name
        self.source = source

    @property
    def web(self):
        """Whether the model's web tools are offered."""
        return self.name != OFFLINE

    @property
    def jail(self):
        """Whether the OS must restrict this process tree to the proxy."""
        return self.name != YOLO

    @property
    def wildcard(self):
        """Whether the proxy may reach any host (yolo only)."""
        return self.name == YOLO

    def hosts(self, env, gateway):
        """The hosts the egress proxy may reach, in order, without duplicates."""
        allowed = [gateway]
        if self.name == OFFLINE:
            return allowed
        # trusted-remote is exactly "the gateway and the hosts this install
        # already allows" (proxyAllow in config/elm-pi.json: PyPI, the container
        # registries, the search providers). A run's own additions are allowed
        # only when trusted-remote or yolo chose them; offline ignores them.
        for value in (env.get("ELM_PROXY_ALLOW"), env.get("ELM_PI_PROXY_ALLOW")):
            for host in (value or "").split(","):
                host = host.strip()
                if host and host not in allowed:
                    allowed.append(host)
        return allowed

    def __repr__(self):
        return "Mode(%r)" % self.name


def saved_mode(root):
    """What /network saved as this install's default: the first line of
    agent/network-mode, or "" - a file that says anything else says nothing."""
    try:
        with open(os.path.join(root, "agent", SAVED_FILE), encoding="utf-8",
                  errors="replace") as handle:
            value = "".join(handle.readline().split())
    except OSError:
        return ""
    return value if value in MODES else ""


def resolve(flag, env, saved=""):
    """Pick the mode: this run's flag, else the environment, else the default
    /network saved, else trusted-remote.

    `flag` is what the launcher's own flag parsing produced (--offline,
    --trusted-remote, --remote/--yolo), or "" - so an explicit flag always beats
    a shell's PI_ELM_NETWORK, and a shell's value beats the default. An
    unrecognised value is not quietly ignored: it is a typo, and reading it as
    the default would be the one direction nobody wants.
    """
    if flag:
        return Mode(flag, "flag")
    value = env.get(ENV)
    if value:
        if value not in MODES:
            raise ValueError("%s=%s is not one of %s."
                             % (ENV, value, ", ".join(MODES)))
        return Mode(value, ENV)
    if saved in MODES:
        return Mode(saved, "saved")
    return Mode(DEFAULT, "default")


def llm_endpoint_only(env, gateway):
    """True when the mode leaves the session no destination but ELM."""
    try:
        mode = resolve("", env)
    except ValueError:
        return False
    return mode.name == OFFLINE and not env.get("ELM_PI_PROXY_ALLOW")


def describe(mode, env=None):
    """The line the launcher prints about the mode, for stderr.

    It says "enforced by the OS" only of a run that will be: with
    ELM_PI_NO_JAIL=1 - the way past a system that cannot make the fence - the
    line still claimed it (seen on Ubuntu 26.04, 2026-11-16), and with
    ELM_PI_NO_PROXY=1 it described a filter that was not running at all.
    """
    if mode.name == YOLO:
        return "network: yolo - every destination, no jail; this session only"
    if env is not None and env.get("ELM_PI_NO_PROXY") == "1":
        return ("network: %s asked for, but ELM_PI_NO_PROXY=1 - no proxy and no OS fence, "
                "so nothing is filtered" % mode.name)
    fence = ", enforced by the OS"
    if env is not None and env.get(UNFENCED_ENV) == "fallback":
        fence = "; NOT fenced by the OS"
    elif env is not None and env.get("ELM_PI_NO_JAIL"):
        fence = "; no OS fence (ELM_PI_NO_JAIL)"
    if mode.name == OFFLINE:
        return "network: offline - the ELM gateway only" + fence
    return ("network: trusted-remote - the gateway, the package sources and the "
            "research hosts, through this install's proxy" + fence)
