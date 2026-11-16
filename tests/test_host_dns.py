"""Isolation retains the host's resolver and the site's upstream proxy.

The on-site network may filter public resolvers. Exercise the real stdlib
create_connection path with getaddrinfo returning only local test servers,
and prove that resolution failures do not open a fallback DNS connection.
No request leaves loopback and no resolver configuration is read or changed.
"""
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

from tests.test_egress_proxy import (
    Echo, Origin, Upstream, egress, exchange, recv_all, recv_exactly, start_handle,
)


class HostResolverTests(unittest.TestCase):
    DESTINATION = "research.example.invalid"
    UPSTREAM = "campus-proxy.example.invalid"
    ESTABLISHED = b"HTTP/1.1 200 Connection Established\r\n\r\n"

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="elm-pi-host-dns-")
        self.addCleanup(self.scratch.cleanup)
        self.log = Path(self.scratch.name) / "egress.log"

    def proxy(self, upstream=None):
        return egress.Proxy([self.DESTINATION], str(self.log), upstream)

    def resolve_to(self, hostname, port):
        def resolve(host, service, family=0, kind=0, proto=0, flags=0):
            self.assertEqual(hostname, host, "only the intended hostname may reach the host resolver")
            self.assertEqual(port, service)
            self.assertEqual(socket.SOCK_STREAM, kind)
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", port))]
        return resolve

    def test_connect_uses_host_getaddrinfo_and_its_returned_address(self):
        origin = Echo()
        self.addCleanup(origin.close)
        proxy = self.proxy()
        client, thread = start_handle(proxy)
        try:
            with mock.patch.object(egress.socket, "getaddrinfo", side_effect=self.resolve_to(self.DESTINATION, origin.port)) as resolver:
                request = "CONNECT %s:%d HTTP/1.1\r\n\r\n" % (self.DESTINATION, origin.port)
                client.sendall(request.encode("ascii"))
                self.assertEqual(self.ESTABLISHED, recv_exactly(client, len(self.ESTABLISHED)))
                client.sendall(b"host-resolved tunnel")
                self.assertEqual(b"host-resolved tunnel", recv_exactly(client, 20))
                resolver.assert_called_once_with(self.DESTINATION, origin.port, 0, socket.SOCK_STREAM)
        finally:
            client.close()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(b"host-resolved tunnel", origin.wait())

    def test_plain_http_uses_host_getaddrinfo_and_preserves_host_header(self):
        origin = Origin()
        self.addCleanup(origin.close)
        authority = "%s:%d" % (self.DESTINATION, origin.port)
        request = "GET http://%s/data?q=1 HTTP/1.1\r\nHost: %s\r\n\r\n" % (authority, authority)
        with mock.patch.object(egress.socket, "getaddrinfo", side_effect=self.resolve_to(self.DESTINATION, origin.port)) as resolver:
            self.assertEqual(origin.RESPONSE, exchange(self.proxy(), request.encode("ascii")))
            resolver.assert_called_once_with(self.DESTINATION, origin.port, 0, socket.SOCK_STREAM)
        self.assertEqual(("GET /data?q=1 HTTP/1.1\r\nHost: %s\r\n\r\n" % authority).encode("ascii"), origin.wait())

    def assert_resolver_failure(self, request, upstream, hostname, port, error_number):
        proxy = self.proxy(upstream)
        # Create the local control socketpair before forbidding new sockets. A public
        # UDP resolver, DNS-over-HTTPS connection or direct-origin fallback would fail here.
        client, thread = start_handle(proxy)
        try:
            with mock.patch.object(egress.socket, "getaddrinfo", side_effect=socket.gaierror(error_number, "site resolver refused")) as resolver, \
                    mock.patch.object(egress.socket, "socket", side_effect=AssertionError("resolution failure must not dial elsewhere")) as opened:
                client.sendall(request)
                client.shutdown(socket.SHUT_WR)
                self.assertEqual(b"", recv_all(client))
                thread.join(5)
                resolver.assert_called_once_with(hostname, port, 0, socket.SOCK_STREAM)
                opened.assert_not_called()
        finally:
            client.close()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertIn("FAILED", self.log.read_text())
        self.assertIn("site resolver refused", self.log.read_text())

    def test_destination_resolver_errors_do_not_try_public_dns(self):
        requests = (
            (b"CONNECT research.example.invalid:443 HTTP/1.1\r\n\r\n", 443),
            (b"GET http://research.example.invalid/data HTTP/1.1\r\nHost: research.example.invalid\r\n\r\n", 80),
        )
        for request, port in requests:
            for error_number in (socket.EAI_NONAME, socket.EAI_AGAIN):
                with self.subTest(request=request.split(b" ")[0], error=error_number):
                    self.assert_resolver_failure(request, None, self.DESTINATION, port, error_number)

    def test_upstream_connect_resolves_only_upstream_and_forwards_original_target(self):
        upstream = Upstream(hang_up=True)
        self.addCleanup(upstream.close)
        request = b"CONNECT research.example.invalid:443 HTTP/1.1\r\nHost: research.example.invalid:443\r\n\r\n"
        with mock.patch.object(egress.socket, "getaddrinfo", side_effect=self.resolve_to(self.UPSTREAM, upstream.port)) as resolver:
            self.assertEqual(upstream.reply[0], exchange(self.proxy((self.UPSTREAM, upstream.port)), request))
            resolver.assert_called_once_with(self.UPSTREAM, upstream.port, 0, socket.SOCK_STREAM)
        self.assertEqual(request, upstream.wait())

    def test_upstream_plain_http_resolves_only_upstream_and_keeps_absolute_uri(self):
        reply = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"
        upstream = Upstream(reply=(reply,), hang_up=True)
        self.addCleanup(upstream.close)
        request = b"GET http://research.example.invalid/data?q=1 HTTP/1.1\r\nHost: research.example.invalid\r\n\r\n"
        with mock.patch.object(egress.socket, "getaddrinfo", side_effect=self.resolve_to(self.UPSTREAM, upstream.port)) as resolver:
            self.assertEqual(reply, exchange(self.proxy((self.UPSTREAM, upstream.port)), request))
            resolver.assert_called_once_with(self.UPSTREAM, upstream.port, 0, socket.SOCK_STREAM)
        # the absolute URI unchanged; the proxy adds only its request to close after this one
        self.assertEqual(request[:-2] + b"Connection: close\r\nProxy-Connection: close\r\n\r\n", upstream.wait())

    def test_upstream_resolution_failure_does_not_resolve_or_dial_destination(self):
        requests = (
            b"CONNECT research.example.invalid:443 HTTP/1.1\r\n\r\n",
            b"GET http://research.example.invalid/data HTTP/1.1\r\nHost: research.example.invalid\r\n\r\n",
        )
        for request in requests:
            with self.subTest(request=request.split(b" ")[0]):
                self.assert_resolver_failure(request, (self.UPSTREAM, 3128), self.UPSTREAM, 3128, socket.EAI_AGAIN)
