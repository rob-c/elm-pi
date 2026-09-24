#!/usr/bin/env python3
"""
egress.py - an allowlisting HTTP CONNECT proxy for this pi install.

Everything pi talks to is HTTPS, and HTTPS through a proxy begins with a
plaintext

    CONNECT elm.edina.ac.uk:443 HTTP/1.1

before the TLS handshake. Filtering on that line needs no certificate, no
interception and no decryption: the host is in the clear, the payload never is.
That is what makes this small enough to own.

The launcher starts one of these per session, points pi's HTTPS_PROXY at it,
and lets it die with pi. Allowed hosts are spliced through untouched. Everything
else gets 403 and a line in the log, which is the point: the log tells you what
tried to leave, so the call can be stopped at source later.

WHAT THIS IS NOT: enforcement. Proxy environment variables are honoured by
well-behaved clients - curl, npm, pip, requests, git over HTTPS - and ignored by
git over SSH, raw sockets, and anything that unsets the variable. The bash tool
can do all three. This stops accidents and tells you about attempts; only a
firewall, or a Linux network namespace with no other route out, stops intent.
See LOCKDOWN.md.

    egress.py --allow elm.edina.ac.uk --port-file /tmp/p --log agent/egress.log
              [--parent-pid N] [--upstream http://proxy:3128]

--parent-pid makes it exit when that process goes. The launcher passes its own
pid and then execs pi, and exec keeps the pid, so the watchdog follows pi itself.
"""

import argparse
import os
import select
import socket
import sys
import threading
import time
from datetime import datetime, timezone

