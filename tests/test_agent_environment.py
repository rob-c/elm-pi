"""What the agent can use beyond pi: its own Python, containers, computer use.

- The agent's Python (agent/python, built with uv) goes on PATH unless pi was
  started from an environment of the researcher's own, and PyPI is on the
  proxy's list so it can install into it.
- Docker/Podman may run only with --network=none, and never push, log in or
  use a remote engine. The rules are evaluated here the way
  pi-permission-system does: glob to regex, last match wins.
- Computer use loads only in a `pi --remote` main session.
"""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
LAUNCHER = (ROOT / "pi").read_text()
BOOTSTRAP = (ROOT / "bootstrap.sh").read_text()


def block(source, start, end):
    return source[source.index(start):source.index(end)]


def bash_rule(command):
    """pi-permission-system's bash decision: wildcard patterns, last match wins."""
    rules = json.loads((ROOT / "templates/extensions/pi-permission-system/config.json").read_text())["permission"]["bash"]
    decision = None
    for pattern, rule in rules.items():
        regex = ".*".join(re.escape(part).replace("\\ ", " ").replace("\\?", ".") for part in pattern.split("*"))
        if regex.endswith(" .*"):
            regex = regex[:-3] + "( .*)?"
        if re.fullmatch(regex, command, re.S):
            decision = rule if isinstance(rule, str) else rule["action"]
    return decision


class ContainerRuleTests(unittest.TestCase):
    def test_containers_run_only_without_a_network(self):
        cases = {
            "docker run --rm -v /p:/work img latexmk main.tex": "deny",
            "docker run --rm --network=none -v /p:/work -w /work texlive/texlive:latest latexmk -pdf main.tex": "allow",
            "docker run --network none img true": "allow",
            "docker container run --net=none img true": "allow",
            "docker create img": "deny",
            "podman run --rm --userns=keep-id img true": "deny",
            "podman run --rm --network=none --userns=keep-id img true": "allow",
            "docker run --network=host img": "deny",
        }
        for command, want in cases.items():
            with self.subTest(command=command):
                self.assertEqual(want, bash_rule(command))

    def test_images_may_be_pulled_and_inspected(self):
        for command in ("docker pull texlive/texlive:latest", "podman pull pandoc/latex", "docker images",
                        "docker info", "podman machine start", "docker ps -a"):
            with self.subTest(command=command):
                self.assertEqual("allow", bash_rule(command))

    def test_nothing_leaves_through_a_registry_or_a_remote_engine(self):
        for command in ("docker push me/data:1", "podman push me/data", "docker image push me/x",
                        "docker login", "podman login quay.io", "docker buildx build --push -t me/x .",
                        "docker -H ssh://host run --network=none img", "docker --context remote ps",
                        "docker context use remote", "podman --remote run --network=none img",
                        "podman --connection box ps", "podman system connection add box ssh://h"):
            with self.subTest(command=command):
                self.assertEqual("deny", bash_rule(command))

    def test_builds_ask_because_run_steps_have_a_network(self):
        for command in ("docker build -t x .", "podman build .", "docker compose up", "docker-compose up"):
            with self.subTest(command=command):
                self.assertEqual("ask", bash_rule(command))

    def test_the_rest_of_the_policy_is_unchanged(self):
        self.assertEqual("deny", bash_rule("ssh host"))
        self.assertEqual("allow", bash_rule("ls -la"))
        self.assertEqual("ask", bash_rule("git push origin main"))

    def test_denials_point_at_the_skill(self):
        rules = json.loads((ROOT / "templates/extensions/pi-permission-system/config.json").read_text())["permission"]["bash"]
        self.assertIn("containers skill", rules["docker run *"]["reason"])
        self.assertIn('-v "$PWD":"$PWD" -w "$PWD"', rules["docker run *"]["reason"])

    def test_the_skill_mounts_the_project_at_its_own_path(self):
        # A container-side path such as /work is a folder outside the project to
        # the permission gate, which asks - and a sub-agent cannot answer.
        skill = (ROOT / "templates/skills/containers/SKILL.md").read_text()
        self.assertIn('--network=none -v "$PWD":"$PWD" -w "$PWD"', skill)
        self.assertNotIn(":/work", skill)


class ProxyListTests(unittest.TestCase):
    def test_pypi_and_the_registries_are_on_the_list_for_every_session(self):
        hosts = CONFIG["proxyAllow"]["hosts"]
        for host in ("pypi.org", "files.pythonhosted.org", "docker.io", "ghcr.io", "quay.io"):
            self.assertIn(host, hosts)
        self.assertIn('"ELM_PROXY_ALLOW"', (ROOT / "scripts/elm_config.py").read_text())
        self.assertIn('PROXY_ALLOW="$ELM_HOST${ELM_PROXY_ALLOW:+,$ELM_PROXY_ALLOW}', LAUNCHER)


