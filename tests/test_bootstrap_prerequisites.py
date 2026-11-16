"""bootstrap.sh run on its own, on a machine without curl.

install.sh checks for curl and tar before it fetches the source. bootstrap.sh is
also an entry point - a clone, `pi setup`, a copied tree - and had no check: on
Ubuntu 26.04, which ships without curl, it printed its first four steps and
ended as "./bootstrap.sh: line 329: curl: command not found", exit 127
(measured in a VM, 2026-11-16).

bootstrap.sh puts /usr/bin on PATH itself, so a missing curl cannot be staged by
running the whole script; the block is run as bootstrap.sh has it, with the
script's own say/warn/die and a PATH that holds only what the case provides.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "bootstrap.bash").read_text()
START = 'MISSING_TOOLS=""\n'
END = "\nfi\n"


def block():
    begin = SOURCE.index(START)
    return SOURCE[begin:SOURCE.index(END, begin) + len(END)]


def helpers():
    lines = [line for line in SOURCE.splitlines()
             if line.startswith(("say()", "warn()", "die()"))]
    assert len(lines) == 3, lines
    return "\n".join(lines) + "\n"


class BootstrapPrerequisiteTests(unittest.TestCase):
    def run_block(self, tools, system="Linux"):
        with tempfile.TemporaryDirectory() as tmp:
            for name in tools:
                path = Path(tmp) / name
                path.write_text("#!/bin/sh\nexit 0\n")
                path.chmod(0o755)
            uname = Path(tmp) / "uname"
            uname.write_text("#!/bin/sh\necho %s\n" % system)
            uname.chmod(0o755)
            script = 'HERE=/opt/elm-pi\n' + helpers() + block() + 'echo "went on"\n'
            return subprocess.run(["/bin/bash", "-c", script], env={"PATH": tmp},
                                  capture_output=True, text=True, timeout=30)

    def test_with_both_tools_nothing_is_said_and_the_install_goes_on(self):
        result = self.run_block(["curl", "tar"])
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("went on\n", result.stdout)
        self.assertEqual("", result.stderr)

    def test_without_curl_it_stops_with_the_command_that_installs_it(self):
        result = self.run_block(["tar"])
        self.assertEqual(1, result.returncode)
        self.assertNotIn("went on", result.stdout)
        self.assertIn("missing required tool(s): curl\n", result.stdout.replace("\033[0m", ""))
        self.assertIn("sudo apt install -y curl tar", result.stdout)
        self.assertIn("sudo dnf install -y curl tar", result.stdout)
        self.assertIn("ERROR: install the tools above, then run /opt/elm-pi/bootstrap.sh again "
                      "- nothing has been downloaded or changed", result.stderr)
        self.assertNotIn("command not found", result.stderr)

    def test_both_missing_are_named_together(self):
        result = self.run_block([])
        self.assertEqual(1, result.returncode)
        self.assertIn("missing required tool(s): curl tar\n", result.stdout.replace("\033[0m", ""))

    def test_on_a_mac_it_names_the_command_line_tools(self):
        result = self.run_block(["curl"], system="Darwin")
        self.assertEqual(1, result.returncode)
        self.assertIn("xcode-select --install", result.stdout)
        self.assertNotIn("apt install", result.stdout)

    def test_the_check_comes_before_anything_is_fetched_or_printed(self):
        check = SOURCE.index(START)
        for later in ("elm_curl_retry   #", 'say "Python"', "curl -q "):
            self.assertLess(check, SOURCE.index(later), later)
        # after the functions it uses, and after PATH is the install's own
        self.assertGreater(check, SOURCE.index("die()  {"))
        self.assertGreater(check, SOURCE.index('elm_install_env "$HERE"'))

    def test_it_asks_for_the_tools_install_sh_asks_for(self):
        installer = (ROOT / "install.sh").read_text()
        self.assertIn("for t in curl tar; do", installer)
        self.assertIn("for _tool in curl tar; do", block())


if __name__ == "__main__":
    unittest.main()