BUF = 65536
CONNECT_TIMEOUT = 15


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Proxy:
    def __init__(self, allow, log_path, upstream=None):
        self.allow = [h.lower().lstrip(".") for h in allow if h]
        self.log_path = log_path
        self.upstream = upstream
        self.log_lock = threading.Lock()

    def log(self, verdict, host, detail=""):
        line = f"{now()} {verdict:8} {host}{(' ' + detail) if detail else ''}\n"
        try:
            with self.log_lock:
                with open(self.log_path, "a", encoding="utf-8") as fh:
                    fh.write(line)
        except OSError:
            pass  # a proxy that cannot write its log still has a job to do

    def allowed(self, host):
        host = host.lower().rstrip(".")
        # exact host, or a subdomain of an allowed host. Never a bare IP: an
        # allowlist that accepts 93.184.x.x accepts anything with a resolver.
        return any(host == a or host.endswith("." + a) for a in self.allow)

    # -- connection handling -------------------------------------------------

    def handle(self, client, peer):
        client.settimeout(CONNECT_TIMEOUT)
        target = "?"
        try:
            head = self.read_head(client)
            if not head:
                return
            line = head.split("\r\n", 1)[0]
            parts = line.split()
            if len(parts) < 2:
                self.deny(client, "malformed", line[:80])
                return
            method, target = parts[0].upper(), parts[1]

            if method != "CONNECT":
                # Plain HTTP. Nothing here speaks it - the ELM gateway and the
                # shim are both HTTPS - so it is refused rather than forwarded.
                self.deny(client, target, f"plain HTTP {method}")
                return

            host, _, port = target.rpartition(":")
            if not host:
                host, port = target, "443"
            host = host.strip("[]")

            if not self.allowed(host):
                self.deny(client, f"{host}:{port}", "not on the allowlist")
                return

            self.connect_through(client, host, port, head)
        except (OSError, socket.timeout) as err:
            # allowed, but the far end did not answer. Logged too: "why did that
            # fail" is the next question after "what did you block".
            self.log("FAILED", target, str(err))
        finally:
            try:
                client.close()
            except OSError:
                pass

    def read_head(self, sock):
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 32768:
            chunk = sock.recv(BUF)
            if not chunk:
                break
            data += chunk
        return data.decode("latin-1", "replace")

    def deny(self, client, host, detail):
        self.log("REJECTED", host, detail)
        body = (
            "This install proxies pi through an allowlist and this host is not on it.\n"
            "See LOCKDOWN.md. The attempt was logged.\n"
        ).encode()
        try:
            client.sendall(
                b"HTTP/1.1 403 Forbidden\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
        except OSError:
            pass

    def connect_through(self, client, host, port, head):
        if self.upstream:
            # A campus proxy in the environment is not something to route
            # around: dial it and pass the CONNECT on.
            up_host, up_port = self.upstream
            server = socket.create_connection((up_host, up_port), CONNECT_TIMEOUT)
            server.sendall(head.encode("latin-1"))
            reply = server.recv(BUF)
            client.sendall(reply)
            if b" 200 " not in reply.split(b"\r\n", 1)[0]:
                server.close()
                return
        else:
            server = socket.create_connection((host, int(port)), CONNECT_TIMEOUT)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

        self.splice(client, server, f"{host}:{port}")

    def splice(self, a, b, target="?"):
        a.settimeout(None)
        b.settimeout(None)
        # An idle tunnel is not a dead tunnel. pi keeps pooled HTTPS connections
        # to the gateway open between requests, and a fan-out of sub-agents can
        # leave one quiet for as long as the children take. An earlier version
        # of this loop treated a select() timeout as end-of-connection and tore
        # the socket down underneath the pool, which surfaced in pi as
        # "Connection error" on the next request that reused it. Idleness now
        # just goes round again; only a close or an error ends the tunnel.
        for sock in (a, b):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except OSError:
                pass  # keepalive is a nicety, not a requirement
        try:
            while True:
                readable, _, errored = select.select([a, b], [], [a, b], 60)
                if errored:
                    self.log("DROPPED", target, "socket error while tunnelling")
                    break
                if not readable:
                    continue
                for src in readable:
                    dst = b if src is a else a
                    data = src.recv(BUF)
                    if not data:
                        return
                    dst.sendall(data)
        except OSError as err:
            # A reset mid-stream used to vanish here. It is the one thing worth
            # knowing when pi reports a connection error and the log is empty.
            self.log("DROPPED", target, str(err))
        finally:
            for sock in (a, b):
                try:
                    sock.close()
                except OSError:
                    pass

    # -- lifecycle -----------------------------------------------------------

    def serve(self, port_file, parent_pid):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(64)
        port = server.getsockname()[1]

        # Write the port atomically: the launcher waits on this file and must
        # never read a half-written one.
        tmp = port_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(str(port))
        os.replace(tmp, port_file)

        self.log("START", "127.0.0.1:%d" % port, "allow=" + ",".join(self.allow))

        if parent_pid:
            threading.Thread(
                target=self.watch_parent, args=(parent_pid,), daemon=True
            ).start()

        while True:
            try:
                client, peer = server.accept()
            except OSError:
                break
            threading.Thread(target=self.handle, args=(client, peer), daemon=True).start()

    def watch_parent(self, pid):
        while True:
            time.sleep(1)
            try:
                os.kill(pid, 0)
            except OSError:
                os._exit(0)


def parse_upstream(value):
    if not value:
        return None
    v = value.split("://", 1)[-1].rstrip("/")
    v = v.rsplit("@", 1)[-1]  # drop any credentials; we only need host:port
    host, _, port = v.rpartition(":")
    if not host:
        host, port = v, "3128"
    return (host, int(port))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow", action="append", default=[], required=True)
    ap.add_argument("--port-file", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--parent-pid", type=int, default=0)
    ap.add_argument("--upstream", default="")
    args = ap.parse_args()

    allow = []
    for entry in args.allow:
        allow.extend(h.strip() for h in entry.split(",") if h.strip())

    proxy = Proxy(allow, args.log, parse_upstream(args.upstream))
    try:
        proxy.serve(args.port_file, args.parent_pid)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
