"""install.sh's internals and configure.sh's flows, against throwaway trees.

Proves, for install.sh: fetch_tarball deletes only what an earlier tarball
recorded as source - never runtime state, files you created, or a manifest
line that leads outside the install - and a second fetch changes nothing;
validate_source refuses a candidate with a shell, Python or JSON error or a
failing self-check; how an existing install is recognised (git, tarball, a
folder that is not one) and how the update follows its branch; what is handed
to bootstrap.sh and said when it fails; the launcher link and the old elm-pi
link; the PATH line written to zsh, bash and fish profiles in a temporary HOME
(once, and not at all with --no-path or when already on PATH); and the closing
advice. For configure.sh: every way the gateway's model list can come back,
the smoke test, what is merged into models.json and settings.json, and that the
key never reaches curl's argument list.

Blocks are taken from install.sh between anchor strings and run in one bash per
class, a subshell per case; git, curl, bootstrap.sh and validate_source are
stubs where a block calls them. configure.sh runs whole, against copies of this
checkout's config and templates, with curl stubbed in the install's .node/bin.
Nothing touches the network, ~/.local or a real shell profile.
"""

import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "install.sh").read_text()
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")
PY = sys.executable


def block(text, start, end=None):
    if text.count(start) != 1:
        raise AssertionError(f"anchor is not unique: {start!r}")
    i = text.index(start)
    return text[i:] if end is None else text[i:text.index(end, i)]


def slug(text):
    return re.sub(r"\W+", "_", text).strip("_").lower()


def q(value):
    return shlex.quote(str(value))


def touch(path, text="", mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    path.chmod(mode)
    return path


class Case:
    def __init__(self, name, check, bug=None, **kw):
        self.name, self.check, self.bug, self.kw = name, check, bug, kw


C = Case


def generate(cls):
    for case in cls.CASES:
        name = "test_" + slug(case.name)
        if hasattr(cls, name):
            raise ValueError(f"duplicate case {name} in {cls.__name__}")

        def test(self, case=case):
            case.check(self, type(self).results[case.name], type(self).dirs[case.name])
        test.__name__ = name
        if case.bug:
            test = unittest.expectedFailure(test)
        setattr(cls, name, test)
    return cls


def cleanup_tree(path):
    for root, dirs, _ in os.walk(path):
        for d in dirs:
            try:
                os.chmod(os.path.join(root, d), 0o700)
            except OSError:
                pass
    shutil.rmtree(path, ignore_errors=True)


DUMP = r'''
_v() { local _n _s _x; for _n in "$@"; do eval "_s=\${$_n+x}"
  if [ -n "$_s" ]; then eval "_x=\${$_n}"; printf '@@%s=%s\n' "$_n" "$_x"; else printf '@@%s\n' "$_n"; fi; done; }
'''


class Run:
    def __init__(self, rc, out, err):
        self.rc, self.out, self.err = rc, out, err
        self.vars = {}
        for line in out.splitlines():
            if line.startswith("@@"):
                key, sep, value = line[2:].partition("=")
                self.vars[key] = value if sep else None


def run_batch(prelude, bodies, env, tmp, parallel=8):
    parts = ['T="$1"', DUMP, prelude]
    for i, body in enumerate(bodies):
        parts.append(f'(\n{body}\n) >"$T/.r{i}.out" 2>"$T/.r{i}.err" </dev/null &\n_pids="${{_pids:-}} $!:{i}"')
        if (i + 1) % parallel == 0 or i == len(bodies) - 1:
            parts.append('for _p in $_pids; do wait "${_p%%:*}"; echo $? >"$T/.r${_p##*:}.rc"; done; _pids=""')
    subprocess.run([BASH, "-c", "\n".join(parts), "batch", str(tmp)], env=env, cwd=str(tmp),
                   check=True, capture_output=True, text=True, timeout=300)
    return [Run(int((tmp / f".r{i}.rc").read_text()), (tmp / f".r{i}.out").read_text(),
                (tmp / f".r{i}.err").read_text()) for i in range(len(bodies))]


class Batch(unittest.TestCase):
    """Every case of a class in one bash; one test method per case."""

    CASES = ()

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        try:
            cls.dirs = {}
            for i, case in enumerate(cls.CASES):
                d = cls.tmp / f"c{i}"
                d.mkdir()
                cls.dirs[case.name] = d
                cls.prepare(case, d)
            env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(cls.tmp / "nohome"), "LANG": "C",
                   "TMPDIR": str(cls.tmp)}
            runs = run_batch(cls.prelude(), [cls.body(c, cls.dirs[c.name]) for c in cls.CASES], env, cls.tmp)
            cls.results = {c.name: r for c, r in zip(cls.CASES, runs)}
        except BaseException:
            cleanup_tree(cls.tmp)
            raise

    @classmethod
    def tearDownClass(cls):
        cleanup_tree(cls.tmp)

    @classmethod
    def prelude(cls):
        return ""

    @classmethod
    def prepare(cls, case, d):
        pass


STUBS = 'say() { echo "== $*"; }; warn() { echo "WARN $*"; }; die() { echo "DIE $*"; exit 1; }'


def lines(path):
    path = Path(path)
    return path.read_text().splitlines() if path.exists() else []


def tree(root, skip=()):
    """Every file and link under root: content, or "-> target" for a link."""
    out = {}
    root = Path(root)
    for p in sorted(root.rglob("*")):
        rel = str(p.relative_to(root))
        if any(rel == s or rel.startswith(s + "/") for s in skip):
            continue
        if p.is_symlink():
            out[rel] = "-> " + os.readlink(p)
        elif p.is_file():
            out[rel] = p.read_text()
    return out


# =====================================================================================
# fetch_tarball: what a tarball refresh deletes, and what it never touches
# =====================================================================================

FETCH = block(INSTALLER, "fetch_tarball() {   # $1 = destination directory", "\nvalidate_source() {")

SOURCE = {"install.sh": "v2", "bootstrap.sh": "v2", "lib/sandbox.sh": "v2", "scripts/check.sh": "v2",
          "docs/my guide.md": "v2", "templates/a.json": "{}"}


