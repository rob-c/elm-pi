"""What the agent can use beyond pi: its own Python, containers, computer use.

- The agent's Python (agent/python, built with uv) goes on PATH unless pi was
  started from an environment of the researcher's own, and PyPI is on the
  proxy's list so it can install into it.
- Docker/Podman may run only with --network=none, and never push, log in or
  use a remote engine. The rules are evaluated here the way
  pi-permission-system does: glob to regex, last match wins.
- Computer use loads only in a `pi --remote` main session.
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
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
        self.assertIn("ast-grep,uv,", BOOTSTRAP)
        version = re.search(r'UV_VERSION="\$\{UV_VERSION:-([0-9.]+)\}"', BOOTSTRAP).group(1)
        sums = (ROOT / "templates/tools.sha256").read_text()
        for triple in ("aarch64-apple-darwin", "x86_64-apple-darwin", "aarch64-unknown-linux-musl", "x86_64-unknown-linux-musl"):
            self.assertIn(f"uv/{version}/uv-{triple}.tar.gz", sums)
        self.assertIn("WITH_PYTHON=0;", BOOTSTRAP)                    # opt-in
        self.assertIn("--with-python) WITH_PYTHON=1", BOOTSTRAP)
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


class PypiIndexTests(unittest.TestCase):
    SCRIPT = ROOT / "scripts/pypi_index.py"

    def row(self, name, summary, downloads, uploaded="2026-01-01", version="1.0", keywords="", classifiers=None):
        return {"name": name, "version": version, "summary": summary, "keywords": keywords,
                "classifiers": classifiers or [], "requires_python": ">=3.9",
                "recent_7d_downloads": downloads, "upload_time": uploaded}

    def build(self, rows):
        import importlib.util
        spec = importlib.util.spec_from_file_location("pypi_index", self.SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        db = Path(tempfile.mkdtemp()).resolve() / "pypi-index.db"
        self.addCleanup(subprocess.run, ["rm", "-rf", str(db.parent)])
        with contextlib.redirect_stdout(io.StringIO()):
            module.write(rows, db, "semvec/pypi-packages", "abc123")
        return db

    def search(self, db, *terms):
        return subprocess.run([sys.executable, "-I", str(self.SCRIPT), "search", *terms, "--db", str(db)],
                              capture_output=True, text=True, check=True).stdout

    def test_any_word_matches_and_use_breaks_ties(self):
        db = self.build([
            self.row("curvy-fit", "Curve fitting toolkit", 3),
            self.row("lmfit", "Least-squares minimization and curve fitting", 98000),
            self.row("ecdsa-lib", "Elliptic curve signatures", 5),
            self.row("lmfit", "an older upload of the same package", 1, uploaded="2020-01-01", version="0.1"),
        ])
        out = self.search(db, "curve", "fitting")
        names = [line.split()[0] for line in out.splitlines() if line and not line.startswith((" ", "["))]
        self.assertEqual("lmfit", names[0])          # popular and a full match
        self.assertIn("ecdsa-lib", names)            # any word matches...
        self.assertNotIn("0.1", out)                 # ...one row per package, its latest upload
        self.assertIn("pip index versions", out)     # every answer says it is a snapshot
        strict = self.search(db, "--all", "curve", "fitting")
        self.assertNotIn("ecdsa-lib", strict)

    def test_query_syntax_in_a_request_is_text(self):
        db = self.build([self.row("h5py", "Read and write HDF5 files from Python", 10)])
        self.assertIn("h5py", self.search(db, 'hdf5 "OR NEAR(*'))

    def test_an_incomplete_index_is_reported_not_a_traceback(self):
        db = Path(tempfile.mkdtemp()).resolve() / "pypi-index.db"
        self.addCleanup(subprocess.run, ["rm", "-rf", str(db.parent)])
        db.write_bytes(b"")
        run = subprocess.run([sys.executable, "-I", str(self.SCRIPT), "search", "hdf5", "--db", str(db)],
                             capture_output=True, text=True)
        self.assertEqual(1, run.returncode)
        self.assertIn("Re-run bootstrap.sh --with-pypi-index", run.stderr)
        self.assertNotIn("Traceback", run.stderr)
        # and bootstrap's revision check opens it read-only, so it never makes that empty file
        self.assertIn('mode=ro", uri=True).execute("SELECT value FROM meta', BOOTSTRAP)

    def test_installed_only_when_asked_and_pinned(self):
        self.assertIn("--with-pypi-index) WITH_PYPI_INDEX=1", BOOTSTRAP)
        self.assertEqual(2, BOOTSTRAP.count("--with-python|--with-pypi-index)"))   # parsed, and repeated from the record
        self.assertIn('[ "$(sha256_of "$file")" = "$want" ] || die "checksum mismatch for $path"', BOOTSTRAP)
        self.assertRegex(CONFIG["pypiIndex"]["revision"], r"^[0-9a-f]{40}$")
        self.assertIn("pypi-search", (ROOT / "templates/skills/scientific-python/SKILL.md").read_text())


class InstallOptionTests(unittest.TestCase):
    """The recorded options, run for real: bootstrap's argument parsing and its
    agent/install-options handling, extracted and run against a scratch install."""

    START = '\nfor arg in "$@"; do\n  case "$arg" in\n    --no-shim'
    PARSE = BOOTSTRAP[BOOTSTRAP.index(START):BOOTSTRAP.index('\n\nsay()  {')]
    OPTIONS = BOOTSTRAP[BOOTSTRAP.index('OPTIONS_FILE="$HERE/agent/install-options"'):
                        BOOTSTRAP.index('for flag in $GIVEN_FLAGS; do apply_flag "$flag"; done')]
    OPTIONS += 'for flag in $GIVEN_FLAGS; do apply_flag "$flag"; done'

    def options(self, *args, record="", python_env=False):
        here = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(here)])
        (here / "agent").mkdir()
        if record:
            (here / "agent/install-options").write_text(f"flags={record}\n")
        if python_env:
            (here / "agent/python/env/bin").mkdir(parents=True)
            (here / "agent/python/env/bin/python").write_text("")
            (here / "agent/python/env/bin/python").chmod(0o755)
        script = ('HERE="$1"; shift; cd "$HERE"\n'
                  'WITH_PYTHON=0; WITH_PYPI_INDEX=0; RESET_OPTIONS=0; GIVEN_FLAGS=""; DROPPED_FLAGS=""\n'
                  'for arg in "$@"; do case "$arg" in --reset-options) RESET_OPTIONS=1 ;; esac; done\n'
                  + self.PARSE.replace('--reset-options) RESET_OPTIONS=1 ;;', '--reset-options) ;;') + "\n"
                  + self.OPTIONS + '\nprintf "%s|%s|%s" "$GIVEN_FLAGS" "$WITH_PYTHON" "$WITH_PYPI_INDEX"')
        out = subprocess.run(["bash", "-c", script, "t", str(here), *args], capture_output=True, text=True)
        self.assertEqual(0, out.returncode, out.stderr)
        flags, python, index = out.stdout.split("|")
        return set(flags.split()), python == "1", index == "1"

    def test_the_agents_python_is_opt_in(self):
        self.assertEqual((set(), False, False), self.options())
        self.assertEqual(({"--with-python"}, True, False), self.options("--with-python"))
        self.assertEqual(({"--with-pypi-index"}, True, True), self.options("--with-pypi-index"))

    def test_a_choice_is_repeated_until_taken_back(self):
        self.assertEqual(({"--with-python"}, True, False), self.options(record="--with-python"))
        self.assertEqual((set(), False, False), self.options("--no-python", record="--with-python --with-pypi-index"))
        self.assertEqual(({"--with-python"}, True, False), self.options("--no-pypi-index", record="--with-python --with-pypi-index"))

    def test_an_install_that_already_has_it_keeps_it(self):
        self.assertEqual(({"--with-python"}, True, False), self.options(python_env=True))
        self.assertEqual((set(), False, False), self.options("--no-python", python_env=True))

    def test_pi_setup_runs_bootstrap_with_the_matching_flag(self):
        snippet = block(LAUNCHER, "# --- 'pi setup'", "# --- keep .pi out of the repository")
        here = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(here)])
        (here / "bootstrap.sh").write_text('#!/bin/sh\necho "$@"\n')
        (here / "bootstrap.sh").chmod(0o755)
        usage = block(LAUNCHER, "elm_usage() {", "WANTS_HELP=0")
        def run(*args):
            return subprocess.run(["bash", "-c", f'HERE="$1"; shift\n{usage}\n{snippet}', "t", str(here), *args],
                                  capture_output=True, text=True)
        self.assertEqual("--non-interactive --with-python", run("setup", "--python").stdout.strip())
        self.assertEqual("--non-interactive --with-pypi-index --no-python",
                         run("setup", "--pypi-index", "--no-python").stdout.strip())
        bad = run("setup", "--everything")
        self.assertEqual(2, bad.returncode)
        self.assertIn("pi setup --python", bad.stderr)

    def test_the_agent_asks_before_changing_the_install(self):
        self.assertEqual("ask", bash_rule("pi setup --python"))
        self.assertEqual("ask", bash_rule("pi update"))


class SoftwareInstallTests(unittest.TestCase):
    def test_mlr_and_resvg_are_pinned_and_checksummed(self):
        self.assertIn("uv,mlr,resvg,", BOOTSTRAP)
        sums = (ROOT / "templates/tools.sha256").read_text()
        for tool, version in (("mlr", "6.22.0"), ("resvg", "0.48.1")):
            self.assertIn(f'{tool.upper()}_VERSION="${{{tool.upper()}_VERSION:-{version}}}"', BOOTSTRAP)
            self.assertGreaterEqual(sums.count(f"{tool}/{version}/"), 3)

    def test_resvg_is_the_first_svg_converter(self):
        source = (ROOT / "templates/extensions/view-outputs.ts").read_text()
        svg = source[source.index("const svg: Converter[]"):source.index("];", source.index("const svg: Converter[]"))]
        self.assertLess(svg.index('"resvg"'), svg.index('"rsvg-convert"'))

    def test_homebrew_asks_and_stays_with_core_formulae(self):
        for command in ("brew install pandoc", "brew upgrade pandoc", "brew uninstall pandoc", "brew update"):
            with self.subTest(command=command):
                self.assertEqual("ask", bash_rule(command))
        for command in ("brew info pandoc", "brew list", "brew deps pandoc", "brew --prefix"):
            with self.subTest(command=command):
                self.assertEqual("allow", bash_rule(command))
        for command in ("brew install --cask firefox", "brew tap someone/tools", "brew install someone/tools/x",
                        "brew install ./evil.rb", "brew install https://x.example/f.rb",
                        "/usr/local/bin/brew install pandoc", "/opt/homebrew/bin/brew install x"):
            with self.subTest(command=command):
                self.assertEqual("deny", bash_rule(command))

    def test_system_package_managers_are_the_users_to_run(self):
        for command in ("apt-get install -y libhdf5-dev", "apt install texlive", "dnf install hdf5-devel",
                        "yum install gcc", "zypper in gcc", "pacman -S gcc", "apk add gcc", "apt-get update"):
            with self.subTest(command=command):
                self.assertEqual("deny", bash_rule(command))
        for command in ("apt-cache search hdf5", "dnf search hdf5", "dpkg -l", "rpm -q gcc"):
            with self.subTest(command=command):
                self.assertEqual("allow", bash_rule(command))

    def test_the_brew_wrapper_runs_approved_changes_past_the_proxy_and_logs_them(self):
        here = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(here)])
        (here / "scripts").mkdir()
        (here / "agent/bin").mkdir(parents=True)
        (here / "sys").mkdir()
        (here / "scripts/brew").write_bytes((ROOT / "scripts/brew").read_bytes())
        (here / "scripts/brew").chmod(0o755)
        (here / "agent/bin/brew").symlink_to(here / "scripts/brew")
        fake = here / "sys/brew"
        fake.write_text('#!/bin/sh\necho "args=$* proxy=${HTTPS_PROXY:-none} analytics=${HOMEBREW_NO_ANALYTICS:-}"\n')
        fake.chmod(0o755)
        env = {"PATH": f"{here}/agent/bin:{here}/sys:/usr/bin:/bin", "HTTPS_PROXY": "http://127.0.0.1:9",
               "HOME": str(here)}
        run = lambda *a, **extra: subprocess.run([str(here / "agent/bin/brew"), *a], env={**env, **extra},
                                                 capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual("args=install pandoc proxy=none analytics=1", run("install", "pandoc"))
        self.assertEqual("args=install x proxy=http://campus:3128 analytics=1",
                         run("install", "x", ELM_PI_UPSTREAM_PROXY="http://campus:3128"))
        self.assertEqual("args=info pandoc proxy=http://127.0.0.1:9 analytics=1", run("info", "pandoc"))
        log = (here / "agent/egress.log").read_text()
        self.assertIn("UNPROXIED brew install pandoc", log)
        self.assertNotIn("brew info", log)

    def test_the_skill_is_routed_and_named_in_the_prompts(self):
        self.assertTrue((ROOT / "templates/skills/installing-software/SKILL.md").is_file())
        self.assertIn("installing-software", (ROOT / "templates/extensions/skill-router.ts").read_text())
        self.assertIn("installing-software", (ROOT / "templates/APPEND_SYSTEM.md").read_text())
        self.assertIn("installing-software", (ROOT / "templates/agents/qwen.md").read_text())


class PixiTests(unittest.TestCase):
    def test_pinned_checksummed_and_kept_in_the_install(self):
        self.assertIn("resvg,pixi}", BOOTSTRAP)
        self.assertIn('PIXI_VERSION="${PIXI_VERSION:-0.82.0}"', BOOTSTRAP)
        self.assertEqual(4, (ROOT / "templates/tools.sha256").read_text().count("pixi/0.82.0/"))
        snippet = block(LAUNCHER, "# --- pixi: conda-forge packages", "# --- where jiti")
        self.assertIn('export PIXI_HOME="$HERE/agent/pixi"', snippet)
        self.assertIn('export PIXI_CACHE_DIR="$HERE/agent/pixi/cache"', snippet)

    def test_tools_installed_with_pixi_come_after_agent_bin(self):
        snippet = block(LAUNCHER, "# --- pixi: conda-forge packages", "# --- where jiti")
        here = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(here)])
        (here / "agent/bin").mkdir(parents=True)
        (here / "agent/bin/pixi").write_text("")
        (here / "agent/bin/pixi").chmod(0o755)
        out = subprocess.run(["bash", "-c", f'HERE="$1"; PATH="$HERE/agent/bin:/usr/bin"\n{snippet}\nprintf %s "$PATH"',
                              "t", str(here)], capture_output=True, text=True, check=True).stdout
        self.assertEqual(f"{here}/agent/bin:{here}/agent/pixi/bin:/usr/bin", out)

    def test_conda_forge_reachable_and_uploads_refused(self):
        hosts = CONFIG["proxyAllow"]["hosts"]
        for host in ("conda.anaconda.org", "api.anaconda.org", "prefix.dev"):
            self.assertIn(host, hosts)
        self.assertEqual("allow", bash_rule("pixi exec --spec ghostscript gs --version"))
        self.assertEqual("allow", bash_rule("pixi global install gdal"))
        self.assertEqual("allow", bash_rule("pixi search 'netcdf*' -p osx-64"))
        self.assertEqual("ask", bash_rule("pixi global install --channel bioconda samtools"))
        self.assertEqual("ask", bash_rule("pixi exec -c someone --spec x x"))
        for command in ("pixi upload prefix.dev x.conda", "pixi auth login prefix.dev", "pixi self-update"):
            self.assertEqual("deny", bash_rule(command))

    def test_conda_search_prints_names_summaries_and_how_to_use_them(self):
        jq = shutil.which("jq") or next((str(p) for p in (Path.home() / "sandboxes/elm-pi/agent/bin/jq",
                                                         ROOT / "agent/bin/jq") if p.exists()), None)
        if not jq:
            self.skipTest("needs jq")
        here = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(here)])
        (here / "jq").symlink_to(jq)
        reply = {"data": {"channel": {"packages": {"page": [
            {"name": "ghostscript", "summary": "An interpreter for\nPostScript", "latestVersion": {"version": "10.08.0"}}]}}}}
        curl = here / "curl"
        curl.write_text("#!/bin/sh\nfor a; do last=$a; done\nprintf '%s' \"$last\" > " + str(here / "sent.json")
                        + "\nprintf '%s' '" + json.dumps(reply) + "'\n")
        curl.chmod(0o755)
        run = subprocess.run([str(ROOT / "scripts/conda-search"), "-n", "3", "ghostscript"],
                             env={"PATH": f"{here}:/usr/bin:/bin"}, capture_output=True, text=True)
        self.assertEqual(0, run.returncode, run.stderr)
        self.assertIn("ghostscript 10.08.0\n    An interpreter for PostScript", run.stdout)
        self.assertIn("pixi exec --spec NAME", run.stdout)
        sent = json.loads((here / "sent.json").read_text())
        self.assertEqual({"t": "ghostscript", "n": 3}, sent["variables"])   # the term travels as a variable, never spliced in

    def test_the_skill_says_search_first_and_tell_the_user(self):
        skill = (ROOT / "templates/skills/installing-software/SKILL.md").read_text()
        for needle in ("conda-search", "pixi exec --spec", "pixi global install", "## 6. Tell the user",
                       "how to remove it", "pypi-search"):
            self.assertIn(needle, skill)
        self.assertNotIn("\\|", skill)   # a backslash in a command would be copied literally


class InstallNotesTests(unittest.TestCase):
    SOURCE = ROOT / "templates/extensions/install-notes.ts"
    RUNNER = (
        "const mod = await import(process.argv[1]);"
        "const [cmds, cwd] = [JSON.parse(process.argv[2]), process.argv[3]];"
        "const out = {}; for (const c of cmds) out[c] = mod.describe(c, cwd);"
        "let handler; mod.default({ on: (e, h) => { handler = h; } });"
        "const ok = await handler({ toolName: 'bash', isError: false, input: { command: cmds[0] }, content: [{ type: 'text', text: 'done' }] }, { cwd });"
        "const failed = await handler({ toolName: 'bash', isError: true, input: { command: cmds[0] }, content: [] }, { cwd });"
        "console.log(JSON.stringify({ out, note: ok.content.at(-1).text, failed: failed === undefined }));"
    )

    def run_notes(self, commands):
        binary = shutil.which("node") or str(Path.home() / "sandboxes/elm-pi/.node/bin/node")
        agent = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(agent)])
        env = {**os.environ, "PI_CODING_AGENT_DIR": str(agent), "PIXI_HOME": str(agent / "pixi"),
               "PIXI_CACHE_DIR": str(agent / "pixi/cache")}
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", self.RUNNER, str(self.SOURCE),
                              json.dumps(commands), "/proj"], env=env, capture_output=True, text=True)
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            self.skipTest("this node cannot load TypeScript")
        self.assertEqual(0, run.returncode, run.stderr)
        return json.loads(run.stdout), agent

    def test_installs_are_described_with_where_and_how_to_remove(self):
        commands = [
            "pixi global install gdal",
            "pixi global install libnetcdf 2>&1",
            "pip install tabulate > .pi/tmp/log 2> /dev/null",
            "mkdir -p x && pixi exec --spec ghostscript gs -q in.eps",
            "pip install tabulate 'numpy>=2'",
            "uv pip install --python .venv/bin/python lmfit",
            "pixi add hdf5",
            "docker pull texlive/texlive:latest-medium",
            "brew install pandoc",
            "pip index versions tabulate",
            "pixi search gdal",
        ]
        result, agent = self.run_notes(commands)
        out = result["out"]
        gdal, = out["pixi global install gdal"]
        self.assertIn(str(agent / "pixi/envs"), gdal["where"])
        self.assertEqual("pixi global uninstall gdal", gdal["undo"])
        gs, = out["mkdir -p x && pixi exec --spec ghostscript gs -q in.eps"]
        self.assertIn("nothing installed", gs["what"])
        self.assertIn(str(agent / "pixi/cache"), gs["where"])
        pip, = out["pip install tabulate 'numpy>=2'"]
        self.assertEqual("pip uninstall tabulate numpy>=2", pip["undo"])
        uv, = out["uv pip install --python .venv/bin/python lmfit"]
        self.assertIn(".venv/bin/python", uv["where"])
        self.assertIn("/proj/pixi.toml", out["pixi add hdf5"][0]["where"])
        self.assertEqual("docker rmi texlive/texlive:latest-medium", out["docker pull texlive/texlive:latest-medium"][0]["undo"])
        self.assertEqual("brew uninstall pandoc", out["brew install pandoc"][0]["undo"])
        # redirections are not packages (seen live: "libnetcdf, 2>&1")
        self.assertEqual("pixi global uninstall libnetcdf", out["pixi global install libnetcdf 2>&1"][0]["undo"])
        self.assertEqual("pip uninstall tabulate", out["pip install tabulate > .pi/tmp/log 2> /dev/null"][0]["undo"])
        self.assertEqual([], out["pip index versions tabulate"])
        self.assertEqual([], out["pixi search gdal"])
        self.assertIn("Tell the user in your report", result["note"])
        self.assertTrue(result["failed"])                       # nothing noted when the install failed
        self.assertIn("pixi global uninstall gdal", (agent / "installs.log").read_text())

    def test_loaded_with_the_other_required_extensions(self):
        self.assertIn("install-notes.ts", CONFIG["requiredExtensions"])


class NotebookToolTests(unittest.TestCase):
    PACKAGES = ("pi-python", "@xl0/pi-lovely-notebook")

    def test_installed_pinned_and_loaded(self):
        manifest = json.loads((ROOT / "templates/packages.json").read_text())["dependencies"]
        pins = json.loads((ROOT / "config/versions.json").read_text())["packages"]
        loaded = json.loads((ROOT / "templates/settings.json").read_text())["packages"]
        for name in self.PACKAGES:
            with self.subTest(name=name):
                self.assertIn(name, manifest)
                self.assertRegex(pins[name], r"^\d+\.\d+\.\d+$")
                self.assertIn(f"npm:{name}", loaded)

    def test_llama_does_not_get_the_persistent_kernel(self):
        meta = (ROOT / "templates/agents/llama.md").read_text().split("---")[1]
        excluded = next(l for l in meta.splitlines() if l.startswith("excludeTools:"))
        self.assertIn(" python,", excluded)
        self.assertIn("python_set_interpreter", excluded)

    def test_scripts_get_agg_and_notebooks_keep_inline_figures(self):
        # MPLBACKEND=Agg stopped Jupyter's inline backend (measured: plots came out as a
        # warning). A matplotlibrc ranks below MPLBACKEND, which ipykernel sets when unset.
        self.assertNotIn("export MPLBACKEND", LAUNCHER)
        self.assertIn("backend: Agg", (ROOT / "config/matplotlibrc").read_text())
        snippet = block(LAUNCHER, "# Figures go to files", "# pi's half of --help")
        def rc(home_rc=False, **env):
            home = Path(tempfile.mkdtemp()).resolve()
            self.addCleanup(subprocess.run, ["rm", "-rf", str(home)])
            if home_rc:
                (home / ".config/matplotlib").mkdir(parents=True)
                (home / ".config/matplotlib/matplotlibrc").write_text("backend: TkAgg\n")
            clean = {k: v for k, v in os.environ.items() if k not in ("MPLBACKEND", "MATPLOTLIBRC", "MPLCONFIGDIR", "XDG_CONFIG_HOME")}
            return subprocess.run(["bash", "-c", f'HERE="$1"\n{snippet}\nprintf %s "${{MATPLOTLIBRC:-}}"', "t", str(ROOT)],
                                  env={**clean, "HOME": str(home), **env}, capture_output=True, text=True, check=True).stdout
        self.assertEqual(str(ROOT / "config/matplotlibrc"), rc())
        self.assertEqual("", rc(home_rc=True))
        self.assertEqual("", rc(MPLBACKEND="QtAgg"))

    def test_the_skill_says_how_to_explore_edit_run_and_look(self):
        skill = (ROOT / "templates/skills/scientific-python/SKILL.md").read_text()
        for needle in ("## Exploring: the `python` tool", "notebook_summary", "notebook_read_cell_output",
                       "nbconvert --to notebook --execute --inplace", "kernel state is not a result"):
            self.assertIn(needle, skill)


class PromptCacheTests(unittest.TestCase):
    """What keeps the gateway's prefix cache warm (profiled through a logging relay)."""

    RUNNER = r"""
const mod = await import(process.argv[1]);
const h = {}; const tools = {};
mod.default({ on: (e, f) => { (h[e] ??= []).push(f); }, registerTool: (t) => { tools[t.name] = t; } });
const ctx = { cwd: process.argv[2] };
const fire = async (e, ev) => { for (const f of h[e] ?? []) await f(ev, ctx); };
const prompt = async () => { const ev = { systemPromptOptions: { sections: {} } }; await fire("before_agent_start", ev); return ev.systemPromptOptions.sections.pinned_instructions ?? ""; };
const out = [];
await fire("session_start", {});
await tools.pin_instruction.execute("1", { instruction: "Use SI units." }, undefined, undefined, ctx);
out.push(await prompt());                     // pinned mid-session: system prompt unchanged
await tools.pin_instruction.execute("2", { instruction: "run7.csv is calibrated." }, undefined, undefined, ctx);
out.push(await prompt());
await fire("session_compact", {});
out.push(await prompt());                     // after compaction: both
await tools.unpin_instruction.execute("3", { number: 1 }, undefined, undefined, ctx);
out.push(await prompt());                     // unpin: at once
console.log(JSON.stringify(out));
"""

    def test_a_new_pin_waits_for_compaction_and_an_unpin_does_not(self):
        binary = shutil.which("node") or str(Path.home() / "sandboxes/elm-pi/.node/bin/node")
        tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(tmp)])
        ext = tmp / "ext"
        (ext / "node_modules/typebox").mkdir(parents=True)
        (ext / "node_modules/typebox/package.json").write_text('{"name":"typebox","type":"module","main":"index.js"}')
        (ext / "node_modules/typebox/index.js").write_text("const f = (...a) => ({ a }); export const Type = { Object: f, String: f, Number: f };")
        shutil.copy(ROOT / "templates/extensions/pinned-instructions.ts", ext / "pinned.ts")
        (tmp / "proj").mkdir()
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", self.RUNNER, str(ext / "pinned.ts"), str(tmp / "proj")],
                             env={**os.environ, "PI_CODING_AGENT_DIR": str(tmp / "agent")}, capture_output=True, text=True)
        if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
            self.skipTest("this node cannot load TypeScript")
        self.assertEqual(0, run.returncode, run.stderr)
        first, second, compacted, unpinned = json.loads(run.stdout)
        self.assertEqual("", first)                   # the session started with none: the prefix stays put
        self.assertEqual("", second)
        self.assertIn("Use SI units.", compacted)
        self.assertIn("run7.csv is calibrated.", compacted)
        self.assertNotIn("Use SI units.", unpinned)    # withdrawn: never still asserted
        self.assertIn("run7.csv is calibrated.", unpinned)

    def test_retries_start_at_the_second_the_gateway_asks_for(self):
        retry = json.loads((ROOT / "templates/settings.json").read_text())["retry"]
        self.assertEqual(1000, retry["baseDelayMs"])   # 429s carry Retry-After: 1
        self.assertEqual(6, retry["maxRetries"])       # 1+2+4+8+16+32 = 63s for a long storm
        self.assertEqual(0, retry["provider"]["maxRetries"])
        self.assertIn('"retry",', BOOTSTRAP)            # installer-owned: reaches existing installs


