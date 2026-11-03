"""The egress proxy, proxy/egress.py, judged by what it lets out and what it says.

Every pi session's HTTPS leaves through this one loopback process, so this file
proves the parts the rest of the install leans on:

- the allowlist: the ELM host plus proxyAllow.hosts from config/elm-pi.json,
  each with its subdomains, and nothing that merely looks like them;
- the request line: CONNECT targets and plain-HTTP absolute URIs are parsed
  into the host the policy is checked against, and anything else is refused;
- the refusal: a 403 whose reasons ride in the headers, and a REJECTED line in
  the log in the format LOCKDOWN.md quotes;
- open mode (`pi --remote`, a single "*"): no gate, one OPEN line per host;
- an upstream (campus) proxy is chained to, and its verdict passed back;
- the process: argument parsing, the port file, the health endpoint, pruning
  of stale port files, and the --parent-pid watchdog.

Nothing here leaves 127.0.0.1. Hosts that are allowed are only ever dialled
when they are loopback servers this file started; real allowlisted names
appear only in refusals, pure host checks, or behind a fake local upstream that
the proxy dials instead of them.
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
EGRESS = ROOT / "proxy/egress.py"
ELM_HOST = "elm.edina.ac.uk"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


if not EGRESS.is_file():
    raise unittest.SkipTest("proxy/egress.py is not in this checkout")
egress = load_module("elm_pi_egress_under_test", EGRESS)

CONFIG_HOSTS = json.loads((ROOT / "config/elm-pi.json").read_text())["proxyAllow"]["hosts"]
# What the launcher passes: the ELM host first, then the configured package hosts.
SHIPPED = [ELM_HOST, *CONFIG_HOSTS]

TMP = None
_counter = [0]


def setUpModule():
    global TMP
    TMP = tempfile.mkdtemp(prefix="elm-pi-egress-test-")


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def fresh_log() -> str:
    _counter[0] += 1
    return os.path.join(TMP, "egress-%d.log" % _counter[0])


def proxy_for(allow, upstream=None):
    return egress.Proxy(list(allow), fresh_log(), upstream)


def log_lines(proxy):
    """The log without its timestamps: 'VERDICT  host detail' per line."""
    try:
        text = Path(proxy.log_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    return [line[21:] for line in text.splitlines()]


def slug(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower() or "empty"


def add_test(cls, name, fn):
    name = "test_" + name
    if hasattr(cls, name):
        raise AssertionError("duplicate generated test name %s.%s" % (cls.__name__, name))
    fn.__name__ = name
    setattr(cls, name, fn)


# -- socket helpers ---------------------------------------------------------------

def recv_all(sock, timeout=5.0):
    sock.settimeout(timeout)
    chunks = []
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    except (socket.timeout, OSError):
        pass
    return b"".join(chunks)


def recv_exactly(sock, n, timeout=5.0):
    sock.settimeout(timeout)
    data = b""
    try:
        while len(data) < n:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    except (socket.timeout, OSError):
        pass
    return data


def start_handle(proxy):
    """A client socket wired to proxy.handle() running in a thread."""
    ours, theirs = socket.socketpair()
    thread = threading.Thread(target=proxy.handle, args=(theirs, ("127.0.0.1", 0)), daemon=True)
    thread.start()
    return ours, thread


def exchange(proxy, request: bytes, shut=True):
    """Send one request, half-close, and return everything the proxy answered."""
    client, thread = start_handle(proxy)

    def send():
        # from a thread: a socketpair buffers only a few KiB, and the proxy
        # stops reading at 32 KiB, so a big request would block the test
        try:
            if request:
                client.sendall(request)
            if shut:
                client.shutdown(socket.SHUT_WR)
        except OSError:
            pass
    sender = threading.Thread(target=send, daemon=True)
    sender.start()
    reply = recv_all(client)
    sender.join(5)
    client.close()
    thread.join(5)
    return reply


def split_response(raw: bytes):
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    headers = {}
    for line in lines[1:]:
        k, _, v = line.partition(":")
        headers[k.strip().lower()] = v.strip()
    return lines[0], headers, body


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_dead = []


def dead_pid():
    """The pid of a process that has exited (and been reaped)."""
    if not _dead:
        p = subprocess.Popen([sys.executable, "-E", "-S", "-c", "pass"])
        p.wait()
        _dead.append(p.pid)
    return _dead[0]


class LocalServer:
    """A loopback server; serve_one(conn) runs per connection in a thread."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.received = []          # one bytearray per connection
        self.done = []              # one Event per connection
        self.accepted = 0
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.accepted += 1
            buf, ev = bytearray(), threading.Event()
            self.received.append(buf)
            self.done.append(ev)
            threading.Thread(target=self._run, args=(conn, buf, ev), daemon=True).start()

    def _run(self, conn, buf, ev):
        conn.settimeout(10)
        try:
            self.serve_one(conn, buf)
        except OSError:
            pass
        finally:
            ev.set()
            try:
                conn.close()
            except OSError:
                pass

    def wait(self, index=0, timeout=5.0):
        deadline = time.time() + timeout
        while len(self.done) <= index and time.time() < deadline:
            time.sleep(0.01)
        if len(self.done) > index:
            self.done[index].wait(max(0.0, deadline - time.time()))
        return bytes(self.received[index]) if len(self.received) > index else None

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Echo(LocalServer):
    """A tunnel destination: optional greeting, then echoes until EOF."""

    def __init__(self, greeting=b""):
        self.greeting = greeting
        super().__init__()

    def serve_one(self, conn, buf):
        if self.greeting:
            conn.sendall(self.greeting)
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
            conn.sendall(chunk)


def read_head_bytes(conn, buf):
    while b"\r\n\r\n" not in buf:
        chunk = conn.recv(65536)
        if not chunk:
            return False
        buf += chunk
    return True


class Origin(LocalServer):
    """A plain-HTTP origin: reads one request (and its Content-Length body),
    answers with a fixed response, and closes."""

    RESPONSE = b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\nX-Origin: local\r\n\r\norigin"

    def serve_one(self, conn, buf):
        if not read_head_bytes(conn, buf):
            return
        head = bytes(buf).split(b"\r\n\r\n", 1)[0].decode("latin-1")
        m = re.search(r"(?im)^content-length:\s*(\d+)", head)
        want = len(head) + 4 + (int(m.group(1)) if m else 0)
        while len(buf) < want:
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf += chunk
        conn.sendall(self.RESPONSE)


class Upstream(LocalServer):
    """A stand-in campus proxy: answers the first head with `reply` (sent as the
    given fragments), then echoes whatever follows, unless told to hang up."""

    def __init__(self, reply=(b"HTTP/1.1 200 Connection established\r\n\r\n",), hang_up=False):
        self.reply = reply
        self.hang_up = hang_up
        super().__init__()

    def serve_one(self, conn, buf):
        if not read_head_bytes(conn, buf):
            return
        for i, fragment in enumerate(self.reply):
            if i:
                time.sleep(0.05)
            conn.sendall(fragment)
        if self.hang_up:
            return
        rest = bytes(buf).split(b"\r\n\r\n", 1)[1]
        if rest:
            conn.sendall(rest)
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                return
            buf += chunk
            conn.sendall(chunk)


# == the allowlist, as pure host checks ===========================================

class ShippedAllowlistTests(unittest.TestCase):
    """Proxy.allowed() with the list the launcher passes: the ELM host plus
    proxyAllow.hosts. One generated test per host."""

    @classmethod
    def setUpClass(cls):
        cls.proxy = egress.Proxy(SHIPPED, os.devnull)


# (host, the allowlist entry that must be shipped for it to pass)
ALLOWED_HOSTS = [
    ("elm.edina.ac.uk", ELM_HOST),
    ("ELM.EDINA.AC.UK", ELM_HOST),
    ("elm.edina.ac.uk.", ELM_HOST),                 # absolute FQDN
    ("elm.edina.ac.uk..", ELM_HOST),                # every trailing dot goes
    ("api.elm.edina.ac.uk", ELM_HOST),
    ("a.b.c.elm.edina.ac.uk", ELM_HOST),
    ("API.Elm.Edina.ac.uk.", ELM_HOST),
    ("pypi.org", "pypi.org"),
    ("PyPI.org", "pypi.org"),
    ("pypi.org.", "pypi.org"),
    ("www.pypi.org", "pypi.org"),
    ("upload.pypi.org", "pypi.org"),                # the cost LOCKDOWN.md states: subdomains included
    ("0.pypi.org", "pypi.org"),
    ("xn--bcher-kva.pypi.org", "pypi.org"),         # a punycode label under an allowed host
    ("files.pythonhosted.org", "files.pythonhosted.org"),
    ("docker.io", "docker.io"),
    ("registry-1.docker.io", "docker.io"),
    ("production.cloudflare.docker.com", "production.cloudflare.docker.com"),
    ("ghcr.io", "ghcr.io"),
    ("pkg-containers.githubusercontent.com", "pkg-containers.githubusercontent.com"),
    ("quay.io", "quay.io"),
    ("cdn01.quay.io", "quay.io"),
    ("conda.anaconda.org", "conda.anaconda.org"),
    ("api.anaconda.org", "api.anaconda.org"),
    ("prefix.dev", "prefix.dev"),
    ("repo.prefix.dev", "prefix.dev"),
]

