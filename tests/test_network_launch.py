"""Exercise network launch wiring with local programs and loopback, without ELM requests."""

from pathlib import Path
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from test_install_fixes import Fixture, write  # noqa: E402


class NetworkLaunchTests(unittest.TestCase):
    def test_mode_hosts_reach_a_new_proxy_as_one_argument(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write(root / "proxy/egress.py", """import argparse
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--allow')
p.add_argument('--port-file')
args, _ = p.parse_known_args()
Path(__file__).with_name('allowed.txt').write_text(args.allow)
Path(args.port_file).write_text('54321')
""")
            script = """import sys
sys.path.insert(0, sys.argv[1])
from elmpi import network, proxy
from elmpi.environ import Environment
proxy._watchdog = lambda *args: None
env = Environment({'ELM_PI_PYTHON': sys.executable, 'TMPDIR': sys.argv[2],
                   'ELM_BASE_URL': 'https://elm.example/v1',
                   'ELM_PROXY_ALLOW': 'research.example,files.example'})
print(proxy.ensure(sys.argv[2], env, network.resolve('', env)))
"""
            result = subprocess.run([sys.executable, "-E", "-S", "-c", script,
                                     str(ROOT / "python"), tmp],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("54321", result.stdout.strip())
            self.assertEqual("elm.example,research.example,files.example",
                             (root / "proxy/allowed.txt").read_text())

    def run_with_fence(self, wrapper, reference=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        fixture = Fixture(base)
        fence = write(base / "fence", "#!/bin/sh\n" + wrapper, 0o755)
        script = """import sys
sys.path.insert(0, sys.argv[1] + '/python')
from elmpi import cli, jail, proxy
proxy.ensure = lambda *args: 54321
jail.plan = lambda *args: jail.Plan([sys.argv[2], 'fence marker'], '')
jail.fence_problem = lambda: []
sys.exit(cli.main(['-p', 'request with spaces'], install_root=sys.argv[1]))
"""
        env = {"PATH": "/usr/bin:/bin", "HOME": str(fixture.home),
               "TMPDIR": temporary.name, "PI_FORCE": "1", "RECORD_ENV": "PI_ELM_CHILD"}
        command = [sys.executable, "-E", "-S", "-c", script, str(fixture.root), str(fence)]
        if reference:
            # Use the real Bash launcher and local proxy; only the OS-specific
            # fence is replaced, so its command dispatch is exercised on CI too.
            shutil.copy2(ROOT / "proxy/egress.py", fixture.root / "proxy/egress.py")
            jail_module = fixture.root / "python/elmpi/jail.py"
            with jail_module.open("a") as handle:
                # ...and a machine that can make one, whatever this one is: on Ubuntu 26.04,
                # which cannot, the launcher otherwise starts unfenced and never asks for the plan.
                handle.write("\ndef plan(*args):\n    return Plan(%r, '')\n"
                             "\ndef fence_problem():\n    return []\n" % [str(fence), "fence marker"])
            command = [str(fixture.root / "pi.bash"), "-p", "request with spaces"]
        result = subprocess.run(command,
                                cwd=fixture.project, env=env, capture_output=True,
                                text=True, timeout=10)
        return base, result

    def test_cli_executes_the_fence_around_pi_and_keeps_arguments_intact(self):
        base, result = self.run_with_fence('printf "%s\\n" "$1" > ../fence-ran\nshift\nexec "$@"\n')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("fence marker\n", (base / "fence-ran").read_text())
        args = [line[4:] for line in result.stdout.splitlines() if line.startswith("ARG:")]
        self.assertEqual(["-p", "request with spaces"], args[-2:])
        self.assertNotIn("fence marker", args)
        self.assertIn("ENV:PI_ELM_CHILD=1", result.stdout)

    def test_a_fence_refusal_never_runs_pi_unfenced(self):
        _, result = self.run_with_fence('echo "fence refused" >&2\nexit 73\n')
        self.assertEqual(73, result.returncode, result.stderr)
        self.assertIn("fence refused", result.stderr)
        self.assertNotIn("ARG:", result.stdout)

    def test_bash_reference_executes_the_same_fenced_handover(self):
        base, result = self.run_with_fence('printf "%s\\n" "$1" > ../fence-ran\nshift\nexec "$@"\n',
                                           reference=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("fence marker\n", (base / "fence-ran").read_text())
        args = [line[4:] for line in result.stdout.splitlines() if line.startswith("ARG:")]
        self.assertEqual(["-p", "request with spaces"], args[-2:])
        self.assertNotIn("fence marker", args)

    def test_bash_offline_child_does_not_adopt_a_broader_parent_proxy(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = Fixture(Path(temporary.name), launcher=ROOT / "pi.bash")
        shutil.copy2(ROOT / "proxy/egress.py", fixture.root / "proxy/egress.py")
        parent_port = Path(temporary.name) / "parent.port"
        parent_log = Path(temporary.name) / "parent.log"
        parent = subprocess.Popen([
            sys.executable, "-E", "-S", str(ROOT / "proxy/egress.py"),
            "--allow", "elm.edina.ac.uk,pypi.org", "--port-file", str(parent_port),
            "--log", str(parent_log),
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        def stop_parent():
            if parent.poll() is None:
                parent.terminate()
            parent.wait(timeout=5)
            parent.stderr.close()
        self.addCleanup(stop_parent)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not parent_port.exists():
            time.sleep(0.02)
        diagnostic = (parent.stderr.read().decode(errors="replace")
                      if parent.poll() is not None else "proxy did not publish its port")
        self.assertTrue(parent_port.exists(), diagnostic)
        inherited = "http://127.0.0.1:%s" % parent_port.read_text().strip()
        result = fixture.run(
            "--offline", "-p", "x",
            env={"ELM_PI_NO_PROXY": "", "ELM_PI_NO_JAIL": "1", "HTTPS_PROXY": inherited,
                 "ELM_PROXY_ALLOW": "pypi.org"},
            record=("HTTPS_PROXY",),
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotEqual(inherited, result.env_seen["HTTPS_PROXY"])

    def test_netns_entrypoint_imports_its_package_in_an_unrelated_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "elmpi.py").write_text("raise RuntimeError('project elmpi imported')\n")
            Path(tmp, "relay.py").write_text("raise RuntimeError('project relay imported')\n")
            result = subprocess.run([sys.executable, "-E", "-S", str(ROOT / "python/elmpi/netns.py")],
                                    cwd=tmp, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": tmp},
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual("netns: proxy and preview ports, sockets and a command are required\n",
                         result.stderr)

    def test_the_inner_linux_relay_follows_pi_after_exec(self):
        sys.path.insert(0, str(ROOT / "python"))
        from elmpi import netns

        process = mock.Mock()
        preview = mock.Mock()
        with mock.patch.object(netns, "loopback_up"), \
                mock.patch.object(netns.subprocess, "Popen",
                                  side_effect=[process, preview]) as popen, \
                mock.patch.object(netns.relay, "wait_for_proxy", return_value=True), \
                mock.patch.object(netns.relay, "wait_for_unix", return_value=True), \
                mock.patch.object(netns.os, "execv") as execute:
            self.assertEqual(0, netns.main(
                ["--port", "43210", "--socket", "/tmp/relay.sock",
                 "--preview-port", "45678", "--preview-socket", "/tmp/preview.sock",
                 "--", "/bin/true"]))
        argv = popen.call_args_list[0].args[0]
        self.assertEqual(str(os.getpid()), argv[argv.index("--parent-pid") + 1])
        preview_argv = popen.call_args_list[1].args[0]
        self.assertEqual("/tmp/preview.sock",
                         preview_argv[preview_argv.index("--unix-listen") + 1])
        self.assertEqual("45678", preview_argv[preview_argv.index("--tcp-connect") + 1])
        execute.assert_called_once_with("/bin/true", ["/bin/true"])
        process.terminate.assert_called_once_with()
        preview.terminate.assert_called_once_with()

    def test_a_relay_exits_with_its_parent_and_removes_its_unix_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            socket_path = str(Path(tmp) / "host-relay.sock")
            parent = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(.3)"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            relay = subprocess.Popen([
                sys.executable, "-E", "-S", str(ROOT / "python/elmpi/relay.py"),
                "--unix-listen", socket_path, "--tcp-connect", "1",
                "--parent-pid", str(parent.pid),
            ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and not os.path.exists(socket_path):
                    time.sleep(0.02)
                self.assertTrue(os.path.exists(socket_path))
                parent.wait(timeout=3)
                relay.wait(timeout=3)
                self.assertEqual(0, relay.returncode, relay.stderr.read().decode(errors="replace"))
                self.assertFalse(os.path.exists(socket_path))
            finally:
                if parent.poll() is None:
                    parent.terminate()
                if relay.poll() is None:
                    relay.terminate()
                parent.wait(timeout=3)
                relay.wait(timeout=3)
                relay.stderr.close()

    def test_reverse_relay_makes_a_loopback_preview_host_visible(self):
        """The Linux bridge direction is host TCP -> Unix -> jailed TCP."""
        with tempfile.TemporaryDirectory() as tmp:
            unix_path = str(Path(tmp) / "preview.sock")
            port_file = Path(tmp) / "preview.port"
            target = socket.socket()
            target.bind(("127.0.0.1", 0))
            target.listen(1)
            self.addCleanup(target.close)
            received = []

            def serve():
                with target.accept()[0] as connection:
                    received.append(connection.recv(4096))
                    connection.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 7\r\n\r\npreview")

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            inner = subprocess.Popen([
                sys.executable, "-E", "-S", str(ROOT / "python/elmpi/relay.py"),
                "--unix-listen", unix_path, "--tcp-connect", str(target.getsockname()[1]),
                "--parent-pid", str(os.getpid()),
            ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            outer = subprocess.Popen([
                sys.executable, "-E", "-S", str(ROOT / "python/elmpi/relay.py"),
                "--tcp-listen", "0", "--unix-connect", unix_path,
                "--port-file", str(port_file), "--parent-pid", str(os.getpid()),
            ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and (not port_file.exists() or not os.path.exists(unix_path)):
                    time.sleep(0.02)
                self.assertTrue(port_file.exists())
                self.assertTrue(os.path.exists(unix_path))
                with socket.create_connection(("127.0.0.1", int(port_file.read_text())), 2) as client:
                    client.sendall(b"GET / HTTP/1.0\r\n\r\n")
                    reply = b""
                    while True:
                        chunk = client.recv(4096)
                        if not chunk:
                            break
                        reply += chunk
                thread.join(3)
                self.assertEqual([b"GET / HTTP/1.0\r\n\r\n"], received)
                self.assertTrue(reply.endswith(b"preview"), reply)
            finally:
                for process in (outer, inner):
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=3)
                    process.stderr.close()


if __name__ == "__main__":
    unittest.main()
