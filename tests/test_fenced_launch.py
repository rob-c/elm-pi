"""A launch from inside a fenced session, and a session that can be stopped.

Three defects measured on 2026-11-15, each with its test here:

* Linux: `unshare --fork` kept the launcher's pid and blocked SIGTERM and
  SIGINT, so a session could not be stopped by its pid, and SIGKILL orphaned it.
* A run started inside a fenced session with another network policy
  (`pi --offline -p x` from the session's shell) started a proxy that had no
  route out: "sandbox_apply: Operation not permitted" on macOS, a session that
  could not reach the model on Linux. The same when the session's proxy missed
  one health check.
* macOS: the fence let a session reach the proxy's port and the shim's and no
  other on loopback, and no Unix socket, so it could not reach a server it had
  started itself, a Jupyter kernel never answered, and multiprocessing.Manager
  could not bind.
* The refusal for a moved permission-gate entry point named a file that no
  longer holds the path.

Everything stays on loopback; the launcher cases run against `pi` and `pi.bash`.
"""

import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "python"))

from test_install_fixes import Fixture, write  # noqa: E402

from elmpi import extensions, jail, network, proxy, runtime, toolchain  # noqa: E402
from elmpi.environ import Environment  # noqa: E402
from elmpi.errors import Refusal  # noqa: E402

LAUNCHERS = (ROOT / "pi", ROOT / "pi.bash")


