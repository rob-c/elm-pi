"""The launcher, configure.sh and the install-options record, run for real
against throwaway installs: stub pi.orig, installer and curl, no network."""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PI_AI = ROOT / "node_modules/@earendil-works/pi-ai"
PI_CORE = ROOT / "node_modules/@earendil-works/pi-coding-agent"


def write(path: Path, text: str, mode: int = 0o644) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)
    return path


# Records how it was called: one ARG: line per argument, then the variables a
# test asks about, as ENV:NAME=value (or ENV:NAME unset).
RECORDER = """#!/bin/sh
for a in "$@"; do printf 'ARG:%s\\n' "$a"; done
for n in $RECORD_ENV; do
  eval "v=\\${$n-__unset__}"
  printf 'ENV:%s=%s\\n' "$n" "$v"
done
exit "${RECORDER_EXIT:-0}"
"""


class Fixture:
    """A minimal install: the real launcher and lib/, everything else stubbed."""

    def __init__(self, base: Path, key: bool = True):
        self.root = base / "install"
        self.project = base / "project"
        self.home = base / "home"
        for d in (self.root, self.project, self.home):
            d.mkdir(parents=True)
        shutil.copy2(ROOT / "pi", self.root / "pi")
        shutil.copytree(ROOT / "lib", self.root / "lib")
        shutil.copytree(ROOT / "config", self.root / "config")
        shutil.copytree(ROOT / "scripts", self.root / "scripts")
        subprocess.run([sys.executable, str(self.root / "scripts/elm_config.py"), "--root", str(self.root), "init"],
                       check=True)
        write(self.root / "agent/settings.json", "{}\n")
        write(self.root / "agent/python-path", sys.executable + "\n")
        for name in ("elm-only", "protected-paths", "trust-guard", "pinned-instructions", "todo", "skill-router", "elm-shim"):
            write(self.root / f"agent/extensions/{name}.ts", "export default () => {};\n")
        self.gate = write(self.root / "agent/npm/node_modules/@gotgenes/pi-permission-system/src/index.ts", "\n")
        write(self.root / "proxy/egress.py", "\n")
        for name in ("pi.orig", "install.sh", "bootstrap.sh"):
            write(self.root / name, RECORDER, 0o755)
        write(self.root / ".env", "ELM_API_KEY=elm-test\n" if key else "ELM_API_KEY=\n")

    def run(self, *args, env=None, record=()):
        environ = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(self.home),
                   "TMPDIR": tempfile.gettempdir(), "PI_FORCE": "1", "ELM_PI_NO_PROXY": "1",
                   "ELM_PI_ALLOW_EXTERNAL_MODULES": "1", "RECORD_ENV": " ".join(record)}
        environ.update(env or {})
        result = subprocess.run([str(self.root / "pi"), *args], cwd=self.project, env=environ,
                                capture_output=True, text=True)
        result.args_seen = [l[4:] for l in result.stdout.splitlines() if l.startswith("ARG:")]
        result.env_seen = dict(l[4:].split("=", 1) for l in result.stdout.splitlines() if l.startswith("ENV:"))
        return result


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def extensions(self, args):
        return [args[i + 1] for i, a in enumerate(args) if a == "-e"]

    # --- item 5: --help in this install's environment --------------------------
    def test_help_runs_pi_against_this_agent_dir_offline_and_scrubbed(self):
        r = self.fx.run("--help", env={"ANTHROPIC_API_KEY": "sk-x", "COPILOT_GITHUB_TOKEN": "t"},
                        record=("PI_CODING_AGENT_DIR", "PI_OFFLINE", "PI_TELEMETRY",
                                "ANTHROPIC_API_KEY", "COPILOT_GITHUB_TOKEN"))
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("Flags added by this launcher", r.stdout)
        self.assertEqual(["--help"], r.args_seen)
        self.assertEqual(str(self.fx.root / "agent"), r.env_seen["PI_CODING_AGENT_DIR"])
        self.assertEqual("1", r.env_seen["PI_OFFLINE"])
        self.assertEqual("0", r.env_seen["PI_TELEMETRY"])
        self.assertEqual("__unset__", r.env_seen["ANTHROPIC_API_KEY"])
        self.assertEqual("__unset__", r.env_seen["COPILOT_GITHUB_TOKEN"])

    def test_help_still_works_on_a_broken_install(self):
        (self.fx.root / "agent/runtime.env").unlink()
        (self.fx.root / ".env").unlink()
        r = self.fx.run("-h", env={"OPENAI_API_KEY": "sk-x"}, record=("OPENAI_API_KEY", "PI_CODING_AGENT_DIR"))
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertIn("Flags added by this launcher", r.stdout)
        self.assertEqual("__unset__", r.env_seen["OPENAI_API_KEY"])   # list read from config/elm-pi.json
        self.assertEqual(str(self.fx.root / "agent"), r.env_seen["PI_CODING_AGENT_DIR"])

    def test_help_after_double_dash_is_prompt_text(self):
        r = self.fx.run("-p", "--", "--help")
        self.assertNotIn("Flags added by this launcher", r.stdout)

    # --- item 3: pi install / remove ----------------------------------------------
    def test_install_and_remove_are_refused_with_the_route_that_works(self):
        for command in ("install", "remove", "uninstall"):
            r = self.fx.run(command, "npm:left-pad")
            self.assertEqual(2, r.returncode, command)
            self.assertEqual([], r.args_seen, command)        # pi.orig never ran
            self.assertIn("templates/packages.json", r.stderr)

    # --- item 7: one policy list, gate required, exclusions merged -----------------
    def test_no_extensions_loads_the_same_policy_as_fast(self):
        policy = {str(self.fx.root / f"agent/extensions/{n}.ts")
                  for n in ("elm-only", "protected-paths", "trust-guard", "pinned-instructions")} | {str(self.fx.gate)}
        for flag in ("--no-extensions", "-ne"):
            r = self.fx.run(flag, "-p", "x")
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertEqual(policy, set(self.extensions(r.args_seen)), flag)
        r = self.fx.run("--fast", "-p", "x")
        self.assertTrue(policy <= set(self.extensions(r.args_seen)))
        self.assertIn("--no-extensions", r.args_seen)
        r = self.fx.run("-p", "x")
        self.assertEqual([], self.extensions(r.args_seen))   # discovery on: nothing added

    def test_a_gate_without_its_entry_point_stops_the_launch(self):
        self.fx.gate.unlink()
        for args in (("--fast", "-p", "x"), ("-ne", "-p", "x")):
            r = self.fx.run(*args)
            self.assertEqual(1, r.returncode, args)
            self.assertIn("permission gate", r.stderr)
        # an install without the package at all (--no-packages) has no gate anywhere
        shutil.rmtree(self.fx.root / "agent/npm")
        self.assertEqual(0, self.fx.run("--fast", "-p", "x").returncode)

    def test_callers_exclude_tools_is_merged_not_obeyed_instead(self):
        config = json.loads((ROOT / "config/elm-pi.json").read_text())
        web = ",".join(config["webTools"])
        always = ",".join(config["excludedTools"]["always"])
        workflows = ",".join(config["excludedTools"]["workflows"])
        default = f"{always},{web},{workflows}"
        excluded = lambda r: r.args_seen[r.args_seen.index("--exclude-tools") + 1]
        r = self.fx.run("-xt", "bash", "--exclude-tools", "edit", "-p", "x")
        args = r.args_seen
        self.assertEqual(1, args.count("--exclude-tools") + args.count("-xt"), args)
        self.assertEqual(f"{default},bash,edit", excluded(r))
        self.assertEqual(["-p", "x"], args[args.index("--exclude-tools") + 2:])
        # prompt text after -- is not an option
        r = self.fx.run("-p", "--", "-xt", "bash")
        self.assertEqual(default, excluded(r))
        self.assertEqual(["--", "-xt", "bash"], r.args_seen[-3:])
        # an explicit allowlist is left exactly as given
        r = self.fx.run("--tools", "read", "-p", "x")
        self.assertNotIn("--exclude-tools", r.args_seen)
        # PI_ELM_WEB=1 brings back the web tools only; --workflows the workflow tools only
        r = self.fx.run("-xt", "bash", "-p", "x", env={"PI_ELM_WEB": "1"})
        self.assertEqual(f"{always},{workflows},bash", excluded(r))
        r = self.fx.run("--workflows", "-p", "x")
        self.assertEqual(f"{always},{web}", excluded(r))
        self.assertNotIn("--workflows", r.args_seen)     # the launcher's flag, not pi's

    # --- item 9: the guard answers before the key check ------------------------------
    def test_guard_refuses_on_an_install_with_no_key(self):
        write(self.fx.root / ".env", "ELM_API_KEY=\n")
        r = self.fx.run("--model", "anthropic/claude-opus-5", "-p", "x")
        self.assertEqual(2, r.returncode)
        self.assertIn("restricted to the University", r.stderr)
        r = self.fx.run("-p", "x")
        self.assertEqual(1, r.returncode)
        self.assertIn("ELM_API_KEY is not set", r.stderr)

    def test_runner_count_is_portable(self):
        launcher = (ROOT / "pi").read_text()
        self.assertNotIn("pgrep -fc", launcher)
        line = next(l for l in launcher.splitlines() if l.strip().startswith("RUNNERS=\"$("))
        out = subprocess.run(["bash", "-c", f"set -euo pipefail; {line.strip()}; printf %s \"$RUNNERS\""],
                             capture_output=True, text=True)
        self.assertEqual(0, out.returncode, out.stderr)
        self.assertRegex(out.stdout, r"^\d+$")

    # --- item 2/6: the update intercepts ---------------------------------------------
    def test_update_paths_call_the_installer_and_bootstrap(self):
        r = self.fx.run("update")
        self.assertEqual(["--update", "--no-path", "--no-link"], r.args_seen)
        r = self.fx.run("update", "--extensions")
        self.assertEqual(["--force-packages", "--non-interactive"], r.args_seen)
        r = self.fx.run("update", env={"RECORDER_EXIT": "1"})
        self.assertEqual(1, r.returncode)
        self.assertIn("did not complete", r.stderr)
        self.assertNotIn("remains active", r.stderr)


