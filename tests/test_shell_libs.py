"""lib/policy.sh, lib/sandbox.sh and lib/state.sh, and the option handling of
install.sh and bootstrap.sh, case by case.

Proves: which folders are never a project (and that their lookalikes are);
which variables the install-time scrub removes and which it keeps, in the
library and in install.sh's first pass; how PATH is cleaned, .env read, npm and
the install environment confined; how session paths are normalised and state
permissions tightened; what install.sh makes of every flag and environment
override, and how much disk it says it needs; and what bootstrap.sh records in
agent/install-options and repeats.

As in tests/test_launcher_cases.py, each class runs all of its cases in one bash
process, one subshell per case, against throwaway folders. Nothing is installed.
"""

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/elm-pi.json").read_text())
INSTALLER = (ROOT / "install.sh").read_text()
BOOTSTRAP = (ROOT / "bootstrap.sh").read_text()
SANDBOX_SRC = (ROOT / "lib/sandbox.sh").read_text()
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")
EXACT = "\n".join(CONFIG["untrustedFolders"]["exact"])
TREE = "\n".join(CONFIG["untrustedFolders"]["tree"])


def block(text, start, end):
    if text.count(start) != 1:
        raise AssertionError(f"anchor is not unique: {start!r}")
    i = text.index(start)
    return text[i:text.index(end, i)]


DUMP = r'''
_v() { local _n _s _x; for _n in "$@"; do eval "_s=\${$_n+x}"
  if [ -n "$_s" ]; then eval "_x=\${$_n}"; printf '@@%s=%s\n' "$_n" "$_x"; else printf '@@%s\n' "$_n"; fi; done; }
_a() { local _n="$1" _x; shift; for _x in "$@"; do printf '@@%s[]=%s\n' "$_n" "$_x"; done; }
'''


class Result:
    def __init__(self, rc, out, err):
        self.rc, self.out, self.err = rc, out, err
        self.vars, self.lists = {}, {}
        for line in out.splitlines():
            if not line.startswith("@@"):
                continue
            key, sep, value = line[2:].partition("=")
            if key.endswith("[]"):
                self.lists.setdefault(key[:-2], []).append(value)
            else:
                self.vars[key] = value if sep else None

    def list(self, name):
        return self.lists.get(name, [])


def run_batch(prelude, bodies, env, tmp):
    parts = ['T="$1"', DUMP, prelude]
    for i, body in enumerate(bodies):
        parts.append(f'(\n{body}\n) >"$T/.r{i}.out" 2>"$T/.r{i}.err" </dev/null\necho $? >"$T/.r{i}.rc"')
    subprocess.run([BASH, "-c", "\n".join(parts), "batch", str(tmp)], env=env, cwd=str(tmp),
                   check=True, capture_output=True, text=True, timeout=300)
    return [Result(int((tmp / f".r{i}.rc").read_text()), (tmp / f".r{i}.out").read_text(),
                   (tmp / f".r{i}.err").read_text()) for i in range(len(bodies))]


def q(value):
    return shlex.quote(str(value))


def exports(env):
    return "\n".join(f"unset {k}" if v is None else f"export {k}={q(v)}" for k, v in env.items())


def setargs(args):
    return "set -- " + " ".join(q(a) for a in args)


def as_list(value):
    if value is None:
        return []
    return [value] if isinstance(value, str) else list(value)


class Case:
    def __init__(self, name, args=(), env=None, bug=None, **kw):
        self.name, self.args, self.env, self.bug, self.kw = name, list(args), dict(env or {}), bug, kw


C = Case


class BatchTest(unittest.TestCase):
    """Runs CASES once per class, in one bash process; one test method per case."""

    CASES = ()

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            cls.home = cls.tmp / "home"
            cls.home.mkdir()
            cls.prepare()
            env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(cls.home), "LANG": "C",
                   "TMPDIR": str(cls.tmp)}
            results = run_batch(cls.prelude(), [cls.body(c) for c in cls.CASES], env, cls.tmp)
            cls.results = {c.name: r for c, r in zip(cls.CASES, results)}
        except BaseException:
            cls.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.cleanup()

    @classmethod
    def cleanup(cls):
        for root, dirs, _ in os.walk(cls.tmp):   # a case may leave a folder read-only
            for d in dirs:
                try:
                    os.chmod(os.path.join(root, d), 0o700)
                except OSError:
                    pass
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def prepare(cls):
        pass

    @classmethod
    def prelude(cls):
        return ""

    @classmethod
    def index(cls, case):
        return next(i for i, c in enumerate(cls.CASES) if c is case)

    def check(self, case, r):
        kw = case.kw
        self.assertEqual(kw.get("rc", 0), r.rc, f"stdout:\n{r.out}\nstderr:\n{r.err}")
        for key, want in kw.get("vars", {}).items():
            self.assertEqual(want, r.vars.get(key, "<not dumped>"), key)
        for text in as_list(kw.get("err_has")):
            self.assertIn(text, r.err)
        for text in as_list(kw.get("out_has")):
            self.assertIn(text, r.out)
        for text in as_list(kw.get("out_lacks")):
            self.assertNotIn(text, r.out)


def generate(cls):
    for case in cls.CASES:
        name = "test_" + re.sub(r"\W+", "_", case.name).strip("_").lower()
        if hasattr(cls, name):
            raise ValueError(f"duplicate case {name} in {cls.__name__}")

        def test(self, case=case):
            skip = case.kw.get("skip_unless")
            if skip is not None and not Path(skip).exists():
                raise unittest.SkipTest(f"{skip} does not exist on this machine")
            self.check(case, type(self).results[case.name])
        test.__name__ = name
        if case.bug:
            test = unittest.expectedFailure(test)
        setattr(cls, name, test)
    return cls


