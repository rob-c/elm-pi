import importlib.util
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class ShimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shim = load_module("elm_pi_shim_test", ROOT / "shim/shim.py")

    def test_extracts_valid_call_from_prose(self):
        calls, leftover = self.shim.extract_call(
            'I will act now: {"name":"read","arguments":{"path":"a.py"}} done.',
            {"read"},
        )
        self.assertEqual("", leftover)
        self.assertEqual("read", calls[0]["function"]["name"])
        self.assertEqual({"path": "a.py"}, json.loads(calls[0]["function"]["arguments"]))

    def test_rejects_unknown_call(self):
        calls, leftover = self.shim.extract_call('{"name":"upload","arguments":{}}', {"read"})
        self.assertIsNone(calls)
        self.assertIn("upload", leftover)


class ProxyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proxy = load_module("elm_pi_proxy_test", ROOT / "proxy/egress.py")

    def test_allowlist_is_exact_or_subdomain(self):
        proxy = self.proxy.Proxy(["elm.edina.ac.uk"], "/dev/null")
        self.assertTrue(proxy.allowed("elm.edina.ac.uk"))
        self.assertTrue(proxy.allowed("api.elm.edina.ac.uk"))
        self.assertFalse(proxy.allowed("evilelm.edina.ac.uk"))
        self.assertFalse(proxy.allowed("example.com"))


class PermissionTests(unittest.TestCase):
    def test_private_state_modes_and_shared_opt_out(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "install"
            session = root / "project/.pi/sessions"
            memory = install / "agent/projects-memory"
            memory.mkdir(parents=True)
            session.mkdir(parents=True)
            auth = install / "agent/auth.json"
            auth.write_text('{"token":"test"}\n')
            transcript = session / "session.jsonl"
            transcript.write_text("test\n")
            database = memory / "sessions.db"
            database.write_text("test\n")
            unrelated = session / "notes.txt"
            unrelated.write_text("leave my mode alone\n")
            for path in (install / "agent", memory, session):
                os.chmod(path, 0o755)
            for path in (auth, transcript, database, unrelated):
                os.chmod(path, 0o644)

            script = f'''
source "{ROOT}/lib/state.sh"
elm_set_auth_mode "{auth}" 0
elm_secure_runtime_state "{install}" "{session}"
'''
            subprocess.run(["bash", "-c", script], check=True)
            self.assertEqual(0o400, stat.S_IMODE(auth.stat().st_mode))
            for path in (install / "agent", memory, session):
                self.assertEqual(0o700, stat.S_IMODE(path.stat().st_mode), path)
            for path in (transcript, database):
                self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode), path)
            self.assertEqual(0o644, stat.S_IMODE(unrelated.stat().st_mode))

            os.chmod(transcript, 0o644)
            subprocess.run(
                ["bash", "-c", f'source "{ROOT}/lib/state.sh"; ELM_PI_SHARED_STATE=1 elm_secure_runtime_state "{install}" "{session}"'],
                check=True,
            )
            self.assertEqual(0o644, stat.S_IMODE(transcript.stat().st_mode))

    def test_session_path_normalization_matches_tilde_relative_and_file_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            home = root / "home"
            cwd = root / "work"
            home.mkdir()
            cwd.mkdir()

            def normalize(value: str) -> str:
                command = f'source "{ROOT}/lib/state.sh"; elm_normalize_session_dir "$1" "$2"'
                return subprocess.run(
                    ["bash", "-c", command, "normalize", value, str(cwd)],
                    check=True,
                    text=True,
                    capture_output=True,
                    env={**os.environ, "HOME": str(home)},
                ).stdout.strip()

            self.assertEqual(str(home / "sessions"), normalize("~/sessions"))
            self.assertEqual(str(cwd / "relative/sessions"), normalize("relative/sessions"))
            self.assertEqual("/tmp/space here", normalize("file:///tmp/space%20here"))

    def test_install_hardening_honors_shared_state(self):
        with tempfile.TemporaryDirectory() as directory:
            install = Path(directory)
            memory = install / "agent/projects-memory"
            memory.mkdir(parents=True)
            data = memory / "sessions.db"
            data.write_text("test\n")
            os.chmod(install / "agent", 0o770)
            os.chmod(memory, 0o770)
            os.chmod(data, 0o660)
            subprocess.run(
                [
                    "bash",
                    "-c",
                    f'source "{ROOT}/lib/state.sh"; ELM_PI_SHARED_STATE=1 elm_secure_install_state "{install}"',
                ],
                check=True,
            )
            self.assertEqual(0o770, stat.S_IMODE((install / "agent").stat().st_mode))
            self.assertEqual(0o770, stat.S_IMODE(memory.stat().st_mode))
            self.assertEqual(0o660, stat.S_IMODE(data.stat().st_mode))

