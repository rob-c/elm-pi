"""The three network modes, and the OS fence each one asks for.

Unit cases for the decisions, and - on macOS - a real `sandbox-exec` run of the
generated profile: only permitted ports connectable, no direct DNS, and host
resolution still available through the proxy. All connections stay on loopback.
The Linux backend is checked for the argv it builds here.
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "python"))

import test_install_fixes as functional  # noqa: E402
import test_python_launcher as launcher_tests  # noqa: E402
from test_egress_proxy import egress  # noqa: E402

from elmpi import jail, network  # noqa: E402


class ModeResolutionTests(unittest.TestCase):
    def test_the_default_is_trusted_remote(self):
        mode = network.resolve("", {})
        self.assertEqual(network.TRUSTED, mode.name)
        self.assertEqual("default", mode.source)
        self.assertTrue(mode.web)
        self.assertTrue(mode.jail)

    def test_a_flag_beats_the_environment_and_the_environment_the_default(self):
        env = {network.ENV: "offline"}
        self.assertEqual("yolo", network.resolve("yolo", env).name)
        self.assertEqual("offline", network.resolve("", env).name)
        self.assertEqual("trusted-remote", network.resolve("", {}).name)

    def test_a_typo_is_refused_rather_than_read_as_the_default(self):
        with self.assertRaises(ValueError) as caught:
            network.resolve("", {network.ENV: "remote"})
        self.assertIn("offline, trusted-remote, yolo", str(caught.exception))

    def test_offline_reaches_the_gateway_alone(self):
        mode = network.resolve("offline", {})
        self.assertFalse(mode.web)
        self.assertTrue(mode.jail)
        self.assertEqual(["elm.example"],
                         mode.hosts({"ELM_PROXY_ALLOW": "pypi.org",
                                     "ELM_PI_PROXY_ALLOW": "run.example"}, "elm.example"))

    def test_trusted_remote_reaches_the_installs_hosts_and_the_runs(self):
        mode = network.resolve("", {})
        self.assertEqual(["elm.example", "pypi.org", "run.example"],
                         mode.hosts({"ELM_PROXY_ALLOW": "pypi.org",
                                     "ELM_PI_PROXY_ALLOW": "run.example"}, "elm.example"))
        self.assertEqual(["elm.example", "pypi.org"],
                         mode.hosts({"ELM_PROXY_ALLOW": "pypi.org,pypi.org"}, "elm.example"))

    def test_yolo_is_the_only_wildcard_and_carries_no_fence(self):
        mode = network.resolve("yolo", {})
        self.assertTrue(mode.web)
        self.assertFalse(mode.jail)
        self.assertTrue(mode.wildcard)


class ProfileTests(unittest.TestCase):
    def plan(self, mode, env=None, port=43210):
        if sys.platform.startswith("linux"):
            process = mock.Mock()
            preview = mock.Mock()
            with mock.patch.object(jail.subprocess, "Popen", return_value=process), \
                    mock.patch.object(jail, "_namespace_problem", return_value=""), \
                    mock.patch.object(jail, "_wait_for_relay", return_value=True):
                with mock.patch.object(jail, "_preview_bridge",
                                       return_value=(preview, 49152, "/tmp/preview.sock")):
                    return jail.plan(mode, ROOT, env or {}, port, sys.executable)
        return jail.plan(mode, ROOT, env or {}, port, sys.executable)

    def test_preview_port_is_validated_and_published_even_without_a_jail(self):
        env = {"ELM_PI_NO_JAIL": "1", network.PREVIEW_ENV: "45678"}
        plan = jail.plan(network.resolve("", env), ROOT, env, 43210, sys.executable)
        self.assertEqual([], plan.prefix)
        self.assertEqual("45678", env[network.PREVIEW_ENV])
        self.assertEqual("0", env["ELM_PI_PREVIEW_BRIDGED"])
        with self.assertRaises(Exception) as caught:
            jail.plan(network.resolve("yolo", {}), ROOT,
                      {network.PREVIEW_ENV: "not-a-port"}, 43210, sys.executable)
        self.assertIn("ELM_PI_PREVIEW_PORT=not-a-port", caught.exception.lines[0])

    def test_the_profile_denies_by_default_and_names_only_loopback(self):
        text = jail.profile()
        self.assertIn("(deny default)", text)
        # every outbound rule is this machine's loopback: no host, no address
        self.assertEqual(['(allow network-outbound (remote ip "localhost:*"))'],
                         [line for line in text.splitlines() if "network-outbound" in line])
        self.assertNotIn('"*:', text)
        self.assertNotIn("unix-socket", text)      # none without a folder to hold them

    def test_unix_sockets_are_opened_only_under_the_folders_given(self):
        text = jail.profile(["/private/tmp/x", '/Users/me/a "b"'])
        self.assertIn('(allow network-bind (local unix-socket (subpath "/private/tmp/x")))', text)
        self.assertIn('(allow network-outbound (remote unix-socket (subpath "/private/tmp/x")))', text)
        self.assertIn('(subpath "/Users/me/a \\"b\\"")', text)   # a quote cannot end the string
        self.assertEqual(4, text.count("unix-socket"))

    def test_the_container_engines_socket_is_opened_alone_and_only_for_connecting(self):
        # 2026-11-17: under the fence every docker command ended "permission denied while trying to connect to the
        # docker API". The user's decision: sessions reach the engine wherever there is one; its socket, nothing beside it.
        text = jail.profile(["/private/tmp/x"], ["/Users/me/.docker/run/docker.sock", '/odd "path"/docker.sock'])
        self.assertIn('(allow network-outbound (remote unix-socket (path-literal "/Users/me/.docker/run/docker.sock")))', text)
        self.assertIn('(path-literal "/odd \\"path\\"/docker.sock")', text)
        self.assertNotIn('(subpath "/Users/me/.docker', text)          # not the folder: its other sockets stay closed
        self.assertNotIn("network-bind (local unix-socket (path-literal", text)

    def test_engine_sockets_are_only_sockets_that_exist(self):
        import socket, tempfile
        with tempfile.TemporaryDirectory(dir="/tmp") as home:
            run = os.path.join(home, ".docker", "run"); os.makedirs(run)
            self.assertEqual([], [p for p in jail.engine_sockets({"HOME": home}) if p.startswith(os.path.realpath(home)) or p.startswith(home)])
            with open(os.path.join(home, ".rd-not-a-socket"), "w"):
                pass
            server = socket.socket(socket.AF_UNIX); server.bind(os.path.join(run, "docker.sock"))
            try:
                found = jail.engine_sockets({"HOME": home, "DOCKER_HOST": "tcp://10.0.0.5:2375"})
                mine = [p for p in found if "docker/run" in p and (p.startswith(home) or p.startswith(os.path.realpath(home)))]
                self.assertIn(os.path.join(home, ".docker", "run", "docker.sock"), mine)
                self.assertTrue(all(os.path.isabs(p) for p in found))
                other = os.path.join(home, "elsewhere.sock"); second = socket.socket(socket.AF_UNIX); second.bind(other)
                try:
                    self.assertIn(other, jail.engine_sockets({"HOME": home, "DOCKER_HOST": "unix://" + other}))
                    self.assertNotIn(os.path.join(home, "missing.sock"), jail.engine_sockets({"HOME": home, "DOCKER_HOST": "unix://" + home + "/missing.sock"}))
                    self.assertNotIn(os.path.join(home, ".rd-not-a-socket"), jail.engine_sockets({"HOME": home, "DOCKER_HOST": "unix://" + home + "/.rd-not-a-socket"}))
                finally:
                    second.close()
            finally:
                server.close()

    def test_the_macos_profile_reaches_a_shim_on_any_loopback_port(self):
        with mock.patch.object(jail.os, "access", return_value=True):
            plan = jail._macos(network.resolve("", {}), {"ELM_SHIM_PORT": "54321"}, 43210)
        self.assertIn('(remote ip "localhost:*")', plan.prefix[2])

    def test_an_invalid_shim_port_is_a_clear_refusal(self):
        with mock.patch.object(jail.os, "access", return_value=True):
            with self.assertRaises(Exception) as caught:
                jail._macos(network.resolve("", {}), {"ELM_SHIM_PORT": "not-a-port"}, 43210)
        self.assertEqual(1, caught.exception.code)
        self.assertIn("ELM_SHIM_PORT=not-a-port", caught.exception.lines[0])

    def test_the_fence_is_not_applied_to_yolo_or_by_request(self):
        mode = network.resolve("yolo", {})
        self.assertEqual([], jail.plan(mode, ROOT, {}, 43210, sys.executable).prefix)
        trusted = network.resolve("", {})
        self.assertEqual([], jail.plan(trusted, ROOT, {"ELM_PI_NO_JAIL": "1"}, 43210,
                                       sys.executable).prefix)
        # Nothing to point the fence at: the documented unfenced debugging run.
        self.assertEqual([], jail.plan(trusted, ROOT, {}, None, sys.executable).prefix)

    def test_a_fenced_run_has_a_prefix_on_every_platform(self):
        mode = network.resolve("", {})
        plan = self.plan(mode)
        if sys.platform == "darwin":
            self.assertEqual(jail.SANDBOX_EXEC, plan.prefix[0])
            self.assertIn("(deny default)", plan.prefix[2])
        elif sys.platform.startswith("linux"):
            self.assertIn("--user", plan.prefix)
            self.assertIn("--map-root-user", plan.prefix)
            self.assertIn("--net", plan.prefix)
            self.assertTrue(any(part.endswith("netns.py") for part in plan.prefix))
            self.assertEqual("49152", plan.prefix[plan.prefix.index("--preview-port") + 1])
            self.assertIn("preview http://127.0.0.1:49152/", plan.note)
        self.assertIn("jail:", plan.note)

    def test_the_linux_plan_names_the_relay_and_the_namespace(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("the Linux backend is built on Linux")
        plan = self.plan(network.resolve("", {}))
        self.assertEqual("unshare", Path(plan.prefix[0]).name)
        # the session keeps the launcher's pid: tests/test_fenced_launch.py
        self.assertNotIn("--fork", plan.prefix)

    def test_linux_refuses_before_launch_when_the_host_relay_cannot_reach_the_proxy(self):
        process = mock.Mock()
        with mock.patch.object(jail.shutil, "which", return_value="/usr/bin/unshare"), \
                mock.patch.object(jail, "_namespace_problem", return_value=""), \
                mock.patch.object(jail.subprocess, "Popen", return_value=process), \
                mock.patch.object(jail, "_wait_for_relay", return_value=False), \
                mock.patch.object(jail.os, "unlink"):
            with self.assertRaises(Exception) as caught:
                jail._linux(network.resolve("", {}), {}, 43210, sys.executable)
        self.assertEqual(1, caught.exception.code)
        self.assertIn("host relay did not reach", caught.exception.lines[0])
        process.terminate.assert_called_once_with()

    def test_linux_refuses_when_an_explicit_preview_port_cannot_be_bound(self):
        process = mock.Mock()
        env = {network.PREVIEW_ENV: "45678"}
        refusal = jail.Refusal("preview unavailable")
        with mock.patch.object(jail.shutil, "which", return_value="/usr/bin/unshare"), \
                mock.patch.object(jail, "_namespace_problem", return_value=""), \
                mock.patch.object(jail.subprocess, "Popen", return_value=process), \
                mock.patch.object(jail, "_wait_for_relay", return_value=True), \
                mock.patch.object(jail, "_preview_bridge", side_effect=refusal):
            with self.assertRaises(Exception) as caught:
                jail._linux(network.resolve("", env), env, 43210, sys.executable,
                            45678, True)
        self.assertIs(refusal, caught.exception)
        process.terminate.assert_called_once_with()


class PreviewBridgeTests(unittest.TestCase):
    def test_unset_linux_preview_uses_a_free_host_loopback_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            process, port, path = jail._preview_bridge(tmp, sys.executable, 8765, False)
            try:
                self.assertGreater(port, 0)
                self.assertNotEqual(8765, port)
                self.assertTrue(path.endswith(".sock"))
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    pass
            finally:
                process.terminate()
                process.wait(timeout=3)

    def test_an_occupied_explicit_preview_port_is_refused(self):
        occupied = socket.socket()
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        self.addCleanup(occupied.close)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(jail, "RELAY_TIMEOUT", 0.2):
            with self.assertRaises(Exception) as caught:
                jail._preview_bridge(tmp, sys.executable, occupied.getsockname()[1], True)
        self.assertIn("is unavailable on host loopback", caught.exception.lines[0])
        self.assertIn("Choose another port", "\n".join(caught.exception.lines))


@unittest.skipUnless(sys.platform == "darwin" and os.access(jail.SANDBOX_EXEC, os.X_OK),
                     "needs sandbox-exec")
class MacOSJailTests(unittest.TestCase):
    """The generated profile, run for real: the fence holds and DNS is gone."""

    def setUp(self):
        self.proxy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.proxy.bind(("127.0.0.1", 0))
        self.proxy.listen(8)
        self.port = self.proxy.getsockname()[1]
        self.profile = jail.profile()
        self.blocked = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.blocked.bind(("127.0.0.1", 0))
        self.blocked.listen(8)
        self.blocked_port = self.blocked.getsockname()[1]

    def tearDown(self):
        self.proxy.close()
        self.blocked.close()

    def run_under(self, *command):
        return subprocess.run([jail.SANDBOX_EXEC, "-p", self.profile] + list(command),
                              capture_output=True, text=True, timeout=30)

    def test_loopback_is_reachable_and_nothing_off_the_machine_is(self):
        # The proxy, and any other listener on this machine's loopback: a
        # session reaches the servers it starts (tests/test_fenced_launch.py).
        for port in (self.port, self.blocked_port):
            self.assertEqual(0, self.run_under("/usr/bin/nc", "-z", "127.0.0.1", str(port)).returncode)
        # EPERM is the fence's own answer, at once and with no packet sent - not
        # a timeout a site's firewall could produce. 192.0.2.1 is TEST-NET-1.
        dial = ("import socket\ntry:\n    socket.create_connection(('192.0.2.1', 9), 3)\n"
                "    print('open')\nexcept OSError as problem:\n    print(type(problem).__name__)")
        self.assertEqual("PermissionError\n", self.run_under(sys.executable, "-c", dial).stdout)

    def test_there_is_no_name_resolution_inside_the_fence(self):
        result = self.run_under(sys.executable, "-c",
                                "import socket; print(socket.getaddrinfo('example.com', 443))")
        self.assertNotEqual(0, result.returncode, result.stdout)

    def test_a_fenced_process_cannot_widen_its_own_sandbox(self):
        result = self.run_under("/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)",
                                "/usr/bin/nc", "-z", "127.0.0.1", str(self.blocked_port))
        self.assertNotEqual(0, result.returncode)

    def test_a_loopback_web_preview_is_visible_from_the_host(self):
        preview = socket.socket()
        preview.bind(("127.0.0.1", 0))
        port = preview.getsockname()[1]
        preview.close()
        process = subprocess.Popen(
            [jail.SANDBOX_EXEC, "-p", self.profile, sys.executable, "-m", "http.server",
             "--bind", "127.0.0.1", str(port)],
            cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            reply = b""
            while time.monotonic() < deadline:
                try:
                    with socket.create_connection(("127.0.0.1", port), 0.2) as connection:
                        connection.sendall(b"GET /README.md HTTP/1.0\r\n\r\n")
                        while True:
                            chunk = connection.recv(65536)
                            if not chunk:
                                break
                            reply += chunk
                    break
                except OSError:
                    time.sleep(0.02)
            self.assertIn(b"HTTP/1.0 200 OK", reply,
                          process.stderr.read().decode(errors="replace") if process.poll() else "")
            self.assertIn(b"elm-pi", reply)
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=3)
            process.stderr.close()

    def test_a_fenced_client_uses_the_host_resolver_through_the_proxy(self):
        # The site's name exists only in the host's resolver. A separate jailed
        # process gets neither this mock nor direct access to the origin port.
        site = "gateway.site-only.invalid"
        payload = b"site DNS worked"
        real_getaddrinfo = socket.getaddrinfo
        errors = []

        def site_resolver(host, port, *args, **kwargs):
            if host != site:
                raise AssertionError("unexpected resolver target: %r" % host)
            return real_getaddrinfo("127.0.0.1", port, *args, **kwargs)

        def serve_origin():
            try:
                self.blocked.settimeout(10)
                with self.blocked.accept()[0] as conn:
                    conn.sendall(payload)
            except Exception as error:
                errors.append(error)

        with tempfile.TemporaryDirectory() as tmp:
            proxy = egress.Proxy([site], str(Path(tmp) / "egress.log"))

            def serve_proxy():
                try:
                    self.proxy.settimeout(10)
                    client, peer = self.proxy.accept()
                    proxy.handle(client, peer)
                except Exception as error:
                    errors.append(error)

            workers = [threading.Thread(target=target, daemon=True)
                       for target in (serve_origin, serve_proxy)]
            with mock.patch.object(socket, "getaddrinfo", side_effect=site_resolver) as resolve:
                for worker in workers:
                    worker.start()
                result = self.run_under(sys.executable, "-c", """
