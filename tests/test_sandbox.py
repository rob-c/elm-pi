import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SANDBOX = ROOT / "lib/sandbox.sh"


def bash(script: str, env=None, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f'set -euo pipefail; source "{SANDBOX}"\n{script}'],
        check=check,
        text=True,
        capture_output=True,
        env=env if env is not None else dict(os.environ),
    )


def fake_python(directory: Path, name: str, exit_code: int) -> Path:
    """A stand-in interpreter that answers elm_python_check with exit_code."""
    path = directory / name
    path.write_text(f"#!/bin/sh\nexit {exit_code}\n")
    path.chmod(0o755)
    return path


class ScrubListTests(unittest.TestCase):
    def test_install_sh_carries_the_same_scrub_lists(self):
        # install.sh runs before lib/sandbox.sh is on disk, so it has a copy.
        pattern = re.compile(r'^(ELM_SCRUB_(?:PREFIXES|NAMES|KEEP))="([^"]*)"', re.M)
        library = dict(pattern.findall(SANDBOX.read_text()))
        installer = dict(pattern.findall((ROOT / "install.sh").read_text()))
        self.assertEqual(3, len(library))
        self.assertEqual(library, installer)


class EnvironmentTests(unittest.TestCase):
    def test_scrub_removes_toolchain_variables_and_keeps_the_rest(self):
        with tempfile.NamedTemporaryFile() as ca:
            env = {
                **os.environ,
                "PYTHONPATH": "/evil",
                "PYTHONHOME": "/evil",
                "CONDA_PREFIX": "/opt/conda",
                "_CE_CONDA": "x",
                "VIRTUAL_ENV": "/venv",
                "PIP_INDEX_URL": "https://evil.example",
                "npm_config_registry": "https://evil.example",
                "NPM_CONFIG_CACHE": "/root/.npm",
                "NODE_OPTIONS": "--require /evil.js",
                "NODE_PATH": "/evil",
                "NVM_DIR": "/nvm",
                "GIT_DIR": "/elsewhere/.git",
                "BASH_ENV": "/evil.sh",
                "CDPATH": "/tmp",
                "TAR_OPTIONS": "--exclude=*",
                "SSL_CERT_FILE": "/no/such/conda/cacert.pem",
                "NODE_EXTRA_CA_CERTS": ca.name,
                "ELM_API_KEY": "kept",
            }
            out = bash("elm_scrub_env; env", env=env).stdout
        names = {line.split("=", 1)[0] for line in out.splitlines() if "=" in line}
        for gone in ("PYTHONPATH", "PYTHONHOME", "CONDA_PREFIX", "_CE_CONDA", "VIRTUAL_ENV",
                     "PIP_INDEX_URL", "npm_config_registry", "NPM_CONFIG_CACHE", "NODE_OPTIONS",
                     "NODE_PATH", "NVM_DIR", "GIT_DIR", "BASH_ENV", "CDPATH", "TAR_OPTIONS",
                     "SSL_CERT_FILE"):
            self.assertNotIn(gone, names)
        self.assertIn("NODE_EXTRA_CA_CERTS", names)   # exists, so it is the site's CA
        self.assertIn("ELM_API_KEY", names)
        self.assertIn("HOME", names)

    def test_clean_path_drops_conda_venv_managers_and_relative_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "anaconda3/conda-meta").mkdir(parents=True)
            (root / "anaconda3/bin").mkdir()
            (root / "anaconda3/condabin").mkdir()
            (root / "venv/bin").mkdir(parents=True)
            (root / "venv/pyvenv.cfg").write_text("home = /usr/bin\n")
            (root / "tools/bin").mkdir(parents=True)
            path = ":".join([
                str(root / "anaconda3/bin"), str(root / "anaconda3/condabin"),
                str(root / "venv/bin"), "/home/u/.pyenv/shims", "/home/u/.nvm/versions/node/v18/bin",
                "/home/u/.volta/bin", "./node_modules/.bin", ".", "", "relative/bin",
                str(root / "tools/bin"), "/usr/bin", "/usr/bin/", str(root / "tools/bin"),
            ])
            out = subprocess.run(["bash", "-c", f'source "{SANDBOX}"; elm_clean_path "$1"', "x", path],
                                 check=True, text=True, capture_output=True).stdout
        self.assertEqual(f"{root / 'tools/bin'}:/usr/bin", out)

    def test_install_env_puts_bundled_node_and_system_first(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "PATH": f"/opt/somewhere/bin:{os.environ['PATH']}"}
            out = bash(f'elm_install_env "{directory}"; echo "$PATH"; echo "$ELM_PI_ROOT"',
                       env=env).stdout.splitlines()
        self.assertTrue(out[0].startswith(f"{directory}/.node/bin:/usr/bin:/bin:"), out[0])
        self.assertIn("/opt/somewhere/bin", out[0])     # kept, but after the system
        self.assertEqual(directory, out[1])

    def test_npm_env_confines_config_cache_and_prefix_to_the_install(self):
        env = {**os.environ, "npm_config_registry": "https://evil.example",
               "Npm_Config_Cache": "/root/.npm", "NODE_OPTIONS": "--inspect"}
        out = bash('elm_npm_env /srv/elm-pi; env | grep -i -e "^npm_config_" -e "^NODE_" | sort',
                   env=env).stdout.splitlines()
        self.assertEqual([
            "NPM_CONFIG_CACHE=/srv/elm-pi/.npm-cache",
            "NPM_CONFIG_GLOBALCONFIG=/dev/null",
            "NPM_CONFIG_PREFIX=/srv/elm-pi/.node",
            "NPM_CONFIG_UPDATE_NOTIFIER=false",
            "NPM_CONFIG_USERCONFIG=/srv/elm-pi/config/npmrc",
        ], out)

    def test_npmrc_pins_the_public_registry_and_disables_scripts(self):
        rc = (ROOT / "config/npmrc").read_text()
        self.assertIn("registry=https://registry.npmjs.org/\n", rc)
        self.assertIn("ignore-scripts=true\n", rc)