DENIED_HOSTS = [
    # parents and siblings of allowed hosts
    "edina.ac.uk", "ac.uk", "uk", "lm.edina.ac.uk", "elmedina.ac.uk",
    "pythonhosted.org", "githubusercontent.com", "raw.githubusercontent.com",
    "anaconda.org", "repo.anaconda.com",
    "cloudflare.docker.com", "docker.com", "hub.docker.com", "github.com", "org",
    # lookalikes: the allowed name as a prefix, a suffix without a dot, or altered
    "evilelm.edina.ac.uk", "elm.edina.ac.uk.evil.com", "elm-edina.ac.uk",
    "elm.edina.ac.uk-evil.com", "elm.edina.ac.ukk", "pypi.org.evil.com",
    "evilpypi.org", "pypi.org-evil.com", "pypi.com", "pypi.org.cn",
    "ypi.org", "pypi.orgx", "pypi-org.com", "pypi_org", "pypi..org",
    # punycode and unicode lookalikes: lower() is not IDNA, and must not need to be
    "xn--pypi-p0a.org", "pypi.xn--rg-9ja", "xn--elm-edina-ac-uk",
    "pyp\u0456.org", "\uff50\uff59\uff50\uff49.org", "pypi\u3002org", "pypi.org\u200b",
    # update-only and commercial hosts: never reachable from a session
    "registry.npmjs.org", "nodejs.org", "api.anthropic.com", "api.openai.com",
    "generativelanguage.googleapis.com", "openrouter.ai",
    "example.com", "localhost",
    # IP literals: an unlisted address never passes, in any spelling
    "127.0.0.1", "0.0.0.0", "10.0.0.1", "169.254.169.254", "151.101.0.223",
    "2130706433", "0x7f000001", "127.1", "::1", "::ffff:127.0.0.1",
    "2a04:4e42::223", "[::1]", "fe80::1%en0",
    # garbage
    "", ".", " ", " pypi.org", "pypi.org ", "pypi.org\n",
    "pypi.org:443", "pypi.org/", "pypi.org/simple", "user@pypi.org",
    "pypi.org@evil.com", "*", "*.evil.com",
]


def _allowed_case(host, base):
    def test(self):
        if base not in SHIPPED:
            raise unittest.SkipTest("%s is no longer in proxyAllow.hosts" % base)
        self.assertTrue(self.proxy.allowed(host), host)
    return test


def _denied_case(host):
    def test(self):
        self.assertFalse(self.proxy.allowed(host), repr(host))
    return test


for _i, (_host, _base) in enumerate(ALLOWED_HOSTS):
    add_test(ShippedAllowlistTests, "allows_%02d_%s" % (_i, slug(_host)), _allowed_case(_host, _base))
for _i, _host in enumerate(DENIED_HOSTS):
    add_test(ShippedAllowlistTests, "denies_%02d_%s" % (_i, slug(_host)), _denied_case(_host))


class AllowlistShapeTests(unittest.TestCase):
    """How allowlist entries themselves are read: case, dots, IPs, '*', empties."""


SHAPES = [
    # (name, allow, host, expected)
    ("entry_is_lowercased", ["Example.COM"], "example.com", True),
    ("leading_dot_entry_is_the_domain", [".example.com"], "example.com", True),
    ("leading_dot_entry_keeps_subdomains", [".example.com"], "a.example.com", True),
    ("several_leading_dots_stripped", ["..example.com"], "example.com", True),
    ("trailing_dot_host_matches_plain_entry", ["example.com"], "example.com.", True),
    ("listed_ipv4_matches_itself", ["127.0.0.1"], "127.0.0.1", True),
    ("listed_ipv4_not_its_neighbour", ["127.0.0.1"], "127.0.0.2", False),
    ("listed_ipv6_matches_itself", ["::1"], "::1", True),
    ("tld_entry_opens_the_whole_tld", ["com"], "example.com", True),
    ("empty_allowlist_denies_everything", [], "example.com", False),
    ("empty_allowlist_denies_empty_host", [], "", False),
    ("empty_entries_are_dropped", ["", "example.com"], "", False),
    ("star_allows_anything", ["*"], "anything.example", True),
    ("star_allows_an_empty_host", ["*"], "", True),
    ("star_allows_metadata_ip", ["*"], "169.254.169.254", True),
    ("star_anywhere_in_the_list_opens", ["example.com", "*"], "evil.com", True),
    ("wildcard_entry_is_not_open_mode", ["*.example.com"], "evil.com", False),
]


def _shape_case(allow, host, expected):
    def test(self):
        self.assertEqual(expected, egress.Proxy(allow, os.devnull).allowed(host))
    return test


for _name, _allow, _host, _expected in SHAPES:
    add_test(AllowlistShapeTests, _name, _shape_case(_allow, _host, _expected))

# Entries and hosts lose dots at both ends alike, so an absolute-FQDN entry
# like "example.com." matches its host.
add_test(AllowlistShapeTests, "trailing_dot_entry_matches_its_host",
         _shape_case(["example.com."], "example.com", True))


class ProxyConstructionTests(unittest.TestCase):
    def test_allow_list_is_normalised(self):
        p = egress.Proxy(["Elm.Edina.AC.uk", ".PyPI.org", "", None, "quay.io"], os.devnull)
        self.assertEqual(["elm.edina.ac.uk", "pypi.org", "quay.io"], p.allow)

    def test_gate_mode_by_default(self):
        self.assertFalse(egress.Proxy(SHIPPED, os.devnull).open_mode)

    def test_single_star_is_open_mode(self):
        self.assertTrue(egress.Proxy(["*"], os.devnull).open_mode)

    def test_star_with_padding_is_not_open_mode(self):
        # main() strips entries; the class takes them as given
        self.assertFalse(egress.Proxy([" *"], os.devnull).open_mode)

    def test_nothing_seen_before_first_connection(self):
        self.assertEqual(set(), egress.Proxy(["*"], os.devnull).seen_open)

    def test_upstream_is_kept_as_given(self):
        self.assertEqual(("campus", 3128), egress.Proxy([], os.devnull, ("campus", 3128)).upstream)

    def test_port_unknown_until_served(self):
        self.assertIsNone(egress.Proxy([], os.devnull).port)

    # port_file is None until serve() writes it; dropping it before then is a no-op.
    def test_drop_port_file_before_serving_is_harmless(self):
        egress.Proxy([], os.devnull).drop_port_file()

    def test_drop_port_file_removes_it(self):
        p = egress.Proxy([], os.devnull)
        p.port_file = os.path.join(TMP, "drop.port")
        Path(p.port_file).write_text("1")
        p.drop_port_file()
        self.assertFalse(os.path.exists(p.port_file))

    def test_drop_port_file_twice_is_harmless(self):
        p = egress.Proxy([], os.devnull)
        p.port_file = os.path.join(TMP, "never-written.port")
        p.drop_port_file()
        self.assertFalse(os.path.exists(p.port_file))


# == the log ======================================================================

STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ ")