class DeletedFolderTests(unittest.TestCase):
    """A shell sitting in a deleted folder must not start pi there."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fx = Fixture(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def from_shell(self, shell, steps):
        gone = Path(self.tmp.name) / "gone"
        gone.mkdir()
        environ = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(self.fx.home),
                   "TMPDIR": tempfile.gettempdir(), "PI_FORCE": "1", "ELM_PI_NO_PROXY": "1"}
        # The launcher runs under the same bash, not whichever `env bash` finds.
        script = f'cd "$1" && {steps} && exec "$0" "$2" -p hi'
        return subprocess.run([shell, "-c", script, shell, str(gone), str(self.fx.root / "pi")],
                              env=environ, capture_output=True, text=True)

    def shells(self):
        # macOS's /bin/bash is 3.2, a Homebrew or Linux bash is 5.x; they report
        # a deleted folder differently, and the launcher runs under either.
        found = {sh for sh in ("/bin/bash", shutil.which("bash") or "") if sh and Path(sh).exists()}
        return sorted(found)

    def test_a_deleted_folder_is_refused(self):
        for shell in self.shells():
            with self.subTest(shell=shell):
                r = self.from_shell(shell, 'rmdir "$1"')
                self.assertEqual(2, r.returncode, r.stderr)
                self.assertIn("has been deleted", r.stderr)
                self.assertNotIn("ARG:", r.stdout)  # pi.orig never ran

    def test_a_folder_recreated_at_the_same_path_is_still_refused(self):
        for shell in self.shells():
            with self.subTest(shell=shell):
                r = self.from_shell(shell, 'rmdir "$1" && mkdir "$1"')
                self.assertEqual(2, r.returncode, r.stderr)
                self.assertIn("has been deleted", r.stderr)
                self.assertNotIn("ARG:", r.stdout)
                gone = Path(self.tmp.name) / "gone"
                gone.rmdir()

    def test_an_ordinary_folder_starts(self):
        r = self.fx.run("-p", "hi")
        self.assertNotIn("has been deleted", r.stderr)
        self.assertEqual(["-p", "hi"], r.args_seen[-2:])


class ConfigureTests(unittest.TestCase):
    GATEWAY = {"data": [{"id": "meta-llama/Llama-3.3-70B-Instruct"}, {"id": "Qwen/Qwen3.5-397B-A17B-FP8-NEW"}]}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "install"
        self.root.mkdir()
        shutil.copy2(ROOT / "configure.sh", self.root / "configure.sh")
        for d in ("lib", "config", "scripts", "templates"):
            shutil.copytree(ROOT / d, self.root / d)
        render = [sys.executable, str(self.root / "scripts/elm_config.py"), "--root", str(self.root)]
        subprocess.run([*render, "init"], check=True)
        for name in ("models.json", "settings.json"):
            subprocess.run([*render, "render", str(self.root / "templates" / name), str(self.root / "agent" / name)],
                           check=True)
        write(self.root / ".env", "ELM_API_KEY=elm-test\n")
        write(self.root / "gateway.json", json.dumps(self.GATEWAY))
        # elm_install_env puts .node/bin first, so this curl wins.
        write(self.root / ".node/bin/curl", f"""#!/bin/sh