def start_proxy(case, allow, folder):
    """A real egress proxy on a free loopback port; returns the port."""
    port_file = Path(folder) / "session.port"
    process = subprocess.Popen(
        [sys.executable, "-E", "-S", str(ROOT / "proxy/egress.py"), "--allow", allow,
         "--port-file", str(port_file), "--log", str(Path(folder) / "session.log")],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop():
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
    case.addCleanup(stop)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not port_file.exists():
        time.sleep(0.02)
    case.assertTrue(port_file.exists(), "the test's proxy did not publish its port")
    return int(port_file.read_text().strip())


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class FencedChildTests(unittest.TestCase):
    """`pi` started from inside a fenced session: its proxy, or a sentence."""

    def fixture(self, launcher):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = Fixture(Path(temporary.name), launcher=launcher)
        shutil.copy2(ROOT / "proxy/egress.py", fixture.root / "proxy/egress.py")
        env = Environment({})
        runtime.load(str(fixture.root), env)
        hosts = ",".join(network.resolve("", env).hosts(env, proxy.elm_host(env)))
        return fixture, temporary.name, hosts

    def launch(self, fixture, *args, **env):
        settings = {"ELM_PI_NO_PROXY": "", "ELM_PI_NO_JAIL": "1"}
        settings.update(env)
        return fixture.run(*args, "-p", "x", env=settings, record=("HTTPS_PROXY",))

    def test_the_same_policy_uses_the_sessions_proxy(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                fixture, folder, hosts = self.fixture(launcher)
                address = "http://127.0.0.1:%d" % start_proxy(self, hosts, folder)
                result = self.launch(fixture, HTTPS_PROXY=address,
                                     ELM_PI_FENCED=address.rsplit(":", 1)[1])
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(address, result.env_seen["HTTPS_PROXY"])

    def test_another_policy_is_refused_in_a_sentence_and_starts_nothing(self):
        for launcher in LAUNCHERS:
            for extra, env in ((("--offline",), {}), (("--remote",), {}),
                               ((), {"ELM_PI_PROXY_ALLOW": "example.org"})):
                with self.subTest(launcher=launcher.name, extra=extra, env=env):
                    fixture, folder, hosts = self.fixture(launcher)
                    port = start_proxy(self, hosts, folder)
                    result = self.launch(fixture, *extra, ELM_PI_FENCED=str(port),
                                         HTTPS_PROXY="http://127.0.0.1:%d" % port, **env)
                    self.assertEqual(1, result.returncode, result.stderr)
                    self.assertEqual([], result.args_seen)               # pi never ran
                    self.assertIn("pi: this run asks for a network policy the session it is "
                                  "inside does not have.", result.stderr)
                    self.assertIn("127.0.0.1:%d" % port, result.stderr)
                    self.assertNotIn("sandbox_apply", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

    def test_outside_a_fence_another_policy_still_gets_its_own_proxy(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                fixture, folder, hosts = self.fixture(launcher)
                address = "http://127.0.0.1:%d" % start_proxy(self, hosts, folder)
                result = self.launch(fixture, "--offline", HTTPS_PROXY=address)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertNotEqual(address, result.env_seen["HTTPS_PROXY"])

    def test_a_session_proxy_that_does_not_answer_is_said_so(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                fixture, _, _ = self.fixture(launcher)
                port = free_port()
                result = self.launch(fixture, ELM_PI_FENCED=str(port),
                                     HTTPS_PROXY="http://127.0.0.1:%d" % port)
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertEqual([], result.args_seen)
                self.assertIn("pi: the proxy of the session this run is inside "
                              "(127.0.0.1:%d) is not answering." % port, result.stderr)

    def test_a_fenced_run_whose_proxy_setting_was_removed_is_said_so(self):
        for launcher in LAUNCHERS:
            for inherited in ("", "http://proxy.example:3128"):
                with self.subTest(launcher=launcher.name, inherited=inherited):
                    fixture, _, _ = self.fixture(launcher)
                    result = self.launch(fixture, ELM_PI_FENCED="40123", HTTPS_PROXY=inherited)
                    self.assertEqual(1, result.returncode, result.stderr)
                    self.assertEqual([], result.args_seen)
                    self.assertIn("pi: this run is inside a session fenced to its proxy on "
                                  "127.0.0.1:40123, and HTTPS_PROXY no longer names it.",
                                  result.stderr)

    def test_both_launchers_say_the_same_thing(self):
        said = []
        for launcher in LAUNCHERS:
            fixture, folder, hosts = self.fixture(launcher)
            port = start_proxy(self, hosts, folder)
            result = self.launch(fixture, "--offline", ELM_PI_FENCED=str(port),
                                 HTTPS_PROXY="http://127.0.0.1:%d" % port)
            lines = [line.replace(str(port), "PORT") for line in result.stderr.splitlines()]
            said.append(lines[lines.index(next(l for l in lines if l.startswith("pi: this run"))):])
        self.assertEqual(said[0], said[1])
        self.assertEqual(5, len(said[0]))


class FencedProxyTests(unittest.TestCase):
    """proxy._fenced: one missed health check is asked again, not believed."""

    def env(self):
        return Environment({network.FENCED_ENV: "40123"})

    def test_one_missed_health_check_does_not_end_the_launch(self):
        answers = iter([False, True])
        with mock.patch.object(proxy, "compatible", side_effect=lambda *a: next(answers)), \
                mock.patch.object(proxy, "alive", return_value=False), \
                mock.patch.object(proxy.time, "sleep") as pause:
            self.assertEqual(40123, proxy._fenced(self.env(), 40123, "elm.example", ""))
        pause.assert_called_once_with(proxy.FENCED_PAUSE)

    def test_it_gives_up_after_its_tries_without_starting_a_proxy(self):
        with mock.patch.object(proxy, "compatible", return_value=False) as asked, \
                mock.patch.object(proxy, "alive", return_value=False), \
                mock.patch.object(proxy.time, "sleep"), \
                mock.patch.object(proxy, "_start_own") as started:
            with self.assertRaises(Refusal) as caught:
                proxy._fenced(self.env(), 40123, "elm.example", "")
        self.assertEqual(proxy.FENCED_TRIES, asked.call_count)
        self.assertEqual(1, caught.exception.code)
        self.assertIn("is not answering", caught.exception.lines[0])
        started.assert_not_called()

    def test_a_proxy_that_answers_with_another_policy_is_not_asked_again(self):
        with mock.patch.object(proxy, "compatible", return_value=False) as asked, \
                mock.patch.object(proxy, "alive", return_value=True), \
                mock.patch.object(proxy.time, "sleep") as pause:
            with self.assertRaises(Refusal) as caught:
                proxy._fenced(self.env(), 40123, "elm.example", "")
        self.assertEqual(1, asked.call_count)
        pause.assert_not_called()
        self.assertIn("network policy", caught.exception.lines[0])


class FenceMarkerTests(unittest.TestCase):
    """ELM_PI_FENCED: set by a fence and by nothing else."""

    def plan(self, env, port=43210):
        mode = network.resolve("", env)
        process = mock.Mock()
        with mock.patch.object(jail.shutil, "which", return_value="/usr/bin/unshare"), \
                mock.patch.object(jail, "_namespace_problem", return_value=""), \
                mock.patch.object(jail.subprocess, "Popen", return_value=process), \
                mock.patch.object(jail, "_wait_for_relay", return_value=True), \
                mock.patch.object(jail, "_wait_for_port_file", return_value=49152), \
                mock.patch.object(jail.os, "access", return_value=True):
            return jail.plan(mode, str(ROOT), env, port, sys.executable)

    @unittest.skipUnless(sys.platform == "darwin" or sys.platform.startswith("linux"),
                         "a fence exists on macOS and Linux")
    def test_a_fenced_session_carries_its_proxy_port(self):
        env = {}
        self.assertTrue(self.plan(env).prefix)
        self.assertEqual("43210", env[network.FENCED_ENV])

    def test_an_unfenced_session_does_not(self):
        for env, port, flag in (({"ELM_PI_NO_JAIL": "1"}, 43210, ""), ({}, None, ""),
                                ({}, 43210, "yolo")):
            with self.subTest(env=env, port=port, flag=flag):
                mode = network.resolve(flag, env)
                self.assertEqual([], jail.plan(mode, str(ROOT), env, port, sys.executable).prefix)
                self.assertNotIn(network.FENCED_ENV, env)

    def test_the_marker_is_documented_as_internal(self):
        self.assertIn("`ELM_PI_FENCED", (ROOT / "python/README.md").read_text())


MACOS = sys.platform == "darwin" and os.access(jail.SANDBOX_EXEC, os.X_OK)


def under(case, profile, *command, **options):
    """Run `command` inside a real sandbox with `profile`."""
    result = subprocess.run([jail.SANDBOX_EXEC, "-p", profile] + list(command),
                            capture_output=True, text=True, timeout=120, **options)
    if "sandbox_apply" in result.stderr:
        case.skipTest("these tests are themselves inside another fence")
    return result


@unittest.skipUnless(MACOS, "macOS's sandbox-exec")
class MacOSSecondFenceTests(unittest.TestCase):
    """A run started inside a fenced session is in that fence already."""

    SCRIPT = """import os, sys
sys.path.insert(0, sys.argv[1])
from elmpi import jail, network
env = {"TMPDIR": sys.argv[2]}
if sys.argv[3]:
    env[network.FENCED_ENV] = sys.argv[3]
plan = jail.plan(network.resolve("", env), sys.argv[1], env, 40124, sys.executable)
print(repr(plan.prefix[:1]))
print(plan.note)
print(env.get(network.FENCED_ENV))
"""

    def plan_inside(self, marker):
        # The session's fence was made in another folder, with another TMPDIR:
        # its profile is not the one this launch would write.
        with tempfile.TemporaryDirectory() as elsewhere:
            result = under(self, jail.profile([os.path.realpath(elsewhere)]), sys.executable, "-E",
                           "-S", "-c", self.SCRIPT, str(ROOT / "python"),
                           tempfile.gettempdir(), marker)
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.splitlines()

    def test_the_sessions_fence_is_kept_and_no_second_one_is_asked_for(self):
        prefix, note, marker = self.plan_inside("40123")
        self.assertEqual("[]", prefix)
        self.assertIn("the fence of the session this run was started in", note)
        self.assertEqual("40124", marker)          # and its own children are told the same

    def test_without_the_marker_the_launch_still_asks_for_its_own_fence(self):
        # ...which macOS then refuses: the case the marker exists for.
        prefix, _, _ = self.plan_inside("")
        self.assertEqual(repr([jail.SANDBOX_EXEC]), prefix)

    def test_the_marker_alone_is_not_believed(self):
        env = {network.FENCED_ENV: "40123", "TMPDIR": tempfile.gettempdir()}
        if jail._inside_a_sandbox():
            self.skipTest("these tests are themselves inside another fence")
        plan = jail.plan(network.resolve("", env), str(ROOT), env, 40123, sys.executable)
        self.assertEqual(jail.SANDBOX_EXEC, plan.prefix[0])

    def test_the_failure_this_replaces_is_still_what_macos_does(self):
        # If macOS ever nests differing profiles, jail._inside_a_sandbox needs another probe.
        result = subprocess.run(
            [jail.SANDBOX_EXEC, "-p", jail.profile(["/private/tmp/a"]), jail.SANDBOX_EXEC, "-p",
             jail.profile(["/private/tmp/b"]), jail.TRUE], capture_output=True, text=True, timeout=60)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("sandbox_apply", result.stderr)

    def test_outside_a_fence_nothing_is_run_to_find_out(self):
        with mock.patch.object(jail, "_inside_a_sandbox") as asked:
            plan = jail.plan(network.resolve("", {}), str(ROOT), {}, 40123, sys.executable)
        self.assertEqual(jail.SANDBOX_EXEC, plan.prefix[0])
        asked.assert_not_called()


class SocketFolderTests(unittest.TestCase):
    """Which folders a fenced session's Unix sockets may live in."""

    def test_a_private_temporary_folder_and_the_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o700)
            self.assertEqual([os.path.realpath(tmp), os.path.realpath(os.getcwd())],
                             jail.socket_folders({"TMPDIR": tmp + "/"}))

    def test_a_shared_temporary_folder_is_left_out(self):
        # /tmp on macOS holds launchd's ssh-agent socket.
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o777)
            for env in ({"TMPDIR": tmp}, {"TMPDIR": "/tmp"}, {}):
                self.assertEqual([os.path.realpath(os.getcwd())], jail.socket_folders(env))


@unittest.skipUnless(MACOS, "macOS's sandbox-exec")
class MacOSLocalWorkTests(unittest.TestCase):
    """What a fenced session could not do on 2026-11-15, under the real profile."""

    PROBE = r"""
import multiprocessing, os, socket, sys, tempfile
def attempt(name, fn):
    try:
        fn(); print(name + ": ok")
    except Exception as problem:
        print(name + ": " + type(problem).__name__)
def server(family, address):
    def run():
        listener = socket.socket(family); listener.bind((address, 0)); listener.listen(1)
        socket.create_connection(listener.getsockname()[:2], 3).close(); listener.close()
    return run
def unix(folder):
    def run():
        path = os.path.join(folder, "probe-%d.sock" % os.getpid())
        listener = socket.socket(socket.AF_UNIX)
        try:
            listener.bind(path); listener.listen(1)
            client = socket.socket(socket.AF_UNIX); client.settimeout(3); client.connect(path); client.close()
        finally:
            listener.close()
            if os.path.exists(path): os.unlink(path)
    return run
def manager():
    with multiprocessing.Manager() as shared:
        box = shared.dict(); box["a"] = 1
        assert box["a"] == 1
def off_machine():
    socket.create_connection(("192.0.2.1", 9), 3)
if __name__ == "__main__":
    attempt("own server, 127.0.0.1", server(socket.AF_INET, "127.0.0.1"))
    attempt("own server, ::1", server(socket.AF_INET6, "::1"))
    attempt("unix socket in TMPDIR", unix(tempfile.gettempdir()))
    attempt("unix socket in the project", unix(os.getcwd()))
    attempt("unix socket elsewhere", unix(sys.argv[1]))
    attempt("multiprocessing.Manager", manager)
    attempt("an address off this machine", off_machine)
    attempt("a name", lambda: socket.getaddrinfo("example.com", 443))
"""

    def setUp(self):
        # The account's own temporary folder, as a session has it: from Python
        # 3.14 multiprocessing puts its socket in /tmp when TMPDIR is too long
        # to hold one (104 bytes on macOS), and a folder made inside TMPDIR for
        # this test is. The project and "elsewhere" are under /tmp, which the
        # fence leaves closed apart from the project itself.
        self.temporary = Path(os.path.realpath(tempfile.gettempdir()))
        if not toolchain.is_private(str(self.temporary)):
            self.skipTest("TMPDIR here is not this account's alone")

        def folder():
            made = tempfile.TemporaryDirectory(dir="/tmp")
            self.addCleanup(made.cleanup)
            return Path(os.path.realpath(made.name))
        self.project, self.elsewhere = folder(), folder()
        self.env = dict(os.environ, TMPDIR=str(self.temporary))
        with mock.patch.object(jail.os, "getcwd", return_value=str(self.project)):
            self.profile = jail.profile(jail.socket_folders({"TMPDIR": str(self.temporary)}))

    def test_a_session_reaches_what_it_starts_and_nothing_beyond_the_machine(self):
        probe = write(self.elsewhere / "probe.py", self.PROBE)
        result = under(self, self.profile, sys.executable, str(probe), str(self.elsewhere),
                       cwd=str(self.project), env=self.env)
        self.assertEqual([
            "own server, 127.0.0.1: ok",
            "own server, ::1: ok",
            "unix socket in TMPDIR: ok",
            "unix socket in the project: ok",
            "unix socket elsewhere: PermissionError",
            "multiprocessing.Manager: ok",
            "an address off this machine: PermissionError",
            "a name: gaierror",
        ], result.stdout.splitlines(), result.stderr)

    def test_curl_reaches_a_server_the_session_started(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        script = ('%s -m http.server %d --bind 127.0.0.1 >/dev/null 2>&1 & server=$!\n'
                  'code=000; n=0\n'
                  'while [ "$code" = 000 ] && [ $n -lt 50 ]; do\n'
                  '  code=$(/usr/bin/curl -s --noproxy "*" -m 3 -o /dev/null -w "%%{http_code}" '
                  'http://127.0.0.1:%d/); n=$((n+1)); [ "$code" != 000 ] || sleep 0.1\n'
                  'done\nkill $server; echo "$code"\n' % (sys.executable, port, port))
        result = under(self, self.profile, "/bin/sh", "-c", script, cwd=str(self.project), env=self.env)
        self.assertEqual("200\n", result.stdout, result.stderr)

    def test_a_jupyter_kernel_answers(self):
        python = os.environ.get("ELM_PI_AGENT_PYTHON") or str(ROOT / "agent/python/env/bin/python")
        if not os.access(python, os.X_OK) or subprocess.run(
                [python, "-c", "import jupyter_client, ipykernel"], capture_output=True).returncode:
            self.skipTest("no agent Python with ipykernel here (pi setup --python)")
        script = ("from jupyter_client.manager import start_new_kernel\n"
                  "manager, client = start_new_kernel(startup_timeout=60)\n"
                  "client.execute_interactive('print(6 * 7)', timeout=60)\n"
                  "client.stop_channels(); manager.shutdown_kernel(now=True)\n")
        result = under(self, self.profile, python, "-c", script, cwd=str(self.project), env=self.env)
        self.assertEqual(0, result.returncode, result.stderr[-800:])
        self.assertEqual("42", result.stdout.strip().splitlines()[-1])


class LinuxSessionPidTests(unittest.TestCase):
    """The pid the launcher was started as is the session's own."""

    def test_the_namespace_is_entered_without_a_fork(self):
        process = mock.Mock()
        with mock.patch.object(jail.shutil, "which", return_value="/usr/bin/unshare"), \
                mock.patch.object(jail, "_namespace_problem", return_value=""), \
                mock.patch.object(jail.subprocess, "Popen", return_value=process), \
                mock.patch.object(jail, "_wait_for_relay", return_value=True), \
                mock.patch.object(jail, "_wait_for_port_file", return_value=49152):
            plan = jail._linux(network.resolve("", {}), {}, 43210, sys.executable)
        unshare = plan.prefix[:plan.prefix.index("--")]
        self.assertEqual(["/usr/bin/unshare", "--user", "--map-root-user", "--net"], unshare)
        self.assertNotIn("--fork", plan.prefix)

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("unshare"),
                         "Linux's unshare")
    def test_sigterm_to_the_launchers_pid_ends_the_session(self):
        if subprocess.run(["unshare", "--user", "--map-root-user", "--net", "--", "/bin/true"],
                          capture_output=True).returncode != 0:
            self.skipTest("this system does not allow unprivileged user namespaces")
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        port = start_proxy(self, "elm.example", temporary.name)
        env = {"TMPDIR": temporary.name}
        plan = jail.plan(network.resolve("", env), str(ROOT), env, port, sys.executable)
        for relay in plan.cleanup:
            self.addCleanup(relay.wait, 5)
            self.addCleanup(relay.terminate)
        session = subprocess.Popen(plan.prefix + ["/bin/sleep", "300"],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.PIPE)
        self.addCleanup(session.stderr.close)
        self.addCleanup(session.kill)
        comm = Path("/proc/%d/comm" % session.pid)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and session.poll() is None \
                and comm.read_text().strip() != "sleep":
            time.sleep(0.05)
        self.assertIsNone(session.poll(), session.stderr.read() if session.poll() is not None else "")
        self.assertEqual("sleep", comm.read_text().strip())      # the pid is the session's
        session.send_signal(signal.SIGTERM)
        self.assertEqual(-signal.SIGTERM, session.wait(timeout=5))


class LinuxNamespaceRefusalTests(unittest.TestCase):
    """A system that will not make the namespace says so before the hand-over."""

    DENIED = "unshare: write failed /proc/self/uid_map: Operation not permitted"

    def test_a_refused_namespace_is_a_refusal_with_the_way_to_allow_it(self):
        started = mock.Mock()
        with mock.patch.object(jail.shutil, "which", return_value="/usr/bin/unshare"), \
                mock.patch.object(jail, "_namespace_problem", return_value=self.DENIED), \
                mock.patch.object(jail.subprocess, "Popen", started):
            with self.assertRaises(Refusal) as caught:
                jail._linux(network.resolve("", {}), {}, 43210, sys.executable)
        said = "\n".join(caught.exception.lines)
        self.assertEqual(1, caught.exception.code)
        self.assertEqual(jail.refusal(jail.namespace_reason(self.DENIED)), caught.exception.lines)
        self.assertIn("unshare said: " + self.DENIED, said)
        self.assertIn("ELM_PI_NO_JAIL=1", said)
        started.assert_not_called()                       # no relay left behind

    def test_the_probe_reports_what_unshare_said(self):
        with tempfile.TemporaryDirectory() as tmp:
            refuses = write(Path(tmp) / "unshare", "#!/bin/sh\necho 'unshare: write failed "
                            "/proc/self/uid_map:   Operation not permitted' >&2\nexit 1\n", 0o755)
            allows = write(Path(tmp) / "allows", "#!/bin/sh\nexit 0\n", 0o755)
            silent = write(Path(tmp) / "silent", "#!/bin/sh\nexit 3\n", 0o755)
            self.assertEqual(self.DENIED, jail._namespace_problem(str(refuses)))
            self.assertEqual("", jail._namespace_problem(str(allows)))
            self.assertEqual("exit status 3", jail._namespace_problem(str(silent)))
            self.assertIn("No such file", jail._namespace_problem(str(Path(tmp) / "missing")))

    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("unshare"),
                         "Linux's unshare")
    def test_the_launcher_agrees_with_this_system(self):
        # Whichever this machine is: a namespace it makes is no problem, and
        # one it refuses is reported in unshare's own words.
        works = subprocess.run(["unshare", "--user", "--map-root-user", "--net", "--", "true"],
                               capture_output=True, text=True)
        problem = jail._namespace_problem(shutil.which("unshare"))
        if works.returncode == 0:
            self.assertEqual("", problem)
        else:
            self.assertEqual(" ".join(works.stderr.split()), problem)
            env = {"TMPDIR": tempfile.gettempdir()}
            with self.assertRaises(Refusal) as caught:
                jail.plan(network.resolve("", env), str(ROOT), env, 43210, sys.executable)
            self.assertIn("needs the OS fence, and this machine cannot make one", caught.exception.lines[0])


class NamespaceAdviceTests(unittest.TestCase):
    """What a machine that cannot fence a session is told, and when."""

    def test_wsl_1_is_told_to_convert_and_not_to_set_a_sysctl(self):
        said = "\n".join(jail.namespace_reason("unshare: unshare failed: Invalid argument",
                                               release="4.4.0-26100-Microsoft"))
        self.assertIn("This is WSL 1, which has no namespaces", said)
        self.assertIn("wsl --set-version <distribution> 2", said)
        self.assertNotIn("sysctl", said)

    def test_wsl_2_and_ordinary_kernels_get_the_sysctl(self):
        for release in ("6.6.87.2-microsoft-standard-WSL2", "7.0.0-43-generic"):
            said = "\n".join(jail.namespace_reason("denied", release=release))
            self.assertIn("kernel.apparmor_restrict_unprivileged_userns=0", said)
            self.assertNotIn("WSL 1", said)

    def test_the_reason_is_the_same_for_the_installer_the_warning_and_the_refusal(self):
        with mock.patch.object(jail.sys, "platform", "linux"), \
                mock.patch.object(jail.shutil, "which", return_value="/usr/bin/unshare"):
            with mock.patch.object(jail, "_namespace_problem", return_value=""):
                self.assertEqual([], jail.fence_problem())
            with mock.patch.object(jail, "_namespace_problem", return_value="denied"):
                reason = jail.fence_problem()
                self.assertEqual(jail.namespace_reason("denied"), reason)
        for line in reason:
            self.assertIn("    " + line, jail.warning(reason))
            self.assertIn("    " + line, jail.refusal(reason))
        with mock.patch.object(jail.sys, "platform", "linux"), \
                mock.patch.object(jail.shutil, "which", return_value=None):
            self.assertIn("unshare, which is part of util-linux, is missing", jail.fence_problem()[0])
        with mock.patch.object(jail.sys, "platform", "darwin"), \
                mock.patch.object(jail.os, "access", return_value=False):
            self.assertIn("sandbox-exec", jail.fence_problem()[0])

    def test_this_machine_gets_an_answer_that_matches_what_it_can_do(self):
        problem = jail.fence_problem()
        if sys.platform == "darwin" and os.access(jail.SANDBOX_EXEC, os.X_OK):
            self.assertEqual([], problem)
        elif sys.platform.startswith("linux") and shutil.which("unshare"):
            works = subprocess.run(["unshare", "--user", "--map-root-user", "--net", "--", "true"],
                                   capture_output=True).returncode == 0
            self.assertEqual(works, problem == [])

    def test_bootstrap_says_it_before_done_and_only_warns(self):
        source = (ROOT / "bootstrap.bash").read_text()
        check = source.index("jail.fence_problem()")
        self.assertLess(source.index('say "verifying the ELM-only policy"'), check)
        self.assertLess(check, source.index('say "done"'))
        block = source[source.index('FENCE_PROBLEM="$('):source.index('say "done"')]
        self.assertIn("|| true", block)          # a failed check never fails an install
        self.assertNotIn("die ", block)

    def test_bootstraps_check_runs_as_written(self):
        source = (ROOT / "bootstrap.bash").read_text()
        begin = source.index("<<'PY' || true\nimport sys\nsys.path.insert(0, sys.argv[1])\nfrom elmpi import jail")
        script = source[source.index("\n", begin) + 1:source.index("\nPY\n", begin)]
        result = subprocess.run([sys.executable, "-E", "-S", "-", str(ROOT / "python")], input=script,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("\n".join(jail.fence_problem()), result.stdout.strip("\n"))


class NetworkLineTests(unittest.TestCase):
    """"enforced by the OS" is said only of a run that will be."""

    def test_the_line_follows_what_the_run_will_really_have(self):
        offline, trusted = network.resolve("offline", {}), network.resolve("", {})
        self.assertEqual("network: offline - the ELM gateway only, enforced by the OS",
                         network.describe(offline, {}))
        self.assertEqual("network: offline - the ELM gateway only; no OS fence (ELM_PI_NO_JAIL)",
                         network.describe(offline, {"ELM_PI_NO_JAIL": "1"}))
        self.assertTrue(network.describe(trusted, {"ELM_PI_NO_JAIL": "1"}).endswith(
            "through this install's proxy; no OS fence (ELM_PI_NO_JAIL)"))
        self.assertEqual("network: trusted-remote asked for, but ELM_PI_NO_PROXY=1 - no proxy and "
                         "no OS fence, so nothing is filtered",
                         network.describe(trusted, {"ELM_PI_NO_PROXY": "1"}))
        self.assertNotIn("enforced", network.describe(network.resolve("yolo", {}), {}))

    def test_both_launchers_print_it(self):
        expected = {
            "ELM_PI_NO_JAIL": "    network: offline - the ELM gateway only; no OS fence (ELM_PI_NO_JAIL)",
            "ELM_PI_NO_PROXY": "    network: offline asked for, but ELM_PI_NO_PROXY=1 - no proxy and "
                               "no OS fence, so nothing is filtered",
        }
        for launcher in LAUNCHERS:
            for name, line in expected.items():
                with self.subTest(launcher=launcher.name, name=name), \
                        tempfile.TemporaryDirectory() as tmp:
                    fixture = Fixture(Path(tmp), launcher=launcher)
                    shutil.copy2(ROOT / "proxy/egress.py", fixture.root / "proxy/egress.py")
                    env = {"ELM_PI_NO_PROXY": "", "ELM_PI_NO_JAIL": ""}
                    env[name] = "1"
                    result = fixture.run("--offline", "-p", "x", env=env)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn(line, result.stderr.splitlines())
                    self.assertNotIn("enforced by the OS", result.stderr)


NO_FENCE = ["this machine has no fence, says the test.", "    and how to get one"]
# What a machine without a fence answers, put into the fixture's own copy of the
# launcher: both launchers ask python/elmpi/jail.py.
WITHOUT_A_FENCE = "\ndef fence_problem():\n    return %r\n" % (NO_FENCE,)


class UnfencedFallbackTests(unittest.TestCase):
    """A machine that cannot make the fence: a warning and a session, or - for
    offline - a refusal. No warning for someone who chose to run unfenced."""

    RECORD = ("ELM_PI_NO_JAIL", "ELM_PI_UNFENCED", "HTTPS_PROXY", "PI_ELM_NETWORK", "ELM_PI_FENCED")

    def launch(self, launcher, *args, fence=False, files=None, **env):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        fixture = Fixture(Path(temporary.name), launcher=launcher)
        shutil.copy2(ROOT / "proxy/egress.py", fixture.root / "proxy/egress.py")
        if not fence:
            with (fixture.root / "python/elmpi/jail.py").open("a") as handle:
                handle.write(WITHOUT_A_FENCE)
        else:   # a machine with one, whatever this one is: the fence itself is not run here
            with (fixture.root / "python/elmpi/jail.py").open("a") as handle:
                handle.write("\ndef fence_problem():\n    return []\n"
                             "\ndef plan(*args):\n    return Plan([], '')\n")
        for name, text in (files or {}).items():
            write(fixture.root / name, text)
        settings = {"ELM_PI_NO_PROXY": "", "ELM_PI_NO_JAIL": ""}
        settings.update(env)
        result = fixture.run(*args, env=settings, record=self.RECORD)
        result.root = fixture.root
        return result

    def test_the_default_mode_starts_unfenced_behind_its_proxy_with_a_warning(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                result = self.launch(launcher, "-p", "x")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(["-p", "x"], result.args_seen[-2:])                 # pi ran
                lines = result.stderr.splitlines()
                at = lines.index("pi: ⚠  WARNING - this session is NOT fenced by the OS.")
                self.assertEqual(["    " + line for line in NO_FENCE], lines[at + 1:at + 3])
                self.assertIn("proxy still filters", lines[at + 3])
                # said straight after the line it corrects, which no longer claims a fence
                self.assertTrue(lines[at - 1].startswith("    network: trusted-remote - "), lines[at - 1])
                self.assertTrue(lines[at - 1].endswith("; NOT fenced by the OS"), lines[at - 1])
                self.assertNotIn("enforced by the OS", result.stderr)
                seen = result.env_seen
                self.assertEqual(("1", "fallback", "trusted-remote", "__unset__"),
                                 (seen["ELM_PI_NO_JAIL"], seen["ELM_PI_UNFENCED"],
                                  seen["PI_ELM_NETWORK"], seen["ELM_PI_FENCED"]))
                self.assertRegex(seen["HTTPS_PROXY"], r"^http://127\.0\.0\.1:\d+$")   # still filtered

    def test_no_warning_when_running_unfenced_was_asked_for(self):
        for launcher in LAUNCHERS:
            for args, env in ((("-p", "x"), {"ELM_PI_NO_JAIL": "1"}), (("--remote", "-p", "x"), {}),
                              (("-p", "x"), {"PI_ELM_NETWORK": "yolo"}),
                              (("-p", "x"), {"ELM_PI_NO_PROXY": "1"})):
                with self.subTest(launcher=launcher.name, args=args, env=env):
                    result = self.launch(launcher, *args, **env)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertNotIn("WARNING", result.stderr)
                    self.assertNotIn(NO_FENCE[0], result.stderr)
                    self.assertEqual("__unset__", result.env_seen["ELM_PI_UNFENCED"])

    def test_offline_is_refused_with_the_reason(self):
        for launcher in LAUNCHERS:
            for args, env in ((("--offline", "-p", "x"), {}), (("-p", "x"), {"PI_ELM_NETWORK": "offline"})):
                with self.subTest(launcher=launcher.name, args=args, env=env):
                    result = self.launch(launcher, *args, **env)
                    self.assertEqual(1, result.returncode, result.stderr)
                    self.assertEqual([], result.args_seen)
                    lines = result.stderr.splitlines()
                    at = lines.index("pi: pi --offline needs the OS fence, and this machine cannot make one:")
                    self.assertEqual(["    " + line for line in NO_FENCE], lines[at + 1:at + 3])
                    self.assertIn("ELM_PI_NO_JAIL=1 pi ...", lines[at + 3])
                    self.assertNotIn("WARNING", result.stderr)

    def test_offline_unfenced_is_still_there_for_someone_who_asks_for_it(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                result = self.launch(launcher, "--offline", "-p", "x", ELM_PI_NO_JAIL="1")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("    network: offline - the ELM gateway only; no OS fence (ELM_PI_NO_JAIL)",
                              result.stderr.splitlines())

    def test_a_command_that_is_not_a_session_runs_without_the_warning(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                result = self.launch(launcher, "--version")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual(["--version"], result.args_seen[-1:])
                self.assertNotIn("WARNING", result.stderr)

    def test_a_run_started_from_that_session_is_not_warned_again(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                result = self.launch(launcher, "-p", "x", ELM_PI_NO_JAIL="1", ELM_PI_UNFENCED="fallback",
                                     PI_ELM_CHILD="1")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertNotIn("WARNING", result.stderr)
                self.assertEqual("fallback", result.env_seen["ELM_PI_UNFENCED"])      # and it knows why
                self.assertIn("; NOT fenced by the OS", result.stderr)

    def test_offline_typed_inside_that_session_is_refused_as_it_is_outside(self):
        inherited = {"ELM_PI_NO_JAIL": "1", "ELM_PI_UNFENCED": "fallback", "PI_ELM_CHILD": "1"}
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                result = self.launch(launcher, "--offline", "-p", "x", **inherited)
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertEqual([], result.args_seen)
                self.assertIn("pi: pi --offline needs the OS fence, and this machine cannot make one:",
                              result.stderr.splitlines())
            with self.subTest(launcher=launcher.name, case="the session went offline with /network"):
                # ...which sets PI_ELM_NETWORK for what the session starts: those runs are its own
                result = self.launch(launcher, "-p", "x", PI_ELM_NETWORK="offline", **inherited)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("    network: offline - the ELM gateway only; NOT fenced by the OS",
                              result.stderr.splitlines())
            with self.subTest(launcher=launcher.name, case="the machine can fence now"):
                result = self.launch(launcher, "--offline", "-p", "x", fence=True, **inherited)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("    network: offline - the ELM gateway only, enforced by the OS",
                              result.stderr.splitlines())
                self.assertEqual("__unset__", result.env_seen["ELM_PI_UNFENCED"])

    def test_a_marker_left_in_a_shell_is_not_this_launchs_answer(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                result = self.launch(launcher, "-p", "x", fence=True, ELM_PI_UNFENCED="fallback")
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertEqual("__unset__", result.env_seen["ELM_PI_UNFENCED"])
                self.assertIn("enforced by the OS", result.stderr)

    def test_a_machine_with_a_fence_is_not_warned(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                result = self.launch(launcher, "-p", "x", fence=True)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertNotIn("WARNING", result.stderr)
                self.assertIn(result.env_seen["ELM_PI_NO_JAIL"], ("", "__unset__"))

    def test_both_launchers_say_the_same_thing(self):
        for args in (("-p", "x"), ("--offline", "-p", "x")):
            said = []
            for launcher in LAUNCHERS:
                result = self.launch(launcher, *args)
                said.append((result.returncode, [line for line in result.stderr.splitlines()
                                                 if "permission mode" not in line]))
            self.assertEqual(said[0], said[1])

    def test_inside_a_fenced_session_nothing_is_asked_of_the_machine(self):
        self.assertEqual([], jail.unavailable(network.resolve("", {}), {network.FENCED_ENV: "40123"}))
        with mock.patch.object(jail, "fence_problem", return_value=NO_FENCE) as asked:
            for env, flag in (({"ELM_PI_NO_JAIL": "1"}, ""), ({"ELM_PI_NO_PROXY": "1"}, ""), ({}, "yolo")):
                self.assertEqual([], jail.unavailable(network.resolve(flag, env), env))
            asked.assert_not_called()
            self.assertEqual(NO_FENCE, jail.unavailable(network.resolve("", {}), {}))


class SavedNetworkDefaultTests(UnfencedFallbackTests):
    """agent/network-mode, which /network writes: below a flag and a shell's
    PI_ELM_NETWORK, above trusted-remote."""

    RECORD = ("PI_ELM_NETWORK", "PI_ELM_NETWORK_DEFAULT")

    def mode(self, launcher, *args, saved=None, **env):
        files = {"agent/network-mode": saved} if saved is not None else None
        result = self.launch(launcher, *args, "-p", "x", fence=True, files=files, **env)
        self.assertEqual(0, result.returncode, result.stderr)
        return result.env_seen["PI_ELM_NETWORK"], result.env_seen["PI_ELM_NETWORK_DEFAULT"]

    def test_the_order_is_flag_then_shell_then_saved_then_trusted_remote(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                self.assertEqual(("trusted-remote", "trusted-remote"), self.mode(launcher))
                self.assertEqual(("offline", "offline"), self.mode(launcher, saved="offline\n"))
                self.assertEqual(("yolo", "yolo"), self.mode(launcher, saved="yolo\n"))
                self.assertEqual(("trusted-remote", "offline"),
                                 self.mode(launcher, "--trusted-remote", saved="offline\n"))
                self.assertEqual(("yolo", "offline"), self.mode(launcher, saved="offline\n", PI_ELM_NETWORK="yolo"))
                self.assertEqual(("offline", "yolo"), self.mode(launcher, "--offline", saved="yolo\n"))

    def test_a_file_that_names_no_mode_says_nothing(self):
        for launcher in LAUNCHERS:
            for text in ("", "\n", "everything\n", "yolo please\n"):
                with self.subTest(launcher=launcher.name, text=text):
                    self.assertEqual(("trusted-remote", "trusted-remote"), self.mode(launcher, saved=text))
            with self.subTest(launcher=launcher.name, text="spaces"):
                self.assertEqual(("offline", "offline"), self.mode(launcher, saved="  offline  \nyolo\n"))

    def test_computer_use_comes_with_a_run_that_asked_for_the_network_not_with_a_saved_default(self):
        extension = "agent/npm/node_modules/@injaneity/pi-computer-use/extensions/computer-use.ts"
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name):
                saved = self.launch(launcher, "-p", "x", fence=True,
                                    files={extension: "\n", "agent/network-mode": "yolo\n"})
                asked = self.launch(launcher, "--remote", "-p", "x", fence=True, files={extension: "\n"})
                self.assertEqual((0, 0), (saved.returncode, asked.returncode), saved.stderr + asked.stderr)
                self.assertNotIn(str(saved.root / extension), saved.args_seen)
                self.assertIn(str(asked.root / extension), asked.args_seen)
                self.assertIn("network: yolo", saved.stderr)

    def test_resolve_names_where_the_mode_came_from(self):
        self.assertEqual(("offline", "saved"), (lambda m: (m.name, m.source))(network.resolve("", {}, "offline")))
        self.assertEqual("default", network.resolve("", {}, "nonsense").source)
        self.assertEqual("flag", network.resolve("yolo", {"PI_ELM_NETWORK": "offline"}, "offline").source)


# The inherited cases are the fallback's; run once, there.
for _name in [name for name in dir(UnfencedFallbackTests) if name.startswith("test_")]:
    setattr(SavedNetworkDefaultTests, _name, None)


class GateMessageTests(unittest.TestCase):
    """The refusal for a moved gate entry point names the file that holds it."""

    def test_the_python_launcher_names_the_file_that_defines_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in extensions.POLICY_EXTENSIONS:
                write(Path(tmp) / "agent/extensions" / (name + ".ts"), "\n")
            (Path(tmp) / extensions.GATE_PACKAGE).mkdir(parents=True)
            with self.assertRaises(Refusal) as caught:
                extensions._policy_arguments(tmp)
        named = os.path.join(tmp, "python", "elmpi", "extensions.py")
        self.assertIn("GATE_ENTRY in %s needs the new path" % named, "\n".join(caught.exception.lines))
        self.assertIn("\nGATE_ENTRY = ", (ROOT / "python/elmpi/extensions.py").read_text())

    def test_both_launchers_print_the_same_line(self):
        for launcher in LAUNCHERS:
            with self.subTest(launcher=launcher.name), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp), launcher=launcher)
                fixture.gate.unlink()
                result = fixture.run("--fast", "-p", "x")
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertEqual([], result.args_seen)
                self.assertIn("    GATE_ENTRY in %s needs the new path; otherwise: pi update "
                              "--extensions" % (fixture.root / "python/elmpi/extensions.py"),
                              result.stderr.splitlines())


if __name__ == "__main__":
    unittest.main()