import socket, sys
with socket.socket() as conn:
    conn.settimeout(5)
    conn.connect(('127.0.0.1', int(sys.argv[1])))
    conn.sendall(('CONNECT %s:%s HTTP/1.1\\r\\n\\r\\n' % tuple(sys.argv[2:])).encode())
    chunks = []
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
    sys.stdout.buffer.write(b''.join(chunks))
""", str(self.port), site, str(self.blocked_port))
                for worker in workers:
                    worker.join(12)
                self.assertFalse(any(worker.is_alive() for worker in workers))
                self.assertEqual([], errors)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("HTTP/1.1 200 Connection Established", result.stdout)
                self.assertTrue(result.stdout.endswith(payload.decode()), result.stdout)
                self.assertEqual(1, resolve.call_count)
                self.assertEqual((site, self.blocked_port), resolve.call_args.args[:2])


class ProxyCommandTests(unittest.TestCase):
    """The argv the proxy is started with: every element a string, the allowlist joined."""

    def test_the_allowlist_reaches_the_proxy_as_one_string(self):
        import subprocess as spawn
        from elmpi import proxy
        captured = {}

        class Recorder:
            def __init__(self, argv, **kwargs):
                captured["argv"] = argv

        saved = spawn.Popen
        spawn.Popen = Recorder
        try:
            with tempfile.TemporaryDirectory() as tmp:
                env = {"ELM_PI_PYTHON": sys.executable, "TMPDIR": tmp,
                       "ELM_PROXY_ALLOW": "pypi.org", "ELM_BASE_URL": "https://elm.example/api"}
                mode = network.resolve("", {})
                with self.assertRaises(Exception):
                    # No proxy will answer, so this ends in the fail-closed
                    # refusal - after the Popen that this test is about.
                    proxy.ensure(str(ROOT), env, mode)
        finally:
            spawn.Popen = saved
        argv = captured["argv"]
        self.assertTrue(all(isinstance(part, str) for part in argv), argv)
        allow = argv[argv.index("--allow") + 1]
        self.assertEqual("elm.example,pypi.org", allow)


class LauncherModeTests(unittest.TestCase):
    """What the launcher hands pi, per mode."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = functional.Fixture(Path(self.tmp.name), launcher=launcher_tests.PYTHON_LAUNCHER)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self, *args, **env):
        result = self.fx.run(*args, env=dict(env), record=(
            "PI_ELM_NETWORK", "PI_ELM_WEB", "PI_ELM_REMOTE", "ELM_PI_PROXY_ALLOW",
            "PI_ELM_PERMISSION_MODE"))
        return result

    def test_the_default_session_is_trusted_remote_with_the_web_tools(self):
        r = self.record("-p", "x")
        self.assertEqual("trusted-remote", r.env_seen["PI_ELM_NETWORK"])
        self.assertEqual("1", r.env_seen["PI_ELM_WEB"])
        self.assertEqual("1", r.env_seen["PI_ELM_REMOTE"])
        self.assertIn("network: trusted-remote", r.stderr)

    def test_offline_takes_the_web_tools_and_the_extra_hosts_away(self):
        r = self.record("--offline", "-p", "x")
        self.assertEqual("offline", r.env_seen["PI_ELM_NETWORK"])
        self.assertEqual("__unset__", r.env_seen["PI_ELM_WEB"])
        self.assertEqual("__unset__", r.env_seen["PI_ELM_REMOTE"])
        self.assertIn("network: offline", r.stderr)

    def test_remote_is_now_yolo(self):
        r = self.record("--remote", "-p", "x")
        self.assertEqual("yolo", r.env_seen["PI_ELM_NETWORK"])
        self.assertTrue(r.env_seen["ELM_PI_PROXY_ALLOW"].endswith("*"))
        self.assertIn("--remote/--yolo - the egress proxy is recording", r.stderr)

    def test_yolo_is_yolo_for_the_network_as_well(self):
        """--yolo is one decision: every ask yes and every destination open.

        It needs a gate that applies the modes, which an install made with
        --no-patch does not have; the fixture's is patched here.
        """
        gate = self.fx.root / "agent/npm/node_modules/@gotgenes/pi-permission-system"
        (gate / "src" / "policy").mkdir(parents=True, exist_ok=True)
        (gate / "src" / "policy" / "permission-manager.ts").write_text(
            'PI_ELM_PERMISSION_MODE === "manual"\n')
        (gate / "src" / "index.ts").write_text('PI_ELM_PERMISSION_MODE === "yolo"\n')
        r = self.record("--yolo", "-p", "x")
        self.assertEqual("yolo", r.env_seen["PI_ELM_NETWORK"])
        self.assertEqual("yolo", r.env_seen["PI_ELM_PERMISSION_MODE"])

    def test_offline_wins_over_the_other_modes(self):
        r = self.record("--remote", "--offline", "-p", "x")
        self.assertEqual("offline", r.env_seen["PI_ELM_NETWORK"])
        self.assertEqual("__unset__", r.env_seen["PI_ELM_WEB"])

    def test_the_environment_sets_the_default_and_a_typo_is_refused(self):
        self.assertEqual("offline", self.record("-p", "x", PI_ELM_NETWORK="offline")
                         .env_seen["PI_ELM_NETWORK"])
        r = self.record("-p", "x", PI_ELM_NETWORK="remote")
        self.assertEqual(2, r.returncode)
        self.assertIn("not one of offline, trusted-remote, yolo", r.stderr)


if __name__ == "__main__":
    unittest.main()