def tarball(files, links=None, top="elm-pi-main"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size, info.mode = len(data), 0o644
            tar.addfile(info, io.BytesIO(data))
        for name, target in (links or {}).items():
            info = tarfile.TarInfo(f"{top}/{name}")
            info.type, info.linkname = tarfile.SYMTYPE, target
            tar.addfile(info)
    return buf.getvalue()


def F(name, check, old=None, manifest=None, extra=None, source=None, links=None, bug=None, **kw):
    """old: the install's files before; manifest: its .elm-pi-source-manifest
    lines; extra: files outside the install (beside it)."""
    return C(name, check, bug=bug, old=old or {}, manifest=manifest, extra=extra or {},
             source=SOURCE if source is None else source, links=links or {}, **kw)


def _dest(d):
    return d / "inst"


def _manifest(d):
    return lines(_dest(d) / ".elm-pi-source-manifest")


FETCH_CASES = [
    F("a_new_install_gets_every_source_file",
      check=lambda t, r, d: t.assertEqual(SOURCE, tree(_dest(d), skip=(".elm-pi-source-manifest",)))),
    F("the_manifest_lists_every_source_file_sorted_bytewise",
      check=lambda t, r, d: t.assertEqual(sorted(SOURCE, key=lambda s: s.encode()), _manifest(d))),
    F("links_in_the_source_are_copied_and_recorded", links={"bin/pi": "../pi"},
      check=lambda t, r, d: (t.assertEqual("../pi", os.readlink(_dest(d) / "bin/pi")),
                             t.assertIn("bin/pi", _manifest(d)))),
    F("a_file_dropped_upstream_is_deleted", old={"scripts/old.sh": "v1"}, manifest=[*SOURCE, "scripts/old.sh"],
      check=lambda t, r, d: t.assertFalse((_dest(d) / "scripts/old.sh").exists())),
    F("runtime_state_never_recorded_is_kept",
      old={".env": "ELM_API_KEY=k\n", "agent/settings.json": "{}", "node_modules/x/index.js": "x"},
      manifest=list(SOURCE),
      check=lambda t, r, d: t.assertEqual({".env": "ELM_API_KEY=k\n", "agent/settings.json": "{}",
                                           "node_modules/x/index.js": "x"},
                                          {k: v for k, v in tree(_dest(d)).items()
                                           if k in (".env", "agent/settings.json", "node_modules/x/index.js")})),
    F("a_file_you_made_in_a_source_folder_is_kept", old={"scripts/mine.sh": "mine"}, manifest=list(SOURCE),
      check=lambda t, r, d: t.assertEqual("mine", (_dest(d) / "scripts/mine.sh").read_text())),
    F("a_source_file_you_edited_is_overwritten", old={"install.sh": "edited"}, manifest=list(SOURCE),
      check=lambda t, r, d: t.assertEqual("v2", (_dest(d) / "install.sh").read_text())),
    F("a_file_still_shipped_is_updated_not_deleted", old={"lib/sandbox.sh": "v1"}, manifest=list(SOURCE),
      check=lambda t, r, d: t.assertEqual("v2", (_dest(d) / "lib/sandbox.sh").read_text())),
    F("an_absolute_manifest_line_is_ignored", old={"etc/keep": "k"}, manifest=[*SOURCE, "/etc/keep"],
      check=lambda t, r, d: t.assertEqual("k", (_dest(d) / "etc/keep").read_text())),
    F("a_manifest_line_leading_up_is_ignored", extra={"outside": "k"}, manifest=[*SOURCE, "../outside"],
      check=lambda t, r, d: t.assertEqual("k", (d / "outside").read_text())),
    F("a_manifest_line_leading_up_from_inside_is_ignored", extra={"outside": "k"},
      manifest=[*SOURCE, "lib/../../outside"],
      check=lambda t, r, d: t.assertEqual("k", (d / "outside").read_text())),
    F("an_empty_manifest_line_is_ignored", manifest=["", *SOURCE, ""],
      check=lambda t, r, d: (t.assertEqual(0, r.rc, r.out + r.err), t.assertEqual("v2", (_dest(d) / "install.sh").read_text()))),
    F("a_recorded_file_already_gone_is_not_an_error", manifest=[*SOURCE, "scripts/gone.sh"],
      check=lambda t, r, d: t.assertEqual(0, r.rc, r.out + r.err)),
    F("a_dropped_name_with_a_space_is_deleted", old={"docs/old guide.md": "v1"},
      manifest=[*SOURCE, "docs/old guide.md"],
      check=lambda t, r, d: t.assertFalse((_dest(d) / "docs/old guide.md").exists())),
    # grep -Fqx: a whole line, literally.
    F("a_dropped_name_that_prefixes_a_shipped_one_is_still_deleted", old={"lib/sandbox": "v1"},
      manifest=[*SOURCE, "lib/sandbox"],
      check=lambda t, r, d: (t.assertFalse((_dest(d) / "lib/sandbox").exists()),
                             t.assertTrue((_dest(d) / "lib/sandbox.sh").exists()))),
    # As a pattern, the dropped "lib/a.b" would match the shipped "lib/aXb" and survive.
    F("a_dropped_name_is_matched_literally_not_as_a_pattern", old={"lib/a.b": "v1"},
      manifest=[*SOURCE, "lib/a.b"], source={**SOURCE, "lib/aXb": "v2"},
      check=lambda t, r, d: (t.assertFalse((_dest(d) / "lib/a.b").exists()),
                             t.assertEqual("v2", (_dest(d) / "lib/aXb").read_text()))),
    F("a_folder_emptied_upstream_is_left_behind_empty", old={"old/only.txt": "v1"}, manifest=[*SOURCE, "old/only.txt"],
      check=lambda t, r, d: (t.assertTrue((_dest(d) / "old").is_dir()),
                             t.assertEqual([], list((_dest(d) / "old").iterdir())))),
    F("the_new_manifest_replaces_the_old_one", old={"gone.txt": "v1"}, manifest=[*SOURCE, "gone.txt"],
      check=lambda t, r, d: t.assertNotIn("gone.txt", _manifest(d))),
    # property: a second fetch of the same source leaves the install as the first did.
    F("a_second_fetch_of_the_same_source_changes_nothing", old={"agent/x": "state"}, twice=True,
      check=lambda t, r, d: t.assertEqual(json.loads((d / "first.json").read_text()), tree(_dest(d)))),
    F("the_source_comes_from_codeload_for_the_slug_and_branch",
      check=lambda t, r, d: t.assertEqual(["https://codeload.github.com/someone/fork/tar.gz/refs/heads/dev"],
                                          lines(d / "curl.log"))),
    F("a_download_that_fails_stops_naming_what_it_fetched", old={"install.sh": "v1"}, manifest=list(SOURCE),
      serve=False,
      check=lambda t, r, d: (t.assertEqual(1, r.rc),
                             t.assertIn("DIE could not download someone/fork@dev", r.out),
                             t.assertEqual("v1", (_dest(d) / "install.sh").read_text()))),
    F("a_source_that_fails_validation_is_not_copied", old={"install.sh": "v1", "scripts/old.sh": "v1"},
      manifest=[*SOURCE, "scripts/old.sh"], invalid=True,
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertEqual("v1", (_dest(d) / "install.sh").read_text()),
                             t.assertTrue((_dest(d) / "scripts/old.sh").exists()),
                             t.assertEqual([*SOURCE, "scripts/old.sh"], _manifest(d)))),
    F("the_download_is_cleaned_up_afterwards",
      check=lambda t, r, d: t.assertEqual([], list((d / "tmp").iterdir()))),
]


@generate
class FetchTarballTests(Batch):
    """install.sh's fetch_tarball(): a manifest-driven refresh of a tarball install."""

    CASES = FETCH_CASES

    @classmethod
    def prepare(cls, case, d):
        kw = case.kw
        if kw.get("serve", True):
            touch(d / "src.tar.gz", tarball(kw["source"], kw["links"]))
        for rel, text in kw["old"].items():
            touch(_dest(d) / rel, text)
        if kw["manifest"] is not None:
            touch(_dest(d) / ".elm-pi-source-manifest", "".join(f"{l}\n" for l in kw["manifest"]))
        for rel, text in kw["extra"].items():
            touch(d / rel, text)
        (d / "tmp").mkdir()

    @classmethod
    def body(cls, case, d):
        validate = 'validate_source() { die "invalid"; }' if case.kw.get("invalid") else 'validate_source() { :; }'
        call = f'fetch_tarball {q(_dest(d))}'
        if case.kw.get("twice"):
            # The first fetch, its tree saved, then the second.
            call = (f'( {call} )\n"$PY" -c {q("import json,os,sys; sys.path.insert(0, sys.argv[2]); from test_installer_internals import tree; print(json.dumps(tree(sys.argv[1])))")}'
                    f' {q(_dest(d))} {q(ROOT / "tests")} > {q(d / "first.json")}\n{call}')
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", f"export TMPDIR={q(d / 'tmp')}", f"PY={q(PY)}", STUBS,
            "SLUG=someone/fork; BRANCH=dev",
            f'curl() {{ for a; do u="$a"; done; echo "$u" >> {q(d / "curl.log")}; '
            f'[ -f {q(d / "src.tar.gz")} ] || return 22; cat {q(d / "src.tar.gz")}; }}',
            validate, FETCH, call])


# =====================================================================================
# validate_source: what stops a downloaded source before it replaces the install
# =====================================================================================

VALIDATE = block(INSTALLER, "validate_source() { # $1 = candidate source tree", '\nOLD_HEAD=""')
PY_FILES = ("patch-pi.py", "proxy/egress.py", "shim/shim.py", "scripts/elm_config.py",
            "scripts/verify_install.py", "scripts/pin_versions.py")
SH_FILES = ("install.sh", "bootstrap.sh", "configure.sh", "pi", "pi.orig")
# The candidate's own lib/sandbox.sh chooses the Python: here, this one.
FAKE_SANDBOX = f'''elm_ensure_python() {{ [ -z "${{NO_PYTHON:-}}" ] || {{ ELM_PY_ERROR="no usable python"; return 1; }}; ELM_PI_PYTHON={q(PY)}; }}
elm_py() {{ "$ELM_PI_PYTHON" -E -S "$@"; }}
'''


def V(name, check, files=None, check_sh=None, env=None, bug=None):
    return C(name, check, bug=bug, files=files or {}, check_sh=check_sh, env=env or {})


