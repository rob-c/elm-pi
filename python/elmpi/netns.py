"""Become the session inside a network namespace that has no route out.

`unshare --user --map-root-user --net` gives this process a fresh network
namespace, which starts with one interface - loopback - that is down and has no
address. So:

1. bring loopback up, with the kernel's own ioctl rather than an `ip` binary
   (minimal images do not have one; measured on AlmaLinux),
2. start the relay that turns 127.0.0.1:<proxy port> into the host's Unix
   socket, so the proxy is the only outbound path,
3. start a reverse Unix-to-loopback relay for the one user-visible preview
   port; this accepts host-loopback connections but creates no outbound path,
4. exec pi.orig, with both relays as its children.

From here there is no interface to the host, no default route and no resolver:
DNS cannot be reached at all. A nested `unshare` gets a new, empty namespace,
not the host's (measured).
"""

import fcntl
import os
import socket
import struct
import subprocess
import sys
import time

# unshare starts this file directly with -E -S, so neither site-packages nor
# PYTHONPATH can supply elmpi. Resolve the sibling relay from this install.
if not __package__:
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

from elmpi import relay

SIOCGIFFLAGS = 0x8913
SIOCSIFFLAGS = 0x8914
IFF_UP = 0x1
PACKAGE = os.path.dirname(os.path.realpath(__file__))


def loopback_up():
    """Bring `lo` up in this namespace and wait for it to take."""
    control = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        request = struct.pack("16sh", b"lo", 0)
        flags = struct.unpack("16sh", fcntl.ioctl(control, SIOCGIFFLAGS, request))[1]
        fcntl.ioctl(control, SIOCSIFFLAGS, struct.pack("16sh", b"lo", flags | IFF_UP))
    finally:
        control.close()


def main(argv):
    options = {"--port": None, "--socket": None,
               "--preview-port": None, "--preview-socket": None, "--": None}
    index = 0
    command = []
    while index < len(argv):
        if argv[index] == "--":
            command = argv[index + 1:]
            break
        if argv[index] in options:
            options[argv[index]] = argv[index + 1]
            index += 2
            continue
        index += 1
    if (not options["--port"] or not options["--socket"]
            or not options["--preview-port"] or not options["--preview-socket"]
            or not command):
        sys.stderr.write("netns: proxy and preview ports, sockets and a command are required\n")
        return 2

    loopback_up()
    relay_process = subprocess.Popen(
        [sys.executable, "-E", "-S", os.path.join(PACKAGE, "relay.py"),
         "--tcp-listen", options["--port"], "--unix-connect", options["--socket"],
         "--parent-pid", str(os.getpid())],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    if not relay.wait_for_proxy(int(options["--port"]), os.getpid(), seconds=10):
        sys.stderr.write("netns: the relay did not reach the proxy; refusing to start pi without it\n")
        relay_process.terminate()
        return 1
    # Reverse direction for a user-visible web preview: host TCP -> shared
    # Unix socket -> this namespace's loopback server. It grants no outbound
    # route and listens on no extra TCP port inside the namespace.
    preview_process = subprocess.Popen(
        [sys.executable, "-E", "-S", os.path.join(PACKAGE, "relay.py"),
         "--unix-listen", options["--preview-socket"],
         "--tcp-connect", options["--preview-port"],
         "--parent-pid", str(os.getpid())],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    if not relay.wait_for_unix(options["--preview-socket"], os.getpid(), seconds=5):
        sys.stderr.write("netns: the local preview bridge did not start\n")
        relay_process.terminate()
        preview_process.terminate()
        return 1
    try:
        os.execv(command[0], command)
    finally:
        relay_process.terminate()
        preview_process.terminate()
    return 0  # reached only by tests that replace execv


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
