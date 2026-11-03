"""Each colour wrapper in templates/shell/colour.sh injects exactly its flag, and only when output goes to pi.

The tools are fakes: tiny scripts first on PATH that log their argv and the
colour variables they were given (CLICOLOR, CLICOLOR_FORCE,
GIT_CONFIG_PARAMETERS) and print `out:<name>`. So every case can say exactly
which arguments reached the tool, whatever git, grep or ls the machine has.

Each case runs in its own subshell that sources the agent's copy of colour.sh
through the shellCommandPrefix from templates/settings.json, as pi's bash tool
does; all the cases of a class run in one bash process whose stdout is the pipe
this test reads, and each case's stdout, stderr, exit status and tool log are
read back after it. One test method is generated per case.
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "templates/settings.json").read_text())
PREFIX = SETTINGS["shellCommandPrefix"]
ESC = "\x1b["

# Every name colour.sh may wrap.
TOOLS = ["git", "grep", "rg", "fd", "jq", "tree", "shellcheck", "pytest", "ruff", "diff",
         "python3", "python", "ls"]
# What git gets in front of a display subcommand.
GITC = ["-c", "color.ui=always", "-c", "color.diff=always", "-c", "color.status=always",
        "-c", "color.branch=always", "-c", "color.grep=always"]
UNSET = "~"
ENV_NAMES = ["CLICOLOR", "CLICOLOR_FORCE", "GIT_CONFIG_PARAMETERS"]

# A fake tool: log argv and colour variables (fields \x1f, groups \x1e, records \x1d,
# so arguments may hold spaces and newlines), print out:<name>, exit $FAKE_EXIT.
FAKE = r"""#!/bin/bash
r=${0##*/}
for a in "$@"; do r+=$'\x1f'"$a"; done
r+=$'\x1e'"${CLICOLOR-~}"$'\x1f'"${CLICOLOR_FORCE-~}"$'\x1f'"${GIT_CONFIG_PARAMETERS-~}"
printf '%s\x1d' "$r" >> "${FAKE_LOG:-/dev/null}"
@PROBE@
printf 'out:%s\n' "${0##*/}"
exit "${FAKE_EXIT:-0}"
"""
# A diff that knows --color answers the support probe as real diff does (0 for
# two empty files), whatever FAKE_EXIT a case gives the call itself.
PROBE_OK = '[ "$*" = "--color=always /dev/null /dev/null" ] && exit 0'
# Comparing directories, diff heads each pair of files with its command line.
HEADER = '[ -n "${FAKE_HEADER-}" ] && printf "diff %s\\n" "$*"'
# An old diff rejects --color as an unknown option.
PROBE_OLD = 'case "$1" in --color*) echo "diff: unrecognized option \'$1\'" >&2; exit 2 ;; esac'

D = {}  # module state: temp dir and bin dirs


def setUpModule():
    stat, cat = shutil.which("stat"), shutil.which("cat")
    if not (stat and cat and shutil.which("bash")):
        raise unittest.SkipTest("needs bash, stat and cat")
    d = Path(tempfile.mkdtemp())
    D["dir"] = d
    agent = d / "agent"
    (agent / "shell").mkdir(parents=True)
    shutil.copy(ROOT / "templates/shell/colour.sh", agent / "shell/colour.sh")
    D["agent"] = agent
    bins = d / "bin"
    fake = bins / "fake"
    fake.mkdir(parents=True)
    for tool in TOOLS:
        script = FAKE.replace("@PROBE@", f"{PROBE_OK}\n{HEADER}" if tool == "diff" else "")
        (fake / tool).write_text(script)
        (fake / tool).chmod(0o755)
    old = bins / "olddiff"
    old.mkdir()
    (old / "diff").write_text(FAKE.replace("@PROBE@", PROBE_OLD))
    (old / "diff").chmod(0o755)
    # The few real programs the harness itself needs, and nothing colour.sh wraps.
    mini = bins / "min"
    mini.mkdir()
    (mini / "stat").symlink_to(stat)
    (mini / "cat").symlink_to(cat)
    # sed, which the diff wrapper needs for a directory diff, apart.
    sed = shutil.which("sed")
    if sed:
        (bins / "sed").mkdir()
        (bins / "sed" / "sed").symlink_to(sed)
    for tool in TOOLS:
        (bins / f"only_{tool}").mkdir()
        (bins / f"only_{tool}" / tool).symlink_to(fake / tool)
        (bins / f"without_{tool}").mkdir()
        for other in TOOLS:
            if other != tool:
                (bins / f"without_{tool}" / other).symlink_to(fake / other)
    (d / "lsdir/sub").mkdir(parents=True)
    (d / "lsdir/file.txt").write_text("x\n")
    (d / "notadir/shell/colour.sh").mkdir(parents=True)
    D["bins"] = bins


def tearDownModule():
    if "dir" in D:
        shutil.rmtree(D["dir"], ignore_errors=True)


def path_for(spec):
    b, m = D["bins"], D["bins"] / "min"
    if spec == "fake":
        return f"{b}/fake:{m}"
    if spec == "nostat":           # the fakes but no stat: colour.sh cannot identify pi's pipe
        return f"{b}/fake"
    if spec == "none":             # none of the wrapped tools exist
        return str(m)
    if spec == "sed":
        return f"{b}/fake:{m}:{b}/sed"
    if spec == "olddiff":
        return f"{b}/olddiff:{b}/fake:{m}"
    if spec == "bin":              # the system's own /bin first, so `type -P ls` is /bin/ls
        return f"/bin:{m}"
    kind, tool = spec.split(":")
    return f"{b}/{kind}_{tool}:{m}"


def environ():
    # A clean environment: nothing from the caller's colour settings leaks in.
    return {"HOME": str(D["dir"]), "PATH": "/usr/bin:/bin", "LC_ALL": "C",
            "PI_CODING_AGENT_DIR": str(D["agent"])}


class Case:
    def __init__(self, slug, cmd, *, path="fake", env=None, pre="", calls=None, envs=None,
                 out=None, has=None, lacks=None, err="", status=0, xfail=None, skip=None):
        self.slug, self.cmd, self.path, self.env, self.pre = slug, cmd, path, env or {}, pre
        self.calls, self.envs, self.out, self.has, self.lacks = calls, envs, out, has, lacks
        self.err, self.status, self.xfail, self.skip = err, status, xfail, skip


def parse_log(text):
    calls = []
    for rec in text.split("\x1d")[:-1]:
        argpart, envpart = rec.split("\x1e")
        name, *args = argpart.split("\x1f")
        env = {k: (None if v == UNSET else v) for k, v in zip(ENV_NAMES, envpart.split("\x1f"))}
        calls.append((name, args, env))
    return calls


def run_batch(cases, bash="bash"):
    """Run every case in one bash process; return {slug: (out, err, status, calls)}."""
    logs = D["dir"] / f"log-{id(cases)}"
    logs.mkdir()
    parts = []
    for i, c in enumerate(cases):
        envlines = "\n".join(f"unset {k}" if v is None else f"export {k}={shlex.quote(v)}"
                             for k, v in c.env.items())
        parts.append(
            f"printf '\\n@@{i}<\\n'\n(\nexport FAKE_LOG={shlex.quote(str(logs / str(i)))}\n"
            f"PATH={shlex.quote(path_for(c.path))}\n{envlines}\n{c.pre}\n{PREFIX}\n{c.cmd}\n"
            f") 2>{shlex.quote(str(logs / (str(i) + '.err')))}\nprintf '\\n@@{i}>%d\\n' $?\n")
    proc = subprocess.run([bash, "-c", "".join(parts)], cwd=D["dir"], capture_output=True,
                          text=True, env=environ(), timeout=300)
    results = {}
    for i, c in enumerate(cases):
        m = re.search(rf"\n@@{i}<\n(.*?)\n@@{i}>(\d+)\n", proc.stdout, re.S)
        if m is None:
            results[c.slug] = None
            continue
        log = logs / str(i)
        err = (logs / f"{i}.err").read_text()
        calls = parse_log(log.read_text()) if log.exists() else []
        results[c.slug] = (m.group(1), err, int(m.group(2)), calls)
    shutil.rmtree(logs, ignore_errors=True)
    return results


class WrapperCases(unittest.TestCase):
    CASES = []
    BASH = "bash"

    @classmethod
    def setUpClass(cls):
        cls.results = run_batch(cls.CASES, cls.BASH)

    def check(self, c):
        if c.skip and c.skip():
            raise unittest.SkipTest(c.skip())
        result = self.results[c.slug]
        self.assertIsNotNone(result, f"case {c.slug} did not finish")
        out, err, status, calls = result
        if c.calls is not None:
            self.assertEqual([(n, a) for n, a, _ in calls], [(n, list(a)) for n, a in c.calls])
        if c.envs is not None:
            self.assertTrue(calls, "the tool was not called")
            got = calls[-1][2]
            self.assertEqual({k: got[k] for k in c.envs}, c.envs)
        if c.out is not None:
            self.assertEqual(out, c.out)
        if c.has is not None:
            self.assertIn(c.has, out)
        if c.lacks is not None:
            self.assertNotIn(c.lacks, out)
        if c.err is not None:
            self.assertEqual(err, c.err)
        self.assertEqual(status, c.status)


def generate(cls):
    for c in cls.CASES:
        name = "test_" + re.sub(r"\W+", "_", c.slug).strip("_")
        assert not hasattr(cls, name), f"duplicate case {name}"

        def test(self, c=c):
            self.check(c)
        if c.xfail:
            test = unittest.expectedFailure(test)
        test.__doc__ = c.xfail or c.cmd.splitlines()[-1][:100]
        setattr(cls, name, test)
    return cls


def no_sed():
    return None if (D["bins"] / "sed").exists() else "needs sed"


def not_darwin():
    return None if sys.platform == "darwin" else "BSD ls lives at /bin/ls only on macOS here"


def no_bin_ls():
    return None if Path("/bin/ls").exists() else "no /bin/ls"


# --- grep, rg, fd, jq, tree, shellcheck, pytest: one forced flag each ---------

FLAG_TOOLS = [  # tool, the flag the wrapper forces, the tool's own "no colour" flag
    ("grep", "--color=always", "--color=never"),
    ("rg", "--color=always", "--color=never"),
    ("fd", "--color=always", "--color=never"),
    ("jq", "-C", "-M"),
    ("tree", "-C", "-n"),
    ("shellcheck", "--color=always", "--color=never"),
    ("pytest", "--color=yes", "--color=no"),
]


def flag_cases():
    cases = []
    for t, flag, off in FLAG_TOOLS:
        plain = [(t, ["needle", "src"])]
        neighbour = "git"
        cases += [
            Case(f"{t}_straight_to_pi_gets_{flag}", f"{t} needle src",
                 calls=[(t, [flag, "needle", "src"])], out=f"out:{t}\n"),
            Case(f"{t}_redirected_to_a_file_is_plain", f'{t} needle src > "$FAKE_LOG.out"; echo saved',
                 calls=plain, out="saved\n"),
            Case(f"{t}_piped_is_plain", f"{t} needle src | cat", calls=plain, out=f"out:{t}\n"),
            Case(f"{t}_in_command_substitution_is_plain", f'x=$({t} needle src); echo "got $x"',
                 calls=plain, out=f"got out:{t}\n"),
            Case(f"{t}_with_no_color_is_plain", f"{t} needle src", env={"NO_COLOR": "1"},
                 calls=plain, out=f"out:{t}\n"),
            Case(f"{t}_through_command_builtin_is_plain", f"command {t} needle src", calls=plain),
            # The forced flag goes first, so the user's own flag, later, wins.
            Case(f"{t}_user_flag_{off}_comes_after_the_forced_one", f"{t} {off} needle",
                 calls=[(t, [flag, off, "needle"])]),
            Case(f"{t}_absent_from_path_gets_no_function", f"type -t {t} || echo none; type -t {neighbour}",
                 path=f"without:{t}", calls=[], out="none\nfunction\n"),
            Case(f"{t}_alone_on_path_is_the_only_wrapper", f"type -t {t}; type -t {neighbour} || echo none",
                 path=f"only:{t}", calls=[], out="function\nnone\n"),
            Case(f"{t}_exit_status_passes_through", f"FAKE_EXIT=3 {t} needle",
                 calls=[(t, [flag, "needle"])], status=3),
        ]
    # Redirecting only stderr leaves stdout on pi's pipe.
    cases.append(Case("grep_with_only_stderr_redirected_is_coloured", "grep needle src 2>/dev/null",
                      calls=[("grep", ["--color=always", "needle", "src"])]))
    cases.append(Case("rg_arguments_with_spaces_and_quotes_are_kept",
                      "rg -e 'two words' \"it's\" '' 'a\"b'",
                      calls=[("rg", ["--color=always", "-e", "two words", "it's", "", 'a"b'])]))
    cases.append(Case("jq_no_arguments_gets_only_the_flag", "jq", calls=[("jq", ["-C"])]))
    return cases


@generate
class FlagToolWrapperTests(WrapperCases):
    CASES = flag_cases()


# --- ls: --color=always for GNU ls, CLICOLOR_FORCE for BSD ls -----------------

BRANCH = ('f=$(declare -f ls); if [[ $f == *CLICOLOR_FORCE=1* ]]; then echo bsd; '
          'elif [[ $f == *--color=always* ]]; then echo gnu; fi')


def ls_cases():
    plain = [("ls", ["-la", "dir"])]
    return [
        Case("fake_ls_off_bin_is_gnu_and_gets_color_always", "ls -la dir",
             calls=[("ls", ["--color=always", "-la", "dir"])], envs={"CLICOLOR": None, "CLICOLOR_FORCE": None}),
        Case("ls_redirected_is_plain", 'ls -la dir > "$FAKE_LOG.out"', calls=plain, out=""),
        Case("ls_piped_is_plain", "ls -la dir | cat", calls=plain, out="out:ls\n"),
        Case("ls_counted_in_substitution_is_plain", 'n=$(ls -la dir); echo "$n"', calls=plain),
        Case("ls_with_no_color_is_plain", "ls -la dir", env={"NO_COLOR": "1"}, calls=plain),
        Case("ls_through_command_builtin_is_plain", "command ls -la dir", calls=plain),
        Case("ls_user_color_never_follows_the_forced_flag", "ls --color=never",
             calls=[("ls", ["--color=always", "--color=never"])]),
        Case("ls_with_no_arguments_gets_only_the_flag", "ls", calls=[("ls", ["--color=always"])]),
        Case("ls_absent_gets_no_function", "type -t ls || echo none", path="without:ls", out="none\n"),
        Case("ls_alone_on_path_is_wrapped", "type -t ls; type -t grep || echo none", path="only:ls",
             out="function\nnone\n"),
        # The branch follows where ls lives, not only OSTYPE: an ls elsewhere on macOS is GNU's.
        Case("darwin_with_ls_outside_bin_takes_the_gnu_branch", BRANCH, pre="OSTYPE=darwin23",
             out="gnu\n"),
        Case("darwin_with_bin_ls_takes_the_bsd_branch", BRANCH, path="bin", pre="OSTYPE=darwin23",
             out="bsd\n", skip=no_bin_ls),
        Case("freebsd_with_bin_ls_takes_the_bsd_branch", BRANCH, path="bin", pre="OSTYPE=freebsd14.0",
             out="bsd\n", skip=no_bin_ls),
        Case("openbsd_with_bin_ls_takes_the_bsd_branch", BRANCH, path="bin", pre="OSTYPE=openbsd7.5",
             out="bsd\n", skip=no_bin_ls),
        Case("linux_with_bin_ls_takes_the_gnu_branch", BRANCH, path="bin", pre="OSTYPE=linux-gnu",
             out="gnu\n", skip=no_bin_ls),
        Case("cygwin_with_bin_ls_takes_the_gnu_branch", BRANCH, path="bin", pre="OSTYPE=cygwin",
             out="gnu\n", skip=no_bin_ls),
        # Real BSD ls: CLICOLOR_FORCE colours a directory name, only straight to pi.
        # BSD ls looks its colours up for $TERM, and pi's commands inherit one.
        Case("real_bsd_ls_colours_directories_straight_to_pi", f'ls "{D_LSDIR}"', path="bin",
             env={"TERM": "xterm-256color"}, has=ESC, skip=not_darwin),
        Case("real_bsd_ls_piped_is_plain", f'ls "{D_LSDIR}" | cat', path="bin", env={"TERM": "xterm-256color"},
             out="file.txt\nsub\n", skip=not_darwin),
        # CLICOLOR and CLICOLOR_FORCE are given to that one ls, not left in the shell.
        Case("bsd_ls_leaves_no_clicolor_in_the_shell",
             f'ls "{D_LSDIR}" >/dev/null; echo "${{CLICOLOR-unset}} ${{CLICOLOR_FORCE-unset}}"',
             path="bin", out="unset unset\n", skip=not_darwin),
    ]


D_LSDIR = "$HOME/lsdir"   # HOME is the module temp dir in the batch environment


@generate
class LsWrapperTests(WrapperCases):
    CASES = ls_cases()


# --- ruff: CLICOLOR_FORCE=1 in its environment, arguments untouched -----------

def ruff_cases():
    plain = {"CLICOLOR_FORCE": None}
    args = [("ruff", ["check", "."])]
    return [
        Case("ruff_straight_to_pi_gets_clicolor_force", "ruff check .", calls=args,
             envs={"CLICOLOR_FORCE": "1", "CLICOLOR": None}, out="out:ruff\n"),
        Case("ruff_redirected_has_no_clicolor_force", 'ruff check . > "$FAKE_LOG.out"', calls=args, envs=plain),
        Case("ruff_piped_has_no_clicolor_force", "ruff check . | cat", calls=args, envs=plain),
        Case("ruff_in_substitution_has_no_clicolor_force", 'x=$(ruff check .)', calls=args, envs=plain, out=""),
        Case("ruff_with_no_color_has_no_clicolor_force", "ruff check .", env={"NO_COLOR": "1"},
             calls=args, envs=plain),
        Case("ruff_through_command_builtin_has_no_clicolor_force", "command ruff check .", calls=args, envs=plain),
        Case("ruff_exit_status_passes_through", "FAKE_EXIT=1 ruff check .", calls=args,
             envs={"CLICOLOR_FORCE": "1"}, status=1),
        Case("ruff_leaves_no_clicolor_force_in_the_shell", 'ruff check . >/dev/null; ruff format; '
             'echo "${CLICOLOR_FORCE-unset}"', calls=[("ruff", ["check", "."]), ("ruff", ["format"])],
             out="out:ruff\nunset\n"),
        Case("ruff_absent_gets_no_function", "type -t ruff || echo none", path="without:ruff", out="none\n"),
        Case("ruff_alone_on_path_is_wrapped", "type -t ruff", path="only:ruff", out="function\n"),
    ]


@generate
class RuffWrapperTests(WrapperCases):
    CASES = ruff_cases()


# --- diff: --color=always, after asking whether this diff has it --------------

PROBE = ("diff", ["--color=always", "/dev/null", "/dev/null"])


def diff_cases():
    plain = [("diff", ["a", "b"])]
    return [
        Case("diff_straight_to_pi_probes_then_colours", "diff a b",
             calls=[PROBE, ("diff", ["--color=always", "a", "b"])], out="out:diff\n"),
        # The probe runs only when colour is wanted.
        Case("diff_redirected_neither_probes_nor_colours", 'diff a b > "$FAKE_LOG.out"', calls=plain, out=""),
        Case("diff_piped_neither_probes_nor_colours", "diff a b | cat", calls=plain, out="out:diff\n"),
        Case("diff_in_substitution_is_plain", 'x=$(diff a b); echo "$x"', calls=plain, out="out:diff\n"),
        Case("diff_with_no_color_is_plain", "diff a b", env={"NO_COLOR": "1"}, calls=plain),
        Case("diff_through_command_builtin_is_plain", "command diff a b", calls=plain),
        Case("diff_user_color_never_follows_the_forced_flag", "diff --color=never a b",
             calls=[PROBE, ("diff", ["--color=always", "--color=never", "a", "b"])]),
        Case("diff_exit_status_one_for_differences_passes_through", "FAKE_EXIT=1 diff a b",
             calls=[PROBE, ("diff", ["--color=always", "a", "b"])], status=1),
        Case("diff_without_color_support_falls_back_quietly", "diff a b", path="olddiff",
             calls=[PROBE, ("diff", ["a", "b"])], out="out:diff\n", err=""),
        Case("old_diff_exit_status_passes_through", "FAKE_EXIT=1 diff -u a b", path="olddiff",
             calls=[PROBE, ("diff", ["-u", "a", "b"])], status=1),
        Case("old_diff_piped_is_not_probed", "diff a b | cat", path="olddiff", calls=plain),
        Case("diff_absent_gets_no_function", "type -t diff || echo none", path="without:diff", out="none\n"),
        Case("diff_alone_on_path_is_wrapped", "type -t diff", path="only:diff", out="function\n"),
        # A directory diff prints its command line: the forced flag is taken back out of it.
        Case("diff_recursive_header_is_the_users_command_line", "FAKE_HEADER=1 diff -r a b", path="sed",
             calls=[PROBE, ("diff", ["--color=always", "-r", "a", "b"])], out="diff -r a b\nout:diff\n", skip=no_sed),
        Case("diff_recursive_cluster_header", "FAKE_HEADER=1 diff -ruN a b", path="sed",
             calls=[PROBE, ("diff", ["--color=always", "-ruN", "a", "b"])], out="diff -ruN a b\nout:diff\n", skip=no_sed),
        Case("diff_recursive_abbreviated_long_option", "FAKE_HEADER=1 diff --recur a b", path="sed",
             out="diff --recur a b\nout:diff\n", skip=no_sed),
        Case("diff_directory_operands_header", "FAKE_HEADER=1 diff -u lsdir lsdir/sub", path="sed",
             out="diff -u lsdir lsdir/sub\nout:diff\n", skip=no_sed),
        Case("diff_recursive_exit_status_passes_through", "FAKE_EXIT=1 diff -r a b", path="sed",
             status=1, out="out:diff\n", skip=no_sed),
        # Two files: diff prints no command line, so nothing goes through sed.
        Case("diff_of_files_is_not_filtered", "FAKE_HEADER=1 diff -u a b", path="sed",
             out="diff --color=always -u a b\nout:diff\n"),
        Case("diff_recursive_without_sed_is_plain", "diff -r a b",
             calls=[PROBE, ("diff", ["-r", "a", "b"])], out="out:diff\n"),
    ]


@generate
class DiffWrapperTests(WrapperCases):
    CASES = diff_cases()


# --- python / python3: --color=yes only for `-m pytest` ------------------------

def python_cases():
    py = "python3"
    mp = ["-m", "pytest", "--color=yes"]
    return [
        Case("python3_m_pytest_gets_color_yes_after_the_module", "python3 -m pytest -q tests",
             calls=[(py, mp + ["-q", "tests"])], out="out:python3\n"),
        Case("python3_m_pytest_with_no_more_arguments", "python3 -m pytest", calls=[(py, mp)]),
        Case("python3_m_pytest_keeps_spaces_in_arguments", "python3 -m pytest -k 'a and b' \"x y\"",
             calls=[(py, mp + ["-k", "a and b", "x y"])]),
        Case("python3_m_pytest_user_color_no_follows", "python3 -m pytest --color=no",
             calls=[(py, mp + ["--color=no"])]),
        Case("python3_m_pip_is_untouched", "python3 -m pip list", calls=[(py, ["-m", "pip", "list"])]),
        Case("python3_script_mentioning_pytest_is_untouched", "python3 run.py -m pytest",
             calls=[(py, ["run.py", "-m", "pytest"])]),
        Case("python3_c_is_untouched", "python3 -c 'import sys'", calls=[(py, ["-c", "import sys"])]),
        Case("python3_one_argument_m_space_pytest_is_untouched", 'python3 "-m pytest"',
             calls=[(py, ["-m pytest"])]),
        Case("python3_mpytest_joined_is_untouched", "python3 -mpytest", calls=[(py, ["-mpytest"])]),
        # Only the first two arguments are looked at.
        Case("python3_options_before_m_pytest_are_untouched", "python3 -X dev -m pytest",
             calls=[(py, ["-X", "dev", "-m", "pytest"])]),
        Case("python3_m_alone_is_untouched", "python3 -m", calls=[(py, ["-m"])]),
        Case("python3_with_no_arguments_is_untouched", "python3 </dev/null", calls=[(py, [])]),
        Case("python3_m_pytest_redirected_is_plain", 'python3 -m pytest > "$FAKE_LOG.out"',
             calls=[(py, ["-m", "pytest"])], out=""),
        Case("python3_m_pytest_piped_is_plain", "python3 -m pytest | cat", calls=[(py, ["-m", "pytest"])]),
        Case("python3_m_pytest_in_substitution_is_plain", 'r=$(python3 -m pytest); echo "$r"',
             calls=[(py, ["-m", "pytest"])], out="out:python3\n"),
        Case("python3_m_pytest_with_no_color_is_plain", "python3 -m pytest", env={"NO_COLOR": "1"},
             calls=[(py, ["-m", "pytest"])]),
        Case("python3_m_pytest_exit_status_passes_through", "FAKE_EXIT=5 python3 -m pytest",
             calls=[(py, mp)], status=5),
        Case("python3_absent_gets_no_function", "type -t python3 || echo none; type -t python",
             path="without:python3", out="none\nfunction\n"),
        Case("python3_alone_on_path_is_wrapped", "type -t python3; type -t python || echo none",
             path="only:python3", out="function\nnone\n"),
        # Under `set -u` a one-argument call has no "$2"; the wrapper must not abort on it.
        Case("python3_one_argument_under_set_u", 'set -u; python3 run.py; echo "after $?"',
             calls=[(py, ["run.py"])], out="out:python3\nafter 0\n", err=""),   # a one-argument call has no $2
        Case("python3_m_pytest_under_set_u", "set -u; python3 -m pytest", calls=[(py, mp)]),
        Case("python_m_pytest_gets_color_yes", "python -m pytest -x",
             calls=[("python", ["-m", "pytest", "--color=yes", "-x"])], out="out:python\n"),
        Case("python_m_pip_is_untouched", "python -m pip install -e .",
             calls=[("python", ["-m", "pip", "install", "-e", "."])]),
        Case("python_m_pytest_redirected_is_plain", 'python -m pytest 2>&1 > "$FAKE_LOG.out"',
             calls=[("python", ["-m", "pytest"])], out=""),
        Case("python_m_pytest_piped_is_plain", "python -m pytest | cat",
             calls=[("python", ["-m", "pytest"])]),
        Case("python_absent_gets_no_function", "type -t python || echo none", path="without:python",
             out="none\n"),
        Case("python_alone_on_path_is_wrapped", "type -t python; type -t python3 || echo none",
             path="only:python", out="function\nnone\n"),
        Case("python_no_arguments_under_set_u", 'set -u; python </dev/null; echo "after $?"',
             calls=[("python", [])], out="out:python\nafter 0\n", err=""),
    ]


@generate
class PythonWrapperTests(WrapperCases):
    CASES = python_cases()


# --- git: colour config for display subcommands only ---------------------------

DISPLAY = [("diff", ["--stat"]), ("show", ["HEAD"]), ("log", ["-1"]), ("status", ["-s"]),
           ("branch", ["-a"]), ("grep", ["-n", "foo"]), ("blame", ["f.py"]), ("shortlog", ["-sn"]),
           ("range-diff", ["a...b"]), ("reflog", ["-5"])]
# Commands that change things or are parsed by scripts and hooks.
OTHER = [("commit", ["-m", "msg"]), ("push", ["origin", "main"]), ("pull", []), ("fetch", ["--all"]),
         ("rev-parse", ["HEAD"]), ("config", ["user.name"]), ("add", ["."]), ("rebase", ["main"]),
         ("merge", ["dev"]), ("checkout", ["-b", "x"]), ("switch", ["main"]), ("reset", ["--hard"]),
         ("stash", ["show"]), ("tag", ["v1"]), ("ls-files", []), ("cat-file", ["-p", "HEAD"]),
         ("format-patch", ["-1"]), ("apply", ["x.patch"]), ("cherry-pick", ["abc"]),
         ("for-each-ref", []), ("help", ["diff"]), ("worktree", ["list"])]

# Global options before the subcommand: (slug, argv, coloured?)
GLOBAL = [
    ("C_dir_then_diff", ["-C", "sub", "diff"], True),
    ("c_setting_then_log", ["-c", "core.pager=less", "log"], True),
    ("git_dir_equals_then_status", ["--git-dir=.git", "status"], True),
    ("git_dir_separate_then_show", ["--git-dir", ".git", "show"], True),
    ("work_tree_equals_then_diff", ["--work-tree=.", "diff"], True),
    ("work_tree_separate_then_diff", ["--work-tree", ".", "diff"], True),
    ("namespace_separate_then_log", ["--namespace", "ns", "log"], True),
    ("namespace_equals_then_log", ["--namespace=ns", "log"], True),
    ("no_pager_then_diff", ["--no-pager", "diff"], True),
    ("P_then_log", ["-P", "log"], True),
    ("paginate_then_log", ["-p", "log"], True),
    ("bare_then_log", ["--bare", "log"], True),
    ("exec_path_equals_then_diff", ["--exec-path=/x", "diff"], True),
    ("several_options_then_blame", ["-C", "a", "-c", "x=1", "--no-pager", "blame", "f"], True),
    # The user's own -c comes after the forced ones, so it wins.
    ("user_color_never_follows_forced", ["-c", "color.ui=never", "diff"], True),
    # An option's value named like a display subcommand is not the subcommand.
    ("C_dir_named_diff_then_commit", ["-C", "diff", "commit"], False),
    ("c_value_diff_then_commit", ["-c", "diff", "commit"], False),
    ("git_dir_named_log_then_push", ["--git-dir", "log", "push"], False),
    ("work_tree_named_status_then_add", ["--work-tree", "status", "add"], False),
    ("no_pager_then_commit", ["--no-pager", "commit"], False),
    ("dangling_C", ["-C"], False),
    ("version", ["--version"], False),
    ("no_arguments", [], False),
]


def git_cases():
    cases = []
    for sub, args in DISPLAY:
        cases.append(Case(f"git_{sub}_straight_to_pi_gets_colour_config",
                          "git " + shlex.join([sub, *args]),
                          calls=[("git", GITC + [sub, *args])], out="out:git\n"))
    for sub, args in OTHER:
        cases.append(Case(f"git_{sub}_never_gets_colour", "git " + shlex.join([sub, *args]),
                          calls=[("git", [sub, *args])]))
    for slug, argv, coloured in GLOBAL:
        cases.append(Case(f"git_global_{slug}", "git " + shlex.join(argv),
                          calls=[("git", (GITC if coloured else []) + argv)]))
    # git also takes `--config-env <name>=<envvar>` as two words (git 2.39 does);
    # the value is not the subcommand.
    cases.append(Case("git_global_config_env_separate_then_diff", "git --config-env core.pager=HOME diff",
                      calls=[("git", GITC + ["--config-env", "core.pager=HOME", "diff"])]))
    diff, cdiff = [("git", ["diff"])], [("git", GITC + ["diff"])]
    cases += [
        Case("git_diff_redirected_is_plain", 'git diff > "$FAKE_LOG.out"', calls=diff, out=""),
        Case("git_diff_appended_is_plain", 'git diff >> "$FAKE_LOG.out"', calls=diff, out=""),
        Case("git_diff_to_dev_null_is_plain", "git diff >/dev/null", calls=diff, out=""),
        Case("git_diff_piped_is_plain", "git diff | cat", calls=diff, out="out:git\n"),
        Case("git_diff_with_stderr_merged_then_piped_is_plain", "git diff 2>&1 | cat", calls=diff),
        Case("git_diff_in_substitution_is_plain", 'x=$(git diff); echo "[$x]"', calls=diff, out="[out:git]\n"),
        Case("git_diff_in_backticks_is_plain", 'x=`git diff`; echo "[$x]"', calls=diff, out="[out:git]\n"),
        Case("git_diff_in_process_substitution_is_plain", "cat <(git diff)", calls=diff, out="out:git\n"),
        Case("git_diff_in_redirected_group_is_plain", '{ git diff; } > "$FAKE_LOG.out"', calls=diff, out=""),
        Case("git_diff_to_stderr_pipe_is_plain", "git diff >&2", calls=diff, out="", err="out:git\n"),
        # stderr made pi's pipe too: output sent there goes straight back to pi.
        Case("git_diff_to_stderr_that_is_pis_pipe_is_coloured", "exec 2>&1; git diff >&2", calls=cdiff,
             out="out:git\n"),
        Case("git_diff_after_exec_redirect_is_plain", 'exec > "$FAKE_LOG.out"; git diff', calls=diff, out=""),
        Case("git_diff_with_no_color_is_plain", "git diff", env={"NO_COLOR": "1"}, calls=diff),
        Case("git_diff_through_command_builtin_is_plain", "command git diff", calls=diff),
        Case("git_diff_in_a_child_bash_is_plain", '"$BASH" -c "git diff"', calls=diff, out="out:git\n"),
        Case("git_diff_in_a_subshell_is_coloured", "(git diff)", calls=cdiff),
        Case("git_diff_in_background_is_coloured", "git diff & wait", calls=cdiff),
        Case("git_diff_through_eval_is_coloured", "eval 'git diff'", calls=cdiff),
        Case("git_diff_in_if_condition_is_coloured", "if git diff --quiet; then echo same; fi",
             calls=[("git", GITC + ["diff", "--quiet"])], out="out:git\nsame\n"),
        # Only stdin is piped: stdout is still pi's.
        Case("git_diff_in_loop_reading_a_pipe_is_coloured", "echo x | while read l; do git diff; done",
             calls=cdiff),
        Case("git_log_in_a_function_is_coloured", "f() { git log; }; f", calls=[("git", GITC + ["log"])]),
        Case("git_log_in_a_redirected_function_is_plain", 'f() { git log; }; f > "$FAKE_LOG.out"',
             calls=[("git", ["log"])], out=""),
        Case("each_git_call_decides_for_itself", "git diff >/dev/null; git diff; git diff | cat",
             calls=[("git", ["diff"]), ("git", GITC + ["diff"]), ("git", ["diff"])], out="out:git\nout:git\n"),
        Case("git_chain_colours_both_display_commands", "git log -1 && git status",
             calls=[("git", GITC + ["log", "-1"]), ("git", GITC + ["status"])]),
        Case("git_colour_is_given_as_c_not_exported", "git diff", calls=cdiff,
             envs={"GIT_CONFIG_PARAMETERS": None, "CLICOLOR_FORCE": None}),
        Case("git_diff_exit_status_passes_through", "FAKE_EXIT=1 git diff --exit-code",
             calls=[("git", GITC + ["diff", "--exit-code"])], status=1),
        Case("git_push_exit_status_passes_through", "FAKE_EXIT=128 git push",
             calls=[("git", ["push"])], status=128),
        Case("git_log_keeps_spaces_and_quotes", "git log --format='%h %s' -- 'a b' \"it's\"",
             calls=[("git", GITC + ["log", "--format=%h %s", "--", "a b", "it's"])]),
        Case("git_commit_keeps_newlines_and_empty_arguments", "git commit -m $'two\\nlines' -m ''",
             calls=[("git", ["commit", "-m", "two\nlines", "-m", ""])]),
        Case("git_grep_quoted_glob_is_not_expanded", "git grep '*.py'",
             calls=[("git", GITC + ["grep", "*.py"])]),
        Case("git_absent_gets_no_function", "type -t git || echo none; type -t ls", path="without:git",
             out="none\nfunction\n"),
        Case("git_alone_on_path_is_wrapped", "type -t git; type -t ls || echo none", path="only:git",
             out="function\nnone\n"),
    ]
    return cases


@generate
class GitWrapperTests(WrapperCases):
    CASES = git_cases()


# --- NO_COLOR, the prefix itself, and shell state ------------------------------

WRAPPED = ["_pi_has", "_pi_here", "diff", "fd", "git", "grep", "jq", "ls", "pytest", "python",
           "python3", "rg", "ruff", "shellcheck", "tree"]


def misc_cases():
    g = [("grep", ["x"])]
    return [
        # NO_COLOR counts only when it is not empty, as no-color.org says.
        Case("empty_no_color_still_colours", "grep x", env={"NO_COLOR": ""},
             calls=[("grep", ["--color=always", "x"])]),
        Case("no_color_0_still_turns_colour_off", "grep x", env={"NO_COLOR": "0"}, calls=g),
        Case("no_color_defines_no_functions_at_all", "compgen -A function || echo none",
             env={"NO_COLOR": "1"}, out="none\n"),
        Case("no_color_leaves_every_tool_a_file", "type -t git grep ls diff python3 ruff",
             env={"NO_COLOR": "1"}, out="file\n" * 6),
        Case("functions_defined_are_exactly_the_wrappers_and_two_helpers", "declare -F",
             out="".join(f"declare -f {f}\n" for f in WRAPPED)),
        Case("no_tools_on_path_defines_only_the_helpers", "declare -F", path="none",
             out="declare -f _pi_has\ndeclare -f _pi_here\n"),
        # NO_COLOR given to one command, after the prefix has run, still turns colour off.
        Case("no_color_on_one_command", "NO_COLOR=1 grep x", calls=g),
        Case("no_color_exported_inside_the_command", "export NO_COLOR=1; git diff", calls=[("git", ["diff"])]),
        # Without stat, pi's pipe cannot be identified, so nothing is coloured - quietly.
        Case("without_stat_nothing_is_coloured", "grep x; git diff; ls",
             path="nostat", calls=[("grep", ["x"]), ("git", ["diff"]), ("ls", [])], err=""),
        Case("prefix_with_agent_dir_unset_is_harmless", "grep x; type -t grep",
             env={"PI_CODING_AGENT_DIR": None}, calls=g, out="out:grep\nfile\n", err=""),
        Case("prefix_with_missing_agent_dir_is_harmless", "grep x; type -t grep",
             env={"PI_CODING_AGENT_DIR": "/nonexistent/elm-pi-agent"}, calls=g, out="out:grep\nfile\n", err=""),
        Case("prefix_when_colour_sh_is_a_directory_is_harmless", "grep x; type -t grep",
             env={"PI_CODING_AGENT_DIR": "__NOTADIR__"}, calls=g, out="out:grep\nfile\n", err=""),
        Case("prefix_alone_prints_nothing", ":", calls=[], out="", err=""),
        Case("prefix_does_not_run_any_wrapped_tool", "true", calls=[]),
        # Non-default shell state in the command does not upset the wrappers.
        Case("ifs_comma_keeps_arguments_whole", "IFS=,; grep 'a,b' c",
             calls=[("grep", ["--color=always", "a,b", "c"])]),
        Case("noglob_keeps_star_literal", "set -f; grep '*' *",
             calls=[("grep", ["--color=always", "*", "*"])]),
        Case("set_u_git_status_works", "set -u; git status", calls=[("git", GITC + ["status"])]),
        Case("set_u_git_without_arguments_works", "set -u; git", calls=[("git", [])]),
        Case("set_e_failing_grep_stops_the_command", 'set -e; FAKE_EXIT=1 grep x; echo unreachable',
             calls=[("grep", ["--color=always", "x"])], out="out:grep\n", status=1),
        Case("command_v_still_finds_a_wrapped_tool", "command -v rg", out="rg\n"),
        Case("command_v_finds_no_absent_tool", "command -v rg || echo none", path="without:rg", out="none\n"),
        Case("type_P_still_gives_the_real_path", 'type -P jq | cat',
             out=f"{'@BINS@'}/fake/jq\n"),
    ]


@generate
class PrefixAndStateTests(WrapperCases):
    CASES = misc_cases()

    @classmethod
    def setUpClass(cls):
        # Paths known only once the module temp dir exists.
        for c in cls.CASES:
            for k, v in c.env.items():
                if v == "__NOTADIR__":
                    c.env[k] = str(D["dir"] / "notadir")
            if c.out and "@BINS@" in c.out:
                c.out = c.out.replace("@BINS@", str(D["bins"]))
        super().setUpClass()


# --- macOS's /bin/bash 3.2 runs the same wrappers ------------------------------

def bash3_cases():
    return [
        Case("bash3_git_diff_coloured", "git diff", calls=[("git", GITC + ["diff"])]),
        Case("bash3_git_C_dir_log_coloured", "git -C sub log", calls=[("git", GITC + ["-C", "sub", "log"])]),
        Case("bash3_git_commit_plain", "git commit -m 'a b'", calls=[("git", ["commit", "-m", "a b"])]),
        Case("bash3_grep_piped_plain", "grep x | cat", calls=[("grep", ["x"])]),
        Case("bash3_grep_in_substitution_plain", "y=$(grep x)", calls=[("grep", ["x"])], out=""),
        Case("bash3_python3_m_pytest_coloured", "python3 -m pytest -q",
             calls=[("python3", ["-m", "pytest", "--color=yes", "-q"])]),
        Case("bash3_diff_probe_then_colour", "diff a b",
             calls=[PROBE, ("diff", ["--color=always", "a", "b"])]),
        Case("bash3_ls_set_u_no_arguments", "set -u; ls", calls=[("ls", ["--color=always"])]),
    ]


@generate
class Bash3Tests(WrapperCases):
    CASES = bash3_cases()
    BASH = "/bin/bash"

    @classmethod
    def setUpClass(cls):
        if not Path(cls.BASH).exists():
            raise unittest.SkipTest("no /bin/bash")
        major = subprocess.run([cls.BASH, "-c", "echo ${BASH_VERSINFO[0]}"], capture_output=True,
                               text=True).stdout.strip()
        if major != "3":
            raise unittest.SkipTest(f"/bin/bash is bash {major}, not the old macOS bash")
        super().setUpClass()


# --- Other shells source the file and get nothing ------------------------------

class OtherShellTests(unittest.TestCase):
    """zsh and dash return at the first line: no functions, the real tools run plain."""

    @classmethod
    def setUpClass(cls):
        cls.runs = {}
        script = {
            "zsh": f"{PREFIX}\nwhence -w git grep ls python3\ngrep x",
            "dash": f"{PREFIX}\ntype git grep | sed 's|/.*/||'\ngrep x",
        }
        for shell, body in script.items():
            exe = shutil.which(shell)
            if not exe:
                continue
            env = environ()
            env.update(PATH=f"{D['bins']}/fake:{D['bins']}/min:/usr/bin:/bin",
                       FAKE_LOG=str(D["dir"] / f"{shell}.log"))
            run = subprocess.run([exe, "-c", body], capture_output=True, text=True, env=env, cwd=D["dir"])
            log = D["dir"] / f"{shell}.log"
            cls.runs[shell] = (run, parse_log(log.read_text()) if log.exists() else [])

    def get(self, shell):
        if shell not in self.runs:
            raise unittest.SkipTest(f"{shell} is not installed")
        return self.runs[shell]

    def test_zsh_defines_no_wrappers(self):
        run, _ = self.get("zsh")
        self.assertEqual("git: command\ngrep: command\nls: command\npython3: command\nout:grep\n", run.stdout)
        self.assertEqual("", run.stderr)

    def test_zsh_runs_the_tool_with_its_own_arguments(self):
        _, calls = self.get("zsh")
        self.assertEqual([("grep", ["x"])], [(n, a) for n, a, _ in calls])

    def test_dash_defines_no_wrappers(self):
        run, _ = self.get("dash")
        self.assertEqual("git is git\ngrep is grep\nout:grep\n", run.stdout)
        self.assertEqual("", run.stderr)

    def test_dash_runs_the_tool_with_its_own_arguments(self):
        _, calls = self.get("dash")
        self.assertEqual([("grep", ["x"])], [(n, a) for n, a, _ in calls])


if __name__ == "__main__":
    unittest.main()