class PythonSelectionTests(unittest.TestCase):
    def check(self, path: Path) -> int:
        return bash(f'elm_python_check "{path}"', check=False).returncode

    def test_check_reports_why_an_interpreter_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            self.assertEqual(0, self.check(fake_python(d, "good", 0)))
            self.assertEqual(10, self.check(fake_python(d, "old", 10)))
            self.assertEqual(11, self.check(fake_python(d, "conda", 11)))
            self.assertEqual(1, self.check(d / "missing"))
            shims = d / ".pyenv/shims"
            shims.mkdir(parents=True)
            self.assertEqual(13, self.check(fake_python(shims, "python3", 0)))
        self.assertEqual(1, bash('elm_python_check python3', check=False).returncode)  # not absolute

    def test_check_accepts_the_interpreter_running_these_tests(self):
        # check.sh runs the suite on the interpreter elm_select_python chose.
        import sys
        self.assertIn(self.check(Path(sys.executable)), (0, 11, 12))

    def test_explicit_choice_is_honoured_or_refused_but_never_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            for code, ok in ((0, True), (11, True), (12, True), (10, False), (13, False)):
                py = fake_python(d, f"py{code}", code)
                env = {**os.environ, "ELM_PI_PYTHON": str(py)}
                result = bash('elm_select_python "" && echo "$ELM_PI_PYTHON" || echo "ERR $ELM_PY_ERROR"',
                              env=env)
                if ok:
                    self.assertEqual(str(py), result.stdout.strip())
                else:
                    self.assertTrue(result.stdout.startswith("ERR ELM_PI_PYTHON="), result.stdout)

    def test_recorded_interpreter_is_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            (d / "agent").mkdir()
            py = fake_python(d, "recorded", 0)
            (d / "agent/python-path").write_text(f"{py}\n")
            env = {k: v for k, v in os.environ.items() if k != "ELM_PI_PYTHON"}
            for mode in ("", "fast"):
                out = bash(f'elm_select_python "{d}" {mode}; echo "$ELM_PI_PYTHON"', env=env).stdout
                self.assertEqual(str(py), out.strip())

    def test_an_activated_conda_first_on_path_is_not_chosen(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            (d / "conda/conda-meta").mkdir(parents=True)
            (d / "conda/bin").mkdir()
            fake_python(d / "conda/bin", "python3", 0)
            env = {k: v for k, v in os.environ.items() if k != "ELM_PI_PYTHON"}
            env["PATH"] = f"{d / 'conda/bin'}:{env['PATH']}"
            result = bash('elm_select_python "" && echo "$ELM_PI_PYTHON" || echo "ERR"', env=env)
        self.assertNotIn(str(d), result.stdout)

    def test_elm_py_ignores_pythonpath_and_the_callers_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            (d / "json.py").write_text("raise SystemExit('shadowed the stdlib')\n")
            env = {k: v for k, v in os.environ.items() if k != "ELM_PI_PYTHON"}
            env["PYTHONPATH"] = str(d)
            result = subprocess.run(
                ["bash", "-c", f'source "{SANDBOX}"; elm_select_python "" || exit 3; '
                 f'ELM_PI_ROOT="{ROOT}" elm_py -c "import json, sys; print(json.__file__)"'],
                cwd=d, env=env, text=True, capture_output=True,
            )
        if result.returncode == 3:
            self.skipTest("no non-conda Python 3.8+ on this machine")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertNotIn(str(d), result.stdout)


class RuntimeTests(unittest.TestCase):
    def test_dotenv_is_read_as_data_not_executed(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            env_file = d / ".env"
            env_file.write_text(
                "# comment\n"
                "ELM_API_KEY=elm-abc$(touch pwned)\n"
                "export ELM_BASE_URL='https://elm.example/api'\n"
                'ELM_SHIM_PORT="8811"\r\n'
                "PYTHONPATH=/evil\n"
                "touch pwned2\n"
                "NODE_OPTIONS=--require /evil.js\n"
            )
            env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "NODE_OPTIONS")}
            result = subprocess.run(
                ["bash", "-c", f'source "{SANDBOX}"; cd "{d}"; elm_load_dotenv .env; '
                 'printf "%s|%s|%s|%s|%s\\n" "$ELM_API_KEY" "$ELM_BASE_URL" "$ELM_SHIM_PORT" '
                 '"${PYTHONPATH:-unset}" "${NODE_OPTIONS:-unset}"'],
                env=env, text=True, capture_output=True, check=True,
            )
            self.assertFalse((d / "pwned").exists())
            self.assertFalse((d / "pwned2").exists())
        self.assertEqual("elm-abc$(touch pwned)|https://elm.example/api|8811|unset|unset",
                         result.stdout.strip())
        self.assertEqual(3, result.stderr.count("ignoring line"))

    def test_launcher_path_drops_only_relative_entries(self):
        out = subprocess.run(
            ["bash", "-c", f'source "{SANDBOX}"; elm_clean_path "$1" relative-only', "x",
             ".:/opt/conda/bin::bin:/usr/bin:/opt/conda/bin"],
            check=True, text=True, capture_output=True).stdout
        self.assertEqual("/opt/conda/bin:/usr/bin", out)

    def test_private_tmpdir_keeps_a_private_one_and_replaces_a_shared_one(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            private = d / "private"
            private.mkdir(mode=0o700)
            shared = d / "shared"
            shared.mkdir()
            os.chmod(shared, 0o1777)
            run = lambda tmp: bash(f'TMPDIR="{tmp}"; elm_private_tmpdir && echo "$TMPDIR"').stdout.strip()
            self.assertEqual(str(private), run(private))
            replaced = run(shared)
            self.assertEqual(str(shared / f"elm-pi-{os.getuid()}"), replaced)
            self.assertEqual(0o700, os.stat(replaced).st_mode & 0o777)
            # someone else's symlink in the shared directory is refused
            os.rmdir(replaced)
            os.symlink(private, replaced)
            result = bash(f'TMPDIR="{shared}"; elm_private_tmpdir', check=False)
            self.assertNotEqual(0, result.returncode)

    def test_node_modules_elsewhere_on_the_machine_stop_nothing(self):
        # A node_modules above the install (a stray `npm install` in a home
        # folder) is the guard's to keep out of pi, not a reason to refuse to
        # install or start: nothing looks for one any more.
        for rel in ("pi", "pi.bash", "bootstrap.sh", "install.sh", "lib/sandbox.sh"):
            text = (ROOT / rel).read_text()
            self.assertNotIn("elm_external_module_dirs", text, rel)
            self.assertNotRegex(text, r"(?<![A-Z_])EXTERNAL_MODULES\b", rel)   # the old check's variable

    def test_the_extension_load_check_runs_under_the_guard(self):
        warm = (ROOT / "bootstrap.bash").read_text()
        self.assertIn('"$HERE/.node/bin/node" --import "$HERE/lib/node-guard.mjs" "$HERE/scripts/check-extensions.mjs"', warm)

    def test_pi_orig_starts_node_clean_with_the_guard(self):
        text = (ROOT / "pi.orig").read_text()
        self.assertIn('exec "$NODE" --import "$GUARD" "$CLI" "$@"', text)
        for name in ("NODE_*|JITI_*", "LD_*|DYLD_*|OPENSSL_*", "PI_PACKAGE_DIR", "LOG_TOKENS"):
            self.assertIn(name, text)

    def test_projects_are_untrusted_by_default_and_the_installer_enforces_it(self):
        import json
        self.assertEqual("never", json.loads((ROOT / "templates/settings.json").read_text())["defaultProjectTrust"])
        self.assertIn('"defaultProjectTrust",', (ROOT / "bootstrap.bash").read_text())


def guard_capable_node():
    """The bundled node, or else one on PATH new enough for the guard
    (module.registerHooks, Node 22.15+): CI and a fresh clone have no .node."""
    import shutil
    bundled = ROOT / ".node/bin/node"
    if bundled.exists():
        return bundled
    found = shutil.which("node")
    if found and subprocess.run([found, "-e", "process.exit(typeof require('node:module').registerHooks === 'function' ? 0 : 1)"],
                                capture_output=True).returncode == 0:
        return Path(found)
    return None


class NodeGuardTests(unittest.TestCase):
    NODE = guard_capable_node()

    def setUp(self):
        if self.NODE is None:
            self.skipTest("no node with module.registerHooks (bundled or on PATH)")

    def test_guard_refuses_packages_outside_and_restores_the_stash(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            package = d / "node_modules/elm-probe"
            package.mkdir(parents=True)
            (package / "index.js").write_text('module.exports = "loaded";\n')
            script = (
                'let out = [process.env.LD_LIBRARY_PATH, "ELM_PI_STASH__LD_LIBRARY_PATH" in process.env];'
                'try { out.push(require("elm-probe")); } catch (e) { out.push(e.message.startsWith("elm-pi: refusing")); }'
                'import("elm-probe").then(() => out.push("loaded"), (e) => out.push(e.message.startsWith("elm-pi: refusing")))'
                '.then(() => console.log(JSON.stringify(out)));'
            )
            env = {**os.environ, "ELM_PI_STASH__LD_LIBRARY_PATH": "/conda/lib"}
            env.pop("ELM_PI_ALLOW_EXTERNAL_MODULES", None)
            out = subprocess.run([str(self.NODE), "--import", str(ROOT / "lib/node-guard.mjs"), "-e", script],
                                 cwd=d, env=env, text=True, capture_output=True, check=True).stdout
            self.assertEqual('["/conda/lib",false,true,true]', out.strip())
            env["ELM_PI_ALLOW_EXTERNAL_MODULES"] = "1"
            out = subprocess.run([str(self.NODE), "--import", str(ROOT / "lib/node-guard.mjs"), "-e", script],
                                 cwd=d, env=env, text=True, capture_output=True, check=True).stdout
            self.assertEqual('["/conda/lib",false,"loaded","loaded"]', out.strip())


    def run_guard(self, guard, script, cwd, **env):
        environment = {**os.environ, **env}
        if "ELM_PI_ALLOW_EXTERNAL_MODULES" not in env:
            environment.pop("ELM_PI_ALLOW_EXTERNAL_MODULES", None)
        return subprocess.run([str(self.NODE), "--import", str(guard), "--input-type=module", "-e", script],
                              cwd=cwd, env=environment, text=True, capture_output=True)

    def test_jiti_style_evaluation_from_outside_is_refused(self):
        # jiti evaluates each file it loads with vm.runInThisContext(code, { filename }).
        with tempfile.TemporaryDirectory() as directory:
            d = Path(os.path.realpath(directory))
            outside = d / "node_modules/leak/index.js"
            outside.parent.mkdir(parents=True)
            outside.write_text("1")
            (d / "project").mkdir()
            (d / "project/ext.js").write_text("1")
            inside = ROOT / "node_modules/x/index.js"
            script = (
                'import vm from "node:vm";'
                'const out = {};'
                'for (const [name, options] of Object.entries(JSON.parse(process.argv[1]))) {'
                '  try { vm.runInThisContext("1", options); out[name] = "ran"; }'
                '  catch (e) { out[name] = e.message.startsWith("elm-pi: refusing") ? "refused" : e.message; } }'
                'console.log(JSON.stringify(out));')
            cases = {"outside_package": {"filename": str(outside)}, "outside_package_as_string": str(outside),
                     "installs_own_package": {"filename": str(inside)},
                     "project_file_outside_node_modules": {"filename": str(d / "project/ext.js")},
                     "no_filename": {}}
            run = lambda **env: subprocess.run(
                [str(self.NODE), "--import", str(ROOT / "lib/node-guard.mjs"), "--input-type=module", "-e", script,
                 json.dumps(cases)], cwd=d, text=True, capture_output=True, check=True,
                env={**{k: v for k, v in os.environ.items() if k != "ELM_PI_ALLOW_EXTERNAL_MODULES"}, **env}).stdout
            self.assertEqual({"outside_package": "refused", "outside_package_as_string": "refused",
                              "installs_own_package": "ran", "project_file_outside_node_modules": "ran",
                              "no_filename": "ran"}, json.loads(run()))
            self.assertEqual("ran", json.loads(run(ELM_PI_ALLOW_EXTERNAL_MODULES="1"))["outside_package"])

    def test_an_install_reached_through_a_symlink_loads_its_own_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(os.path.realpath(directory))
            (d / "real/inst/lib").mkdir(parents=True)
            (d / "real/inst/lib/node-guard.mjs").write_text((ROOT / "lib/node-guard.mjs").read_text())
            own = d / "real/inst/agent/npm/node_modules/p/index.js"
            own.parent.mkdir(parents=True)
            own.write_text("1")
            (d / "link").symlink_to(d / "real")
            via_link = d / "link/inst/agent/npm/node_modules/p/index.js"
            script = ('import vm from "node:vm";'
                      'try { vm.runInThisContext("1", { filename: process.argv[1] }); console.log("ran"); }'
                      'catch (e) { console.log(e.message); }')
            out = subprocess.run([str(self.NODE), "--import", str(d / "link/inst/lib/node-guard.mjs"),
                                  "--input-type=module", "-e", script, str(via_link)],
                                 cwd=d, text=True, capture_output=True, check=True).stdout.strip()
            self.assertEqual("ran", out)

    def test_jiti_cannot_take_a_package_from_above_the_install(self):
        # The case the guard exists for: an extension imports a package the
        # install lacks, and jiti's own resolver finds it in a node_modules
        # above the install. Refused under the guard; loaded without it.
        package = next((p for p in (ROOT / "node_modules/jiti", ROOT / "agent/npm/node_modules/jiti")
                        if (p / "lib/jiti.mjs").exists()), None)
        if package is None:
            self.skipTest("jiti is not installed in this checkout")
        with tempfile.TemporaryDirectory() as directory:
            d = Path(os.path.realpath(directory))
            leak = d / "above/node_modules/leakpkg/index.js"
            leak.parent.mkdir(parents=True)
            leak.write_text('module.exports = "leaked";\n')
            install = d / "above/inst"
            (install / "lib").mkdir(parents=True)
            (install / "lib/node-guard.mjs").write_text((ROOT / "lib/node-guard.mjs").read_text())
            (install / "agent").mkdir()
            (install / "agent/ext.ts").write_text('import leak from "leakpkg";\nexport default leak;\n')
            # jiti is the install's own, as pi's is: one from outside would be refused itself.
            shutil.copytree(package, install / "node_modules/jiti")
            jiti = install / "node_modules/jiti/lib/jiti.mjs"
            script = ('const { createJiti } = await import(process.argv[1]);'
                      'const jiti = createJiti(import.meta.url, { fsCache: false, moduleCache: false });'
                      'try { console.log(String((await jiti.import(process.argv[2], { default: true })))); }'
                      'catch (e) { console.log(e.message.startsWith("elm-pi: refusing") ? "refused" : e.message); }')
            args = [str(self.NODE), "--import", str(install / "lib/node-guard.mjs"), "--input-type=module", "-e",
                    script, str(jiti), str(install / "agent/ext.ts")]
            env = {k: v for k, v in os.environ.items() if k != "ELM_PI_ALLOW_EXTERNAL_MODULES"}
            guarded = subprocess.run(args, cwd=install, env=env, text=True, capture_output=True, check=True)
            self.assertEqual("refused", guarded.stdout.strip(), guarded.stderr)
            open_ = subprocess.run(args, cwd=install, env={**env, "ELM_PI_ALLOW_EXTERNAL_MODULES": "1"},
                                   text=True, capture_output=True, check=True)
            self.assertEqual("leaked", open_.stdout.strip(), open_.stderr)


class NoBareInterpreterTests(unittest.TestCase):
    # Every Python, node and npm run by install-time code and the launcher goes
    # through lib/sandbox.sh or the bundled Node by path. A bare `python3` is
    # whatever PATH says, which on a conda account is conda's.
    FILES = ("bootstrap.sh", "configure.sh", "pi", "pi.bash", "pi.orig", "install.sh",
             "scripts/check.sh")
    # In command position only: start of line, after $( | ; & ( exec then do,
    # optionally behind VAR=value assignments. Prose in messages is not code.
    COMMAND = re.compile(
        r"(?:^\s*|\$\(\s*|[|;&]\s*|\(\s*|\bexec\s+|\bthen\s+|\bdo\s+)"
        r"(?:\w+=\S*\s+)*(?:python3?|npm|npx|node)\s"
    )
    HEREDOC = re.compile(r"<<-?\s*'?(\w+)'?")

    def test_no_bare_interpreter_invocations(self):
        offenders = []
        for rel in self.FILES:
            terminator = None
            for number, line in enumerate((ROOT / rel).read_text().splitlines(), 1):
                if terminator:   # heredoc bodies are Python or help text
                    if line.strip() == terminator:
                        terminator = None
                    continue
                if line.lstrip().startswith("#"):
                    continue
                if self.COMMAND.search(line.split(" #")[0]):
                    offenders.append(f"{rel}:{number}: {line.strip()}")
                heredoc = self.HEREDOC.search(line)
                if heredoc:
                    terminator = heredoc.group(1)
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