VALIDATE_CASES = [
    V("a_sound_source_passes_and_names_its_python",
      check=lambda t, r, d: (t.assertEqual(0, r.rc, r.out), t.assertIn(f"    checking the source with {PY}", r.out))),
    V("a_shell_syntax_error_in_the_installer_stops_it", files={"install.sh": "if then fi\n"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE downloaded source failed its shell syntax check", r.out))),
    # `bash -n a b c` checks a alone - the rest are its arguments - so each
    # shell file is checked on its own, bootstrap.sh, the launcher and lib/ too.
    V("a_shell_syntax_error_in_bootstrap_stops_it", files={"bootstrap.sh": "if then fi\n"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE downloaded source failed its shell syntax check", r.out))),
    V("a_shell_syntax_error_in_the_launcher_stops_it", files={"pi": "case x in\n"},
      check=lambda t, r, d: t.assertIn("DIE downloaded source failed its shell syntax check", r.out)),
    V("a_shell_syntax_error_in_lib_sandbox_stops_it", files={"lib/sandbox.sh": FAKE_SANDBOX + "{ \n"},
      check=lambda t, r, d: t.assertIn("DIE downloaded source failed its shell syntax check", r.out)),
    V("a_python_syntax_error_stops_it", files={"shim/shim.py": "def (:\n"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE downloaded source failed its Python/JSON checks", r.out))),
    V("a_missing_python_file_stops_it", files={"patch-pi.py": None},
      check=lambda t, r, d: t.assertIn("DIE downloaded source failed its Python/JSON checks", r.out)),
    V("a_broken_config_json_stops_it", files={"config/elm-pi.json": "{"},
      check=lambda t, r, d: t.assertIn("DIE downloaded source failed its Python/JSON checks", r.out)),
    V("a_broken_json_deep_in_templates_stops_it", files={"templates/a/b/c.json": "[1,]"},
      check=lambda t, r, d: t.assertIn("DIE downloaded source failed its Python/JSON checks", r.out)),
    V("broken_json_outside_config_and_templates_is_not_checked", files={"docs/x.json": "{"},
      check=lambda t, r, d: t.assertEqual(0, r.rc, r.out)),
    V("a_failing_self_check_stops_it", check_sh="exit 1",
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE downloaded source failed its self-checks", r.out))),
    V("the_self_check_runs_source_only_in_the_candidate", check_sh='echo "$PWD $*" > "$OUT_FILE"',
      env={"OUT_FILE": "{d}/ran"},
      check=lambda t, r, d: t.assertEqual(f"{d / 'src'} --source-only\n", (d / "ran").read_text())),
    V("run_tests_runs_the_whole_self_check", check_sh='echo "$PWD $*" > "$OUT_FILE"',
      env={"OUT_FILE": "{d}/ran", "ELM_PI_RUN_TESTS": "1"},
      check=lambda t, r, d: (t.assertEqual(f"{d / 'src'} \n", (d / "ran").read_text()),
                             t.assertIn("ELM_PI_RUN_TESTS=1", r.out))),
    V("run_tests_set_to_anything_else_stays_source_only", check_sh='echo "$PWD $*" > "$OUT_FILE"',
      env={"OUT_FILE": "{d}/ran", "ELM_PI_RUN_TESTS": "yes"},
      check=lambda t, r, d: t.assertEqual(f"{d / 'src'} --source-only\n", (d / "ran").read_text())),
    V("failing_tests_stop_it", check_sh="exit 1", env={"ELM_PI_RUN_TESTS": "1"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc),
                             t.assertIn("DIE downloaded source failed its tests (ELM_PI_RUN_TESTS=1)", r.out))),
    V("a_self_check_that_is_not_executable_is_not_run", check_sh="noexec",
      check=lambda t, r, d: t.assertEqual(0, r.rc, r.out)),
    V("no_usable_python_stops_it_with_the_reason", env={"NO_PYTHON": "1"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE no usable python", r.out))),
]


@generate
class ValidateSourceTests(Batch):
    """install.sh's validate_source(), on candidate trees with one fault each."""

    CASES = VALIDATE_CASES

    @classmethod
    def prepare(cls, case, d):
        src = d / "src"
        for name in SH_FILES:
            touch(src / name, "#!/bin/bash\necho ok\n")
        touch(src / "lib/sandbox.sh", FAKE_SANDBOX)
        for name in PY_FILES:
            touch(src / name, "x = 1\n")
        touch(src / "config/elm-pi.json", "{}")
        touch(src / "templates/settings.json", "{}")
        for rel, text in case.kw["files"].items():
            if text is None:
                (src / rel).unlink()
            else:
                touch(src / rel, text)
        if case.kw["check_sh"] == "noexec":
            touch(src / "scripts/check.sh", "#!/bin/sh\nexit 1\n", 0o644)
        elif case.kw["check_sh"]:
            touch(src / "scripts/check.sh", f"#!/bin/sh\n{case.kw['check_sh']}\n", 0o755)

    @classmethod
    def body(cls, case, d):
        env = {k: v.format(d=d) for k, v in case.kw["env"].items()}
        return "\n".join(["set -euo pipefail", f"cd {q(d)}", STUBS, f"PREFIX={q(d / 'prefix')}",
                          *(f"export {k}={q(v)}" for k, v in env.items()), VALIDATE, f"validate_source {q(d / 'src')}"])


# =====================================================================================
# which kind of install this is, and how it is brought up to date
# =====================================================================================

DETECT = block(INSTALLER, 'OLD_HEAD=""\nif [ -e "$PREFIX/.git" ]', 'chmod +x "$PREFIX/pi" "$PREFIX/pi.orig"')

# git, stubbed: logs each call, answers from FAKE_* variables.
GIT_STUB = r'''
git() {
  [ "$1" = -C ] && shift 2
  echo "git $*" >> "$LOG"
  case "$1" in
    symbolic-ref) [ -n "${FAKE_SYMREF:-}" ] && echo "$FAKE_SYMREF" || return 1 ;;
    diff) case "$*" in *--cached*) return "${FAKE_STAGED:-0}" ;; *) return "${FAKE_DIRTY:-0}" ;; esac ;;
    fetch) return "${FAKE_FETCH:-0}" ;;
    archive) tar -cf - -C "$FAKE_SRC" . ;;
    rev-parse) if [ -f "$LOG.merged" ]; then echo def456; else echo abc123; fi ;;
    merge) [ "${FAKE_FF:-0}" = 0 ] && touch "$LOG.merged"; return "${FAKE_FF:-0}" ;;
    clone) return "${FAKE_CLONE:-0}" ;;
  esac
}
fetch_tarball() { echo "fetch_tarball $1" >> "$LOG"; }
validate_source() { echo "validate_source" >> "$LOG"; }
'''


def D(name, check, layout="git", have_git=1, branch="", env=None):
    return C(name, check, layout=layout, have_git=have_git, branch=branch, env=env or {})


def _log(d):
    return lines(d / "log")


DETECT_CASES = [
    D("a_git_install_pulls_the_recorded_branch", branch="dev",
      check=lambda t, r, d: (t.assertIn("git fetch --quiet origin dev", _log(d)),
                             t.assertIn("git merge --ff-only origin/dev --quiet", _log(d)),
                             t.assertIn("    existing git install — pulling dev", r.out))),
    D("a_recorded_branch_is_used_without_asking_git", branch="dev", env={"FAKE_SYMREF": "other"},
      check=lambda t, r, d: t.assertFalse(any("symbolic-ref" in l for l in _log(d)))),
    D("a_git_install_with_no_record_follows_its_checked_out_branch", env={"FAKE_SYMREF": "feature"},
      check=lambda t, r, d: (t.assertIn("git fetch --quiet origin feature", _log(d)), t.assertEqual("feature", r.vars["BRANCH"]))),
    D("a_detached_git_install_with_no_record_follows_main",
      check=lambda t, r, d: t.assertIn("git fetch --quiet origin main", _log(d))),
    D("tracked_changes_stop_the_update_before_any_fetch", env={"FAKE_DIRTY": "1"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc),
                             t.assertIn("DIE tracked local changes prevent a safe update; commit or stash them first", r.out),
                             t.assertFalse(any(l.startswith("git fetch") for l in _log(d))))),
    D("staged_changes_stop_the_update", env={"FAKE_STAGED": "1"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE tracked local changes", r.out))),
    D("a_failed_fetch_stops_the_update", env={"FAKE_FETCH": "1"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("DIE git fetch failed", r.out),
                             t.assertNotIn("validate_source", _log(d)))),
    D("the_fetched_source_is_validated_before_the_install_moves", branch="dev",
      check=lambda t, r, d: t.assertLess(_log(d).index("validate_source"),
                                         _log(d).index("git merge --ff-only origin/dev --quiet"))),
    D("an_update_that_cannot_fast_forward_stops", branch="dev", env={"FAKE_FF": "1"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc),
                             t.assertIn("DIE the install cannot fast-forward to origin/dev", r.out))),
    D("the_head_before_the_update_is_kept_for_the_way_back",
      check=lambda t, r, d: t.assertEqual("abc123", r.vars["OLD_HEAD"])),
    D("the_new_head_is_reported",
      check=lambda t, r, d: t.assertIn("    now at def456", r.out)),
    D("a_git_install_without_git_is_refreshed_from_a_tarball", have_git=0, layout="git+bootstrap",
      check=lambda t, r, d: (t.assertIn(f"fetch_tarball {d}/p", _log(d)),
                             t.assertIn("    existing install found — refreshing the source files", r.out),
                             t.assertEqual("", r.vars["OLD_HEAD"]))),
    D("a_tarball_install_is_refreshed", layout="bootstrap",
      check=lambda t, r, d: (t.assertEqual([f"fetch_tarball {d}/p"], _log(d)),
                             t.assertIn("existing install found", r.out))),
    D("a_folder_that_is_not_an_install_is_refused", layout="other",
      check=lambda t, r, d: (t.assertEqual(1, r.rc),
                             t.assertIn(f"DIE {d}/p exists and is not an elm-pi install. Move it, or set ELM_PI_PREFIX.", r.out),
                             t.assertEqual([], _log(d)))),
    D("a_git_folder_without_git_or_bootstrap_is_refused", have_git=0, layout="git",
      check=lambda t, r, d: (t.assertEqual(1, r.rc), t.assertIn("is not an elm-pi install", r.out))),
    D("an_empty_folder_is_cloned_into_with_the_branch_shallow", layout="empty", branch="dev",
      check=lambda t, r, d: t.assertEqual([f"git clone --quiet --branch dev --depth 1 https://x/r.git {d}/p",
                                           "git rev-parse --short HEAD"], _log(d))),
    D("a_failed_clone_stops_the_install", layout="none", env={"FAKE_CLONE": "1"},
      check=lambda t, r, d: (t.assertEqual(1, r.rc),
                             t.assertIn("DIE git clone failed — check the network, or that the repository is public", r.out))),
    D("no_folder_and_no_git_downloads_a_tarball", layout="none", have_git=0, branch="dev",
      check=lambda t, r, d: (t.assertEqual([f"fetch_tarball {d}/p"], _log(d)),
                             t.assertIn("    downloaded someone/fork@dev", r.out))),
]


@generate
class ExistingInstallTests(Batch):
    """install.sh step 2: git pull, tarball refresh, fresh clone, or refusal."""

    CASES = DETECT_CASES

    @classmethod
    def prepare(cls, case, d):
        p = d / "p"
        layout = case.kw["layout"]
        if layout in ("git", "git+bootstrap"):
            (p / ".git").mkdir(parents=True)
        if layout in ("bootstrap", "git+bootstrap"):
            touch(p / "bootstrap.sh", "")
        if layout == "other":
            touch(p / "notes.txt", "mine")
        if layout == "empty":
            p.mkdir()
        touch(d / "src/install.sh", "x")

    @classmethod
    def body(cls, case, d):
        branch = case.kw["branch"]
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", STUBS, f"LOG={q(d / 'log')}", f"export FAKE_SRC={q(d / 'src')}",
            *(f"export {k}={q(v)}" for k, v in case.kw["env"].items()),
            f"PREFIX={q(d / 'p')}; HAVE_GIT={case.kw['have_git']}; REPO=https://x/r.git; SLUG=someone/fork",
            f"BRANCH_GIVEN={q(branch)}; BRANCH={q(branch or 'main')}", GIT_STUB, DETECT, "_v BRANCH OLD_HEAD"])


# =====================================================================================
# the hand-over to bootstrap.sh, and what a failure says
# =====================================================================================

HANDOFF = block(INSTALLER, 'if [ -d "$PREFIX/node_modules" ] || [ -d "$PREFIX/agent/npm/node_modules" ]; then',
                "# --- 4. put pi on the PATH")
RECORDER = '#!/bin/sh\nfor a in "$@"; do echo "ARG $a"; done > "$(dirname "$0")/boot.log"\n' \
           'echo "ENV $ELM_PI_BRANCH $ELM_PI_REPO" >> "$(dirname "$0")/boot.log"\nexit "${BOOT_RC:-0}"\n'


def H(name, check, args=(), update=0, existing=None, rc=0, old_head=""):
    return C(name, check, args=list(args), update=update, existing=existing, rc=rc, old_head=old_head)


def _boot(d):
    return lines(d / "p/boot.log")


HANDOFF_CASES = [
    H("a_new_install_says_it_takes_a_few_minutes",
      check=lambda t, r, d: t.assertIn("== running bootstrap (Node, pi, extensions — a few minutes)", r.out)),
    H("an_install_with_pi_says_what_it_keeps", existing="node_modules",
      check=lambda t, r, d: t.assertIn("== running bootstrap (existing install — keeping pi, binaries and packages)", r.out)),
    H("an_install_with_only_the_packages_counts_as_existing", existing="agent/npm/node_modules",
      check=lambda t, r, d: t.assertIn("existing install", r.out)),
    # stdin is not a terminal here: bootstrap is told not to prompt.
    H("without_a_terminal_bootstrap_is_non_interactive",
      check=lambda t, r, d: (t.assertEqual(["ARG --non-interactive"], [l for l in _boot(d) if l.startswith("ARG")]),
                             t.assertIn("WARN not running on a terminal — bootstrap cannot prompt for your ELM key", r.out))),
    H("the_flags_go_through_in_order_before_non_interactive", args=("--no-tools", "--with-python"),
      check=lambda t, r, d: t.assertEqual(["ARG --no-tools", "ARG --with-python", "ARG --non-interactive"],
                                          [l for l in _boot(d) if l.startswith("ARG")])),
    H("update_goes_first", args=("--no-shim",), update=1,
      check=lambda t, r, d: t.assertEqual(["ARG --update", "ARG --no-shim", "ARG --non-interactive"],
                                          [l for l in _boot(d) if l.startswith("ARG")])),
    H("update_with_no_other_flags", update=1,
      check=lambda t, r, d: t.assertEqual(["ARG --update", "ARG --non-interactive"],
                                          [l for l in _boot(d) if l.startswith("ARG")])),
    H("the_branch_and_repository_reach_bootstrap",
      check=lambda t, r, d: t.assertIn("ENV dev https://x/r.git", _boot(d))),
    H("a_failed_bootstrap_stops_the_install", rc=3,
      check=lambda t, r, d: (t.assertEqual(1, r.rc),
                             t.assertIn(f"DIE fix the cause above and re-run, or run {d}/p/bootstrap.sh", r.out),
                             t.assertIn("WARN   agent/ (generated extensions, agents, skills, settings it owns): rewritten, not rolled back", r.out))),
    H("a_failed_git_update_says_how_to_go_back", rc=1, old_head="abc123",
      check=lambda t, r, d: (t.assertIn("WARN   the elm-pi source: now def456, was abc123 - not rolled back", r.out),
                             t.assertIn(f"WARN To go back:  git -C {d}/p reset --hard abc123 && {d}/p/bootstrap.sh", r.out))),
    H("a_failed_tarball_install_says_the_source_was_replaced", rc=1,
      check=lambda t, r, d: (t.assertIn("WARN   the elm-pi source: replaced by someone/fork@dev - not rolled back", r.out),
                             t.assertNotIn("To go back", r.out))),
]


@generate
class BootstrapHandoffTests(Batch):
    """install.sh step 3: bootstrap.sh's arguments and environment, and its failure report."""

    CASES = HANDOFF_CASES

    @classmethod
    def setUpClass(cls):
        cls.recorder = Path(tempfile.mkdtemp()).resolve() / "bootstrap.sh"
        touch(cls.recorder, RECORDER, 0o755)
        subprocess.run([str(cls.recorder)], capture_output=True)   # its first run is checked by macOS
        try:
            super().setUpClass()
        finally:
            shutil.rmtree(cls.recorder.parent, ignore_errors=True)

    @classmethod
    def prepare(cls, case, d):
        (d / "p").mkdir()
        os.symlink(cls.recorder, d / "p/bootstrap.sh")
        if case.kw["existing"]:
            (d / "p" / case.kw["existing"]).mkdir(parents=True)

    @classmethod
    def body(cls, case, d):
        kw = case.kw
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", STUBS, f"export BOOT_RC={kw['rc']}",
            'git() { echo def456; }',
            f"PREFIX={q(d / 'p')}; BRANCH=dev; REPO=https://x/r.git; SLUG=someone/fork; UPDATE={kw['update']}",
            f"OLD_HEAD={q(kw['old_head'])}", "PASS_ARGS=(" + " ".join(q(a) for a in kw["args"]) + ")", HANDOFF])


# =====================================================================================
# the launcher link
# =====================================================================================

LINK = block(INSTALLER, 'say "linking the launcher"', "# Put BINDIR on PATH for the shells")


def L(name, check, pre="", no_link=0, force=0, user_path="/usr/bin:/bin"):
    return C(name, check, pre=pre, no_link=no_link, force=force, user_path=user_path)


def _link(d, name="pi"):
    p = d / "bin" / name
    return os.readlink(p) if p.is_symlink() else None


LINK_CASES = [
    L("a_new_link_points_at_the_launcher",
      check=lambda t, r, d: (t.assertEqual(f"{d}/p/pi", _link(d)), t.assertEqual("1", r.vars["LINKED"]),
                             t.assertIn(f"    {d}/bin/pi -> {d}/p/pi", r.out))),
    L("no_link_makes_no_link", no_link=1,
      check=lambda t, r, d: (t.assertIsNone(_link(d)), t.assertIn("    skipped (--no-link)", r.out),
                             t.assertEqual("0", r.vars["LINKED"]))),
    L("a_file_in_the_way_is_left_alone", pre='mkdir -p bin && echo mine > bin/pi',
      check=lambda t, r, d: (t.assertEqual("mine\n", (d / "bin/pi").read_text()),
                             t.assertIn(f"WARN {d}/bin/pi exists and is not a symlink — leaving it alone", r.out),
                             t.assertIn(f"WARN run pi as: {d}/p/pi", r.out))),
    L("a_link_to_another_pi_is_left_alone", pre='mkdir -p bin && ln -s /opt/other/pi bin/pi',
      check=lambda t, r, d: (t.assertEqual("/opt/other/pi", _link(d)),
                             t.assertIn(f"WARN {d}/bin/pi already points at /opt/other/pi — leaving it alone", r.out),
                             t.assertEqual("0", r.vars["LINKED"]))),
    L("force_link_replaces_a_link_to_another_pi", force=1, pre='mkdir -p bin && ln -s /opt/other/pi bin/pi',
      check=lambda t, r, d: (t.assertEqual(f"{d}/p/pi", _link(d)), t.assertEqual("1", r.vars["LINKED"]))),
    L("force_link_still_leaves_a_real_file_alone", force=1, pre='mkdir -p bin && echo mine > bin/pi',
      check=lambda t, r, d: t.assertEqual("mine\n", (d / "bin/pi").read_text())),
    L("our_own_link_is_renewed_without_force", pre='mkdir -p bin && ln -s "$PREFIX/pi" bin/pi',
      check=lambda t, r, d: (t.assertEqual(f"{d}/p/pi", _link(d)), t.assertEqual("1", r.vars["LINKED"]))),
    L("a_bindir_that_cannot_be_made_is_a_warning", pre='echo file > notadir; BINDIR="$PWD/notadir/bin"; LINK="$BINDIR/pi"',
      check=lambda t, r, d: (t.assertEqual(0, r.rc), t.assertIn(f"WARN could not create {d}/notadir/bin — launcher was not linked", r.out))),
    L("the_old_elm_pi_link_to_us_is_retired", pre='mkdir -p bin && ln -s "$PREFIX/pi" bin/elm-pi',
      check=lambda t, r, d: (t.assertFalse(os.path.lexists(d / "bin/elm-pi")),
                             t.assertIn(f"    removed the old {d}/bin/elm-pi symlink (the command is now pi)", r.out))),
    L("someone_elses_elm_pi_link_is_kept", pre='mkdir -p bin && ln -s /opt/elm-pi bin/elm-pi',
      check=lambda t, r, d: t.assertEqual("/opt/elm-pi", _link(d, "elm-pi"))),
    L("the_old_link_is_kept_when_linking_was_skipped", no_link=1, pre='mkdir -p bin && ln -s "$PREFIX/pi" bin/elm-pi',
      check=lambda t, r, d: t.assertEqual(f"{d}/p/pi", _link(d, "elm-pi"))),
    L("the_old_link_is_kept_when_the_new_one_was_refused",
      pre='mkdir -p bin && echo mine > bin/pi && ln -s "$PREFIX/pi" bin/elm-pi',
      check=lambda t, r, d: t.assertEqual(f"{d}/p/pi", _link(d, "elm-pi"))),
    L("another_pi_earlier_on_path_is_warned_about",
      pre='mkdir -p other && printf "#!/bin/sh\\n" > other/pi && chmod 755 other/pi && ELM_PI_USER_PATH="$PWD/other:$BINDIR"',
      check=lambda t, r, d: (t.assertIn(f"WARN another pi is earlier on your PATH: {d}/other/pi", r.out),
                             t.assertIn(f"WARN that one will keep winning — remove it, or move {d}/bin ahead of it", r.out))),
    L("another_pi_is_not_mentioned_while_bindir_is_not_on_path",
      pre='mkdir -p other && printf "#!/bin/sh\\n" > other/pi && chmod 755 other/pi && ELM_PI_USER_PATH="$PWD/other"',
      check=lambda t, r, d: t.assertNotIn("another pi", r.out)),
    L("our_own_pi_first_on_path_is_not_a_warning", pre='ELM_PI_USER_PATH="$BINDIR:/usr/bin"',
      check=lambda t, r, d: t.assertNotIn("another pi", r.out)),
]


@generate
class LauncherLinkTests(Batch):
    """install.sh step 4: ~/.local/bin/pi, and the retired elm-pi link."""

    CASES = LINK_CASES

    @classmethod
    def prepare(cls, case, d):
        touch(d / "p/pi", "#!/bin/sh\n", 0o755)

    @classmethod
    def body(cls, case, d):
        kw = case.kw
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", STUBS, f"PREFIX={q(d / 'p')}", 'BINDIR="$PWD/bin"',
            f"NO_LINK={kw['no_link']}; FORCE_LINK={kw['force']}; ELM_PI_USER_PATH={q(kw['user_path'])}",
            kw["pre"], LINK, "_v LINKED"])


# =====================================================================================
# PATH in the shell profiles, in a temporary HOME
# =====================================================================================

PROFILE = block(INSTALLER, "ON_PATH=0\ncase", "# --- 5. what to do next")


def posix_line(bindir):
    return f'\n# added by the elm-pi installer\nexport PATH="{bindir}:$PATH"\n'


def fish_line(bindir):
    return f"\n# added by the elm-pi installer\nfish_add_path {bindir}\n"


def P(name, check, shell="zsh", os_="macOS", files=None, no_path=0, on_path=False, twice=False, bug=None):
    return C(name, check, bug=bug, shell=shell, os=os_, files=files or {}, no_path=no_path, on_path=on_path,
             twice=twice)


def _home(d, rel):
    p = d / "home" / rel
    return p.read_text() if p.is_file() else None


def _bindir(d):
    return f"{d}/home/.local/bin"


PROFILE_CASES = [
    P("zsh_gets_the_line_in_zshrc",
      check=lambda t, r, d: (t.assertEqual(posix_line(_bindir(d)), _home(d, ".zshrc")),
                             t.assertIn(f"    added {_bindir(d)} to .zshrc", r.out))),
    P("bash_on_macos_gets_bash_profile", shell="bash",
      check=lambda t, r, d: (t.assertEqual(posix_line(_bindir(d)), _home(d, ".bash_profile")),
                             t.assertIsNone(_home(d, ".bashrc")))),
    P("bash_on_linux_gets_bashrc", shell="bash", os_="Linux",
      check=lambda t, r, d: (t.assertEqual(posix_line(_bindir(d)), _home(d, ".bashrc")),
                             t.assertIsNone(_home(d, ".bash_profile")))),
    P("fish_gets_fish_add_path_in_its_config", shell="fish",
      check=lambda t, r, d: t.assertEqual(fish_line(_bindir(d)), _home(d, ".config/fish/config.fish"))),
    P("a_shell_from_a_full_path_is_known_by_its_name", shell="/usr/local/bin/zsh",
      check=lambda t, r, d: t.assertEqual(posix_line(_bindir(d)), _home(d, ".zshrc"))),
    P("an_unknown_shell_with_no_profiles_is_told_the_line", shell="tcsh",
      check=lambda t, r, d: (t.assertIn("WARN could not work out which shell profile to edit. Add this line yourself:", r.out),
                             t.assertIn(f'      export PATH="{_bindir(d)}:$PATH"', r.out),
                             t.assertEqual([], [p.name for p in (d / "home").iterdir()]))),
    P("an_unknown_shell_with_a_zshrc_gets_it_there", shell="tcsh", files={".zshrc": "# mine\n"},
      check=lambda t, r, d: t.assertEqual("# mine\n" + posix_line(_bindir(d)), _home(d, ".zshrc"))),
    P("a_zsh_user_with_a_bashrc_gets_both", files={".bashrc": ""},
      check=lambda t, r, d: t.assertEqual([posix_line(_bindir(d))] * 2, [_home(d, ".zshrc"), _home(d, ".bashrc")])),
    P("a_bash_user_on_macos_with_a_zshrc_gets_both", shell="bash", files={".zshrc": ""},
      check=lambda t, r, d: t.assertEqual([posix_line(_bindir(d))] * 2, [_home(d, ".bash_profile"), _home(d, ".zshrc")])),
    P("a_bash_user_on_macos_leaves_bashrc_alone", shell="bash", files={".bashrc": "# mine\n"},
      check=lambda t, r, d: t.assertEqual("# mine\n", _home(d, ".bashrc"))),
    P("a_bash_user_on_linux_leaves_bash_profile_alone", shell="bash", os_="Linux", files={".bash_profile": "# mine\n"},
      check=lambda t, r, d: t.assertEqual("# mine\n", _home(d, ".bash_profile"))),
    P("a_fish_user_on_macos_with_a_bash_profile_gets_both", shell="fish", files={".bash_profile": ""},
      check=lambda t, r, d: (t.assertEqual(posix_line(_bindir(d)), _home(d, ".bash_profile")),
                             t.assertEqual(fish_line(_bindir(d)), _home(d, ".config/fish/config.fish")))),
    P("a_zsh_user_on_linux_with_a_bash_profile_leaves_it", os_="Linux", files={".bash_profile": ""},
      check=lambda t, r, d: t.assertEqual("", _home(d, ".bash_profile"))),
    P("a_profile_that_already_has_it_is_left_as_it_is", files={".zshrc": "export PATH=\"{bindir}:$PATH\"\n"},
      check=lambda t, r, d: (t.assertEqual(f'export PATH="{_bindir(d)}:$PATH"\n', _home(d, ".zshrc")),
                             t.assertIn("    already in .zshrc", r.out), t.assertEqual("1", r.vars["PATH_PRESENT"]),
                             t.assertEqual("0", r.vars["PATH_ADDED"]))),
    # property: running the installer again never adds the line twice.
    P("a_second_run_adds_nothing", files={".bashrc": ""}, twice=True,
      check=lambda t, r, d: t.assertEqual([1, 1], [_home(d, ".zshrc").count("added by the elm-pi installer"),
                                                   _home(d, ".bashrc").count("added by the elm-pi installer")])),
    P("already_on_path_touches_no_profile", on_path=True, files={".zshrc": "# mine\n"},
      check=lambda t, r, d: (t.assertIn(f"    {_bindir(d)} is already on PATH", r.out),
                             t.assertEqual("# mine\n", _home(d, ".zshrc")))),
    P("no_path_touches_no_profile_and_says_how_to_run", no_path=1, files={".zshrc": "# mine\n"},
      check=lambda t, r, d: (t.assertEqual("# mine\n", _home(d, ".zshrc")),
                             t.assertIn(f"WARN {_bindir(d)} is not on PATH, and --no-path was given. Run pi as: {d}/p/pi", r.out))),
    P("the_fish_config_folder_is_created", shell="fish",
      check=lambda t, r, d: t.assertTrue((d / "home/.config/fish").is_dir())),
    # An unwritable profile is warned about; a return 1 there would trip set -e
    # and fail the installer after a successful install.
    P("a_profile_that_cannot_be_written_is_a_warning_not_a_failure", files={".zshrc/": None},
      check=lambda t, r, d: (t.assertIn(f"WARN could not write {d}/home/.zshrc", r.out), t.assertEqual(0, r.rc))),
    # Not a substring match: a profile that only mentions a file under
    # ~/.local/bin, a longer path, or a comment does not have it on PATH.
    P("a_profile_that_only_mentions_a_file_in_bindir_still_gets_the_line",
      files={".zshrc": "alias x={bindir}/x\n"},
      check=lambda t, r, d: t.assertIn(posix_line(_bindir(d)), _home(d, ".zshrc"))),
    P("a_profile_with_a_longer_path_still_gets_the_line",
      files={".zshrc": 'export PATH="{bindir}2:$PATH"\n'},
      check=lambda t, r, d: t.assertIn(posix_line(_bindir(d)), _home(d, ".zshrc"))),
    P("a_profile_with_it_only_in_a_comment_still_gets_the_line",
      files={".zshrc": '# export PATH="{bindir}:$PATH"\n'},
      check=lambda t, r, d: t.assertIn(posix_line(_bindir(d)), _home(d, ".zshrc"))),
    P("a_fish_config_that_already_has_it_is_left_as_it_is", shell="fish",
      files={".config/fish/config.fish": "fish_add_path {bindir}\n"},
      check=lambda t, r, d: (t.assertEqual(f"fish_add_path {_bindir(d)}\n", _home(d, ".config/fish/config.fish")),
                             t.assertIn("    already in config.fish", r.out))),
]


@generate
class ProfilePathTests(Batch):
    """install.sh: the PATH line, per shell and system, in a temporary HOME."""

    CASES = PROFILE_CASES

    @classmethod
    def prepare(cls, case, d):
        (d / "home").mkdir()
        for rel, text in case.kw["files"].items():
            if text is None:
                (d / "home" / rel).mkdir(parents=True)
            else:
                touch(d / "home" / rel, text.format(bindir=_bindir(d)))

    @classmethod
    def body(cls, case, d):
        kw = case.kw
        user_path = f"/usr/bin:{_bindir(d)}:/bin" if kw["on_path"] else "/usr/bin:/bin"
        run = PROFILE + ("\n" + PROFILE if kw["twice"] else "")
        return "\n".join([
            "set -euo pipefail", f"cd {q(d)}", STUBS, f"export HOME={q(d / 'home')}", f"SHELL={q(kw['shell'])}",
            f"OS={kw['os']}", f"PREFIX={q(d / 'p')}", 'BINDIR="$HOME/.local/bin"', f"NO_PATH={kw['no_path']}",
            f"ELM_PI_USER_PATH={q(user_path)}", run, "_v PATH_ADDED PATH_PRESENT ON_PATH"])


# =====================================================================================
# the closing advice
# =====================================================================================

DONE = block(INSTALLER, "# --- 5. what to do next")


def E(name, check, on_path=0, added=0, present=0):
    return C(name, check, on_path=on_path, added=added, present=present)


DONE_CASES = [
    E("on_path_already_says_run_pi_with_no_export", on_path=1,
      check=lambda t, r, d: (t.assertIn("    Start it:      pi\n", r.out), t.assertNotIn("For this one", r.out))),
    E("a_line_just_added_says_new_shells_and_the_export_for_this_one", added=1,
      check=lambda t, r, d: (t.assertIn(f'    New shells will find pi. For this one:  export PATH="{d}/bin:$PATH"', r.out),
                             t.assertIn("    Start it:      pi\n", r.out))),
    E("a_line_already_in_a_profile_says_the_same", present=1,
      check=lambda t, r, d: t.assertIn("New shells will find pi.", r.out)),
    E("no_path_at_all_says_run_it_by_its_full_path",
      check=lambda t, r, d: (t.assertIn(f"    Start it:      {d}/p/pi\n", r.out),
                             t.assertIn(f'    One-shot:      {d}/p/pi -p "explain this repo"', r.out))),
    E("the_uninstall_line_names_both_paths", on_path=1,
      check=lambda t, r, d: t.assertIn(f"    Uninstall:     rm -rf {d}/p {d}/bin/pi", r.out)),
    E("the_docs_line_is_the_configured_docs", on_path=1,
      check=lambda t, r, d: t.assertIn("    Docs:          https://docs.example/", r.out)),
]


@generate
class ClosingAdviceTests(Batch):
    """install.sh step 5: how to start pi, given where the PATH step left things."""

    CASES = DONE_CASES

    @classmethod
    def body(cls, case, d):
        kw = case.kw
        return "\n".join([
            "set -euo pipefail", STUBS, f"PREFIX={q(d / 'p')}", f"BINDIR={q(d / 'bin')}", "DOCS=https://docs.example/",
            f"ON_PATH={kw['on_path']}; PATH_ADDED={kw['added']}; PATH_PRESENT={kw['present']}", DONE])


# =====================================================================================
# configure.sh, whole, against a stubbed gateway
# =====================================================================================

QWEN = "Qwen/Qwen3.5-397B-A17B-FP8"
LLAMA = "meta-llama/Llama-3.3-70B-Instruct"
OK_CHAT = {"choices": [{"message": {"content": "OK"}}]}

# curl, stubbed in the install's .node/bin (first on configure.sh's PATH): logs
# its arguments one per line, then the header file's content, and answers from
# the case's files.
FAKE_CURL = r'''#!/bin/sh
here="$(cd "$(dirname "$0")/../.." && pwd)"
{ echo "CALL"; for a in "$@"; do echo "ARG $a"; done; } >> "$here/curl.log"
prev=""
for a in "$@"; do
  [ "$prev" = -H ] && case "$a" in @*) echo "HEADER $(cat "${a#@}")" >> "$here/curl.log" ;; esac
  prev="$a"
done
case "$*" in
  */models*) [ -f "$here/models.rc" ] && exit "$(cat "$here/models.rc")"; cat "$here/gateway.out" ;;
  *) cat "$here/chat.out" ;;
esac
'''


def G(name, check, gateway=None, chat=None, args=(), env_file="ELM_API_KEY=elm-secret-key\n", models=None,
      settings=None, models_rc=None, twice=False, bug=None):
    return C(name, check, bug=bug, gateway={"data": [{"id": LLAMA}, {"id": QWEN}]} if gateway is None else gateway,
             chat=OK_CHAT if chat is None else chat, args=list(args), env_file=env_file, models=models,
             settings=settings, models_rc=models_rc, twice=twice)


def _json(d, rel):
    return json.loads((d / rel).read_text())


def _state(d):
    return _json(d, "agent/model-ids.json")


def _curl_calls(d):
    calls, cur = [], None
    for line in lines(d / "curl.log"):
        if line == "CALL":
            cur = []
            calls.append(cur)
        else:
            cur.append(line)
    return calls


STATE_FILES = ("agent/model-ids.json", "agent/models.json", "agent/settings.json")
# The three files as the base install had them, kept after it is removed.
BASELINE = {}


def _unchanged(t, d):
    for rel in STATE_FILES:
        t.assertEqual(BASELINE[rel], (d / rel).read_text(), rel)


def _qwen_entries(d):
    return [m for m in _json(d, "agent/models.json")["providers"]["elm"]["models"] if "qwen" in m["id"].lower()]


CONFIGURE_CASES = [
    G("a_reply_that_is_not_json_fails_and_changes_nothing", gateway="<html>login</html>",
      check=lambda t, r, d: (t.assertNotEqual(0, r.rc), t.assertIn("Gateway did not return JSON:\n<html>login</html>", r.err),
                             _unchanged(t, d))),
    G("a_gateway_error_is_reported_as_one", gateway={"error": {"message": "bad key"}},
      check=lambda t, r, d: (t.assertNotEqual(0, r.rc), t.assertIn('Gateway error: {"message": "bad key"}', r.err),
                             _unchanged(t, d))),
    G("no_matching_id_lists_what_is_there_sorted", gateway={"data": [{"id": "zeta"}, {"id": "alpha"}]},
      check=lambda t, r, d: (t.assertNotEqual(0, r.rc),
                             t.assertIn("No model id matching 'qwen'. Available:\n    alpha\n    zeta\n", r.err),
                             _unchanged(t, d))),
    G("a_gateway_with_only_llama_has_no_qwen_to_set", gateway={"data": [{"id": LLAMA}]},
      check=lambda t, r, d: (t.assertNotEqual(0, r.rc), t.assertIn("No model id matching 'qwen'", r.err))),
    G("of_several_qwens_the_397b_wins_and_the_others_are_named",
      gateway={"data": [{"id": "Qwen/Qwen3-32B-long-name"}, {"id": "Qwen/Qwen3.5-397B"}]},
      check=lambda t, r, d: (t.assertEqual("Qwen/Qwen3.5-397B", _state(d)["qwen"]),
                             t.assertIn("Matched 2, choosing Qwen/Qwen3.5-397B (others: Qwen/Qwen3-32B-long-name)", r.err))),
    G("without_a_397b_the_longest_qwen_wins",
      gateway={"data": [{"id": "Qwen/Q-7B"}, {"id": "Qwen/Q-72B-Instruct"}, {"id": "Qwen/Q-14B"}]},
      check=lambda t, r, d: t.assertEqual("Qwen/Q-72B-Instruct", _state(d)["qwen"])),
    G("a_bare_list_of_models_is_read", gateway=[{"id": "Qwen/Listed-397B"}],
      check=lambda t, r, d: (t.assertEqual(0, r.rc, r.err), t.assertEqual("Qwen/Listed-397B", _state(d)["qwen"]))),
    G("ids_given_as_plain_strings_are_read", gateway={"data": ["Qwen/Plain-397B", LLAMA]},
      check=lambda t, r, d: t.assertEqual("Qwen/Plain-397B", _state(d)["qwen"])),
    G("the_substring_matches_in_any_case", args=("QWEN3.5",),
      check=lambda t, r, d: (t.assertEqual(0, r.rc, r.err), t.assertEqual(QWEN, _state(d)["qwen"]))),
    G("a_substring_without_qwen_in_it_may_still_name_qwen", args=("397b",),
      check=lambda t, r, d: (t.assertEqual(0, r.rc, r.err), t.assertEqual(QWEN, _state(d)["qwen"]))),
    G("a_smoke_test_that_is_not_json_fails_before_anything_changes", chat="Bad Gateway",
      check=lambda t, r, d: (t.assertNotEqual(0, r.rc), t.assertIn("  non-JSON reply: Bad Gateway", r.err),
                             _unchanged(t, d))),
    G("a_smoke_test_error_fails_before_anything_changes", chat={"error": "overloaded"},
      check=lambda t, r, d: (t.assertNotEqual(0, r.rc), t.assertIn('  error: "overloaded"', r.err), _unchanged(t, d))),
    G("a_smoke_test_that_answers_is_shown",
      check=lambda t, r, d: t.assertIn("  reply: OK", r.out)),
    G("the_model_list_cannot_be_fetched_and_nothing_changes", models_rc=22,
      check=lambda t, r, d: (t.assertNotEqual(0, r.rc), _unchanged(t, d), t.assertEqual(1, len(_curl_calls(d))))),
    # The key goes in a header file, never on curl's command line where `ps`
    # shows it to every account on the machine.
    G("the_key_never_appears_in_curls_arguments",
      check=lambda t, r, d: (t.assertEqual(2, len(_curl_calls(d))),
                             t.assertFalse(any("elm-secret-key" in a for c in _curl_calls(d) for a in c if a.startswith("ARG"))),
                             t.assertEqual(["HEADER Authorization: Bearer elm-secret-key"] * 2,
                                           [a for c in _curl_calls(d) for a in c if a.startswith("HEADER")]))),
    G("no_temporary_file_is_left_behind_after_a_run",
      check=lambda t, r, d: t.assertEqual([], sorted(p.name for p in (d / "agent").iterdir()
                                                     if p.name.startswith((".models-raw.", ".auth-header."))))),
    G("no_temporary_file_is_left_behind_after_a_failure", gateway="nope",
      check=lambda t, r, d: t.assertEqual([], sorted(p.name for p in (d / "agent").iterdir()
                                                     if p.name.startswith((".models-raw.", ".auth-header."))))),
    G("the_smoke_test_asks_the_chosen_model_for_a_short_unthinking_reply",
      check=lambda t, r, d: t.assertEqual(
          {"model": QWEN, "messages": [{"role": "user", "content": "Reply with exactly: OK"}], "max_tokens": 256,
           "reasoning_effort": "none"},
          json.loads(_curl_calls(d)[1][_curl_calls(d)[1].index("ARG -d") + 1][4:]))),
    G("the_two_requests_have_their_timeouts",
      check=lambda t, r, d: t.assertEqual([["ARG -m", "ARG 30"], ["ARG -m", "ARG 120"]],
                                          [c[c.index("ARG -m"):c.index("ARG -m") + 2] for c in _curl_calls(d)])),
    G("a_base_url_from_env_file_is_queried_and_recorded",
      env_file="ELM_API_KEY=elm-secret-key\nELM_BASE_URL=https://gw.example/v9\n",
      check=lambda t, r, d: (t.assertEqual("ARG https://gw.example/v9/models",
                                           [a for a in _curl_calls(d)[0] if a.startswith("ARG")][-1]),
                             t.assertEqual("https://gw.example/v9",
                                           _json(d, "agent/models.json")["providers"]["elm"]["baseUrl"]))),
    G("a_models_file_without_a_qwen_gets_one_first_with_the_defaults",
      models={"providers": {"elm": {"models": [{"id": "other/model"}]}}},
      check=lambda t, r, d: t.assertEqual(
          [{"id": QWEN, "name": f"{QWEN} (ELM, university-hosted)", "reasoning": True, "input": ["text"],
            "contextWindow": 262144, "maxTokens": 32768, "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}},
           {"id": "other/model"}],
          _json(d, "agent/models.json")["providers"]["elm"]["models"])),
    G("an_empty_models_file_gets_a_provider_with_the_api_and_key_reference", models={},
      check=lambda t, r, d: t.assertEqual(("openai-completions", "$ELM_API_KEY", "https://elm.edina.ac.uk/api/v1"),
                                          tuple(_json(d, "agent/models.json")["providers"]["elm"][k]
                                                for k in ("api", "apiKey", "baseUrl")))),
    G("the_qwen_entrys_tuned_fields_are_kept",
      models={"providers": {"elm": {"models": [{"id": "Qwen/Old", "contextWindow": 1000, "samplingParams": {"t": 1}}]}}},
      check=lambda t, r, d: t.assertEqual([{"id": QWEN, "contextWindow": 1000, "samplingParams": {"t": 1}}],
                                          _qwen_entries(d))),
    G("your_api_and_key_reference_are_kept",
      models={"providers": {"elm": {"api": "mine-api", "apiKey": "$MY_KEY", "models": [{"id": "Qwen/Old"}]}}},
      check=lambda t, r, d: t.assertEqual(("mine-api", "$MY_KEY"),
                                          tuple(_json(d, "agent/models.json")["providers"]["elm"][k] for k in ("api", "apiKey")))),
    G("a_default_model_on_llama_is_not_re_pointed", settings={"defaultProvider": "elm-shim", "defaultModel": f"{LLAMA}"},
      check=lambda t, r, d: t.assertEqual({"defaultProvider": "elm-shim", "defaultModel": LLAMA},
                                          _json(d, "agent/settings.json"))),
    G("no_default_model_becomes_the_qwen", settings={"theme": "dark"},
      check=lambda t, r, d: t.assertEqual({"theme": "dark", "defaultProvider": "elm", "defaultModel": QWEN},
                                          _json(d, "agent/settings.json"))),
    G("a_qwen_default_follows_the_new_id_and_the_rest_is_kept",
      settings={"defaultProvider": "x", "defaultModel": "Qwen/Old", "packages": ["npm:a"]},
      check=lambda t, r, d: t.assertEqual({"defaultProvider": "elm", "defaultModel": QWEN, "packages": ["npm:a"]},
                                          _json(d, "agent/settings.json"))),
    G("an_empty_key_stops_before_any_request", env_file="ELM_API_KEY=\n",
      check=lambda t, r, d: (t.assertNotEqual(0, r.rc), t.assertIn("Set ELM_API_KEY in", r.err),
                             t.assertEqual([], _curl_calls(d)))),
    # property: configuring twice against the same gateway is the same as once.
    G("a_second_run_changes_nothing", twice=True,
      check=lambda t, r, d: t.assertEqual(json.loads((d / "first.json").read_text()),
                                          {rel: (d / rel).read_text() for rel in
                                           ("agent/model-ids.json", "agent/models.json", "agent/settings.json")})),
]

_BASE = {}


def configure_base():
    """One install rendered from this checkout, copied for each case."""
    if "dir" not in _BASE:
        base = Path(tempfile.mkdtemp()).resolve() / "base"
        base.mkdir()
        shutil.copy2(ROOT / "configure.sh", base / "configure.sh")
        for name in ("lib", "config", "scripts", "templates"):
            shutil.copytree(ROOT / name, base / name, ignore=shutil.ignore_patterns("__pycache__"))
        render = [PY, str(base / "scripts/elm_config.py"), "--root", str(base)]
        subprocess.run([*render, "init"], check=True, capture_output=True)
        for name in ("models.json", "settings.json"):
            subprocess.run([*render, "render", str(base / "templates" / name), str(base / "agent" / name)],
                           check=True, capture_output=True)
        touch(base / ".node/bin/curl", FAKE_CURL, 0o755)
        # Run each once (configure.sh stops at the missing key) so the cases do not wait on the check.
        subprocess.run([str(base / ".node/bin/curl"), "warm"], capture_output=True)
        subprocess.run([str(base / "configure.sh")], capture_output=True, cwd=base,
                       env={"PATH": "/usr/bin:/bin", "HOME": str(base), "ELM_PI_PYTHON": PY})
        (base / "curl.log").unlink(missing_ok=True)
        BASELINE.update({rel: (base / rel).read_text() for rel in STATE_FILES})
        _BASE["dir"] = base
    return _BASE["dir"]


@generate
class ConfigureTests(Batch):
    """configure.sh, run whole: the gateway's answer, the smoke test, and the merge."""

    CASES = CONFIGURE_CASES

    @classmethod
    def setUpClass(cls):
        try:
            super().setUpClass()
        finally:
            shutil.rmtree(configure_base().parent, ignore_errors=True)
            _BASE.clear()

    @classmethod
    def prepare(cls, case, d):
        kw = case.kw
        shutil.rmtree(d)
        base = configure_base()
        shutil.copytree(base, d, symlinks=True)
        # macOS checks each new executable the first time it runs: these two
        # are links to the base install's copies, which have already run.
        for rel in ("configure.sh", ".node/bin/curl"):
            (d / rel).unlink()
            os.link(base / rel, d / rel)
        touch(d / ".env", kw["env_file"], 0o600)
        touch(d / "gateway.out", kw["gateway"] if isinstance(kw["gateway"], str) else json.dumps(kw["gateway"]))
        touch(d / "chat.out", kw["chat"] if isinstance(kw["chat"], str) else json.dumps(kw["chat"]))
        if kw["models_rc"] is not None:
            touch(d / "models.rc", str(kw["models_rc"]))
        if kw["models"] is not None:
            touch(d / "agent/models.json", json.dumps(kw["models"]))
        if kw["settings"] is not None:
            touch(d / "agent/settings.json", json.dumps(kw["settings"]))

    @classmethod
    def body(cls, case, d):
        env = f"env -i PATH=/usr/bin:/bin HOME={q(d)} ELM_PI_PYTHON={q(PY)}"
        run = f"{env} ./configure.sh " + " ".join(q(a) for a in case.kw["args"])
        if case.kw["twice"]:
            save = ('"$PY" -c ' + q("import json,sys; print(json.dumps({r: open(r).read() for r in sys.argv[1:]}))")
                    + " agent/model-ids.json agent/models.json agent/settings.json > first.json")
            run = f"{run} >/dev/null 2>&1\n{save}\n{run}"
        return "\n".join([f"cd {q(d)}", f"PY={q(PY)}", run])


if __name__ == "__main__":
    unittest.main()