def touch(path, text="", mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(mode)
    return path


# --- folders that are never a project (lib/policy.sh elm_untrusted_folder) ----------

HOME_MSG = "your home folder"
ANCESTOR_MSG = "a folder that contains your home folder"


def exact(entry):
    return f"{entry}, which holds far more than one project"


def inside(path):
    return f"inside {path}, which holds credentials or system files"


def refused(name, path, what, **kw):
    return C(name, path=path, want="YES:" + what, **kw)


def fine(name, path, **kw):
    return C(name, path=path, want="NO", **kw)


HOME_EXACT = ("Desktop", "Downloads", "Library", "Library/Mobile Documents",
              "Library/Mobile Documents/com~apple~CloudDocs", ".config", ".local", ".local/share", ".cache")
HOME_TREE = (".gnupg", ".aws", ".azure", ".kube", ".docker", ".pi", ".password-store", ".config/gh",
             ".config/gcloud", "Library/Keychains", "Library/Application Support", "Library/Mail",
             "Library/Messages", "Library/Cookies", "Library/Safari")
NESTED_TREE = ((".aws/sso/cache", ".aws"), (".pi/agent", ".pi"), (".config/gh/hosts", ".config/gh"),
               ("Library/Application Support/Code/User", "Library/Application Support"))
LOOKALIKES = ("projects", "projects/a/b", ".sshx", ".ssh-backup", ".aws2", ".config/ghx", ".config/gh-cli",
              "Library/Mailbox", "projects/.ssh", ".pix", ".dockerfiles", "Desktop/talk", "Downloads/dataset",
              ".config/myapp", ".local/share/proj", ".cache/build",
              "Library/Mobile Documents/com~apple~CloudDocs/paper", "Library/Application Supportive")


def slug(rel):
    return re.sub(r"\W+", "_", rel.replace("~", "tilde")).strip("_").lower()


SYSTEM_EXACT = ("/tmp", "/opt", "/Users", "/home", "/Volumes")
SYSTEM_TREE = (("/usr/bin", "/usr"), ("/etc/ssh", "/etc"), ("/System/Library", "/System"),
               ("/Library/Preferences", "/Library"), ("/Applications/Utilities", "/Applications"))

UNTRUSTED_CASES = (
    refused("home_with_a_trailing_slash", "{home}/", HOME_MSG),
    refused("home_through_dot_dot", "{home}/projects/..", HOME_MSG),
    refused("home_through_a_symlink", "{tmp}/homelink", HOME_MSG),
    refused("a_literal_tilde", "~", HOME_MSG),
    refused("the_grandparent_of_home", "{tmp}/..", ANCESTOR_MSG),
    *(refused(f"container_{slug(rel)}", "{home}/" + rel, exact("~/" + rel)) for rel in HOME_EXACT),
    *(C(f"system_container_{slug(p)}", path=p, system_exact=p, skip_unless=p) for p in SYSTEM_EXACT),
    *(refused(f"credential_folder_{slug(rel)}", "{home}/" + rel, inside("{home}/" + rel)) for rel in HOME_TREE),
    *(refused(f"inside_{slug(rel)}", "{home}/" + rel, inside("{home}/" + top)) for rel, top in NESTED_TREE),
    *(C(f"system_tree_{slug(p)}", path=p, system_tree=top, skip_unless=p) for p, top in SYSTEM_TREE),
    refused("a_symlink_into_ssh", "{home}/keys-link", inside("{home}/.ssh")),
    refused("a_symlink_to_downloads", "{home}/dl", exact("~/Downloads")),
    refused("a_home_with_a_space", "{tmp}/My Home", HOME_MSG, env={"HOME": "{tmp}/My Home"}),
    refused("ssh_in_a_home_with_a_space", "{tmp}/My Home/.ssh", inside("{tmp}/My Home/.ssh"),
            env={"HOME": "{tmp}/My Home"}),
    fine("a_project_in_a_home_with_a_space", "{tmp}/My Home/proj", env={"HOME": "{tmp}/My Home"}),
    refused("home_variable_with_a_trailing_slash", "{home}", HOME_MSG, env={"HOME": "{home}/"}),
    refused("home_variable_through_a_symlink", "{home}", HOME_MSG, env={"HOME": "{tmp}/homelink"}),
    refused("ssh_with_home_through_a_symlink", "{home}/.ssh", inside("{home}/.ssh"),
            env={"HOME": "{tmp}/homelink"}),
    refused("empty_lists_still_refuse_home", "{home}", HOME_MSG,
            env={"ELM_UNTRUSTED_EXACT": "", "ELM_UNTRUSTED_TREE": ""}),
    fine("empty_lists_leave_ssh_alone", "{home}/.ssh", env={"ELM_UNTRUSTED_EXACT": "", "ELM_UNTRUSTED_TREE": ""}),
    fine("empty_lists_leave_downloads_alone", "{home}/Downloads",
         env={"ELM_UNTRUSTED_EXACT": "", "ELM_UNTRUSTED_TREE": ""}),
    *(fine(f"lookalike_{slug(rel)}", "{home}/" + rel) for rel in LOOKALIKES),
    fine("a_sibling_whose_name_starts_like_home", "{tmp}/homework"),
    fine("another_folder_beside_home", "{tmp}/other"),
    fine("a_folder_under_slash_tmp", "{slashtmp}"),
    fine("a_symlink_to_a_project", "{home}/plink"),
)


@generate
class UntrustedFolderTests(BatchTest):
    """elm_untrusted_folder: the refusal, and the description the launcher prints."""

    CASES = UNTRUSTED_CASES

    @classmethod
    def prepare(cls):
        h = cls.home
        for rel in (*HOME_EXACT, *HOME_TREE, *(r for r, _ in NESTED_TREE), *LOOKALIKES, ".ssh"):
            (h / rel).mkdir(parents=True, exist_ok=True)
        (cls.tmp / "homelink").symlink_to(h)
        (h / "keys-link").symlink_to(h / ".ssh")
        (h / "dl").symlink_to(h / "Downloads")
        (h / "plink").symlink_to(h / "projects")
        for sub in ("My Home/.ssh", "My Home/proj", "homework", "other"):
            (cls.tmp / sub).mkdir(parents=True)
        cls.slashtmp = Path(tempfile.mkdtemp(dir="/tmp")) if Path("/tmp").is_dir() else cls.tmp / "other"

    @classmethod
    def cleanup(cls):
        slashtmp = getattr(cls, "slashtmp", None)
        if slashtmp is not None and str(slashtmp).startswith("/tmp/"):
            shutil.rmtree(slashtmp, ignore_errors=True)
        super().cleanup()

    @classmethod
    def fill(cls, text):
        return text.format(home=cls.home, tmp=cls.tmp, slashtmp=cls.slashtmp)

    @classmethod
    def prelude(cls):
        return f". {q(ROOT / 'lib/policy.sh')}"

    @classmethod
    def body(cls, case):
        env = {"ELM_UNTRUSTED_EXACT": EXACT, "ELM_UNTRUSTED_TREE": TREE,
               **{k: cls.fill(v) for k, v in case.env.items()}}
        return "\n".join([exports(env),
                          f'if elm_untrusted_folder {q(cls.fill(case.kw["path"]))}; then V="YES:$ELM_UNTRUSTED_WHAT"; '
                          'else V=NO; fi', "_v V"])

    def check(self, case, r):
        self.assertEqual(0, r.rc, r.err)
        kw = case.kw
        if "system_exact" in kw:
            # The temporary home may itself be under one of these (/tmp on Linux),
            # and then it is refused as an ancestor of home before the list is read.
            real = os.path.realpath(kw["path"])
            home = os.path.realpath(self.home)
            want = "YES:" + (ANCESTOR_MSG if home.startswith(real + "/") else exact(kw["path"]))
        elif "system_tree" in kw:
            want = "YES:" + inside(os.path.realpath(kw["system_tree"]))
        else:
            want = self.fill(kw["want"])
        self.assertEqual(want, r.vars["V"])


# --- the install-time scrub (lib/sandbox.sh elm_scrub_env) ----------------------------

def gone(var, value="x"):
    return C(f"removes_{var.lower()}", var=var, value=value, kept=False)


def kept(var, value="x"):
    return C(f"keeps_{var.lower()}", var=var, value=value, kept=True)


PREFIXED = ("PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONX", "CONDA_EXE", "CONDA_DEFAULT_ENV", "CONDAX",
            "_CE_M", "MAMBA_ROOT_PREFIX", "MAMBA_EXE", "VIRTUAL_ENV_PROMPT", "PIP_CONFIG_FILE",
            "PIP_REQUIRE_VIRTUALENV", "PYENV_VERSION", "PYENV_ROOT", "npm_config_prefix", "NPM_CONFIG_REGISTRY",
            "NODE_ENV", "NODE_TLS_REJECT_UNAUTHORIZED", "NVM_BIN", "VOLTA_HOME", "FNM_DIR", "ASDF_DATA_DIR",
            "COREPACK_HOME", "YARN_CACHE_FOLDER", "PNPM_HOME", "BUN_INSTALL", "GIT_SSH_COMMAND", "GIT_EXEC_PATH")
NAMED = ("ENV", "GZIP", "UNZIP", "UNZIPOPT", "GREP_OPTIONS", "CURL_HOME", "LD_PRELOAD", "LD_LIBRARY_PATH")
# Lookalikes: a prefix matches at the start only, and the _ is part of it.
UNSCRUBBED = ("MY_PYTHON", "XNODE_OPTIONS", "NODEJS_HOME", "GITHUB_TOKEN", "GITLAB_TOKEN", "PIPENV_VENV_IN_PROJECT",
              "VIRTUALENVWRAPPER_PYTHON", "node_options", "Npm_Config_Cache", "BASH_ENV_FILE", "ENVIRONMENT",
              "LD_RUN_PATH", "DYLD_LIBRARY_PATH", "AWS_PROFILE", "HTTPS_PROXY", "SSH_AUTH_SOCK")

SCRUB_CASES = (
    *(gone(v) for v in PREFIXED),
    *(gone(v) for v in NAMED),
    *(kept(v) for v in UNSCRUBBED),
    C("removes_a_curl_ca_bundle_that_is_gone", var="CURL_CA_BUNDLE", value="{missing}", kept=False),
    C("keeps_a_curl_ca_bundle_that_exists", var="CURL_CA_BUNDLE", value="{file}", kept=True),
    C("removes_a_requests_ca_bundle_that_is_gone", var="REQUESTS_CA_BUNDLE", value="{missing}", kept=False),
    C("keeps_a_requests_ca_bundle_that_exists", var="REQUESTS_CA_BUNDLE", value="{file}", kept=True),
    C("keeps_an_ssl_cert_file_that_exists", var="SSL_CERT_FILE", value="{file}", kept=True),
    C("removes_an_ssl_cert_file_naming_a_folder", var="SSL_CERT_FILE", value="{tmp}", kept=False),
    C("removes_a_node_extra_ca_certs_that_is_gone", var="NODE_EXTRA_CA_CERTS", value="{missing}", kept=False),
    C("keeps_an_empty_ssl_cert_file", var="SSL_CERT_FILE", value="", kept=True),
)


@generate
class ScrubEnvTests(BatchTest):
    """Every scrubbed prefix and name, the lookalikes kept, and the CA-bundle rule."""

    CASES = SCRUB_CASES

    @classmethod
    def prepare(cls):
        touch(cls.tmp / "ca.pem", "-----BEGIN CERTIFICATE-----\n")

    @classmethod
    def value(cls, case):
        return case.kw["value"].format(file=cls.tmp / "ca.pem", missing=cls.tmp / "gone/ca.pem", tmp=cls.tmp)

    @classmethod
    def prelude(cls):
        return f". {q(ROOT / 'lib/sandbox.sh')}"

    @classmethod
    def body(cls, case):
        var = case.kw["var"]
        return "\n".join([f"export {var}={q(cls.value(case))}", "elm_scrub_env", f"_v {var} HOME PATH"])

    def check(self, case, r):
        self.assertEqual(0, r.rc, r.err)
        want = self.value(case) if case.kw["kept"] else None
        self.assertEqual(want, r.vars[case.kw["var"]])
        self.assertEqual(str(self.home), r.vars["HOME"])


INSTALL_SCRUB_CASES = (
    *(C(f"removes_{v.lower()}", var=v, kept=False) for v in
      ("PYTHONSAFEPATH", "CONDA_SHLVL", "npm_config_userconfig", "NODE_PATH", "VOLTA_FEATURE_PNPM",
       "GIT_CONFIG_PARAMETERS", "LD_PRELOAD", "GREP_OPTIONS", "UNZIP")),
    *(C(f"keeps_{v.lower()}", var=v, kept=True) for v in ("GITHUB_TOKEN", "NODEJS_ORG_MIRROR", "ELM_API_KEY")),
    C("keeps_node_extra_ca_certs_by_name", var="NODE_EXTRA_CA_CERTS", kept=True),
    # The first pass has no CA-bundle check: that is lib/sandbox.sh's, in bootstrap.
    C("first_pass_keeps_a_ca_bundle_that_is_gone", var="SSL_CERT_FILE", value="/no/such/cacert.pem", kept=True),
    C("system_folders_go_first_on_path", var="X", kept=True,
      vars={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/mine/bin:/usr/bin:/bin",
            "ELM_PI_USER_PATH": "/opt/mine/bin:/usr/bin:/bin"}),
    C("git_ignores_the_accounts_config", var="X", kept=True,
      vars={"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}),
)


@generate
class InstallerScrubTests(BatchTest):
    """install.sh's own first pass, before lib/sandbox.sh has been downloaded."""

    CASES = INSTALL_SCRUB_CASES
    BLOCK = block(INSTALLER, 'ELM_SCRUB_PREFIXES="', 'PREFIX="${ELM_PI_PREFIX')

    @classmethod
    def body(cls, case):
        var = case.kw["var"]
        return "\n".join(["set -euo pipefail", "PATH=/opt/mine/bin:/usr/bin:/bin",
                          f"export {var}={q(case.kw.get('value', 'x'))}", cls.BLOCK,
                          f"_v {var} PATH ELM_PI_USER_PATH GIT_CONFIG_NOSYSTEM GIT_CONFIG_GLOBAL GIT_TERMINAL_PROMPT"])

    def check(self, case, r):
        super().check(case, r)
        self.assertEqual(case.kw.get("value", "x") if case.kw["kept"] else None, r.vars[case.kw["var"]])


# --- other lib/sandbox.sh helpers ----------------------------------------------------

REL = re.search(r'ELM_STANDALONE_PY_RELEASE="([^"]+)"', SANDBOX_SRC).group(1)
VER = re.search(r'ELM_STANDALONE_PY_VERSION="([^"]+)"', SANDBOX_SRC).group(1)


def asset(name, system, machine, triple):
    want = None if triple is None else f"cpython-{VER}+{REL}-{triple}-install_only.tar.gz"
    return C(name, script=f'uname() {{ case "$1" in -s) echo {system} ;; -m) echo {machine} ;; esac; }}\n'
                          'OUT="$(elm_standalone_python_asset)" || OUT="NONE"', asset=want)


SANDBOX_CASES = (
    C("clean_path_drops_fnm_versions", script='OUT="$(elm_clean_path "/h/.fnm/node-versions/v20/bin:/usr/bin")"',
      vars={"OUT": "/usr/bin"}),
    C("clean_path_drops_fnm_multishells", script='OUT="$(elm_clean_path "/tmp/fnm_multishells/1_2/bin:/bin")"',
      vars={"OUT": "/bin"}),
    C("clean_path_drops_asdf_shims", script='OUT="$(elm_clean_path "/h/.asdf/shims:/bin")"', vars={"OUT": "/bin"}),
    C("clean_path_drops_npm_global", script='OUT="$(elm_clean_path "/h/.npm-global/bin:/bin")"',
      vars={"OUT": "/bin"}),
    C("clean_path_drops_node_modules_bin", script='OUT="$(elm_clean_path "/p/node_modules/.bin:/bin")"',
      vars={"OUT": "/bin"}),
    C("relative_only_keeps_version_managers", script='OUT="$(elm_clean_path "/h/.pyenv/shims:./x:/bin" relative-only)"',
      vars={"OUT": "/h/.pyenv/shims:/bin"}),
    C("clean_path_of_nothing_is_nothing", script='OUT="$(elm_clean_path "")"', vars={"OUT": ""}),
    C("clean_path_does_not_glob", script='OUT="$(elm_clean_path "/b*n:/usr/bin")"', vars={"OUT": "/b*n:/usr/bin"}),
    C("npm_env_takes_a_site_npmrc", env={"ELM_PI_NPM_USERCONFIG": "/site/npmrc"}, script="elm_npm_env /srv/i",
      vars={"NPM_CONFIG_USERCONFIG": "/site/npmrc", "NPM_CONFIG_PREFIX": "/srv/i/.node"}),
    C("npm_env_drops_node_env", env={"NODE_ENV": "production"}, script="elm_npm_env /srv/i",
      vars={"NODE_ENV": None}),
    C("npm_env_drops_any_spelling_of_npm_config", env={"npm_CONFIG_foo": "1", "NPM_config_BAR": "2"},
      script="elm_npm_env /srv/i", vars={"npm_CONFIG_foo": None, "NPM_config_BAR": None}),
    C("install_env_remembers_the_accounts_path", script='PATH=/opt/mine/bin:/usr/bin; elm_install_env /srv/i',
      vars={"ELM_PI_USER_PATH": "/opt/mine/bin:/usr/bin", "ELM_PI_ROOT": "/srv/i"}),
    C("install_env_keeps_an_earlier_user_path", env={"ELM_PI_USER_PATH": "/kept/bin"},
      script="elm_install_env /srv/i", vars={"ELM_PI_USER_PATH": "/kept/bin"}),
    C("install_env_puts_bundled_node_first",
      script='PATH=/opt/mine/bin; elm_install_env /srv/i',
      vars={"PATH": "/srv/i/.node/bin:/usr/bin:/bin:/usr/sbin:/sbin:/opt/mine/bin"}),
    C("install_env_turns_off_the_accounts_git_config", script="elm_install_env /srv/i",
      vars={"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}),
    C("install_env_sets_umask_022", script='umask 077; elm_install_env /srv/i; OUT="$(umask)"',
      vars={"OUT": "0022"}),
    C("install_env_scrubs_too", env={"PYTHONPATH": "/evil"}, script="elm_install_env /srv/i",
      vars={"PYTHONPATH": None}),
    asset("standalone_python_for_apple_silicon", "Darwin", "arm64", "aarch64-apple-darwin"),
    asset("standalone_python_for_intel_macs", "Darwin", "x86_64", "x86_64-apple-darwin"),
    asset("standalone_python_for_linux_x86_64", "Linux", "x86_64", "x86_64-unknown-linux-gnu"),
    asset("standalone_python_for_linux_amd64", "Linux", "amd64", "x86_64-unknown-linux-gnu"),
    asset("standalone_python_for_linux_aarch64", "Linux", "aarch64", "aarch64-unknown-linux-gnu"),
    asset("standalone_python_for_linux_arm64", "Linux", "arm64", "aarch64-unknown-linux-gnu"),
    asset("no_standalone_python_for_freebsd", "FreeBSD", "amd64", None),
    asset("no_standalone_python_for_32_bit_linux", "Linux", "i686", None),
    C("reason_for_too_old", script='OUT="$(elm_python_reason 10)"', vars={"OUT": "older than 3.8"}),
    C("reason_for_conda", script='OUT="$(elm_python_reason 11)"', vars={"OUT": "conda"}),
    C("reason_for_virtualenv", script='OUT="$(elm_python_reason 12)"', vars={"OUT": "virtualenv"}),
    C("reason_for_a_shim", script='OUT="$(elm_python_reason 13)"', vars={"OUT": "version-manager shim"}),
    C("reason_for_anything_else", script='OUT="$(elm_python_reason 1)"', vars={"OUT": "does not run"}),
    C("python_check_refuses_an_asdf_install", script='mkdir -p "$T/x/.asdf/bin"; printf "#!/bin/sh\\n" > '
      '"$T/x/.asdf/bin/python3"; chmod 755 "$T/x/.asdf/bin/python3"; '
      'elm_python_check "$T/x/.asdf/bin/python3" && OUT=0 || OUT=$?', vars={"OUT": "13"}),
    C("python_check_refuses_a_directory", script='elm_python_check "$T" && OUT=0 || OUT=$?', vars={"OUT": "1"}),
    C("an_explicit_shim_is_refused_with_the_way_out",
      script='mkdir -p "$T/s/.pyenv/shims"; printf "#!/bin/sh\\n" > "$T/s/.pyenv/shims/python3"; '
      'chmod 755 "$T/s/.pyenv/shims/python3"; export ELM_PI_PYTHON="$T/s/.pyenv/shims/python3"; '
      'elm_select_python "" && OUT=ok || OUT="$ELM_PY_ERROR"',
      out_has="is a version-manager shim; name the real interpreter"),
    C("an_explicit_missing_python_is_refused", env={"ELM_PI_PYTHON": "/no/such/python3"},
      script='elm_select_python "" && OUT=ok || OUT="$ELM_PY_ERROR"',
      out_has="ELM_PI_PYTHON=/no/such/python3 is not a runnable Python (it must be an absolute path)"),
    C("a_private_folder_is_private", script='mkdir -m 700 "$T/p1"; elm_dir_is_private "$T/p1" && OUT=1 || OUT=0',
      vars={"OUT": "1"}),
    C("a_group_writable_folder_is_not_private",
      script='mkdir "$T/p2"; chmod 770 "$T/p2"; elm_dir_is_private "$T/p2" && OUT=1 || OUT=0', vars={"OUT": "0"}),
    C("a_symlink_to_a_private_folder_is_not_private",
      script='mkdir -m 700 "$T/p3"; ln -s "$T/p3" "$T/p3link"; elm_dir_is_private "$T/p3link" && OUT=1 || OUT=0',
      vars={"OUT": "0"}),
    C("private_tmpdir_refuses_a_tmpdir_that_is_a_file",
      script='touch "$T/afile"; TMPDIR="$T/afile"; elm_private_tmpdir && OUT=ok || OUT="$ELM_PY_ERROR"',
      out_has="is not a private directory owned by you"),
    C("private_tmpdir_ignores_a_trailing_slash",
      script='mkdir -m 700 "$T/p4"; TMPDIR="$T/p4/"; elm_private_tmpdir; OUT="$TMPDIR"',
      vars={"OUT": "{tmp}/p4/"}),
)


@generate
class SandboxHelperTests(BatchTest):
    """PATH cleaning, npm and install-time environments, the standalone Python's
    asset per platform, interpreter refusals and the private TMPDIR."""

    CASES = SANDBOX_CASES

    @classmethod
    def prelude(cls):
        return f". {q(ROOT / 'lib/sandbox.sh')}"

    @classmethod
    def body(cls, case):
        return "\n".join([exports(case.env), case.kw["script"],
                          "_v OUT " + " ".join(case.kw.get("vars", {}))])

    def check(self, case, r):
        self.assertEqual(0, r.rc, r.err)
        for key, want in case.kw.get("vars", {}).items():
            self.assertEqual(None if want is None else want.format(tmp=self.tmp), r.vars[key], key)
        for text in as_list(case.kw.get("out_has")):
            self.assertIn(text, r.vars["OUT"])
        if "asset" in case.kw:
            if case.kw["asset"] is None:
                self.assertEqual("NONE", r.vars["OUT"])
            else:
                name, digest = r.vars["OUT"].split(" ")
                self.assertEqual(case.kw["asset"], name)
                self.assertRegex(digest, r"^[0-9a-f]{64}$")


# --- .env read as data -----------------------------------------------------------------

DOTENV_CASES = (
    C("a_value_with_an_equals_sign", text="ELM_X=a=b\n", value="a=b"),
    C("an_empty_value", text="ELM_X=\n", value=""),
    C("double_quotes_are_removed", text='ELM_X="a b"\n', value="a b"),
    C("single_quotes_are_removed", text="ELM_X='a b'\n", value="a b"),
    C("an_unclosed_quote_is_kept", text='ELM_X="abc\n', value='"abc'),
    C("mismatched_quotes_are_kept", text="ELM_X=\"abc'\n", value="\"abc'"),
    C("inner_quotes_are_kept", text='ELM_X=a"b"\n', value='a"b"'),
    C("leading_spaces_are_ignored", text="   ELM_X=1\n", value="1"),
    C("trailing_spaces_are_part_of_the_value", text="ELM_X=a  \n", value="a  "),
    C("an_indented_comment", text="   # ELM_X=1\n", value=None, ignored=0),
    C("a_lower_case_key_is_ignored", text="elm_x=1\n", value=None, ignored=1),
    C("a_mixed_case_key_is_ignored", text="ELM_x=1\n", value=None, ignored=1),
    C("a_space_before_the_equals_is_ignored", text="ELM_X =1\n", value=None, ignored=1),
    C("a_key_without_a_value_is_ignored", text="ELM_X\n", value=None, ignored=1),
    C("export_with_two_spaces_is_ignored", text="export  ELM_X=1\n", value=None, ignored=1),
    C("the_last_line_needs_no_newline", text="ELM_X=1", value="1"),
    C("a_later_line_wins", text="ELM_X=1\nELM_X=2\n", value="2"),
    C("elm_with_nothing_after_is_ignored", text="ELM_=1\n", value=None, ignored=1),
    C("digits_in_the_key", text="ELM_X=1\nELM_2=two\n", value="1", other=("ELM_2", "two")),
    C("home_cannot_be_set", text="HOME=/evil\nELM_X=1\n", value="1", ignored=1, home_kept=True),
    C("a_missing_file_is_not_an_error", text=None, value=None, ignored=0),
    C("the_reported_line_number_counts_comments", text="# a\n\nbad line\n", value=None, ignored=1,
      err_has="ignoring line 3 of"),
)


@generate
class DotenvTests(BatchTest):
    """elm_load_dotenv: ELM_*=value lines only, quotes stripped only in pairs."""

    CASES = DOTENV_CASES

    @classmethod
    def prepare(cls):
        for i, case in enumerate(cls.CASES):
            if case.kw["text"] is not None:
                (cls.tmp / f"env{i}").write_text(case.kw["text"])

    @classmethod
    def prelude(cls):
        return f". {q(ROOT / 'lib/sandbox.sh')}"

    @classmethod
    def body(cls, case):
        return "\n".join(["unset ELM_X ELM_2", f'elm_load_dotenv "$T/env{cls.index(case)}"', "_v ELM_X ELM_2 HOME"])

    def check(self, case, r):
        kw = case.kw
        self.assertEqual(0, r.rc, r.err)
        self.assertEqual(kw["value"], r.vars["ELM_X"])
        self.assertEqual(kw.get("ignored", 0), r.err.count("ignoring line"))
        if "other" in kw:
            self.assertEqual(kw["other"][1], r.vars[kw["other"][0]])
        if kw.get("home_kept"):
            self.assertEqual(str(self.home), r.vars["HOME"])
        for text in as_list(kw.get("err_has")):
            self.assertIn(text, r.err)


# --- permissions: lib/state.sh, and elm_tighten_install_perms ----------------------------

MODE_CASES = (
    C("auth_writable_when_asked", files={"auth.json": 0o644}, run="elm_set_auth_mode auth.json 1",
      modes={"auth.json": 0o600}),
    C("auth_mode_on_a_missing_file_is_fine", files={}, run="elm_set_auth_mode auth.json 0", modes={}),
    C("a_missing_session_folder_is_made_private", files={}, run="elm_secure_session_dir s/new",
      modes={"s/new": 0o700}),
    C("transcripts_in_subfolders_are_secured", files={"s/sub/a.jsonl": 0o644}, run="elm_secure_session_dir s",
      modes={"s/sub/a.jsonl": 0o600}),
    C("other_files_in_the_session_folder_are_left", files={"s/notes.md": 0o664, "s/x.jsonl.bak": 0o644},
      run="elm_secure_session_dir s", modes={"s/notes.md": 0o664, "s/x.jsonl.bak": 0o644}),
    C("the_egress_log_is_secured", files={"i/agent/egress.log": 0o644}, run="elm_secure_install_state i",
      modes={"i/agent/egress.log": 0o600, "i/agent": 0o700}),
    C("memory_folders_are_secured", files={"i/agent/projects-memory/p/x.db": 0o644},
      run="elm_secure_install_state i",
      modes={"i/agent/projects-memory/p": 0o700, "i/agent/projects-memory/p/x.db": 0o600}),
    C("secure_file_on_a_missing_file_is_fine", files={}, run="elm_secure_file nothing-here", modes={}),
    C("tighten_takes_group_write_off_code", files={"r/lib/x.sh": 0o664}, run="elm_tighten_install_perms r",
      modes={"r/lib/x.sh": 0o644}),
    C("tighten_when_shared_takes_only_other_write", files={"r/lib/x.sh": 0o666}, env={"ELM_PI_SHARED_STATE": "1"},
      run="elm_tighten_install_perms r", modes={"r/lib/x.sh": 0o664}),
    C("tighten_leaves_folders_that_are_not_code", files={"r/agent/sessions/s.txt": 0o666},
      run="elm_tighten_install_perms r", modes={"r/agent/sessions/s.txt": 0o666}),
    C("tighten_covers_the_launcher", files={"r/pi": 0o777}, run="elm_tighten_install_perms r",
      modes={"r/pi": 0o755}),
)


@generate
class ModeTests(BatchTest):
    """The permission helpers, on real files."""

    CASES = MODE_CASES

    @classmethod
    def prepare(cls):
        for i, case in enumerate(cls.CASES):
            d = cls.tmp / f"m{i}"
            d.mkdir()
            for rel, mode in case.kw["files"].items():
                touch(d / rel, "x\n", mode)

    @classmethod
    def prelude(cls):
        return f". {q(ROOT / 'lib/state.sh')}\n. {q(ROOT / 'lib/sandbox.sh')}"

    @classmethod
    def body(cls, case):
        return "\n".join([exports(case.env), f'cd "$T/m{cls.index(case)}"', case.kw["run"]])

    def check(self, case, r):
        self.assertEqual(0, r.rc, r.err)
        d = self.tmp / f"m{self.index(case)}"
        for rel, mode in case.kw["modes"].items():
            self.assertEqual(oct(mode), oct(stat.S_IMODE((d / rel).stat().st_mode)), rel)


NORMALIZE_CASES = (
    C("a_tilde_alone", value="~", want="{home}"),
    C("an_absolute_path_loses_its_trailing_slash", value="/abs/x/", want="/abs/x"),
    C("dot_dot_is_resolved", value="a/../b", want="{cwd}/b"),
    C("dot_slash_is_relative", value="./s", want="{cwd}/s"),
    C("doubled_and_dot_segments", value="/a//b/./c", want="/a/b/c"),
    C("tilde_user_is_not_expanded", value="~other/x", want="{cwd}/~other/x"),
    C("file_url_on_localhost", value="file://localhost/tmp/x", want="/tmp/x"),
    C("file_url_on_another_host_is_refused", value="file://elsewhere/x", rc=1),
)


@generate
class SessionPathTests(BatchTest):
    """elm_normalize_session_dir: the path pi will use, worked out the way pi does."""

    CASES = NORMALIZE_CASES

    @classmethod
    def prepare(cls):
        (cls.tmp / "work").mkdir()

    @classmethod
    def prelude(cls):
        return f". {q(ROOT / 'lib/state.sh')}\nexport ELM_PI_PYTHON={q(sys.executable)}"

    @classmethod
    def body(cls, case):
        return "\n".join(["set -euo pipefail",
                          f'OUT="$(elm_normalize_session_dir {q(case.kw["value"])} {q(cls.tmp / "work")})"', "_v OUT"])

    def check(self, case, r):
        if case.kw.get("rc"):
            self.assertNotEqual(0, r.rc)
            self.assertIn("unsupported non-local session file URL", r.err)
            return
        self.assertEqual(0, r.rc, r.err)
        self.assertEqual(case.kw["want"].format(home=self.home, cwd=self.tmp / "work"), r.vars["OUT"])


# --- install.sh: flags and environment -----------------------------------------------------

PASSED = ("--no-packages", "--no-shim", "--no-auth-lock", "--no-tools", "--no-patch", "--force",
          "--force-packages", "--reset-options", "--with-python", "--with-pypi-index", "--no-python",
          "--no-pypi-index")
UNKNOWN = (("--bogus", "bogus"), ("--non-interactive", "bootstraps_non_interactive"),
           ("--with-all=1", "with_all_with_a_value"), ("-u", "a_short_flag"), ("update", "a_bare_word"),
           ("", "an_empty_argument"), ("--UPDATE", "a_flag_in_capitals"), ("--no-paths", "a_misspelt_flag"))
DEFAULT_REPO = "https://github.com/rob-c/elm-pi.git"


def flag_case(flag):
    return C(f"passes_{flag.strip('-').replace('-', '_')}_to_bootstrap", [flag], passed=[flag])


INSTALLER_CASES = (
    C("update_flag", ["--update"], vars={"UPDATE": "1"}, passed=[]),
    C("no_path_flag", ["--no-path"], vars={"NO_PATH": "1", "NO_LINK": "0"}, passed=[]),
    C("no_link_flag", ["--no-link"], vars={"NO_LINK": "1", "NO_PATH": "0"}, passed=[]),
    C("force_link_flag", ["--force-link"], vars={"FORCE_LINK": "1"}, passed=[]),
    *(flag_case(f) for f in PASSED),
    C("order_is_kept_and_installer_flags_are_not_passed", ["--no-tools", "--update", "--no-shim"],
      vars={"UPDATE": "1"}, passed=["--no-tools", "--no-shim"]),
    *(C(f"refuses_{name}", [f], rc=2, err_has=f"unknown option: {f}\n") for f, name in UNKNOWN),
    C("short_help", ["-h"], rc=0, out_has="Installer flags:", out_lacks="@@UPDATE"),
    C("help_wins_over_an_unknown_flag", ["--bogus", "--help"], rc=0, out_has="Passed through to bootstrap.sh:"),
    C("update_from_the_environment", [], env={"ELM_PI_UPDATE": "1"}, vars={"UPDATE": "1"}),
    C("no_path_from_the_environment", [], env={"ELM_PI_NO_PATH": "1"}, vars={"NO_PATH": "1"}),
    C("no_link_from_the_environment", [], env={"ELM_PI_NO_LINK": "1"}, vars={"NO_LINK": "1"}),
    C("force_link_from_the_environment", [], env={"ELM_PI_FORCE_LINK": "1"}, vars={"FORCE_LINK": "1"}),
    C("with_all_needs_exactly_one", [], env={"ELM_PI_WITH_ALL": "true"}, passed=[]),
    C("defaults_with_nothing_set", [],
      vars={"UPDATE": "0", "NO_PATH": "0", "NO_LINK": "0", "FORCE_LINK": "0", "PREFIX": "{home}/.local/share/elm-pi",
            "BINDIR": "{home}/.local/bin", "REPO": DEFAULT_REPO, "SLUG": "rob-c/elm-pi", "BRANCH_GIVEN": "",
            "DOCS": "https://rob-c.github.io/elm-pi/"}, passed=[]),
    C("prefix_from_the_environment", [], env={"ELM_PI_PREFIX": "/srv/elm-pi"}, vars={"PREFIX": "/srv/elm-pi"}),
    C("bindir_from_the_environment", [], env={"ELM_PI_BINDIR": "/srv/bin"}, vars={"BINDIR": "/srv/bin"}),
    C("docs_from_the_environment", [], env={"ELM_PI_DOCS": "https://docs.example/"},
      vars={"DOCS": "https://docs.example/"}),
    C("slug_from_an_ssh_url", [], env={"ELM_PI_REPO": "git@github.com:someone/fork.git"},
      vars={"SLUG": "someone/fork"}),
    C("slug_from_a_url_without_dot_git", [], env={"ELM_PI_REPO": "https://github.com/someone/fork"},
      vars={"SLUG": "someone/fork"}),
    C("repository_from_the_environment_beats_the_record", [], env={"ELM_PI_REPO": "https://github.com/a/b.git"},
      saved="repo=https://github.com/x/y.git\n", vars={"REPO": "https://github.com/a/b.git", "SLUG": "a/b"}),
    C("a_recorded_branch_without_a_repository", [], saved="branch=dev\n",
      vars={"BRANCH": "dev", "BRANCH_GIVEN": "dev", "REPO": DEFAULT_REPO}),
    C("the_last_recorded_branch_wins", [], saved="branch=one\nbranch=two\n", vars={"BRANCH": "two"}),
    C("an_empty_recorded_branch_means_main", [], saved="flags=\nbranch=\nrepo=\n",
      vars={"BRANCH": "main", "BRANCH_GIVEN": "", "REPO": DEFAULT_REPO}),
    C("the_record_is_read_as_data", [], saved="branch=$(touch pwned)\n",
      vars={"BRANCH": "$(touch pwned)"}, not_created="pwned"),
)


@generate
class InstallerOptionTests(BatchTest):
    """install.sh: each flag, each unknown spelling, and each environment override."""

    CASES = INSTALLER_CASES
    BLOCK = block(INSTALLER, 'PREFIX="${ELM_PI_PREFIX', "if [ -t 1 ]; then B=")

    @classmethod
    def prepare(cls):
        for i, case in enumerate(cls.CASES):
            if "saved" in case.kw:
                touch(cls.tmp / f"p{i}/agent/install-options", case.kw["saved"])

    @classmethod
    def body(cls, case):
        i = cls.index(case)
        env = dict(case.env)
        if "saved" in case.kw:
            env["ELM_PI_PREFIX"] = str(cls.tmp / f"p{i}")
        return "\n".join(["set -euo pipefail", f'cd "$T"', exports(env), setargs(case.args), cls.BLOCK,
                          "_v PREFIX REPO BRANCH BRANCH_GIVEN BINDIR UPDATE SLUG DOCS NO_PATH NO_LINK FORCE_LINK",
                          '_a PASS ${PASS_ARGS[@]+"${PASS_ARGS[@]}"}'])

    def check(self, case, r):
        kw = case.kw
        vars_ = {k: v.format(home=self.home) for k, v in kw.get("vars", {}).items()}
        super().check(Case(case.name, **{**kw, "vars": vars_}), r)
        if "passed" in kw:
            self.assertEqual(kw["passed"], r.list("PASS"))
        if "not_created" in kw:
            self.assertFalse((self.tmp / kw["not_created"]).exists())


# --- install.sh: what a new install says it needs ------------------------------------------

DISK_CASES = (
    C("with_python_keeps_two_gigabytes", ["--with-python"], out_has="downloads and keeps about 2.0 GB",
      out_lacks="more while it runs"),
    C("with_the_index_keeps_more_and_needs_room_to_build", ["--with-pypi-index"],
      out_has=["downloads and keeps about 2.4 GB", "the agent's Python (~1.0 GB)", "about 1.0 GB more while it runs"]),
    C("taking_python_back_adds_nothing", ["--no-python"], out_has="downloads and keeps about 1.0 GB"),
    C("a_git_install_is_not_new", [], git=True, out_lacks="disk space", noted=None),
    C("exactly_enough_room", [], free=1000 * 1024, out_lacks="DIE"),
    C("one_kilobyte_short", [], free=1000 * 1024 - 1, rc=1,
      out_has="DIE only 1.0 GB free on this filesystem, and the install needs about 1.0 GB."),
    C("not_enough_room_for_python", ["--with-python"], free=1500 * 1024, rc=1,
      out_has=["DIE only 1.5 GB free", "needs about 2.0 GB"]),
    C("not_enough_room_to_build_the_index", ["--with-pypi-index"], free=3000 * 1024, rc=1,
      out_has="needs about 3.4 GB"),
    C("no_reading_from_df", [], free="none", out_lacks="DIE"),
    C("a_reading_that_is_not_a_number", [], free="n/a", out_lacks="DIE"),
    C("ignoring_the_check_warns_with_the_figure", [], free=500 * 1024, env={"ELM_PI_IGNORE_DISK_SPACE": "1"},
      out_has="WARN only 0.5 GB free; going ahead (ELM_PI_IGNORE_DISK_SPACE=1)"),
)


@generate
class InstallerDiskTests(BatchTest):
    """install.sh's disk estimate for a new install, and the free-space check."""

    CASES = DISK_CASES
    BLOCK = block(INSTALLER, "# A new install: say what it will download", "# --- 2. get the source")
    # the disk check creates the folder it measures first
    MAKE_PARENT = block(INSTALLER, "make_parent() {", "\n}\n") + "\n}\n"

    @classmethod
    def prepare(cls):
        for i, case in enumerate(cls.CASES):
            if case.kw.get("git"):
                (cls.tmp / f"d{i}/elm-pi/.git").mkdir(parents=True)

    @classmethod
    def body(cls, case):
        i = cls.index(case)
        free = case.kw.get("free", 50_000_000)
        line = "" if free == "none" else f"echo 'disk 999999999 1 {free} 1% /'"
        return "\n".join([
            "set -euo pipefail", "unset ELM_PI_DISK_NOTED ELM_PI_IGNORE_DISK_SPACE", exports(case.env),
            'say() { echo "== $*"; }; warn() { echo "WARN $*"; }; die() { echo "DIE $*"; exit 1; }',
            f"df() {{ echo 'Filesystem 1024-blocks Used Available Capacity Mounted'; {line or ':'}; }}",
            f'PREFIX="$T/d{i}/elm-pi"', "PASS_ARGS=(" + " ".join(q(a) for a in case.args) + ")",
            cls.MAKE_PARENT, cls.BLOCK, "_v ELM_PI_DISK_NOTED"])

    def check(self, case, r):
        super().check(case, r)
        if r.rc == 0:
            self.assertEqual(case.kw.get("noted", "1"), r.vars["ELM_PI_DISK_NOTED"])


# --- bootstrap.sh: the options it records and repeats --------------------------------------

def rec(flags="", tools="", branch="", repo=""):
    return {"flags": flags, "tools": tools, "branch": branch, "repo": repo}


WITH = ("WITH_SHIM", "WITH_PACKAGES", "AUTH_LOCK", "WITH_TOOLS", "WITH_PATCH", "WITH_PYTHON", "WITH_PYPI_INDEX")

BOOT_CASES = (
    C("defaults_record_nothing", [], record=rec(), vars=dict.fromkeys(WITH[:5], "1")),
    C("no_packages_alone", ["--no-packages"], record=rec("--no-packages"), vars={"WITH_PACKAGES": "0"}),
    C("no_auth_lock_alone", ["--no-auth-lock"], record=rec("--no-auth-lock"), vars={"AUTH_LOCK": "0"}),
    C("no_tools_alone", ["--no-tools"], record=rec("--no-tools"), vars={"WITH_TOOLS": "0"}),
    C("no_patch_alone", ["--no-patch"], record=rec("--no-patch"), vars={"WITH_PATCH": "0", "WITH_TOOLS": "1"}),
    C("a_repeated_flag_is_recorded_once", ["--no-tools", "--no-tools"], record=rec("--no-tools")),
    C("run_only_flags_are_not_recorded", ["--non-interactive", "--update", "--force", "--force-packages"],
      record=rec(), vars={"INTERACTIVE": "0", "UPDATE": "1", "FORCE": "1", "FORCE_PACKAGES": "1"}),
    C("an_unknown_flag_stops_before_anything_is_written", ["--bogus"], rc=2, record=None,
      err_has="unknown option: --bogus"),
    C("an_installer_only_flag_is_unknown_here", ["--no-path"], rc=2, record=None,
      err_has="unknown option: --no-path"),
    C("given_flags_come_before_repeated_ones", ["--no-tools"], saved="flags=--no-shim\n",
      record=rec("--no-tools --no-shim"), vars={"WITH_SHIM": "0", "WITH_TOOLS": "0"}),
    C("an_unknown_recorded_flag_is_dropped", [], saved="flags=--evil --no-patch\n", record=rec("--no-patch")),
    C("a_recorded_run_only_flag_is_not_repeated", [], saved="flags=--force\n", record=rec(), vars={"FORCE": "0"}),
    C("the_last_recorded_flags_line_wins", [], saved="flags=--no-shim\nflags=--no-tools\n",
      record=rec("--no-tools"), vars={"WITH_SHIM": "1"}),
    C("recorded_tools_with_shell_characters_are_dropped", [], saved="tools=fd;touch x\n", record=rec(),
      vars={"ELM_PI_TOOLS": None}),
    C("recorded_tools_in_capitals_are_dropped", [], saved="tools=FD\n", record=rec()),
    C("tools_from_the_environment_beat_the_record", [], saved="tools=fd,rg\n", env={"ELM_PI_TOOLS": "jq"},
      record=rec(tools="jq")),
    C("recorded_tools_are_repeated", [], saved="tools=fd,ast-grep\n", record=rec(tools="fd,ast-grep"),
      vars={"ELM_PI_TOOLS": "fd,ast-grep"}),
    C("reset_records_tools_from_the_environment", ["--reset-options"], saved="tools=fd\n",
      env={"ELM_PI_TOOLS": "rg"}, record=rec(tools="rg")),
    C("reset_keeps_only_this_runs_flags", ["--reset-options", "--no-patch"], saved="flags=--no-tools\n",
      record=rec("--no-patch"), vars={"WITH_TOOLS": "1", "WITH_PATCH": "0"}),
    C("a_branch_with_a_space_is_not_recorded", [], env={"ELM_PI_BRANCH": "a b"}, record=rec()),
    C("a_repository_with_a_space_is_not_recorded", [], env={"ELM_PI_REPO": "https://x/y z.git"}, record=rec()),
    C("a_new_repository_replaces_the_recorded_one", [], saved="repo=https://x/old.git\nbranch=dev\n",
      env={"ELM_PI_REPO": "https://x/new.git"}, record=rec(branch="dev", repo="https://x/new.git")),
    C("an_old_install_with_the_shim_is_not_no_shim", [], files={"agent/settings.json": "{}",
      "agent/extensions/elm-shim.ts": ""}, record=rec()),
    C("an_old_install_with_a_locked_auth_file", [], files={"agent/settings.json": "{}"}, locked_auth=True,
      record=rec()),
    C("an_old_install_with_one_tool_is_not_no_tools", [], files={"agent/settings.json": "{}"},
      exe="agent/bin/rg", record=rec()),
    C("an_old_install_whose_tools_do_not_run_is_no_tools", [], files={"agent/settings.json": "{}",
      "agent/bin/fd": ""}, record=rec("--no-tools"), vars={"WITH_TOOLS": "0"}),
    C("without_settings_nothing_is_inferred", [], files={"agent/extensions/other.ts": ""}, record=rec()),
    C("an_old_install_with_packages_listed", [], files={"agent/settings.json": '{"packages": ["npm:x"]}'},
      record=rec()),
    C("reset_does_not_infer_the_agents_python", ["--reset-options"], python_env=True, record=rec(),
      vars={"WITH_PYTHON": "0"}),
    C("an_existing_python_joins_a_recorded_index", [], python_env=True, saved="flags=--with-pypi-index\n",
      record=rec("--with-pypi-index --with-python"), vars={"WITH_PYTHON": "1", "WITH_PYPI_INDEX": "1"}),
    C("taking_back_an_index_that_was_never_recorded", ["--no-pypi-index"], record=rec(),
      vars={"WITH_PYPI_INDEX": "0"}),
    C("with_all_and_a_recorded_flag", ["--with-all"], saved="flags=--no-shim\n",
      record=rec("--with-python --with-pypi-index --no-shim"), vars={"WITH_SHIM": "0", "WITH_PYPI_INDEX": "1"}),
    C("flags_are_recorded_in_the_order_given", ["--with-python", "--no-shim"],
      record=rec("--with-python --no-shim")),
)


@generate
class BootstrapOptionTests(BatchTest):
    """bootstrap.sh's argument parsing and agent/install-options, run on scratch installs."""

    CASES = BOOT_CASES
    DEFAULTS = block(BOOTSTRAP, "WITH_SHIM=1; WITH_PACKAGES=1; INTERACTIVE=1", 'TMP=""; TOOLS_TMP=""')
    PARSE = block(BOOTSTRAP, '\nfor arg in "$@"; do\n  case "$arg" in\n    --no-shim', "\n\nsay()  {")
    OPTIONS = block(BOOTSTRAP, "# --- the options this install was made with", "# Before anything runs pi:")

    @classmethod
    def prepare(cls):
        for i, case in enumerate(cls.CASES):
            d = cls.tmp / f"b{i}"
            d.mkdir()
            kw = case.kw
            if "saved" in kw:
                touch(d / "agent/install-options", kw["saved"])
            for rel, text in kw.get("files", {}).items():
                touch(d / rel, text)
            if kw.get("locked_auth"):
                touch(d / "agent/auth.json", "{}", 0o400)
            if "exe" in kw:
                touch(d / kw["exe"], "#!/bin/sh\n", 0o755)
            if kw.get("python_env"):
                touch(d / "agent/python/env/bin/python", "#!/bin/sh\n", 0o755)

    @classmethod
    def body(cls, case):
        return "\n".join(["set -euo pipefail", "say() { :; }", "unset ELM_PI_TOOLS ELM_PI_BRANCH ELM_PI_REPO",
                          exports(case.env), f'cd "$T/b{cls.index(case)}"', 'HERE="$PWD"', setargs(case.args),
                          cls.DEFAULTS, cls.PARSE, cls.OPTIONS,
                          "_v " + " ".join(WITH) + " INTERACTIVE UPDATE FORCE FORCE_PACKAGES ELM_PI_TOOLS"])

    def check(self, case, r):
        super().check(case, r)
        d = self.tmp / f"b{self.index(case)}"
        options = d / "agent/install-options"
        self.assertFalse((d / "agent/install-options.tmp").exists())
        want = case.kw["record"]
        if want is None:
            self.assertEqual(case.kw.get("saved"), options.read_text() if options.exists() else None)
            return
        lines = options.read_text().splitlines()
        self.assertTrue(lines[0].startswith("# The options this install was made with"))
        self.assertEqual(want, dict(l.split("=", 1) for l in lines if not l.startswith("#")))


if __name__ == "__main__":
    unittest.main()
