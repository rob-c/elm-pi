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

This process runs on the host, outside the session's OS network fence.
Destination names go unchanged to create_connection below: the host's
system resolver must handle site/VPN DNS and local host mappings. No public
resolver or fallback is selected here. With a corporate upstream, only its
name is resolved here; it receives the original target name to resolve itself.

The proxy alone cannot fence a client that ignores its environment variables.
The launcher adds that restriction with macOS sandbox-exec or a Linux network
namespace in offline/trusted-remote modes. See LOCKDOWN.md for the scope.

    egress.py --allow elm.edina.ac.uk --port-file /tmp/p --log agent/egress.log
              [--parent-pid N] [--upstream http://proxy:3128]

A single "*" in --allow is open mode: every host is spliced through, and each
new destination is logged once as OPEN. That is what `pi --remote` asks for,
where an allowlist cannot express "the web" and the log is the point - the
proxy stops being a gate and stays a record.

--parent-pid makes it exit when that process goes. The launcher passes its own
pid and then execs pi, and exec keeps the pid, so the watchdog follows pi itself.
"""

import argparse
import errno
import glob
import json
import os
import re
import select
import socket
import sys
import threading
import time
from datetime import datetime, timezone

BUF = 65536
CONNECT_TIMEOUT = 15
# A tunnel no longer closes because it went quiet, so a peer that dies without a
# FIN would otherwise hold its thread until the system default keepalive fires -
# two hours on macOS. Probe after a minute of silence, give up after four tries.
# Answered locally and never forwarded, so the launcher's heartbeat can tell a
# live proxy of ours from a dead port or a stranger holding it.
HEALTH_PATH = "/__elm_pi_egress__/health"
# POST <this>?allow=host,host - keep only these hosts, each of which the proxy
# must already allow. /network uses it to make a running session offline. It
# can only take hosts away, which is why it needs no secret: a session cannot
# be given one its own agent could not read, so nothing here can widen a list.
NARROW_PATH = "/__elm_pi_egress__/narrow"
KEEPALIVE_IDLE_S = 60
KEEPALIVE_INTVL_S = 15
KEEPALIVE_CNT = 4
# Keepalive only probes a quiet connection. One with data the far side has
# stopped acknowledging is not quiet: the kernel retransmits until its own limit,
# about 15 minutes on macOS, and the send that filled the buffer waits all that
# time. On 2026-11-13 a request carrying a page screenshot stalled that way
# mid-upload; pi's idle timer, which starts once the request is sent, never ran,
# and the session sat 921 s until "[Errno 60] Operation timed out". Unacknowledged
# data now drops the connection after 120 s - pi's httpIdleTimeoutMs - and pi
# retries at once. A slow but live link keeps acknowledging and is not affected.
UNACKED_TIMEOUT_S = 120
TCP_RXT_CONNDROPTIME = 0x80   # macOS <netinet/tcp.h>; Python does not name it
# Errors that say "not right now", not "stop serving". Ending the accept loop on
# one of these takes the session's only route out with it.
TRANSIENT_ACCEPT_ERRNOS = frozenset(
    e for e in (
        getattr(errno, name, None)
        for name in ("EMFILE", "ENFILE", "ENOBUFS", "ENOMEM", "ECONNABORTED",
                     "EINTR", "EAGAIN", "EWOULDBLOCK", "EPROTO", "EHOSTUNREACH",
                     "ENETDOWN", "ENONET", "ENETUNREACH", "ETIMEDOUT")
    ) if e is not None
)


def raise_fd_limit():
    """Take as many descriptors as the system will give.

    Every tunnel costs two, and a wide fan-out over a long session can want
    hundreds at once against a soft limit of 256 on macOS.
    """
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = 10240 if hard == resource.RLIM_INFINITY else hard
        if soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
            return target
        return soft
    except Exception:
        return None


def tune_keepalive(sock):
    """Keep a live connection up, and notice a dead one in minutes not hours.

    True when the kernel has taken the limit on unacknowledged data
    (tune_unacked); False when the proxy has to keep that limit itself.
    """
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:
        return False
    for name, value in (("TCP_KEEPIDLE", KEEPALIVE_IDLE_S),    # Linux
                        ("TCP_KEEPALIVE", KEEPALIVE_IDLE_S),   # macOS
                        ("TCP_KEEPINTVL", KEEPALIVE_INTVL_S),
                        ("TCP_KEEPCNT", KEEPALIVE_CNT)):
        opt = getattr(socket, name, None)
        if opt is None:
            continue
        try:
            sock.setsockopt(socket.IPPROTO_TCP, opt, value)
        except OSError:
            pass  # a platform that will not tune it still keepalives
    return tune_unacked(sock)


def tune_unacked(sock):
    """Drop a connection whose sent data has gone unacknowledged for
    UNACKED_TIMEOUT_S. True when the kernel will do it.

    The kernel's own limit is the one to have: it sees data it is holding as
    well as data the proxy is still trying to hand it. It is read back after it
    is set, because a system can define the option and not have it: WSL 1
    answers "Protocol not available" (measured 2026-11-16). Where this is
    False, splice() keeps the limit itself, with send_within().
    """
    if hasattr(socket, "TCP_USER_TIMEOUT"):                 # Linux: milliseconds
        option, value = socket.TCP_USER_TIMEOUT, UNACKED_TIMEOUT_S * 1000
    elif sys.platform == "darwin":                          # macOS: seconds
        option, value = TCP_RXT_CONNDROPTIME, UNACKED_TIMEOUT_S
    else:
        return False
    try:
        sock.setsockopt(socket.IPPROTO_TCP, option, value)
        return sock.getsockopt(socket.IPPROTO_TCP, option) == value
    except OSError:
        return False


SEND_RETRY_S = 1.0


class Stalled(OSError):
    """The other end took no data for the whole of the limit."""


def send_within(sock, data, limit=None):
    """sendall, given up once `sock` has taken nothing for `limit` seconds.

    The backup for a system without TCP_USER_TIMEOUT. An upload the far end
    has stopped acknowledging fills the kernel's send buffer, and sendall()
    then waits as long as the kernel keeps retransmitting - 921 s in the
    session of 2026-11-13 that the kernel option was added for. Here the wait
    is for room in that buffer, and it starts again each time some is taken,
    so a slow connection that is still moving is left alone, as it is by the
    kernel's limit. What this cannot see is data the kernel already holds: a
    request small enough to fit the buffer whole is the kernel's to give up on.
    """
    limit = UNACKED_TIMEOUT_S if limit is None else limit
    view = memoryview(data)
    # The limit is kept by the clock, since the last byte taken - not by
    # select() alone: a socket can be reported writable and then take nothing
    # (a Unix socket on macOS does, with less room than its low-water mark),
    # and a loop that trusted the report never gave up.
    last_taken = time.monotonic()
    # Non-blocking for the length of this call, and put back after: a blocking
    # send() waits until all of it is queued, which is the wait this function
    # exists to bound - and MSG_DONTWAIT is not enough to stop it everywhere
    # (on macOS a send so flagged still waited on a full Unix socket).
    before = sock.gettimeout()
    sock.setblocking(False)
    try:
        while view:
            # The send first, and the wait only when it takes nothing: a far
            # end that has gone is then an error at once, as it is to sendall,
            # whatever select() makes of such a socket - and the usual case,
            # room in the buffer, is one call.
            try:
                sent = sock.send(view)
            except (BlockingIOError, InterruptedError):
                sent = 0
            except OSError as problem:
                if problem.errno != errno.ENOBUFS:
                    raise
                sent = 0
            if sent:
                view = view[sent:]
                last_taken = time.monotonic()
                continue
            left = limit - (time.monotonic() - last_taken)
            if left <= 0:
                raise Stalled("no data taken for %g s (this proxy's own limit: the system "
                              "has no per-connection one)" % limit)
            # A second at most, then the send is tried again whatever was
            # reported: the clock keeps the limit, not select().
            began = time.monotonic()
            select.select([], [sock], [sock], min(left, SEND_RETRY_S))
            if time.monotonic() - began < 0.01:
                time.sleep(0.01)               # "ready", and it took nothing: do not spin
    finally:
        try:
            sock.settimeout(before)
        except OSError:
            pass                               # closed under us: nothing to put back


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# RFC 3986's reg-name (unreserved, pct-encoded, sub-delims) plus the colons of
# an IPv6 literal. What is missing is what changes the authority's meaning -
# "@", "/", "?", "#", whitespace - so "u:p@exa.ai", userinfo dressed as a host,
# is refused rather than matched by suffix and dialled as written (found by
# adding exa.ai to proxyAllow).
HOST_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789._~%!$&'()*+,;=:-")


def is_host(host):
    return bool(host) and all(character.lower() in HOST_CHARS for character in host)


def one_request_body(head):
    """How many body bytes follow this request head, or None if it does not say.

    A chunked body ends where its own framing says, which this proxy does not
    parse; forwarding one would mean forwarding whatever followed it.
    """
    length = 0
    for line in head.split("\r\n")[1:]:
        name, _, value = line.partition(":")
        name = name.strip().lower()
        if name == "transfer-encoding":
            return None
        if name == "content-length":
            if not value.strip().isdigit():
                return None
            length = int(value.strip())
    return length


def closing(head):
    """The request head asking the next hop to close after its response."""
    lines = [line for line in head.rstrip("\r\n").split("\r\n")
             if line.partition(":")[0].strip().lower() not in ("connection", "proxy-connection", "keep-alive")]
    return "\r\n".join(lines + ["Connection: close", "Proxy-Connection: close"]) + "\r\n\r\n"


class Proxy:
    def __init__(self, allow, log_path, upstream=None):
        # Leading dots are the "and subdomains" spelling, trailing ones the
        # absolute-FQDN spelling; neither is part of the name a host matches.
        self.allow = [h.lower().strip(".") for h in allow if h]
        # "*" is open mode: no gate, but still a record of every destination.
        self.open_mode = "*" in self.allow
        self.seen_open = set()
        self.log_path = log_path
        self.upstream = upstream
        self.log_lock = threading.Lock()
        self.port_file = None
        self.port = None

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
        if self.open_mode:
            return True
        # exact host, or a subdomain of an allowed host. Never a bare IP: an
        # allowlist that accepts 93.184.x.x accepts anything with a resolver.
        return any(host == a or host.endswith("." + a) for a in self.allow)

    def note_open(self, host):
        """First contact with a host in open mode. Once per host, not per
        connection: a session opens many sockets to the same few places, and a
        log nobody can read is a log nobody reads."""
        host = host.lower().rstrip(".")
        if host in self.seen_open:
            return
        self.seen_open.add(host)
        self.log("OPEN", host, "recorded, not gated: an open run (pi --remote, --allow '*')")

    # -- connection handling -------------------------------------------------

    def handle(self, client, peer):
        client.settimeout(CONNECT_TIMEOUT)
        target = "?"
        try:
            head, pending = self.read_head(client)
            if not head:
                return
            line = head.split("\r\n", 1)[0]
            parts = line.split()
            if len(parts) < 2:
                self.deny(client, "malformed", line[:80])
                return
            method, target = parts[0].upper(), parts[1]

            if method == "GET" and target.split("?", 1)[0] == HEALTH_PATH:
                # Answered here, never forwarded. The launcher's heartbeat uses
                # it to tell a live proxy of ours from a dead port, and from
                # something else that has taken the port. A TCP connect proves
                # neither.
                self.serve_health(client)
                return

            if method == "POST" and target.split("?", 1)[0] == NARROW_PATH:
                self.serve_narrow(client, target.partition("?")[2])
                return

            if method != "CONNECT":
                # Plain HTTP, which arrives as an absolute-form request line:
                #   GET http://host/path HTTP/1.1
                # The host check is the policy; the method is not. Refusing
                # these outright meant `curl http://www.ph.ed.ac.uk/...` failed
                # even under `pi --remote`, where the proxy is meant to record
                # rather than gate - and it failed as a bare 403, which reads as
                # the site's doing.
                self.forward_plain(client, method, target, head, pending)
                return

            host, _, port = target.rpartition(":")
            if not host or (target.startswith("[") and target.endswith("]")):
                # No port, and "[2001:db8::1]" is an IPv6 literal without one:
                # its last colon is inside the brackets, not a port separator.
                host, port = target, "443"
            host = host.strip("[]")
            if not is_host(host):
                self.deny(client, f"{host}:{port}", "malformed host")
                return
            if not port.isdigit() or not 0 < int(port) < 65536:
                self.deny(client, f"{host}:{port}", "malformed port")
                return

            if not self.allowed(host):
                self.deny(client, f"{host}:{port}", "not on the allowlist")
                return
            if self.open_mode:
                self.note_open(host)

            self.connect_through(client, host, port, head, pending)
        except (OSError, socket.timeout) as err:
            # allowed, but the far end did not answer. Logged too: "why did that
            # fail" is the next question after "what did you block".
            self.log("FAILED", target, str(err))
        except Exception as err:
            self.log("FAILED", target, "unexpected %r" % (err,))
        finally:
            try:
                client.close()
            except OSError:
                pass

    def read_head(self, sock):
        """Return (header, leftover).

        A client may put the first bytes of the tunnel in the same packet as
        the CONNECT line - most wait for the 200 first, but nothing requires
        it. Those bytes belong to the tunnel, not to the header, and an earlier
        version of this dropped them on the floor: the destination then waited
        for a TLS ClientHello that had already been sent and thrown away, which
        is a hang with nothing in any log to explain it.
        """
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 32768:
            chunk = sock.recv(BUF)
            if not chunk:
                break
            data += chunk
        head, sep, rest = data.partition(b"\r\n\r\n")
        return (head + sep).decode("latin-1", "replace"), rest

    def read_upstream_reply(self, sock):
        """The upstream proxy's answer to a forwarded CONNECT, in full.

        One recv() can return half a status line. Judging the verdict on half a
        line either drops a tunnel the upstream allowed or splices one it
        refused, and both are rare enough to be diagnosed as something else.
        """
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 32768:
            chunk = sock.recv(BUF)
            if not chunk:
                break
            data += chunk
        return data

    def serve_health(self, client):
        body = json.dumps({
            "proxy": "elm-pi-egress",
            "pid": os.getpid(),
            "port": self.port,
            "allow": self.allow,
            "upstream": bool(self.upstream),
        }).encode()
        try:
            client.sendall(
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
        except OSError:
            pass  # the heartbeat will simply try again

    def narrow(self, hosts):
        """Keep only `hosts`; returns why not, or "" when it is done.

        Every host asked for must be one this proxy already allows, so the
        list after is never wider than the list before - from "*" too, which
        allows them all and is itself never kept.
        """
        wanted = []
        for host in hosts:
            host = host.strip().lower().strip(".")
            if host and host not in wanted:
                wanted.append(host)
        if not wanted:
            return "no hosts named"
        for host in wanted:
            if host == "*" or not is_host(host):
                return "not a host name: %s" % host[:80]
            if not self.allowed(host):
                return "%s is not on this proxy's list, and a list is only ever narrowed" % host
        # One assignment each: handle() runs on other threads and reads these.
        self.allow = wanted
        self.open_mode = False
        self.log("NARROWED", ",".join(wanted))
        return ""

    def serve_narrow(self, client, query):
        hosts = []
        for part in query.split("&"):
            name, _, value = part.partition("=")
            if name == "allow":
                hosts += value.split(",")
        problem = self.narrow(hosts)
        body = json.dumps({"proxy": "elm-pi-egress", "allow": self.allow,
                           "upstream": bool(self.upstream),
                           **({"error": problem} if problem else {})}).encode()
        status = b"403 Forbidden" if problem else b"200 OK"
        try:
            client.sendall(b"HTTP/1.1 " + status + b"\r\nContent-Type: application/json\r\n"
                           b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                           b"Connection: close\r\n\r\n" + body)
        except OSError:
            pass

    def deny(self, client, host, detail):
        """Refuse, and say whose refusal it is.

        The body said so already, and that turned out not to be enough: `curl
        -I` prints only headers, `curl -o` writes the body into the file, and
        `curl -s` throws it away. A session that saw nothing but "403 Forbidden"
        on 31 hosts concluded that CERN, NASA and Wikimedia were blocking
        hotlinking - picsum.photos and placekitten.com among them - and spent
        6.2M tokens on the wrong problem. The reason now rides in the headers,
        where every one of those invocations shows it.
        """
        self.log("REJECTED", host, detail)
        body = (
            "Refused by this pi install's egress proxy, not by the host.\n"
            f"{host}: {detail}.\n"
            "Start the session with `pi --remote` to reach hosts outside the\n"
            "ELM gateway, or see LOCKDOWN.md. The attempt was logged to\n"
            "agent/egress.log.\n"
        ).encode()
        try:
            client.sendall(
                b"HTTP/1.1 403 Forbidden\r\n"
                b"Content-Type: text/plain\r\n"
                b"Proxy-Agent: elm-pi-egress\r\n"
                b"X-Elm-Pi-Egress: refused\r\n"
                b"X-Elm-Pi-Reason: " + detail.encode("latin-1", "replace") + b"\r\n"
                b"X-Elm-Pi-Remedy: start the session with `pi --remote`\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
        except OSError:
            pass

    def forward_plain(self, client, method, target, head, pending=b""):
        """Proxy one plain-HTTP request, subject to the same allowlist.

        Only absolute-form targets can be forwarded: an origin-form line (`GET
        /path`) names no host, so there is nothing to dial and nothing to check.
        """
        if "://" not in target:
            self.deny(client, target, f"plain HTTP {method} without a host")
            return
        scheme, _, rest = target.partition("://")
        # The authority ends at the path, the query or the fragment, whichever
        # comes first: "http://host?q" has no path, and reading "host?q" as the
        # host refused allowed hosts - and, behind an upstream that parses it
        # properly, let "http://evil.example?.allowed.host" through.
        authority = re.match(r"[^/?#]*", rest).group()
        path = rest[len(authority):]
        host, _, port = authority.rpartition(":")
        if not host:
            host, port = authority, "80"
        host = host.strip("[]")
        if host and not port:
            port = "80"                # "pypi.org:" - RFC 3986: an empty port is the default
        elif not port.isdigit():
            host, port = authority.strip("[]"), "80"
        if not is_host(host):
            self.deny(client, f"{host}:{port}", "malformed host")
            return
        if not self.allowed(host):
            self.deny(client, f"{host}:{port}", "not on the allowlist")
            return
        if self.open_mode:
            self.note_open(host)

        # Rewrite the request line to origin-form, which is what an origin
        # server expects, and leave every header as the client wrote it.
        line, _, tail = head.partition("\r\n")
        if not path.startswith("/"):
            path = "/" + path
        origin_line = f"{method} {path} {line.rsplit(' ', 1)[-1]}"
        request = (origin_line + "\r\n" + tail).encode("latin-1", "replace") + pending

        if self.upstream:
            # One request, and the connection is over. The host checked above is
            # this request's; spliced to the campus proxy for as long as the
            # client kept the connection, every later request on it - to any
            # host, CONNECT included - went out unchecked and unlogged.
            length = one_request_body(head)
            if length is None:
                self.deny(client, f"{host}:{port}", "plain HTTP with a body of unstated length")
                return
            up_host, up_port = self.upstream
            server = socket.create_connection((up_host, up_port), CONNECT_TIMEOUT)
            server.sendall(closing(head).encode("latin-1") + pending[:length])
            self.one_exchange(client, server, length - len(pending[:length]), f"{host}:{port}")
            return
        else:
            server = socket.create_connection((host, int(port)), CONNECT_TIMEOUT)
            server.sendall(request)
        self.splice(client, server, f"{host}:{port}")

    def one_exchange(self, client, server, body_left, target):
        """The rest of one request's body up, and its response down, then close.

        Anything the client sends past the body it declared is a second
        request, which has to come back on a new connection to be checked.
        """
        client.settimeout(None)
        server.settimeout(None)
        watching = [client, server]
        try:
            while server in watching:
                readable, _, errored = select.select(watching, [], watching, 60)
                if errored:
                    break
                for src in readable:
                    data = src.recv(BUF)
                    if src is server:
                        if not data:
                            return
                        client.sendall(data)
                    elif not data:
                        watching.remove(client)
                    elif body_left > 0:
                        server.sendall(data[:body_left])
                        body_left -= len(data[:body_left])
                    else:
                        # Not forwarded, and not read again; the first request's
                        # response is still owed to the client.
                        self.log("REJECTED", target, "a second request on a plain-HTTP connection")
                        watching.remove(client)
        except OSError as err:
            self.log("DROPPED", target, str(err))
        finally:
            try:
                server.close()
            except OSError:
                pass

    def connect_through(self, client, host, port, head, pending=b""):
        if self.upstream:
            # A campus proxy in the environment is not something to route
            # around: dial it and pass the CONNECT on, with anything the client
            # pipelined behind it.
            up_host, up_port = self.upstream
            server = socket.create_connection((up_host, up_port), CONNECT_TIMEOUT)
            server.sendall(head.encode("latin-1") + pending)
            reply = self.read_upstream_reply(server)
            client.sendall(reply)
            # The code, not a substring of the line: "403 Blocked 200 times"
            # is a refusal.
            status = reply.split(b"\r\n", 1)[0].split()
            if len(status) < 2 or status[1] != b"200":
                server.close()
                return
        else:
            server = socket.create_connection((host, int(port)), CONNECT_TIMEOUT)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if pending:
                server.sendall(pending)

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
        # The kernel's limit on unacknowledged data where it has one; this
        # proxy's own, on each send, for a socket it would not take it on.
        unlimited = [sock for sock in (a, b) if not tune_keepalive(sock)]
        # The sides still sending. An EOF is a half-close, not a hang-up: a
        # client that shuts its write side once the request is out (nc -N,
        # shutdown(SHUT_WR)) still wants the response, and ending both
        # directions on it meant that response never arrived.
        sending = [a, b]
        try:
            while sending:
                readable, _, errored = select.select(sending, [], sending, 60)
                if errored:
                    self.log("DROPPED", target, "socket error while tunnelling")
                    break
                if not readable:
                    continue
                for src in readable:
                    dst = b if src is a else a
                    data = src.recv(BUF)
                    if not data:
                        sending.remove(src)
                        try:
                            dst.shutdown(socket.SHUT_WR)
                        except OSError:
                            return             # the other side is gone too
                        continue
                    try:
                        if dst in unlimited:
                            send_within(dst, data)
                        else:
                            dst.sendall(data)
                    except Stalled:
                        raise                  # said in the log, half-closed or not
                    except OSError:
                        if dst in sending:
                            raise
                        return                 # it had half-closed; now it has gone
        except OSError as err:
            # A reset mid-stream used to vanish here. It is the one thing worth
            # knowing when pi reports a connection error and the log is empty.
            self.log("DROPPED", target, str(err))
        except Exception as err:                       # never kill the thread silently
            self.log("DROPPED", target, "unexpected %r" % (err,))
        finally:
            for sock in (a, b):
                try:
                    sock.close()
                except OSError:
                    pass

    # -- lifecycle -----------------------------------------------------------

    def serve(self, port_file, parent_pid, want_port=0):
        self.port_file = port_file
        prune_stale_port_files(port_file)
        limit = raise_fd_limit()
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # want_port is how the launcher's supervisor puts a replacement back on
        # the port the session already exported as HTTPS_PROXY.
        server.bind(("127.0.0.1", want_port))
        server.listen(512)
        port = server.getsockname()[1]
        self.port = port

        # Write the port atomically: the launcher waits on this file and must
        # never read a half-written one.
        tmp = port_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(str(port))
        os.replace(tmp, port_file)

        self.log("START", "127.0.0.1:%d" % port,
                 "allow=%s fds=%s" % (",".join(self.allow), limit if limit else "?"))

        if parent_pid:
            threading.Thread(
                target=self.watch_parent, args=(parent_pid,), daemon=True
            ).start()

        me = "127.0.0.1:%d" % port
        while True:
            try:
                client, peer = server.accept()
            except OSError as err:
                if server.fileno() == -1:
                    break                      # listening socket gone: shut down
                if err.errno in TRANSIENT_ACCEPT_ERRNOS:
                    # Descriptor exhaustion during a wide fan-out is the one that
                    # matters: this loop used to end on it, and the session lost
                    # its only way out for good. Back off and keep serving.
                    self.log("ACCEPT", me, "%s - backing off" % (err,))
                    time.sleep(0.05)
                    continue
                self.log("ACCEPT", me, "fatal %s" % (err,))
                break
            except Exception as err:
                self.log("ACCEPT", me, "unexpected %r - continuing" % (err,))
                time.sleep(0.05)
                continue
            try:
                threading.Thread(target=self.handle, args=(client, peer), daemon=True).start()
            except (RuntimeError, MemoryError) as err:
                # Refusing one connection is survivable. Falling out of the loop
                # is not, so this is deliberately not a break.
                self.log("ACCEPT", me, "no thread for %s: %s" % (peer, err))
                try:
                    client.close()
                except OSError:
                    pass
                time.sleep(0.05)

    def watch_parent(self, pid):
        while True:
            time.sleep(1)
            try:
                os.kill(pid, 0)
            except OSError:
                self.drop_port_file()
                os._exit(0)

    def drop_port_file(self):
        # The file advertises a live proxy to the tool-call shim, so it must not
        # outlive the proxy. A crash can still leave one behind, which is why
        # the shim tests the port before believing it.
        if self.port_file is None:
            return                              # not serving yet: nothing to drop
        try:
            os.unlink(self.port_file)
        except OSError:
            pass


def prune_stale_port_files(port_file, max_age_s=86400):
    """Clear out port files a killed proxy never got to remove.

    A proxy unlinks its own file when its session ends, but only if it is alive
    to notice: a SIGKILLed one leaves the file behind. The shim resolves a proxy
    by testing the advertised ports in turn, so every leftover file costs it a
    connect attempt, and they accumulate for as long as the machine is up.

    A file is removed when nothing answers on its port and either its owner is
    gone or the file is old enough to be PID reuse. A temporarily dead port for
    a fresh live session is kept while its watchdog rebinds it; any listening
    long-running proxy is kept regardless of the file's age.
    """
    pattern = os.path.join(os.path.dirname(port_file) or ".", "elm-pi-egress-*.port")
    now = time.time()
    for path in glob.glob(pattern):
        if os.path.abspath(path) == os.path.abspath(port_file):
            continue                        # ours; we are about to write it
        try:
            old = now - os.path.getmtime(path) > max_age_s
            owner = int(os.path.basename(path)[len("elm-pi-egress-"):-len(".port")])
            try:
                os.kill(owner, 0)
                owner_alive = True
            except OSError:
                owner_alive = False
            with open(path, encoding="utf-8") as fh:
                port = int(fh.read().strip())
            try:
                with socket.create_connection(("127.0.0.1", port), 0.2):
                    continue                # a long-running proxy still serves it: keep it
            except OSError:
                # A fresh file owned by a live session can sit briefly between
                # a killed proxy and the watchdog rebinding its port. An old
                # dead port with a live PID is PID reuse, not a live session.
                if not owner_alive or old:
                    os.unlink(path)
        except (OSError, ValueError):
            pass


def parse_upstream(value):
    if not value:
        return None
    v = value.split("://", 1)[-1].rstrip("/")
    v = v.rsplit("@", 1)[-1]  # drop any credentials; we only need host:port
    if v.startswith("["):
        # An IPv6 literal: its colons are not the port separator, and the
        # brackets are URL syntax that create_connection() cannot resolve.
        host, _, port = v[1:].partition("]")
        port = port[1:] if port.startswith(":") else (port or "3128")
        return (host, int(port))
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
    ap.add_argument("--port", type=int, default=0,
                    help="bind this port instead of an ephemeral one, so a "
                         "restart lands where HTTPS_PROXY already points")
    args = ap.parse_args()

    allow = []
    for entry in args.allow:
        allow.extend(h.strip() for h in entry.split(",") if h.strip())

    proxy = Proxy(allow, args.log, parse_upstream(args.upstream))
    try:
        proxy.serve(args.port_file, args.parent_pid, args.port)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