class LogFormatTests(unittest.TestCase):
    def setUp(self):
        self.proxy = proxy_for(["*"])

    def raw(self):
        return Path(self.proxy.log_path).read_text(encoding="utf-8")

    def test_line_starts_with_a_utc_timestamp(self):
        self.proxy.log("REJECTED", "evil.com:443", "not on the allowlist")
        self.assertRegex(self.raw(), STAMP)

    def test_timestamp_is_now_in_utc(self):
        self.proxy.log("REJECTED", "x", "y")
        stamp = datetime.strptime(self.raw()[:20], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self.assertLess(abs((datetime.now(timezone.utc) - stamp).total_seconds()), 5)

    def test_rejected_line_matches_lockdown_md(self):
        self.proxy.log("REJECTED", "example.com:443", "not on the allowlist")
        self.assertEqual(["REJECTED example.com:443 not on the allowlist"], log_lines(self.proxy))

    def test_short_verdict_is_padded_to_eight(self):
        self.proxy.log("OPEN", "pypi.org", "first")
        self.assertEqual(["OPEN     pypi.org first"], log_lines(self.proxy))

    def test_long_verdict_is_not_truncated(self):
        self.proxy.log("UNPROXIED", "brew install pandoc")
        self.assertEqual(["UNPROXIED brew install pandoc"], log_lines(self.proxy))

    def test_no_detail_means_no_trailing_space(self):
        self.proxy.log("START", "127.0.0.1:1")
        self.assertTrue(self.raw().endswith("START    127.0.0.1:1\n"))

    def test_lines_are_appended(self):
        Path(self.proxy.log_path).write_text("earlier\n", encoding="utf-8")
        self.proxy.log("FAILED", "a:1", "b")
        self.assertEqual("earlier", self.raw().splitlines()[0])
        self.assertEqual(2, len(self.raw().splitlines()))

    def test_non_ascii_host_is_written_as_utf8(self):
        self.proxy.log("REJECTED", "pyp\u0456.org:443", "x")
        self.assertIn("pyp\u0456.org:443", self.raw())

    def test_unwritable_log_is_not_fatal(self):
        p = egress.Proxy([], TMP)          # a directory: open() fails
        p.log("REJECTED", "a", "b")        # must not raise

    def test_concurrent_lines_do_not_interleave(self):
        threads = [threading.Thread(target=self.proxy.log, args=("FAILED", "h%d" % i, "x" * 200))
                   for i in range(40)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        lines = log_lines(self.proxy)
        self.assertEqual(40, len(lines))
        self.assertTrue(all(re.fullmatch(r"FAILED   h\d+ x{200}", l) for l in lines))


class OpenModeRecordTests(unittest.TestCase):
    """note_open: one OPEN line per host for the life of the proxy."""

    def setUp(self):
        self.proxy = proxy_for(["*"])

    def test_first_contact_is_logged_with_reason(self):
        self.proxy.note_open("pypi.org")
        self.assertEqual(["OPEN     pypi.org no allowlist in this install (--allow '*')"],
                         log_lines(self.proxy))

    def test_second_contact_is_not_logged(self):
        self.proxy.note_open("pypi.org")
        self.proxy.note_open("pypi.org")
        self.assertEqual(1, len(log_lines(self.proxy)))

    def test_case_variants_are_one_host(self):
        self.proxy.note_open("pypi.org")
        self.proxy.note_open("PyPI.ORG")
        self.assertEqual(1, len(log_lines(self.proxy)))

    def test_trailing_dot_is_one_host(self):
        self.proxy.note_open("pypi.org.")
        self.proxy.note_open("pypi.org")
        self.assertEqual({"pypi.org"}, self.proxy.seen_open)

    def test_host_is_logged_lowercased(self):
        self.proxy.note_open("WWW.Example.COM")
        self.assertTrue(log_lines(self.proxy)[0].startswith("OPEN     www.example.com "))

    def test_each_new_host_is_logged(self):
        for h in ("a.example", "b.example", "a.example", "c.example"):
            self.proxy.note_open(h)
        self.assertEqual(["a.example", "b.example", "c.example"],
                         [l.split()[1] for l in log_lines(self.proxy)])


# == the request line, end to end through handle() ===============================

class RequestLineTests(unittest.TestCase):
    """One request per test through Proxy.handle() on a socketpair, with the
    shipped allowlist. Each case names the log line it must produce."""


# (name, request, expected log line without timestamp)
REFUSALS = [
    ("connect_unlisted_host", b"CONNECT evil.com:443 HTTP/1.1\r\nHost: evil.com:443\r\n\r\n",
     "REJECTED evil.com:443 not on the allowlist"),
    ("connect_lockdown_example", b"CONNECT example.com:443 HTTP/1.1\r\n\r\n",
     "REJECTED example.com:443 not on the allowlist"),
    ("connect_lowercase_method", b"connect evil.com:443 HTTP/1.1\r\n\r\n",
     "REJECTED evil.com:443 not on the allowlist"),
    ("connect_host_logged_as_sent", b"CONNECT EVIL.COM:443 HTTP/1.1\r\n\r\n",
     "REJECTED EVIL.COM:443 not on the allowlist"),
    ("connect_without_port_is_443", b"CONNECT evil.net HTTP/1.1\r\n\r\n",
     "REJECTED evil.net:443 not on the allowlist"),
    ("connect_nonstandard_port", b"CONNECT evil.com:8443 HTTP/1.1\r\n\r\n",
     "REJECTED evil.com:8443 not on the allowlist"),
    ("connect_port_zero", b"CONNECT evil.com:0 HTTP/1.1\r\n\r\n",
     "REJECTED evil.com:0 not on the allowlist"),
    ("connect_ipv6_loopback", b"CONNECT [::1]:443 HTTP/1.1\r\n\r\n",
     "REJECTED ::1:443 not on the allowlist"),
    ("connect_ipv6_global", b"CONNECT [2a04:4e42::223]:443 HTTP/1.1\r\n\r\n",
     "REJECTED 2a04:4e42::223:443 not on the allowlist"),
    ("connect_ipv4_literal", b"CONNECT 151.101.0.223:443 HTTP/1.1\r\n\r\n",
     "REJECTED 151.101.0.223:443 not on the allowlist"),
    ("connect_metadata_ip", b"CONNECT 169.254.169.254:80 HTTP/1.1\r\n\r\n",
     "REJECTED 169.254.169.254:80 not on the allowlist"),
    ("connect_suffix_lookalike", b"CONNECT pypi.org.evil.com:443 HTTP/1.1\r\n\r\n",
     "REJECTED pypi.org.evil.com:443 not on the allowlist"),
    ("connect_prefix_lookalike", b"CONNECT evilpypi.org:443 HTTP/1.1\r\n\r\n",
     "REJECTED evilpypi.org:443 not on the allowlist"),
    ("connect_elm_lookalike", b"CONNECT elm.edina.ac.uk.evil.com:443 HTTP/1.1\r\n\r\n",
     "REJECTED elm.edina.ac.uk.evil.com:443 not on the allowlist"),
    ("connect_anthropic", b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n\r\n",
     "REJECTED api.anthropic.com:443 not on the allowlist"),
    ("connect_userinfo_trick", b"CONNECT pypi.org@evil.com:443 HTTP/1.1\r\n\r\n",
     "REJECTED pypi.org@evil.com:443 not on the allowlist"),
    ("connect_without_version", b"CONNECT evil.io:443\r\n\r\n",
     "REJECTED evil.io:443 not on the allowlist"),
    ("connect_extra_tokens", b"CONNECT evil.com:443 HTTP/1.1 extra\r\n\r\n",
     "REJECTED evil.com:443 not on the allowlist"),
    ("connect_tab_separated", b"CONNECT\tevil.com:443\tHTTP/1.1\r\n\r\n",
     "REJECTED evil.com:443 not on the allowlist"),
    ("connect_leading_whitespace", b"  CONNECT evil.com:443 HTTP/1.1\r\n\r\n",
     "REJECTED evil.com:443 not on the allowlist"),
    ("connect_lf_only_line_endings", b"CONNECT evil.com:443 HTTP/1.1\n\n",
     "REJECTED evil.com:443 not on the allowlist"),
    ("connect_head_never_terminated", b"CONNECT evil.com:443 HTTP/1.1\r\n",
     "REJECTED evil.com:443 not on the allowlist"),
    ("connect_host_header_is_ignored", b"CONNECT evil.com:443 HTTP/1.1\r\nHost: pypi.org:443\r\n\r\n",
     "REJECTED evil.com:443 not on the allowlist"),
    ("malformed_empty_line", b"\r\n\r\n", "REJECTED malformed"),
    ("malformed_bare_connect", b"CONNECT\r\n\r\n", "REJECTED malformed CONNECT"),
    ("malformed_single_token", b"HELLO\r\n\r\n", "REJECTED malformed HELLO"),
    ("malformed_long_token_truncated", b"A" * 200 + b"\r\n\r\n", "REJECTED malformed " + "A" * 80),
    ("malformed_oversized_head", b"B" * 40000, "REJECTED malformed " + "B" * 80),
    ("origin_form_get", b"GET /index.html HTTP/1.1\r\nHost: evil.com\r\n\r\n",
     "REJECTED /index.html plain HTTP GET without a host"),
    ("origin_form_post", b"POST /upload HTTP/1.1\r\nContent-Length: 0\r\n\r\n",
     "REJECTED /upload plain HTTP POST without a host"),
    ("origin_form_lowercase_method", b"get /x HTTP/1.1\r\n\r\n",
     "REJECTED /x plain HTTP GET without a host"),
    ("origin_form_asterisk", b"OPTIONS * HTTP/1.1\r\n\r\n",
     "REJECTED * plain HTTP OPTIONS without a host"),
    ("authority_form_get", b"GET evil.com:80 HTTP/1.1\r\n\r\n",
     "REJECTED evil.com:80 plain HTTP GET without a host"),
    ("origin_form_host_header_not_trusted", b"GET /simple/ HTTP/1.1\r\nHost: pypi.org\r\n\r\n",
     "REJECTED /simple/ plain HTTP GET without a host"),
    ("absolute_http", b"GET http://evil.com/ HTTP/1.1\r\n\r\n",
     "REJECTED evil.com:80 not on the allowlist"),
    ("absolute_with_port", b"GET http://evil.com:8080/x HTTP/1.1\r\n\r\n",
     "REJECTED evil.com:8080 not on the allowlist"),
    ("absolute_https_scheme", b"GET https://evil.com/ HTTP/1.1\r\n\r\n",
     "REJECTED evil.com:80 not on the allowlist"),
    ("absolute_ipv6_with_port", b"GET http://[::1]:8080/ HTTP/1.1\r\n\r\n",
     "REJECTED ::1:8080 not on the allowlist"),
    ("absolute_ipv6_without_port", b"GET http://[::1]/ HTTP/1.1\r\n\r\n",
     "REJECTED ::1:80 not on the allowlist"),
    ("absolute_non_numeric_port", b"GET http://evil.com:abc/ HTTP/1.1\r\n\r\n",
     "REJECTED evil.com:abc:80 not on the allowlist"),
    ("absolute_userinfo_trick", b"GET http://pypi.org@evil.com/ HTTP/1.1\r\n\r\n",
     "REJECTED pypi.org@evil.com:80 not on the allowlist"),
    ("absolute_lookalike", b"GET http://pypi.org.evil.com/simple/ HTTP/1.1\r\n\r\n",
     "REJECTED pypi.org.evil.com:80 not on the allowlist"),
    ("absolute_without_path", b"GET http://evil.com HTTP/1.1\r\n\r\n",
     "REJECTED evil.com:80 not on the allowlist"),
    ("absolute_post_with_body", b"POST http://evil.com/up HTTP/1.1\r\nContent-Length: 4\r\n\r\ndata",
     "REJECTED evil.com:80 not on the allowlist"),
    ("absolute_health_is_not_served", b"GET http://127.0.0.1:1/__elm_pi_egress__/health HTTP/1.1\r\n\r\n",
     "REJECTED 127.0.0.1:1 not on the allowlist"),
    ("health_by_post", b"POST /__elm_pi_egress__/health HTTP/1.1\r\n\r\n",
     "REJECTED /__elm_pi_egress__/health plain HTTP POST without a host"),
    ("health_by_head", b"HEAD /__elm_pi_egress__/health HTTP/1.1\r\n\r\n",
     "REJECTED /__elm_pi_egress__/health plain HTTP HEAD without a host"),
    ("health_trailing_slash", b"GET /__elm_pi_egress__/health/ HTTP/1.1\r\n\r\n",
     "REJECTED /__elm_pi_egress__/health/ plain HTTP GET without a host"),
    ("health_longer_name", b"GET /__elm_pi_egress__/healthz HTTP/1.1\r\n\r\n",
     "REJECTED /__elm_pi_egress__/healthz plain HTTP GET without a host"),
    ("health_path_is_case_sensitive", b"GET /__ELM_PI_EGRESS__/health HTTP/1.1\r\n\r\n",
     "REJECTED /__ELM_PI_EGRESS__/health plain HTTP GET without a host"),
]


def _refusal_case(request, expected):
    def test(self):
        proxy = proxy_for(SHIPPED)
        status = split_response(exchange(proxy, request))[0]
        self.assertEqual("HTTP/1.1 403 Forbidden", status)
        self.assertEqual([expected], log_lines(proxy))
    return test


for _name, _req, _expected in REFUSALS:
    add_test(RequestLineTests, "refuses_" + _name, _refusal_case(_req, _expected))


HEALTH_REQUESTS = [
    ("health", b"GET /__elm_pi_egress__/health HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"),
    ("health_with_query", b"GET /__elm_pi_egress__/health?t=1 HTTP/1.1\r\n\r\n"),
    ("health_lowercase_method", b"get /__elm_pi_egress__/health HTTP/1.1\r\n\r\n"),
    ("health_http10", b"GET /__elm_pi_egress__/health HTTP/1.0\r\n\r\n"),
    ("health_without_version", b"GET /__elm_pi_egress__/health\r\n\r\n"),
]


def _health_case(request):
    def test(self):
        proxy = proxy_for(SHIPPED)
        status, _, body = split_response(exchange(proxy, request))
        self.assertEqual("HTTP/1.1 200 OK", status)
        self.assertEqual("elm-pi-egress", json.loads(body)["proxy"])
        self.assertEqual([], log_lines(proxy))   # a heartbeat a second must not fill the log
    return test


for _name, _req in HEALTH_REQUESTS:
    add_test(RequestLineTests, "answers_" + _name, _health_case(_req))


class RequestLineEdgeTests(unittest.TestCase):
    def test_client_that_sends_nothing_gets_nothing_and_no_log(self):
        proxy = proxy_for(SHIPPED)
        self.assertEqual(b"", exchange(proxy, b""))
        self.assertEqual([], log_lines(proxy))

    def test_tls_hello_without_connect_is_refused(self):
        # a client that forgot it is talking to a proxy
        hello = b"\x16\x03\x01\x00\xa5\x01\x00\x00\xa1\x03\x03" + bytes(range(32, 96)) + b"\r\n\r\n"
        proxy = proxy_for(SHIPPED)
        self.assertTrue(exchange(proxy, hello).startswith(b"HTTP/1.1 403 "))
        self.assertTrue(log_lines(proxy)[0].startswith("REJECTED "))

    def test_head_sent_one_byte_at_a_time(self):
        proxy = proxy_for(SHIPPED)
        client, thread = start_handle(proxy)
        for b in b"CONNECT evil.com:443 HTTP/1.1\r\n\r\n":
            client.send(bytes([b]))
        reply = recv_all(client)
        client.close()
        thread.join(5)
        self.assertTrue(reply.startswith(b"HTTP/1.1 403 Forbidden\r\n"))
        self.assertEqual(["REJECTED evil.com:443 not on the allowlist"], log_lines(proxy))

    def test_refusal_without_half_close(self):
        # a complete head is enough; the proxy must not wait for EOF to answer
        proxy = proxy_for(SHIPPED)
        reply = exchange(proxy, b"CONNECT evil.com:443 HTTP/1.1\r\n\r\n", shut=False)
        self.assertTrue(reply.startswith(b"HTTP/1.1 403 Forbidden\r\n"))

    def test_bytes_pipelined_after_a_refused_connect_are_not_sent_anywhere(self):
        proxy = proxy_for(SHIPPED)
        reply = exchange(proxy, b"CONNECT evil.com:443 HTTP/1.1\r\n\r\n\x16\x03\x01secret")
        self.assertNotIn(b"secret", reply)
        self.assertNotIn("secret", Path(proxy.log_path).read_text())

    def test_latin1_method_survives_into_the_reason(self):
        proxy = proxy_for(SHIPPED)
        _, headers, _ = split_response(exchange(proxy, "G\xc9T /x HTTP/1.1\r\n\r\n".encode("latin-1")))
        self.assertEqual("plain HTTP G\xc9T without a host", headers["x-elm-pi-reason"])


# == the refusal itself ===========================================================

class RefusalResponseTests(unittest.TestCase):
    """The 403 for `CONNECT example.com:443`: every header that says whose
    refusal it is, and a body that says the same."""

    @classmethod
    def setUpClass(cls):
        raw = exchange(proxy_for(SHIPPED), b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
        cls.status, cls.headers, cls.body = split_response(raw)
        cls.text = cls.body.decode()

    def test_status_line(self):
        self.assertEqual("HTTP/1.1 403 Forbidden", self.status)

    def test_content_type(self):
        self.assertEqual("text/plain", self.headers["content-type"])

    def test_proxy_agent_names_us(self):
        self.assertEqual("elm-pi-egress", self.headers["proxy-agent"])

    def test_egress_header_says_refused(self):
        self.assertEqual("refused", self.headers["x-elm-pi-egress"])

    def test_reason_header(self):
        self.assertEqual("not on the allowlist", self.headers["x-elm-pi-reason"])

    def test_remedy_header(self):
        self.assertEqual("start the session with `pi --remote`", self.headers["x-elm-pi-remedy"])

    def test_content_length_is_the_body(self):
        self.assertEqual(len(self.body), int(self.headers["content-length"]))

    def test_connection_close(self):
        self.assertEqual("close", self.headers["connection"])

    def test_body_says_it_is_not_the_host(self):
        self.assertEqual("Refused by this pi install's egress proxy, not by the host.",
                         self.text.splitlines()[0])

    def test_body_names_target_and_reason(self):
        self.assertEqual("example.com:443: not on the allowlist.", self.text.splitlines()[1])

    def test_body_points_at_the_log(self):
        self.assertIn("agent/egress.log", self.text)

    def test_body_points_at_lockdown_md(self):
        self.assertIn("LOCKDOWN.md", self.text)

    def test_no_header_carries_the_body_text(self):
        # the reason is short enough for `curl -I`; the explanation stays in the body
        self.assertFalse(any("Refused by" in v for v in self.headers.values()))


class RefusalReasonTests(unittest.TestCase):
    """X-Elm-Pi-Reason for each kind of refusal."""

    def reason(self, request):
        return split_response(exchange(proxy_for(SHIPPED), request))[1]["x-elm-pi-reason"]

    def test_reason_for_origin_form(self):
        self.assertEqual("plain HTTP DELETE without a host", self.reason(b"DELETE /x HTTP/1.1\r\n\r\n"))

    def test_reason_for_malformed_is_the_line(self):
        self.assertEqual("NONSENSE", self.reason(b"NONSENSE\r\n\r\n"))

    def test_reason_for_empty_line_is_empty(self):
        self.assertEqual("", self.reason(b"\r\n\r\n"))

    def test_reason_for_plain_http_unlisted(self):
        self.assertEqual("not on the allowlist", self.reason(b"GET http://evil.com/ HTTP/1.1\r\n\r\n"))

    def test_body_for_malformed_names_it(self):
        body = split_response(exchange(proxy_for(SHIPPED), b"NONSENSE\r\n\r\n"))[2].decode()
        self.assertEqual("malformed: NONSENSE.", body.splitlines()[1])


class HealthResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proxy = proxy_for(["Elm.Edina.ac.uk", ".pypi.org"])
        cls.proxy.port = 43210
        raw = exchange(cls.proxy, b"GET /__elm_pi_egress__/health HTTP/1.0\r\n\r\n")
        cls.status, cls.headers, cls.body = split_response(raw)
        cls.data = json.loads(cls.body)

    def test_content_type_is_json(self):
        self.assertEqual("application/json", self.headers["content-type"])

    def test_content_length_is_the_body(self):
        self.assertEqual(len(self.body), int(self.headers["content-length"]))

    def test_connection_close(self):
        self.assertEqual("close", self.headers["connection"])

    def test_reports_its_pid(self):
        self.assertEqual(os.getpid(), self.data["pid"])

    def test_reports_its_port(self):
        self.assertEqual(43210, self.data["port"])

    def test_reports_the_normalised_allowlist(self):
        self.assertEqual(["elm.edina.ac.uk", "pypi.org"], self.data["allow"])

    def test_reports_no_upstream(self):
        self.assertIs(False, self.data["upstream"])

    def test_reports_an_upstream_without_naming_it(self):
        raw = exchange(proxy_for([], ("campus.example", 3128)),
                       b"GET /__elm_pi_egress__/health HTTP/1.0\r\n\r\n")
        body = split_response(raw)[2]
        self.assertIs(True, json.loads(body)["upstream"])
        self.assertNotIn(b"campus.example", body)

    def test_exact_key_set(self):
        self.assertEqual({"proxy", "pid", "port", "allow", "upstream"}, set(self.data))


# == allowed traffic, against loopback servers ====================================

class TunnelTests(unittest.TestCase):
    """CONNECT to an allowed host: a local echo server on 127.0.0.1, listed."""

    @classmethod
    def setUpClass(cls):
        cls.echo = Echo()
        cls.target = b"127.0.0.1:%d" % cls.echo.port

    @classmethod
    def tearDownClass(cls):
        cls.echo.close()

    def open_tunnel(self, proxy=None, extra=b""):
        proxy = proxy or proxy_for(["127.0.0.1"])
        client, thread = start_handle(proxy)
        client.sendall(b"CONNECT " + self.target + b" HTTP/1.1\r\n\r\n" + extra)
        return proxy, client, thread

    ESTABLISHED = b"HTTP/1.1 200 Connection Established\r\n\r\n"

    def test_answers_connection_established(self):
        _, client, thread = self.open_tunnel()
        self.assertEqual(self.ESTABLISHED, recv_exactly(client, len(self.ESTABLISHED)))
        client.close()
        thread.join(5)

    def test_bytes_flow_both_ways(self):
        _, client, thread = self.open_tunnel()
        recv_exactly(client, len(self.ESTABLISHED))
        client.sendall(b"ping")
        self.assertEqual(b"ping", recv_exactly(client, 4))
        client.close()
        thread.join(5)

    def test_bytes_pipelined_behind_connect_reach_the_destination(self):
        # the ClientHello-in-the-same-packet case the docstring describes
        _, client, thread = self.open_tunnel(extra=b"\x16\x03\x01early")
        got = recv_exactly(client, len(self.ESTABLISHED) + 8)
        self.assertEqual(self.ESTABLISHED + b"\x16\x03\x01early", got)
        client.close()
        thread.join(5)

    def test_every_byte_value_passes_unchanged(self):
        _, client, thread = self.open_tunnel()
        recv_exactly(client, len(self.ESTABLISHED))
        payload = bytes(range(256)) * 4
        client.sendall(payload)
        self.assertEqual(payload, recv_exactly(client, len(payload)))
        client.close()
        thread.join(5)

    def test_a_megabyte_round_trips(self):
        _, client, thread = self.open_tunnel()
        recv_exactly(client, len(self.ESTABLISHED))
        payload = os.urandom(1 << 20)
        sender = threading.Thread(target=client.sendall, args=(payload,))
        sender.start()
        got = recv_exactly(client, len(payload), timeout=20)
        sender.join(20)
        self.assertEqual(payload, got)
        client.close()
        thread.join(5)

    def test_closing_the_client_ends_the_tunnel(self):
        _, client, thread = self.open_tunnel()
        recv_exactly(client, len(self.ESTABLISHED))
        client.close()
        thread.join(5)
        self.assertFalse(thread.is_alive())

    def test_an_allowed_tunnel_is_not_logged(self):
        proxy, client, thread = self.open_tunnel()
        recv_exactly(client, len(self.ESTABLISHED))
        client.close()
        thread.join(5)
        self.assertEqual([], log_lines(proxy))

    def test_destination_that_speaks_first(self):
        greeter = Echo(greeting=b"220 hello\r\n")
        self.addCleanup(greeter.close)
        client, thread = start_handle(proxy_for(["127.0.0.1"]))
        client.sendall(b"CONNECT 127.0.0.1:%d HTTP/1.1\r\n\r\n" % greeter.port)
        self.assertEqual(self.ESTABLISHED + b"220 hello\r\n",
                         recv_exactly(client, len(self.ESTABLISHED) + 11))
        client.close()
        thread.join(5)

    def test_unreachable_destination_is_logged_as_failed(self):
        port = free_port()
        proxy = proxy_for(["127.0.0.1"])
        reply = exchange(proxy, b"CONNECT 127.0.0.1:%d HTTP/1.1\r\n\r\n" % port)
        self.assertEqual(b"", reply)       # no 200, and no 403 that blames the policy
        [line] = log_lines(proxy)
        self.assertTrue(line.startswith("FAILED   127.0.0.1:%d " % port), line)
        self.assertIn("refused", line.lower())

    def test_non_numeric_port_on_an_allowed_host_fails_without_dialling(self):
        proxy = proxy_for(["127.0.0.1"])
        self.assertEqual(b"", exchange(proxy, b"CONNECT 127.0.0.1:https HTTP/1.1\r\n\r\n"))
        [line] = log_lines(proxy)
        self.assertTrue(line.startswith("FAILED   127.0.0.1:https unexpected ValueError("), line)


class OpenModeTests(unittest.TestCase):
    """--allow '*': nothing is gated, every new destination is recorded once."""

    @classmethod
    def setUpClass(cls):
        cls.echo = Echo()
        cls.origin = Origin()

    @classmethod
    def tearDownClass(cls):
        cls.echo.close()
        cls.origin.close()

    def tunnel(self, proxy, host="127.0.0.1"):
        client, thread = start_handle(proxy)
        client.sendall(b"CONNECT %s:%d HTTP/1.1\r\n\r\n" % (host.encode(), self.echo.port))
        head = recv_exactly(client, len(TunnelTests.ESTABLISHED))
        client.close()
        thread.join(5)
        return head

    def test_any_host_is_tunnelled(self):
        self.assertEqual(TunnelTests.ESTABLISHED, self.tunnel(proxy_for(["*"])))

    def test_first_contact_is_recorded(self):
        proxy = proxy_for(["*"])
        self.tunnel(proxy)
        self.assertEqual(["OPEN     127.0.0.1 no allowlist in this install (--allow '*')"],
                         log_lines(proxy))

    def test_repeat_contact_is_not_recorded_again(self):
        proxy = proxy_for(["*"])
        self.tunnel(proxy)
        self.tunnel(proxy)
        self.assertEqual(1, len(log_lines(proxy)))

    def test_plain_http_is_forwarded_and_recorded(self):
        proxy = proxy_for(["*"])
        reply = exchange(proxy, b"GET http://127.0.0.1:%d/x HTTP/1.1\r\n\r\n" % self.origin.port, shut=False)
        self.assertEqual(Origin.RESPONSE, reply)
        self.assertEqual("OPEN     127.0.0.1 no allowlist in this install (--allow '*')",
                         log_lines(proxy)[0])

    def test_failure_is_failed_not_rejected(self):
        proxy = proxy_for(["*"])
        exchange(proxy, b"CONNECT 127.0.0.1:%d HTTP/1.1\r\n\r\n" % free_port())
        verdicts = [l.split()[0] for l in log_lines(proxy)]
        self.assertEqual(["OPEN", "FAILED"], verdicts)

    def test_malformed_is_still_refused(self):
        proxy = proxy_for(["*"])
        self.assertTrue(exchange(proxy, b"HELLO\r\n\r\n").startswith(b"HTTP/1.1 403 "))
        self.assertEqual(["REJECTED malformed HELLO"], log_lines(proxy))

    def test_origin_form_is_still_refused(self):
        # open mode removes the gate, not the need for a host to dial
        proxy = proxy_for(["*"])
        self.assertTrue(exchange(proxy, b"GET / HTTP/1.1\r\n\r\n").startswith(b"HTTP/1.1 403 "))

    def test_health_still_answered_locally(self):
        proxy = proxy_for(["*"])
        reply = exchange(proxy, b"GET /__elm_pi_egress__/health HTTP/1.0\r\n\r\n")
        self.assertEqual(["*"], json.loads(split_response(reply)[2])["allow"])
        self.assertEqual([], log_lines(proxy))


class PlainForwardTests(unittest.TestCase):
    """Plain HTTP to an allowed host: rewritten to origin-form, headers kept."""

    def setUp(self):
        self.origin = Origin()
        self.addCleanup(self.origin.close)
        self.proxy = proxy_for(["127.0.0.1"])
        self.base = b"http://127.0.0.1:%d" % self.origin.port

    def send(self, request):
        reply = exchange(self.proxy, request, shut=False)
        return reply, self.origin.wait()

    def test_request_line_becomes_origin_form(self):
        _, seen = self.send(b"GET " + self.base + b"/a/b?c=1 HTTP/1.1\r\nHost: x\r\n\r\n")
        self.assertEqual(b"GET /a/b?c=1 HTTP/1.1", seen.split(b"\r\n")[0])

    def test_headers_pass_verbatim(self):
        _, seen = self.send(b"GET " + self.base + b"/ HTTP/1.1\r\nHost: x\r\nX-Odd:  keep  me \r\n\r\n")
        self.assertEqual(b"Host: x\r\nX-Odd:  keep  me \r\n\r\n", seen.split(b"\r\n", 1)[1])

    def test_missing_path_becomes_slash(self):
        _, seen = self.send(b"GET " + self.base + b" HTTP/1.1\r\n\r\n")
        self.assertEqual(b"GET / HTTP/1.1", seen.split(b"\r\n")[0])

    def test_http_version_is_kept(self):
        _, seen = self.send(b"GET " + self.base + b"/v HTTP/1.0\r\n\r\n")
        self.assertEqual(b"GET /v HTTP/1.0", seen.split(b"\r\n")[0])

    def test_method_is_uppercased(self):
        _, seen = self.send(b"delete " + self.base + b"/d HTTP/1.1\r\n\r\n")
        self.assertEqual(b"DELETE /d HTTP/1.1", seen.split(b"\r\n")[0])

    def test_pipelined_body_is_forwarded(self):
        _, seen = self.send(b"POST " + self.base + b"/p HTTP/1.1\r\nContent-Length: 5\r\n\r\nhello")
        self.assertTrue(seen.endswith(b"\r\n\r\nhello"), seen)

    def test_origin_reply_reaches_the_client_verbatim(self):
        reply, _ = self.send(b"GET " + self.base + b"/ HTTP/1.1\r\n\r\n")
        self.assertEqual(Origin.RESPONSE, reply)

    def test_allowed_plain_request_is_not_logged(self):
        self.send(b"GET " + self.base + b"/ HTTP/1.1\r\n\r\n")
        self.assertEqual([], log_lines(self.proxy))

    # A client that half-closes after sending its request (nc -N,
    # shutdown(SHUT_WR)) still gets the response: EOF is passed on, not fatal.
    def test_half_closed_client_still_gets_the_response(self):
        reply = exchange(self.proxy, b"GET " + self.base + b"/ HTTP/1.1\r\n\r\n", shut=True)
        self.assertEqual(Origin.RESPONSE, reply)

    # The authority ends at "?" as well as "/": "http://host:port?q" is host:port.
    def test_query_without_path_is_forwarded(self):
        _, seen = self.send(b"GET " + self.base + b"?q=1 HTTP/1.1\r\n\r\n")
        self.assertEqual(b"GET /?q=1 HTTP/1.1", (seen or b"").split(b"\r\n")[0])


class UpstreamTests(unittest.TestCase):
    """A campus proxy in the environment is chained to. The upstream here is a
    loopback fake, so allowlisted names are never resolved or dialled."""

    def chain(self, upstream):
        self.addCleanup(upstream.close)
        return proxy_for(SHIPPED, ("127.0.0.1", upstream.port))

    def test_connect_head_is_passed_on_verbatim(self):
        up = Upstream()
        head = b"CONNECT pypi.org:443 HTTP/1.1\r\nHost: pypi.org:443\r\nUser-Agent: pip\r\n\r\n"
        exchange(self.chain(up), head)
        self.assertEqual(head, up.wait())

    def test_upstream_reply_is_relayed_not_replaced(self):
        reply = b"HTTP/1.1 200 Connection established\r\nVia: 1.1 campus\r\n\r\n"
        up = Upstream(reply=(reply,))
        got = exchange(self.chain(up), b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n")
        self.assertEqual(reply, got)

    def test_tunnel_through_upstream(self):
        up = Upstream()
        client, thread = start_handle(self.chain(up))
        client.sendall(b"CONNECT files.pythonhosted.org:443 HTTP/1.1\r\n\r\n")
        recv_exactly(client, len(up.reply[0]))
        client.sendall(b"PING")
        self.assertEqual(b"PING", recv_exactly(client, 4))
        client.close()
        thread.join(5)

    def test_pipelined_bytes_go_to_upstream(self):
        up = Upstream()
        head = b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n"
        client, thread = start_handle(self.chain(up))
        client.sendall(head + b"\x16\x03\x01hello")
        recv_exactly(client, len(up.reply[0]) + 8)
        client.close()
        thread.join(5)
        self.assertEqual(head + b"\x16\x03\x01hello", up.wait())

    def test_refusal_is_relayed_and_tunnel_not_opened(self):
        reply = b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n"
        up = Upstream(reply=(reply,))
        client, thread = start_handle(self.chain(up))
        client.sendall(b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n")
        self.assertEqual(reply, recv_exactly(client, len(reply)))
        try:
            client.sendall(b"PING")
        except OSError:
            pass
        self.assertEqual(b"", recv_all(client, timeout=3))
        client.close()
        thread.join(5)

    def test_reply_split_across_packets_is_read_whole(self):
        up = Upstream(reply=(b"HTTP/1.1 2", b"00 OK\r\n", b"\r\n"))
        client, thread = start_handle(self.chain(up))
        client.sendall(b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n")
        self.assertEqual(b"HTTP/1.1 200 OK\r\n\r\n", recv_exactly(client, 19))
        client.sendall(b"PING")
        self.assertEqual(b"PING", recv_exactly(client, 4))
        client.close()
        thread.join(5)

    def test_upstream_that_hangs_up_gives_the_client_nothing(self):
        up = Upstream(reply=(), hang_up=True)
        self.assertEqual(b"", exchange(self.chain(up), b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n"))

    def test_unlisted_host_is_refused_before_upstream(self):
        up = Upstream()
        proxy = self.chain(up)
        reply = exchange(proxy, b"CONNECT evil.com:443 HTTP/1.1\r\n\r\n")
        self.assertTrue(reply.startswith(b"HTTP/1.1 403 Forbidden"))
        self.assertEqual(0, up.accepted)

    def test_unlisted_plain_http_is_refused_before_upstream(self):
        up = Upstream()
        reply = exchange(self.chain(up), b"GET http://evil.com/ HTTP/1.1\r\n\r\n")
        self.assertTrue(reply.startswith(b"HTTP/1.1 403 Forbidden"))
        self.assertEqual(0, up.accepted)

    def test_plain_http_goes_to_upstream_in_absolute_form(self):
        up = Upstream(reply=(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n",), hang_up=True)
        head = b"GET http://pypi.org/simple/ HTTP/1.1\r\nHost: pypi.org\r\n\r\n"
        exchange(self.chain(up), head)
        self.assertEqual(head, up.wait())

    def test_unreachable_upstream_is_logged(self):
        proxy = proxy_for(SHIPPED, ("127.0.0.1", free_port()))
        self.assertEqual(b"", exchange(proxy, b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n"))
        [line] = log_lines(proxy)
        self.assertTrue(line.startswith("FAILED   pypi.org:443 "), line)

    # The status code decides, not "200" anywhere in the line.
    def test_status_code_not_reason_phrase_decides(self):
        reply = b"HTTP/1.1 403 Blocked 200 times\r\n\r\n"
        up = Upstream(reply=(reply,))
        client, thread = start_handle(self.chain(up))
        client.sendall(b"CONNECT pypi.org:443 HTTP/1.1\r\n\r\n")
        recv_exactly(client, len(reply))
        try:
            client.sendall(b"PING")
        except OSError:
            pass
        leaked = recv_all(client, timeout=2)
        client.close()
        thread.join(5)
        self.assertEqual(b"", leaked)


# == reading heads ================================================================

class ReadHeadTests(unittest.TestCase):
    def setUp(self):
        self.proxy = proxy_for([])
        self.ours, self.theirs = socket.socketpair()
        self.theirs.settimeout(5)
        self.addCleanup(self.ours.close)
        self.addCleanup(self.theirs.close)

    def test_head_and_leftover_are_split(self):
        self.ours.sendall(b"CONNECT a:1 HTTP/1.1\r\nX: y\r\n\r\nTLS")
        self.assertEqual(("CONNECT a:1 HTTP/1.1\r\nX: y\r\n\r\n", b"TLS"), self.proxy.read_head(self.theirs))

    def test_head_across_several_sends(self):
        def feed():
            for part in (b"CONNECT a", b":1 HTTP/1.1\r\n", b"\r\n"):
                self.ours.sendall(part)
                time.sleep(0.02)
        t = threading.Thread(target=feed)
        t.start()
        head, rest = self.proxy.read_head(self.theirs)
        t.join()
        self.assertEqual(("CONNECT a:1 HTTP/1.1\r\n\r\n", b""), (head, rest))

    def test_eof_before_terminator_returns_what_came(self):
        self.ours.sendall(b"CONNECT a:1 HTTP/1.1\r\n")
        self.ours.shutdown(socket.SHUT_WR)
        self.assertEqual(("CONNECT a:1 HTTP/1.1\r\n", b""), self.proxy.read_head(self.theirs))

    def test_immediate_eof(self):
        self.ours.shutdown(socket.SHUT_WR)
        self.assertEqual(("", b""), self.proxy.read_head(self.theirs))

    def test_stops_reading_at_32k_without_a_terminator(self):
        # the socket stays open: a head that never ends must not hang the thread
        threading.Thread(target=self.ours.sendall, args=(b"x" * 40000,), daemon=True).start()
        head, rest = self.proxy.read_head(self.theirs)
        self.assertGreaterEqual(len(head), 32768)
        self.assertEqual(b"", rest)

    def test_high_bytes_decode_as_latin1(self):
        self.ours.sendall(b"GET /caf\xe9 HTTP/1.1\r\n\r\n")
        self.assertEqual("GET /caf\u00e9 HTTP/1.1\r\n\r\n", self.proxy.read_head(self.theirs)[0])

    def test_upstream_reply_keeps_bytes_after_the_head(self):
        self.ours.sendall(b"HTTP/1.1 200 OK\r\n\r\nearly")
        self.assertEqual(b"HTTP/1.1 200 OK\r\n\r\nearly", self.proxy.read_upstream_reply(self.theirs))

    def test_upstream_reply_assembled_from_fragments(self):
        def feed():
            for part in (b"HTTP/1.1 ", b"200 OK\r\n", b"\r\n"):
                self.ours.sendall(part)
                time.sleep(0.02)
        t = threading.Thread(target=feed)
        t.start()
        got = self.proxy.read_upstream_reply(self.theirs)
        t.join()
        self.assertEqual(b"HTTP/1.1 200 OK\r\n\r\n", got)


# == upstream parsing =============================================================

class ParseUpstreamTests(unittest.TestCase):
    """parse_upstream turns HTTPS_PROXY into the (host, port) to dial."""


UPSTREAMS = [
    ("empty_is_none", "", None),
    ("none_is_none", None, None),
    ("scheme_host_port", "http://proxy.ed.ac.uk:3128", ("proxy.ed.ac.uk", 3128)),
    ("trailing_slash", "http://proxy.ed.ac.uk:8080/", ("proxy.ed.ac.uk", 8080)),
    ("several_trailing_slashes", "http://proxy:8080//", ("proxy", 8080)),
    ("no_scheme", "proxy:8080", ("proxy", 8080)),
    ("bare_host_defaults_3128", "proxy", ("proxy", 3128)),
    ("scheme_without_port_defaults_3128", "http://proxy", ("proxy", 3128)),
    ("credentials_dropped", "http://user:pass@proxy:3128", ("proxy", 3128)),
    ("at_sign_in_password", "http://us@er:p@ss@proxy:3129", ("proxy", 3129)),
    ("https_scheme", "https://proxy:443", ("proxy", 443)),
    ("other_scheme", "socks5://h:1080", ("h", 1080)),
    ("case_preserved", "HTTP://Proxy.Example:3128", ("Proxy.Example", 3128)),
    ("ipv4_host", "http://10.0.0.1:3128", ("10.0.0.1", 3128)),
]


def _upstream_case(value, expected):
    def test(self):
        self.assertEqual(expected, egress.parse_upstream(value))
    return test


for _name, _value, _expected in UPSTREAMS:
    add_test(ParseUpstreamTests, _name, _upstream_case(_value, _expected))

# create_connection() needs an IPv6 upstream without its brackets.
add_test(ParseUpstreamTests, "ipv6_brackets_are_removed",
         _upstream_case("http://[fd00::1]:3128", ("fd00::1", 3128)))
# A bracketed IPv6 upstream without a port takes the default, rather than
# failing to start the proxy, and with it pi.
add_test(ParseUpstreamTests, "ipv6_without_port_defaults_3128",
         _upstream_case("http://[fd00::1]", ("fd00::1", 3128)))


class ParseUpstreamErrorTests(unittest.TestCase):
    def test_non_numeric_port_raises(self):
        with self.assertRaises(ValueError):
            egress.parse_upstream("http://proxy:abc")


# == main(): arguments ============================================================

class MainArgumentTests(unittest.TestCase):
    """main() with serve() replaced: what the command line turns into."""

    def run_main(self, *argv):
        seen = {}

        def fake_serve(proxy, port_file, parent_pid, want_port=0):
            seen.update(proxy=proxy, port_file=port_file, parent_pid=parent_pid, want_port=want_port)

        with mock.patch.object(egress.Proxy, "serve", fake_serve), \
                mock.patch.object(sys, "argv", ["egress.py", *argv]):
            seen["rc"] = egress.main()
        return seen

    BASE = ("--port-file", "/nonexistent/p", "--log", "/nonexistent/l")

    def allow_of(self, *allow_args):
        return self.run_main(*allow_args, *self.BASE)["proxy"].allow

    def test_repeated_allow_flags_accumulate(self):
        self.assertEqual(["a.example", "b.example"], self.allow_of("--allow", "a.example", "--allow", "b.example"))

    def test_comma_separated_allow(self):
        self.assertEqual(["a.example", "b.example"], self.allow_of("--allow", "a.example,b.example"))

    def test_spaces_and_empty_items_are_dropped(self):
        self.assertEqual(["a.example", "b.example"], self.allow_of("--allow", " a.example , , b.example ,"))

    def test_allow_is_normalised(self):
        self.assertEqual(["pypi.org", "elm.edina.ac.uk"], self.allow_of("--allow", ".PyPI.org,ELM.edina.ac.uk"))

    def test_empty_allow_denies_everything(self):
        proxy = self.run_main("--allow", "", *self.BASE)["proxy"]
        self.assertEqual([], proxy.allow)
        self.assertFalse(proxy.allowed(ELM_HOST))

    def test_padded_star_is_open_mode(self):
        self.assertTrue(self.run_main("--allow", " * ", *self.BASE)["proxy"].open_mode)

    def test_star_after_hosts_is_open_mode(self):
        # what `ELM_PI_PROXY_ALLOW=api.exa.ai pi --remote` produces
        self.assertTrue(self.run_main("--allow", "api.exa.ai,*", *self.BASE)["proxy"].open_mode)

    def test_log_path_passed_through(self):
        self.assertEqual("/nonexistent/l", self.run_main("--allow", "a", *self.BASE)["proxy"].log_path)

    def test_port_file_passed_through(self):
        self.assertEqual("/nonexistent/p", self.run_main("--allow", "a", *self.BASE)["port_file"])

    def test_parent_pid_defaults_to_zero(self):
        self.assertEqual(0, self.run_main("--allow", "a", *self.BASE)["parent_pid"])

    def test_parent_pid_passed_through(self):
        self.assertEqual(4242, self.run_main("--allow", "a", "--parent-pid", "4242", *self.BASE)["parent_pid"])

    def test_port_defaults_to_ephemeral(self):
        self.assertEqual(0, self.run_main("--allow", "a", *self.BASE)["want_port"])

    def test_port_passed_through(self):
        self.assertEqual(51234, self.run_main("--allow", "a", "--port", "51234", *self.BASE)["want_port"])

    def test_no_upstream_by_default(self):
        self.assertIsNone(self.run_main("--allow", "a", *self.BASE)["proxy"].upstream)

    def test_empty_upstream_is_none(self):
        self.assertIsNone(self.run_main("--allow", "a", "--upstream", "", *self.BASE)["proxy"].upstream)

    def test_upstream_is_parsed(self):
        seen = self.run_main("--allow", "a", "--upstream", "http://u:p@campus:8080/", *self.BASE)
        self.assertEqual(("campus", 8080), seen["proxy"].upstream)

    def test_returns_zero(self):
        self.assertEqual(0, self.run_main("--allow", "a", *self.BASE)["rc"])

    def test_keyboard_interrupt_is_a_clean_exit(self):
        with mock.patch.object(egress.Proxy, "serve", side_effect=KeyboardInterrupt), \
                mock.patch.object(sys, "argv", ["egress.py", "--allow", "a", *self.BASE]):
            self.assertEqual(0, egress.main())


ARG_ERRORS = [
    ("missing_allow", ("--port-file", "p", "--log", "l")),
    ("missing_port_file", ("--allow", "a", "--log", "l")),
    ("missing_log", ("--allow", "a", "--port-file", "p")),
    ("non_numeric_parent_pid", ("--allow", "a", "--port-file", "p", "--log", "l", "--parent-pid", "me")),
    ("non_numeric_port", ("--allow", "a", "--port-file", "p", "--log", "l", "--port", "http")),
    ("unknown_flag", ("--allow", "a", "--port-file", "p", "--log", "l", "--open")),
]


def _arg_error_case(argv):
    def test(self):
        served = []
        with mock.patch.object(egress.Proxy, "serve", lambda *a, **k: served.append(a)), \
                mock.patch.object(sys, "argv", ["egress.py", *argv]), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                egress.main()
        self.assertEqual(2, caught.exception.code)
        self.assertEqual([], served)      # no proxy, so the launcher refuses to start pi
    return test


for _name, _argv in ARG_ERRORS:
    add_test(MainArgumentTests, "exits_2_on_" + _name, _arg_error_case(_argv))


# == stale port files =============================================================

class PrunePortFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(dir=TMP))
        self.own = str(self.dir / ("elm-pi-egress-%d.port" % os.getpid()))

    def port_file(self, owner, content, age=0):
        path = self.dir / ("elm-pi-egress-%s.port" % owner)
        path.write_text(content)
        if age:
            t = time.time() - age
            os.utime(path, (t, t))
        return path

    def test_dead_owner_and_nothing_listening_is_removed(self):
        path = self.port_file(dead_pid(), str(free_port()))
        egress.prune_stale_port_files(self.own)
        self.assertFalse(path.exists())

    def test_dead_owner_but_port_still_served_is_kept(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        path = self.port_file(dead_pid(), str(listener.getsockname()[1]))
        egress.prune_stale_port_files(self.own)
        self.assertTrue(path.exists())

    def test_live_owner_is_kept(self):
        path = self.port_file(os.getppid(), str(free_port()))
        egress.prune_stale_port_files(self.own)
        self.assertTrue(path.exists())

    def test_older_than_a_day_is_removed_even_if_owner_lives(self):
        path = self.port_file(os.getppid(), "1", age=86400 + 60)
        egress.prune_stale_port_files(self.own)
        self.assertFalse(path.exists())

    def test_custom_max_age(self):
        path = self.port_file(os.getppid(), "1", age=120)
        egress.prune_stale_port_files(self.own, max_age_s=60)
        self.assertFalse(path.exists())

    def test_own_file_is_never_touched(self):
        Path(self.own).write_text("1")
        t = time.time() - 10 * 86400
        os.utime(self.own, (t, t))
        egress.prune_stale_port_files(self.own)
        self.assertTrue(Path(self.own).exists())

    def test_name_without_a_pid_is_kept(self):
        path = self.port_file("session", "1")
        egress.prune_stale_port_files(self.own)
        self.assertTrue(path.exists())

    def test_unreadable_port_is_kept(self):
        path = self.port_file(dead_pid(), "not-a-port")
        egress.prune_stale_port_files(self.own)
        self.assertTrue(path.exists())

    def test_other_files_are_untouched(self):
        other = self.dir / "other.port"
        other.write_text("1")
        t = time.time() - 10 * 86400
        os.utime(other, (t, t))
        egress.prune_stale_port_files(self.own)
        self.assertTrue(other.exists())

    def test_other_directories_are_untouched(self):
        elsewhere = Path(tempfile.mkdtemp(dir=TMP))
        path = elsewhere / ("elm-pi-egress-%d.port" % dead_pid())
        path.write_text(str(free_port()))
        egress.prune_stale_port_files(self.own)
        self.assertTrue(path.exists())

    def test_missing_directory_is_harmless(self):
        egress.prune_stale_port_files(str(self.dir / "gone" / "elm-pi-egress-1.port"))


# == sockets and limits ===========================================================

class SocketTuningTests(unittest.TestCase):
    def tuned(self):
        s = socket.socket()
        self.addCleanup(s.close)
        egress.tune_keepalive(s)
        return s

    def option(self, name):
        opt = getattr(socket, name, None)
        if opt is None:
            raise unittest.SkipTest("socket.%s is not on this platform" % name)
        return self.tuned().getsockopt(socket.IPPROTO_TCP, opt)

    def test_keepalive_is_on(self):
        self.assertNotEqual(0, self.tuned().getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE))

    def test_idle_before_probing(self):
        name = "TCP_KEEPALIVE" if hasattr(socket, "TCP_KEEPALIVE") else "TCP_KEEPIDLE"
        self.assertEqual(60, self.option(name))

    def test_probe_interval(self):
        self.assertEqual(15, self.option("TCP_KEEPINTVL"))

    def test_probe_count(self):
        self.assertEqual(4, self.option("TCP_KEEPCNT"))

    def test_closed_socket_is_harmless(self):
        s = socket.socket()
        s.close()
        self.assertIsNone(egress.tune_keepalive(s))

    def test_unix_socket_is_harmless(self):
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        egress.tune_keepalive(a)

    def test_fd_limit_is_never_lowered(self):
        import resource
        before = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        got = egress.raise_fd_limit()
        after = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        self.assertGreaterEqual(after, before)
        if got is not None:
            self.assertEqual(after, got)

    def test_descriptor_exhaustion_is_transient(self):
        # the accept loop used to end on EMFILE during a wide fan-out
        import errno
        self.assertIn(errno.EMFILE, egress.TRANSIENT_ACCEPT_ERRNOS)

    def test_a_closed_listener_is_not_transient(self):
        import errno
        self.assertNotIn(errno.EBADF, egress.TRANSIENT_ACCEPT_ERRNOS)


# == the process, as the launcher runs it =========================================

def start_proxy(args, cwd):
    return subprocess.Popen([sys.executable, "-E", "-S", str(EGRESS), *args],
                            cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def wait_for(predicate, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def tcp_exchange(port, request, timeout=5.0):
    with socket.create_connection(("127.0.0.1", port), timeout) as s:
        s.sendall(request)
        s.shutdown(socket.SHUT_WR)
        return recv_all(s, timeout)


class ServeProcessTests(unittest.TestCase):
    """One real proxy process, started the way the launcher starts it."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(dir=TMP))
        # left behind by a SIGKILLed session, and one whose session lives
        cls.stale = cls.dir / ("elm-pi-egress-%d.port" % dead_pid())
        cls.stale.write_text(str(free_port()))
        cls.alive = cls.dir / ("elm-pi-egress-%d.port" % os.getpid())
        cls.alive.write_text("1")
        cls.port_file = cls.dir / "elm-pi-egress-own.port"
        cls.log = cls.dir / "egress.log"
        cls.proc = start_proxy(["--allow", "Localhost, 127.0.0.1", "--allow", ".PyPI.org",
                                "--port-file", str(cls.port_file), "--log", str(cls.log)], cls.dir)
        if not wait_for(lambda: cls.port_file.exists() and cls.port_file.read_text().strip()):
            cls.proc.kill()
            raise unittest.SkipTest("the proxy did not write its port file: %r"
                                    % cls.proc.stderr.read().decode(errors="replace"))
        cls.port = int(cls.port_file.read_text())
        cls.health = split_response(tcp_exchange(cls.port, b"GET /__elm_pi_egress__/health HTTP/1.0\r\n\r\n"))
        cls.refusal = tcp_exchange(cls.port, b"CONNECT evil.com:443 HTTP/1.1\r\n\r\n")
        results = [None] * 20

        def one(i):
            results[i] = tcp_exchange(cls.port, b"CONNECT evil%d.example:443 HTTP/1.1\r\n\r\n" % i)
        threads = [threading.Thread(target=one, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(20)
        cls.concurrent = results
        tcp_exchange(cls.port, b"\x00\xff garbage\r\n\r\n")
        cls.after_garbage = tcp_exchange(cls.port, b"GET /__elm_pi_egress__/health HTTP/1.0\r\n\r\n")
        wait_for(lambda: cls.log.read_text().count("\n") >= 23, 5)
        cls.log_lines = [l[21:] for l in cls.log.read_text().splitlines()]

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()
        cls.proc.wait(10)
        cls.proc.stderr.close()

    def test_port_file_holds_the_listening_port(self):
        self.assertEqual(self.port, json.loads(self.health[2])["port"])

    def test_port_file_written_atomically(self):
        self.assertFalse((self.dir / "elm-pi-egress-own.port.tmp").exists())

    def test_start_line(self):
        self.assertRegex(self.log_lines[0],
                         r"^START    127\.0\.0\.1:%d allow=localhost,127\.0\.0\.1,pypi\.org fds=(\d+|\?)$" % self.port)

    def test_health_names_this_process(self):
        self.assertEqual(self.proc.pid, json.loads(self.health[2])["pid"])

    def test_health_shows_the_split_allowlist(self):
        self.assertEqual(["localhost", "127.0.0.1", "pypi.org"], json.loads(self.health[2])["allow"])

    def test_refusal_over_tcp(self):
        self.assertTrue(self.refusal.startswith(b"HTTP/1.1 403 Forbidden\r\n"))

    def test_concurrent_refusals_all_answered(self):
        self.assertTrue(all(r and r.startswith(b"HTTP/1.1 403 ") for r in self.concurrent))

    def test_concurrent_refusals_all_logged(self):
        rejected = {l.split()[1] for l in self.log_lines if l.startswith("REJECTED evil")}
        self.assertEqual({"evil.com:443"} | {"evil%d.example:443" % i for i in range(20)}, rejected)

    def test_survives_garbage(self):
        self.assertIsNone(self.proc.poll())
        self.assertIn(b"elm-pi-egress", self.after_garbage)

    def test_stale_port_file_of_dead_session_pruned_at_start(self):
        self.assertFalse(self.stale.exists())

    def test_port_file_of_live_session_kept(self):
        self.assertTrue(self.alive.exists())


class WatchdogProcessTests(unittest.TestCase):
    """--parent-pid and --port: the proxy follows pi, on the port pi was given."""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(dir=TMP))
        cls.port_file = cls.dir / "elm-pi-egress-watch.port"
        cls.log = cls.dir / "egress.log"
        cls.want = free_port()
        cls.parent = subprocess.Popen([sys.executable, "-E", "-S", "-c", "import time; time.sleep(60)"])
        cls.proc = start_proxy(["--allow", "elm.edina.ac.uk", "--port", str(cls.want),
                                "--parent-pid", str(cls.parent.pid),
                                "--upstream", "http://user:hunter2@campus.invalid:3128",
                                "--port-file", str(cls.port_file), "--log", str(cls.log)], cls.dir)
        if not wait_for(lambda: cls.port_file.exists() and cls.port_file.read_text().strip()):
            cls.proc.kill()
            cls.parent.kill()
            raise unittest.SkipTest("the proxy did not write its port file")
        cls.port = int(cls.port_file.read_text())
        cls.health = json.loads(split_response(
            tcp_exchange(cls.port, b"GET /__elm_pi_egress__/health HTTP/1.0\r\n\r\n"))[2])
        # a second proxy asked for the same port while the first holds it
        second_file = cls.dir / "elm-pi-egress-second.port"
        second = start_proxy(["--allow", "x", "--port", str(cls.port),
                              "--port-file", str(second_file), "--log", str(cls.dir / "second.log")], cls.dir)
        try:
            cls.second_rc = second.wait(15)
        except subprocess.TimeoutExpired:
            second.kill()
            cls.second_rc = None
        second.stderr.close()
        cls.second_file_exists = second_file.exists()
        cls.parent.kill()
        cls.parent.wait()
        try:
            cls.exit_code = cls.proc.wait(15)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
            cls.exit_code = None

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.kill()
            cls.proc.wait()
        cls.proc.stderr.close()

    def test_binds_the_requested_port(self):
        self.assertEqual(self.want, self.port)

    def test_health_reports_an_upstream(self):
        self.assertIs(True, self.health["upstream"])

    def test_upstream_credentials_are_not_logged(self):
        self.assertNotIn("hunter2", self.log.read_text())

    def test_exits_cleanly_when_the_parent_goes(self):
        self.assertEqual(0, self.exit_code)

    def test_port_file_removed_on_exit(self):
        self.assertFalse(self.port_file.exists())

    def test_second_proxy_cannot_take_a_live_port(self):
        self.assertNotEqual(0, self.second_rc)
        self.assertFalse(self.second_file_exists)


if __name__ == "__main__":
    unittest.main()