class FixedPromptTests(unittest.TestCase):
    """Every request carries AGENTS.md, APPEND_SYSTEM.md, the skill list and the tool
    definitions (~24k tokens before trimming); detail needed now and then is read on demand."""

    def test_every_reference_agents_md_points_to_exists_and_renders_to_a_real_path(self):
        agents = (ROOT / "templates/AGENTS.md").read_text()
        named = set(re.findall(r"@AGENT_DIR@/reference/([a-z0-9-]+\.md)", agents))
        shipped = {p.name for p in (ROOT / "templates/reference").glob("*.md")}
        self.assertEqual(shipped, named)                 # none missing, none unreferenced
        out = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(subprocess.run, ["rm", "-rf", str(out)])
        subprocess.run([sys.executable, str(ROOT / "scripts/elm_config.py"), "--root", str(ROOT), "render",
                        str(ROOT / "templates/AGENTS.md"), str(out / "AGENTS.md")], check=True)
        rendered = (out / "AGENTS.md").read_text()
        self.assertNotIn("@AGENT_DIR@", rendered)
        self.assertIn(f"{ROOT / 'agent'}/reference/finished-work.md", rendered)
        self.assertIn("rm -rf agent/reference && mkdir -p agent/reference", BOOTSTRAP)

    def test_the_rules_stay_and_only_the_detail_moved(self):
        agents = (ROOT / "templates/AGENTS.md").read_text()
        for rule in (".pi/.gitignore", "`## Facts`", ".pi/tmp/", "five lowercase letters",
                     '"$PI_CODING_AGENT_DIR/egress.log"', "pi --remote", "(from memory,", "pi --workflows"):
            self.assertIn(rule, agents)
        detail = "".join(p.read_text() for p in (ROOT / "templates/reference").glob("*.md"))
        for moved in ("git rm -r --cached", "pi-hermes-memory", "requirePath", "X-Elm-Pi-Remedy", "__pycache__"):
            self.assertIn(moved, detail)
            self.assertNotIn(moved, agents)

    def test_sizes_do_not_creep_back(self):
        self.assertLess(len((ROOT / "templates/AGENTS.md").read_text()), 10000)
        self.assertLess(len((ROOT / "templates/APPEND_SYSTEM.md").read_text()), 11500)
        for skill in (ROOT / "templates/skills").glob("*/SKILL.md"):
            description = re.search(r"^description: (.*)$", skill.read_text(), re.M).group(1)
            self.assertLessEqual(len(description), 230, skill.parent.name)

    def test_rarely_used_tools_are_left_out_and_workflows_come_back_on_request(self):
        excluded = CONFIG["excludedTools"]
        self.assertEqual(["workflow", "workflow_control"], excluded["workflows"])
        self.assertIn("notebook_merge", excluded["always"])
        env = (ROOT / "scripts/elm_config.py").read_text()
        self.assertIn('"ELM_EXCLUDED_TOOLS"', env)
        self.assertIn('"ELM_WORKFLOW_TOOLS"', env)
        self.assertIn("--workflows) WORKFLOWS=1", LAUNCHER)
        skill = (ROOT / "templates/skills/scientific-python/SKILL.md").read_text()
        for tool in excluded["always"]:
            self.assertNotIn(f"`{tool}`", skill)          # never advertise a tool that is not offered


if __name__ == "__main__":
    unittest.main()