class AgentPythonTests(unittest.TestCase):
    SNIPPET = block(LAUNCHER, "# --- the agent's Python", "# --- where jiti")

    def path_after(self, env_exists=True, **env):
        here = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(here)])
        if env_exists:
            (here / "agent/python/env/bin").mkdir(parents=True)
            python = here / "agent/python/env/bin/python"
            python.write_text("#!/bin/sh\n")
            python.chmod(0o755)
        script = f'HERE="$1"; PATH="$HERE/agent/bin:/usr/bin:/bin"\n{self.SNIPPET}\nprintf %s "$PATH"'
        clean = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "CONDA_DEFAULT_ENV")}
        out = subprocess.run(["bash", "-c", script, "t", str(here)], env={**clean, **env},
                             capture_output=True, text=True, check=True).stdout
        return out.replace(str(here), "$HERE").split(":")

    def test_on_path_after_agent_bin(self):
        self.assertEqual(["$HERE/agent/bin", "$HERE/agent/python/env/bin", "/usr/bin", "/bin"], self.path_after())
        self.assertIn("$HERE/agent/python/env/bin", self.path_after(CONDA_DEFAULT_ENV="base"))

    def test_the_researchers_own_environment_stays_first(self):
        self.assertNotIn("$HERE/agent/python/env/bin", self.path_after(VIRTUAL_ENV="/p/.venv"))
        self.assertNotIn("$HERE/agent/python/env/bin", self.path_after(CONDA_DEFAULT_ENV="analysis"))

    def test_an_install_without_it_is_unchanged(self):
        self.assertEqual(["$HERE/agent/bin", "/usr/bin", "/bin"], self.path_after(env_exists=False))

    def test_bootstrap_builds_it_with_a_pinned_checksummed_uv(self):
        self.assertIn('TOOLSET="${ELM_PI_TOOLS:-fd,rg,jq,yq,shellcheck,ast-grep,uv}"', BOOTSTRAP)
        version = re.search(r'UV_VERSION="\$\{UV_VERSION:-([0-9.]+)\}"', BOOTSTRAP).group(1)
        sums = (ROOT / "templates/tools.sha256").read_text()
        for triple in ("aarch64-apple-darwin", "x86_64-apple-darwin", "aarch64-unknown-linux-musl", "x86_64-unknown-linux-musl"):
            self.assertIn(f"uv/{version}/uv-{triple}.tar.gz", sums)
        self.assertEqual(3, BOOTSTRAP.count("--no-tools|--no-patch|--no-python)") + BOOTSTRAP.count("--no-python) WITH_PYTHON=0"))
        self.assertIn("uv venv --quiet --seed --managed-python", BOOTSTRAP)
        self.assertTrue(CONFIG["python"]["packages"])


class ComputerUseTests(unittest.TestCase):
    SNIPPET = block(LAUNCHER, "# --- computer use, with --remote only", 'LLAMA_MODEL="elm-shim/')

    def run_block(self, remote, child=False):
        here = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(here)])
        ext = here / "agent/npm/node_modules/@injaneity/pi-computer-use/extensions/computer-use.ts"
        ext.parent.mkdir(parents=True)
        ext.write_text("")
        script = (f'HERE="$1"; REMOTE="$2"; PRE=()\n{self.SNIPPET}\n'
                  'printf "%s\\n" "${PRE[@]+"${PRE[@]}"}" "SIGN=${PI_COMPUTER_USE_CODESIGN_IDENTITY:-}" '
                  '"APP=${PI_COMPUTER_USE_HELPER_APP_PATH:-}"')
        env = {k: v for k, v in os.environ.items() if not k.startswith("PI_COMPUTER_USE") and k != "PI_ELM_CHILD"}
        if child:
            env["PI_ELM_CHILD"] = "1"
        out = subprocess.run(["bash", "-c", script, "t", str(here), "1" if remote else "0"], env=env,
                             capture_output=True, text=True, check=True).stdout
        return out.replace(str(here), "$HERE").splitlines()

    def test_loaded_with_remote_inside_the_install_and_signed_ad_hoc(self):
        out = self.run_block(remote=True)
        self.assertIn("-e", out)
        self.assertIn("SIGN=-", out)                                    # no certificate in the login keychain
        self.assertIn("APP=$HERE/agent/helpers/pi-computer-use.app", out)  # not ~/Applications

    def test_not_without_remote_and_never_in_a_child(self):
        self.assertNotIn("-e", self.run_block(remote=False))
        self.assertNotIn("-e", self.run_block(remote=True, child=True))

    def test_installed_but_not_loaded_by_default(self):
        packages = json.loads((ROOT / "templates/packages.json").read_text())["dependencies"]
        settings = json.loads((ROOT / "templates/settings.json").read_text())["packages"]
        pins = json.loads((ROOT / "config/versions.json").read_text())["packages"]
        self.assertIn("@injaneity/pi-computer-use", packages)
        self.assertIn("@injaneity/pi-computer-use", pins)
        self.assertNotIn("pi-computer-use", json.dumps(settings))


if __name__ == "__main__":
    unittest.main()