case "$*" in
  */models*) cat "{self.root}/gateway.json" ;;
  *) echo '{{"choices":[{{"message":{{"content":"OK"}}}}]}}' ;;
esac
""", 0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def configure(self, *args):
        env = {"PATH": "/usr/bin:/bin", "HOME": self.tmp.name, "ELM_PI_PYTHON": sys.executable}
        return subprocess.run([str(self.root / "configure.sh"), *args], cwd=self.root, env=env,
                              capture_output=True, text=True)

    def state(self):
        return json.loads((self.root / "agent/model-ids.json").read_text())

    def test_llama_is_refused_and_nothing_changes(self):
        before = {p: (self.root / "agent" / p).read_text() for p in ("model-ids.json", "models.json", "settings.json")}
        for match in ("llama", "Llama-3.3", "70B"):
            r = self.configure(match)
            self.assertEqual(2, r.returncode, (match, r.stderr))
            self.assertIn("Qwen model only", r.stderr)
        for p, text in before.items():
            self.assertEqual(text, (self.root / "agent" / p).read_text(), p)

    def test_qwen_is_set_in_the_qwen_slot_only(self):
        llama = self.state()["llama"]
        r = self.configure()
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual("Qwen/Qwen3.5-397B-A17B-FP8-NEW", self.state()["qwen"])
        self.assertEqual(llama, self.state()["llama"])
        models = json.loads((self.root / "agent/models.json").read_text())
        self.assertIn("Qwen/Qwen3.5-397B-A17B-FP8-NEW", [m["id"] for m in models["providers"]["elm"]["models"]])
        self.assertEqual([], list((self.root / "agent").glob(".models-raw.*")))
        # BSD mktemp randomises only trailing Xs
        self.assertNotRegex((ROOT / "configure.sh").read_text(), r'mktemp "[^"]*X{6}[^"X]')


class InstallOptionsTests(unittest.TestCase):
    """bootstrap.sh's options block, run on its own against a scratch agent/."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        text = (ROOT / "bootstrap.sh").read_text()
        apply_flag = re.search(r"^apply_flag\(\) \{.*?^\}\n", text, re.S | re.M).group(0)
        block = text[text.index("# --- the options this install was made with"):
                     text.index("# Before anything runs pi:")]
        self.script = ("set -euo pipefail\nsay() { :; }\n"
                       "WITH_SHIM=1; WITH_PACKAGES=1; AUTH_LOCK=1; WITH_TOOLS=1; WITH_PATCH=1\n"
                       'GIVEN_FLAGS="$1"; RESET_OPTIONS="$2"; HERE="$PWD"\n'
                       + apply_flag + block +
                       'echo "RESULT $WITH_SHIM $WITH_PACKAGES $AUTH_LOCK $WITH_TOOLS $WITH_PATCH|${ELM_PI_TOOLS:-}"\n')

    def tearDown(self):
        self.tmp.cleanup()

    def run_block(self, flags="", reset="0", **env):
        out = subprocess.run(["bash", "-c", self.script, "options", flags, reset], cwd=self.root,
                             env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True)
        self.assertEqual(0, out.returncode, out.stderr)
        return out.stdout.splitlines()[-1].split(" ", 1)[1]

    def saved(self):
        lines = (self.root / "agent/install-options").read_text().splitlines()
        return dict(l.split("=", 1) for l in lines if not l.startswith("#"))

    def test_flags_and_tools_are_recorded_and_repeated(self):
        self.assertEqual("0 1 1 1 1|fd,rg", self.run_block("--no-shim", ELM_PI_TOOLS="fd,rg",
                                                            ELM_PI_BRANCH="dev", ELM_PI_REPO="https://x/y.git"))
        self.assertEqual({"flags": "--no-shim", "tools": "fd,rg", "branch": "dev", "repo": "https://x/y.git"},
                         self.saved())
        # what `pi update --extensions` does: no flags, no environment
        self.assertEqual("0 1 1 1 1|fd,rg", self.run_block())
        # a flag given later is added; the branch and repository are kept
        self.assertEqual("0 0 1 1 1|fd,rg", self.run_block("--no-packages"))
        self.assertEqual({"flags": "--no-packages --no-shim", "tools": "fd,rg", "branch": "dev",
                          "repo": "https://x/y.git"}, self.saved())
        # --reset-options takes them back
        self.assertEqual("1 1 0 1 1|", self.run_block("--no-auth-lock", "1"))
        self.assertEqual("--no-auth-lock", self.saved()["flags"])
        self.assertEqual("dev", self.saved()["branch"])

    def test_an_install_from_before_the_record_is_read_from_what_it_left(self):
        write(self.root / "agent/settings.json", json.dumps({"packages": []}, indent=2))
        (self.root / "agent/extensions").mkdir()
        write(self.root / "agent/auth.json", "{}", 0o400)
        (self.root / "agent/bin").mkdir()
        self.assertEqual("0 0 1 0 1|", self.run_block())
        self.assertEqual({"--no-packages", "--no-shim", "--no-tools"}, set(self.saved()["flags"].split()))

    def test_installer_follows_the_recorded_branch_and_repository(self):
        text = (ROOT / "install.sh").read_text()
        block = text[text.index('PREFIX="${ELM_PI_PREFIX'):text.index('BRANCH="${BRANCH:-main}"')]
        script = f'set -euo pipefail\n{block}BRANCH="${{BRANCH:-main}}"\necho "$BRANCH $REPO"'
        run = lambda **env: subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                                           env={"PATH": "/usr/bin:/bin", "ELM_PI_PREFIX": str(self.root), **env}
                                           ).stdout.strip()
        self.assertEqual("main https://github.com/rob-c/elm-pi.git", run())
        write(self.root / "agent/install-options", "flags=\nbranch=dev\nrepo=https://x/y.git\n")
        self.assertEqual("dev https://x/y.git", run())
        self.assertEqual("other https://x/y.git", run(ELM_PI_BRANCH="other"))

    def test_verify_install_knows_no_shim_was_asked_for(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_install import extension_problems
        shutil.copytree(ROOT / "config", self.root / "config")
        for name in json.loads((ROOT / "config/elm-pi.json").read_text())["requiredExtensions"]:
            if name != "elm-shim.ts":
                write(self.root / "agent/extensions" / name, "\n")
        self.assertEqual(["required extension elm-shim.ts is missing from agent/extensions"],
                         extension_problems(self.root))
        write(self.root / "agent/install-options", "flags=--no-shim\n")
        self.assertEqual([], extension_problems(self.root))


class PinTests(unittest.TestCase):
    """scripts/pin_versions.py: what bootstrap.sh stamps and CI installs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.versions = write(self.dir / "versions.json", json.dumps(
            {"core": {"@earendil-works/pi-coding-agent": "1.4.0"}, "packages": {"a": "1.0.0"}}))
        self.manifest = write(self.dir / "package.json", json.dumps(
            {"dependencies": {"@earendil-works/pi-coding-agent": "latest"},
             "devDependencies": {"@earendil-works/pi-ai": "latest", "typescript": "latest"}}))

    def tearDown(self):
        self.tmp.cleanup()

    def pins(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "scripts/pin_versions.py"), "--versions",
                               str(self.versions), *args], check=True, capture_output=True, text=True).stdout

    def test_digest_moves_with_the_pins_of_its_own_section_only(self):
        core = self.pins("digest", str(self.manifest), "core")
        packages = self.pins("digest", str(self.manifest), "packages")
        data = json.loads(self.versions.read_text())
        data["packages"]["a"] = "2.0.0"
        self.versions.write_text(json.dumps(data))
        self.assertEqual(core, self.pins("digest", str(self.manifest), "core"))
        self.assertNotEqual(packages, self.pins("digest", str(self.manifest), "packages"))
        data["core"]["@earendil-works/pi-coding-agent"] = "1.5.0"
        self.versions.write_text(json.dumps(data))
        self.assertNotEqual(core, self.pins("digest", str(self.manifest), "core"))

    def test_stage_pins_unless_updating_and_pi_version_overrides(self):
        dest = self.dir / "staged.json"
        self.pins("stage", str(self.manifest), str(dest), "core", "--pi-version", "")
        self.assertEqual("1.4.0", json.loads(dest.read_text())["dependencies"]["@earendil-works/pi-coding-agent"])
        self.pins("stage", str(self.manifest), str(dest), "core", "--update", "--pi-version", "")
        self.assertEqual("latest", json.loads(dest.read_text())["dependencies"]["@earendil-works/pi-coding-agent"])
        self.pins("stage", str(self.manifest), str(dest), "core", "--update", "--pi-version", "1.3.9")
        self.assertEqual("1.3.9", json.loads(dest.read_text())["dependencies"]["@earendil-works/pi-coding-agent"])
        self.assertEqual("1.4.0\n", self.pins("pinned", "core", "@earendil-works/pi-coding-agent"))
        self.assertEqual("", self.pins("pinned", "packages", "absent"))

    def test_ci_manifest_moves_pis_siblings_with_it(self):
        data = json.loads(self.pins("dev", str(self.manifest)))
        self.assertEqual("1.4.0", data["dependencies"]["@earendil-works/pi-coding-agent"])
        self.assertEqual("1.4.0", data["devDependencies"]["@earendil-works/pi-ai"])
        self.assertEqual("latest", data["devDependencies"]["typescript"])

    def test_bootstrap_stamps_with_the_digest_and_extensions_mean_the_tested_set(self):
        text = (ROOT / "bootstrap.sh").read_text()
        self.assertIn('CORE_MANIFEST_DIGEST="$(manifest_digest package.json core)"', text)
        self.assertEqual(2, text.count('PACKAGE_MANIFEST_DIGEST="$(manifest_digest templates/packages.json packages)"'))
        self.assertNotIn("sha256_of package.json", text)
        self.assertIn('[ "$FORCE_PACKAGES" = "1" ] && [ -n "$PI_TESTED" ]', text)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("pin_versions.py --versions config/versions.json dev package.json", ci)


class CredentialListTests(unittest.TestCase):
    ENV_KEYS = PI_AI / "dist/env-api-keys.js"
    # In the list though no pi 1.4 file reads them: commercial-provider keys
    # other SDKs and older pi releases read. Unsetting them costs nothing.
    KEPT_DELIBERATELY = {"OPENAI_ORGANIZATION", "GOOGLE_GENERATIVE_AI_API_KEY"}

    def configured(self):
        return set(json.loads((ROOT / "config/elm-pi.json").read_text())["providerCredentials"])

    @unittest.skipUnless(ENV_KEYS.is_file(), "pi-ai is not installed in this checkout")
    def test_every_credential_pi_ai_reads_is_scrubbed(self):
        source = self.ENV_KEYS.read_text()
        env_map = re.search(r"const envMap = \{(.*?)\};", source, re.S).group(1)
        names = set(re.findall(r':\s*"([A-Z][A-Z0-9_]+)"', env_map))
        for listed in re.findall(r"return \[([^\]]*)\]", source):
            names |= set(re.findall(r'"([A-Z][A-Z0-9_]+)"', listed))
        names |= set(re.findall(r'export const \w+_ENV = "([A-Z][A-Z0-9_]+)"', source))
        self.assertGreater(len(names), 35)
        self.assertEqual(set(), names - self.configured(), "pi reads these and the launcher leaves them set")

    @unittest.skipUnless(PI_AI.is_dir() and PI_CORE.is_dir(), "pi is not installed in this checkout")
    def test_no_stale_names_in_the_scrub_list(self):
        text = []
        for tree in (PI_AI / "dist", PI_CORE / "dist"):
            for path in tree.rglob("*.js"):
                text.append(path.read_text(errors="replace"))
        text = "\n".join(text)
        stale = {n for n in self.configured() - self.KEPT_DELIBERATELY if f'"{n}"' not in text}
        self.assertEqual(set(), stale, "no file in this pi reads these")

    def test_huggingface_uses_pis_name(self):
        self.assertIn("HF_TOKEN", self.configured())
        self.assertNotIn("HUGGINGFACE_API_KEY", self.configured())


if __name__ == "__main__":
    unittest.main()
