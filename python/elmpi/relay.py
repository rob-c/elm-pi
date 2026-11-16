"""The bytes-between-two-sockets relay the Linux jail needs, and nothing else.

A network namespace has no route to the host, so the proxy cannot be reached by
TCP from inside it. The one thing that does cross the boundary is a filesystem:
a Unix socket created outside is connectable inside. Two relays therefore carry
the proxy connection:

    host    unix socket  <-relay->  tcp 127.0.0.1:<proxy port>
    inside  tcp 127.0.0.1:<same number> <-relay-> unix socket

The web preview uses the same constrained transport in reverse:

    host    tcp 127.0.0.1:<preview port> <-relay-> unix socket
    inside  unix socket <-relay-> tcp 127.0.0.1:<same number>

The relay is deliberately dumb - it accepts, connects, and copies bytes each
way. It parses nothing, and it can only ever reach the one endpoint it was
started with. The proxy direction grants only the proxy's policy; the preview
direction accepts only host-loopback traffic and grants no outbound route.
"""

import os
import json
import selectors
import errno
import socket
import sys
import time

BUFFER = 65536


def pump(first, second):
    """Copy until both directions are done."""
    selector = selectors.DefaultSelector()
    selector.register(first, selectors.EVENT_READ, second)
    selector.register(second, selectors.EVENT_READ, first)
    open_reads = 2
    try:
        while open_reads:
            for key, _ in selector.select(1.0):
                try:
                    data = key.fileobj.recv(BUFFER)
                except OSError:
                    data = b""
                if data:
                    try:
                        key.data.sendall(data)
                    except OSError:
                        data = b""
                if not data:
                    selector.unregister(key.fileobj)
                    open_reads -= 1
                    try:
                        key.data.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
    finally:
        selector.close()
        for sock in (first, second):
            try:
                sock.close()
            except OSError:
                pass


def serve(listener, connect):
    """Accept until the process is gone, one thread per connection."""
    import threading
    while True:
        try:
            client, _ = listener.accept()
        except OSError as problem:
            # Out of descriptors is a full house, not a closed door: each
            # tunnel holds three, and returning here ended the relay - the
            # jailed session's only route - with nothing to start it again.
            if problem.errno in (errno.EMFILE, errno.ENFILE, errno.ENOBUFS, errno.ENOMEM,
                                 errno.ECONNABORTED, errno.EINTR):
                time.sleep(0.2)
                continue
            return
        try:
            upstream = connect()
        except OSError:
            client.close()
            continue
        threading.Thread(target=pump, args=(client, upstream), daemon=True).start()


def _listener_tcp(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(64)
    return sock


def _listener_unix(path):
    try:
        os.unlink(path)
    except OSError:
        pass
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(path)
    os.chmod(path, 0o600)
    sock.listen(64)
    return sock


def _connect_tcp(port):
    def connect():
        sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        # The ten seconds are for connecting. Left on the socket they also
        # bound every send, and an upload to a destination that paused for
        # longer was cut off mid-stream.
        sock.settimeout(None)
        return sock
    return connect


def _connect_unix(path):
    def connect():
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(10)
        sock.connect(path)
        sock.settimeout(None)
        return sock
    return connect


def wait_for_port(port, parent, seconds=5.0):
    """Block until the relay listens, or the parent goes away."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return True
        except OSError:
            pass
        if parent and not _alive(parent):
            return False
        time.sleep(0.02)
    return False


def wait_for_unix(path, parent, seconds=5.0):
    """Block until a Unix listener has published its path, or its parent dies."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if os.path.exists(path):
            return True
        if parent and not _alive(parent):
            return False
        time.sleep(0.02)
    return False


def wait_for_proxy(port, parent, seconds=5.0):
    """Wait until the relay reaches the elm-pi proxy end to end."""
    deadline = time.monotonic() + seconds
    request = (b"GET /__elm_pi_egress__/health HTTP/1.0\r\n"
               b"Host: 127.0.0.1\r\nConnection: close\r\n\r\n")
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2) as connection:
                connection.sendall(request)
                reply = b""
                while len(reply) <= 131072:
                    chunk = connection.recv(BUFFER)
                    if not chunk:
                        break
                    reply += chunk
            head, separator, body = reply.partition(b"\r\n\r\n")
            if separator and head.startswith(b"HTTP/1.1 200 "):
                document = json.loads(body.decode("utf-8"))
                if isinstance(document, dict) and document.get("proxy") == "elm-pi-egress":
                    return True
        except (OSError, UnicodeDecodeError, ValueError):
            pass
        if parent and not _alive(parent):
            return False
        time.sleep(0.02)
    return False


def _alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main(argv):
    """`relay.py --unix-listen PATH --tcp-connect PORT --parent-pid PID` or the
    reverse (`--tcp-listen PORT --unix-connect PATH`)."""
    options = dict(zip(argv[::2], argv[1::2]))
    try:
        if "--unix-listen" in options:
            listener = _listener_unix(options["--unix-listen"])
            connect = _connect_tcp(int(options["--tcp-connect"]))
        else:
            listener = _listener_tcp(int(options["--tcp-listen"]))
            connect = _connect_unix(options["--unix-connect"])
    except (KeyError, ValueError, OSError) as problem:
        sys.stderr.write("relay: %s\n" % problem)
        return 2
    parent = int(options.get("--parent-pid", "0") or 0)
    cleanup = options.get("--unix-listen")
    port_file = options.get("--port-file")
    if port_file:
        try:
            temporary = port_file + ".tmp"
            with open(temporary, "w", encoding="ascii") as handle:
                handle.write(str(listener.getsockname()[1]))
            os.replace(temporary, port_file)
        except (OSError, IndexError) as problem:
            listener.close()
            sys.stderr.write("relay: could not publish listening port: %s\n" % problem)
            return 2

    def remove_paths():
        for path in (cleanup, port_file):
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass
    if parent:
        # The relay follows its session: it is a child of the launcher, which
        # execs pi, so the pid it watches stays the session's for its lifetime.
        import threading
        def watch():
            while _alive(parent):
                time.sleep(1)
            remove_paths()
            os._exit(0)
        threading.Thread(target=watch, daemon=True).start()
    try:
        serve(listener, connect)
    finally:
        remove_paths()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
