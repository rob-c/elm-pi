"""Real tools' colour, end to end: printed straight to pi, read plain by the model, drawn in colour.

templates/shell/colour.sh makes git, ls, grep, rg, fd, jq, diff, ruff,
shellcheck and pytest colour what they print when stdout is the pipe pi reads;
templates/extensions/command-output.ts then hands the model plain text and the
display the colour. Each case here runs a real command on a real fixture (git
repositories with history, renames, binaries and a conflict; a directory of
links, executables and dotfiles; text to search; JSON; Python and shell with
lint findings; pytest suites that pass and fail) twice in one bash process:
once as pi's bash tool runs it - `<shellCommandPrefix>\\n<command>`, stdout a
pipe - and once with NO_COLOR=1, which turns every wrapper off.

Each output is then turned into the result pi's bash tool would return (its own
OutputAccumulator, so long outputs are truncated and saved as pi saves them),
passed through the extension's tool_result handler and drawn by its renderer,
all in one node process. One test method per case and invariant proves:

- the model's copy has no escape codes or `\\r` and is exactly what the
  NO_COLOR run gave the model: taking colour out never changes text;
- the colour reaches the display (details.colour, and the note to the model)
  exactly when the tool coloured, and its text is the model's text;
- every drawn panel row keeps the panel's structure (terminal background,
  margin, the box tint, the full width), and shows the plain run's lines;
- wrapped into a narrow panel, no character is lost or invented;
- a long output's collapsed view is its plain head and tail;
- a truncated output's saved file becomes exactly what the plain run printed,
  the model's tail ends that output, and the view names the file.

Known bugs these cases found are expected failures, each naming the bug.

The tests skip when node, the pi packages or a tool are missing; pytest cases
skip when pytest is not installed.
"""

import base64
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = json.loads((ROOT / "templates/settings.json").read_text())
PREFIX = SETTINGS["shellCommandPrefix"]
SOURCE = ROOT / "templates/extensions/command-output.ts"
PACKAGES = ROOT / "node_modules/@earendil-works"
ACCUMULATOR = PACKAGES / "pi-coding-agent/dist/core/tools/output-accumulator.js"
TRUNCATE = PACKAGES / "pi-coding-agent/dist/core/tools/truncate.js"
COLOUR_NOTE = re.search(r'COLOUR_NOTE = "([^"]+)"', SOURCE.read_text()).group(1)
ESC = "\x1b"
SGR = re.compile(r"\x1b\[[0-9;:]*m")
# The theme stub's tags, by name, so text such as pytest's `<module>` is left alone.
TAGS = re.compile(r"<(?:error|warning|success|toolDiffAdded|toolDiffRemoved|accent|muted|toolOutput)>|</>")
# The stub's box tints: real escape codes, so they take no width.
BG = {"ok": "\x1b[48;5;22m", "error": "\x1b[48;5;52m"}
WIDE, NARROW = 400, 40      # panel widths: no fixture line wraps at the first
# A collapsed view shows this many lines from each end.
HEAD, TAIL = 4, 12
# A timed run prints how long it took; the two runs differ only there.
TIMING = re.compile(rb" in \d+\.\d\ds")
# What a terminal draws nothing for.
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1a\x1c-\x1f\x7f]")

# The bundled tools; git, grep, diff and ls are the system's own.
AGENT_TOOLS = ["rg", "fd", "jq", "ruff", "shellcheck"]
SYSTEM_TOOLS = ["git", "grep", "diff", "ls"]

D = {}        # module state: work dir, PATH, results


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


# ------------------------------------------------------------------ fixtures

def git(cwd, *args, env=None):
    subprocess.run(["git", "-c", "user.name=Ada Byron", "-c", "user.email=ada@example.org",
                    "-c", "init.defaultBranch=main", "-c", "commit.gpgsign=false", *args],
                   cwd=cwd, check=True, capture_output=True, env=env)


def commit(cwd, message, date, env):
    stamp = f"{date} +0000"
    git(cwd, "commit", "-qm", message, env={**env, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp})


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text)
    return path


FIT = """import numpy as np


def slope(x, y):
    return np.polyfit(x, y, 1)[0]


SLOPE = 2.4
"""


def build_repo(d, env):
    """History on main and a feature branch, a rename, a binary, a tag, and work in progress."""
    repo = d / "repo"
    repo.mkdir()
    git(repo, "init", "-q", env=env)
    write(repo / "fit.py", FIT)
    write(repo / "README.md", "# Fit\n\nFits a straight line.\n")
    write(repo / "notes.txt", "first note\nsecond note\nthird note\n")
    write(repo / "data.bin", bytes(range(256)))
    git(repo, "add", ".", env=env)
    commit(repo, "Fit a straight line", "2024-01-02T10:00:00", env)
    write(repo / "fit.py", FIT.replace("2.4", "2.5") + "\n\ndef intercept(x, y):\n    return np.polyfit(x, y, 1)[1]\n")
    (repo / "docs").mkdir()
    git(repo, "mv", "notes.txt", "docs/notes.txt", env=env)
    write(repo / "docs/notes.txt", "first note\nsecond note\nthird note, revised\n")
    write(repo / "CHANGES.md", "- intercept\n")
    git(repo, "add", ".", env=env)
    commit(repo, "Add the intercept and move the notes", "2024-01-03T11:30:00", env)
    git(repo, "tag", "v1.0", env=env)
    git(repo, "checkout", "-qb", "feature", env=env)
    write(repo / "feature.py", "def residuals(x, y):\n    return y - x\n")
    git(repo, "add", ".", env=env)
    commit(repo, "Add residuals", "2024-01-04T09:15:00", env)
    git(repo, "checkout", "-q", "main", env=env)
    write(repo / "README.md", "# Fit\n\nFits a straight line to data.\n")
    git(repo, "add", ".", env=env)
    commit(repo, "Say what the fit is for", "2024-01-05T16:45:00", env)
    # Work in progress: unstaged, staged, untracked, a binary change, a trailing space.
    write(repo / "fit.py", (repo / "fit.py").read_text().replace("2.5", "2.6") + "WEIGHTS = None   \n")
    write(repo / "CHANGES.md", "- intercept\n- weights\n")
    git(repo, "add", "CHANGES.md", env=env)
    write(repo / "scratch.txt", "try a weighted fit\n")
    write(repo / "data.bin", bytes(reversed(range(256))))


def build_quirks(d, env):
    """Files whose diffs carry a tab, a CR line ending, and a function moved within the file."""
    repo = d / "quirks"
    repo.mkdir()
    git(repo, "init", "-q", env=env)
    write(repo / "Makefile", "all:\n\tcc -o fit fit.c\n")
    write(repo / "crlf.txt", b"alpha\r\nbeta\r\n")
    write(repo / "lib.py", "def a():\n    return 1\n\n\ndef b():\n    return 2\n\n\ndef c():\n    return 3\n")
    git(repo, "add", ".", env=env)
    commit(repo, "Start", "2024-02-01T08:00:00", env)
    write(repo / "Makefile", "all:\n\tcc -O2 -o fit fit.c\n")
    write(repo / "crlf.txt", b"alpha\r\nBETA\r\n")
    write(repo / "lib.py", "def c():\n    return 3\n\n\ndef b():\n    return 2\n\n\ndef a():\n    return 1\n")


def build_merge(d, env):
    """A repository stopped in a merge conflict."""
    repo = d / "merge"
    repo.mkdir()
    git(repo, "init", "-q", env=env)
    write(repo / "fit.py", "SLOPE = 2.4\nINTERCEPT = 0.1\n")
    git(repo, "add", ".", env=env)
    commit(repo, "Base", "2024-03-01T08:00:00", env)
    git(repo, "checkout", "-qb", "other", env=env)
    write(repo / "fit.py", "SLOPE = 2.7\nINTERCEPT = 0.1\n")
    git(repo, "commit", "-qam", "Other slope", env={**env, "GIT_AUTHOR_DATE": "2024-03-02T08:00:00 +0000",
                                                   "GIT_COMMITTER_DATE": "2024-03-02T08:00:00 +0000"})
    git(repo, "checkout", "-q", "main", env=env)
    write(repo / "fit.py", "SLOPE = 2.5\nINTERCEPT = 0.1\n")
    git(repo, "commit", "-qam", "Main slope", env={**env, "GIT_AUTHOR_DATE": "2024-03-03T08:00:00 +0000",
                                                  "GIT_COMMITTER_DATE": "2024-03-03T08:00:00 +0000"})
    run = subprocess.run(["git", "-c", "user.name=Ada Byron", "-c", "user.email=ada@example.org", "merge", "-q", "other"],
                         cwd=repo, capture_output=True, env=env, check=False)
    assert run.returncode != 0, "the fixture merge was meant to conflict"


def build_tree(d):
    """What ls and fd colour by type: links, executables, dotfiles, a fifo, a sticky directory."""
    tree = d / "tree"
    write(tree / "README", "read me\n")
    write(tree / "run.sh", "#!/bin/sh\necho run\n").chmod(0o755)
    write(tree / ".hidden", "secret-ish\n")
    write(tree / ".config/settings.toml", "x = 1\n")
    write(tree / "src/a.py", "A = 1\n")
    write(tree / "src/b.py", "B = 2\n")
    write(tree / "src/deep/c.py", "C = 3\n")
    write(tree / "with space.txt", "spaced\n")
    write(tree / "ünïcode.txt", "accents\n")
    write(tree / "日本.txt", "wide\n")
    write(tree / "empty.log", "")
    write(tree / "archive.tar.gz", b"\x1f\x8b\x08\x00")
    (tree / "link").symlink_to("README")
    (tree / "broken").symlink_to("nowhere")
    (tree / "srclink").symlink_to("src")
    (tree / "sticky").mkdir()
    (tree / "sticky").chmod(0o1777)
    os.mkfifo(tree / "pipe")
    # Fixed times, so long listings read the same in both runs and sort the same by time.
    for i, path in enumerate(sorted(tree.rglob("*"), key=str)):
        os.utime(path, (1700000000 + i * 3600, 1700000000 + i * 3600), follow_symlinks=False)


LOG = """2024-05-01 10:00:01 INFO starting fit of run 42
2024-05-01 10:00:02 WARNING slope prior is wide
2024-05-01 10:00:03 ERROR could not read calib.dat
2024-05-01 10:00:04 INFO retrying with defaults
2024-05-01 10:00:05 error: retry failed, Error code 7
2024-05-01 10:00:06 INFO fit converged: slope=2.48 intercept=0.11
2024-05-01 10:00:07 DEBUG slope slope slope
2024-05-01 10:00:08 INFO done
"""


def build_text(d):
    """Text for grep and rg: a log, Python sources, CSV, a binary with a match, an ignored file."""
    text = d / "text"
    write(text / "log.txt", LOG)
    write(text / "src/fit.py", FIT)
    write(text / "src/plot.py", "import matplotlib.pyplot as plt\n\n\ndef plot(slope):\n    plt.plot([0, 1], [0, slope])\n")
    write(text / "data.csv", "x,y\n0,0.1\n1,2.6\n2,5.0\n")
    write(text / "blob.bin", b"\x00\x01slope\x00\x02")
    write(text / "unicode.txt", "café slope — résumé\n日本 slope\n")
    write(text / ".gitignore", "ignored.txt\n")
    write(text / "ignored.txt", "slope hidden by .gitignore\n")
    # rg reads .gitignore only inside a repository.
    (text / ".git").mkdir()


DATA = {
    "name": "run 42",
    "fit": {"slope": 2.48, "intercept": 0.11, "converged": True, "warnings": None},
    "points": [{"x": 0, "y": 0.1}, {"x": 1, "y": 2.6}, {"x": 2, "y": 5.0}],
    "tags": ["linear", "calibrated"],
    "notes": "line one\nline \"two\"",
    "empty": {"list": [], "map": {}},
    "unit": "°C 日本",
}


def build_json(d):
    j = d / "json"
    write(j / "data.json", json.dumps(DATA))
    write(j / "bad.json", '{"slope": 2.48,, }\n')
    write(j / "lines.json", "\n".join(json.dumps({"id": i, "ok": i % 2 == 0}) for i in range(4)) + "\n")


BAD_PY = """import os
import sys
from math import *


def check(value):
    unused = 3
    if value == None:
        return sys.argv
    return pi
"""
BAD_SH = """#!/bin/bash
name=unused
cd /some/dir
echo $1
for f in $(ls *.txt); do
  echo "$f"
done
"""


def build_lint(d):
    lint = d / "lint"
    write(lint / "bad.py", BAD_PY)
    write(lint / "ok.py", "def double(x):\n    return 2 * x\n")
    write(lint / "broken.py", "def f(:\n    return 1\n")
    write(lint / "messy.py", "x=[1,2 ,3]\ndef f( a ):\n  return a\n")
    write(lint / "bad.sh", BAD_SH)
    write(lint / "ok.sh", '#!/bin/sh\necho "fine"\n')


PASSING = """def test_slope():
    assert round(2.48, 1) == 2.5


def test_intercept():
    assert 0.11 > 0


def test_points():
    assert len([1, 2, 3]) == 3
"""
FAILING = """import pytest


def test_passes():
    assert True


def test_slope():
    assert round(2.48, 2) == 2.5


def test_dict():
    assert {"slope": 2.48, "n": 3} == {"slope": 2.5, "n": 3}


def test_raises():
    raise ValueError("x and y must have the same length")


@pytest.mark.skip(reason="needs calibration data")
def test_skipped():
    pass


@pytest.mark.xfail(reason="known drift")
def test_drift():
    assert 1 == 2
"""


def build_suites(d):
    write(d / "suites/passing/test_ok.py", PASSING)
    write(d / "suites/failing/test_bad.py", FAILING)


def build_cmp(d):
    """Pairs of files and directories for diff."""
    c = d / "cmp"
    write(c / "old.txt", "alpha\nbeta\ngamma\ndelta\nepsilon\n")
    write(c / "new.txt", "alpha\nBETA\ngamma\nepsilon\nzeta\n")
    write(c / "same.txt", "alpha\nbeta\ngamma\ndelta\nepsilon\n")
    write(c / "a/one.txt", "one\n")
    write(c / "a/two.txt", "two\n")
    write(c / "a/only-a.txt", "a\n")
    write(c / "b/one.txt", "ONE\n")
    write(c / "b/two.txt", "two\n")
    write(c / "b/only-b.txt", "b\n")


def build_big(d, env):
    """Outputs long enough that pi truncates them and saves the whole output to a file."""
    big = d / "big"
    write(big / "lines.txt", "".join(f"line {i}: slope {i * 0.01:.2f} fit ok\n" for i in range(2600)))
    write(big / "old.txt", "".join(f"value {i}\n" for i in range(2400)))
    write(big / "new.txt", "".join(f"value {i * 2 if i % 3 == 0 else i}\n" for i in range(2400)))
    write(big / "items.json", json.dumps([{"id": i, "slope": i / 7, "tags": ["a", "b"]} for i in range(1500)]))
    # Directories, so ls colours every name.
    (big / "many").mkdir()
    for i in range(2100):
        os.mkdir(big / f"many/run{i:04d}")
    repo = big / "repo"
    repo.mkdir()
    git(repo, "init", "-q", env=env)
    write(repo / "table.txt", "".join(f"row {i} = {i * i}\n" for i in range(2300)))
    git(repo, "add", ".", env=env)
    commit(repo, "Add the table", "2024-04-01T12:00:00", env)


# ------------------------------------------------------------------ cases

class Case:
    """One command, run in `where` under the fixture dir.

    coloured: whether the display should get the tool's colour.
    needs: tools that must exist. long: more lines than a collapsed view shows.
    unordered: the tool may print its lines in any order. bugs: {invariant: one line naming a known bug}.
    """

    def __init__(self, slug, cmd, where, coloured=True, needs=(), long=False, unordered=False, bugs=None):
        self.slug, self.cmd, self.where, self.coloured = slug, cmd, where, coloured
        self.needs, self.long, self.unordered, self.bugs = tuple(needs), long, unordered, bugs or {}



CASES = []


def add(slug, cmd, where, **kw):
    CASES.append(Case(slug, cmd, where, **kw))


# git: what it shows, on a repository with history and work in progress.
G = ("git",)
add("git_status", "git status", "repo", needs=G)
add("git_status_short", "git status --short", "repo", needs=G)
add("git_diff_work_tree", "git diff", "repo", needs=G, long=True)
add("git_diff_stat", "git diff --stat", "repo", needs=G)
add("git_diff_name_status_range", "git diff --name-status HEAD~2 HEAD", "repo", coloured=False, needs=G)
add("git_diff_rename_detected", "git diff -M HEAD~2 HEAD~1", "repo", needs=G, long=True)
add("git_diff_binary_file", "git diff -- data.bin", "repo", needs=G)
add("git_diff_binary_patch", "git diff --binary -- data.bin", "repo", needs=G, long=True)
add("git_diff_color_words", "git diff --color-words -- fit.py", "repo", needs=G)
add("git_diff_trailing_whitespace", "git diff -- fit.py", "repo", needs=G)
add("git_diff_moved_lines", "git diff --color-moved -- lib.py", "quirks", needs=G, long=True)
add("git_diff_tab_in_makefile", "git diff -- Makefile", "quirks", needs=G)
add("git_diff_crlf_line", "git diff -- crlf.txt", "quirks", needs=G)
add("git_diff_no_index", "git diff --no-index ../cmp/old.txt ../cmp/new.txt", "repo", needs=G)
add("git_diff_check", "git diff --check", "repo", needs=G)
add("git_diff_merge_conflict", "git diff", "merge", needs=G)
add("git_status_merge_conflict", "git status", "merge", needs=G)
add("git_log", "git log", "repo", needs=G)
add("git_log_graph_all", "git log --graph --oneline --all", "repo", needs=G)
add("git_log_patch", "git log -p -2", "repo", needs=G, long=True)
add("git_log_stat", "git log --stat -2", "repo", needs=G, long=True)
add("git_log_follow_rename", "git log --follow --name-status --oneline -- docs/notes.txt", "repo", needs=G)
add("git_log_format_colours", "git log --format='%C(yellow)%h%C(reset) %C(bold)%s%C(reset) %an'", "repo", needs=G)
add("git_show_head", "git show", "repo", needs=G)
add("git_show_tag_stat", "git show --stat v1.0", "repo", needs=G)
add("git_show_file_at_revision", "git show HEAD~1:fit.py", "repo", coloured=False, needs=G)
add("git_branch_verbose_all", "git branch -a -vv", "repo", needs=G)
add("git_grep", "git grep -n slope", "repo", needs=G)
# Committed lines only: a line not yet committed is stamped with the time blame ran.
add("git_blame", "git blame HEAD -- fit.py", "repo", coloured=False, needs=G)
add("git_reflog", "git reflog -4", "repo", needs=G)
add("git_range_diff", "git range-diff main~1..main main~1..feature", "repo", needs=G)
add("git_with_dash_c_dir", "git -C ../repo log --oneline -2", "merge", needs=G)
add("git_rev_parse_not_wrapped", "git rev-parse --abbrev-ref HEAD", "repo", coloured=False, needs=G)
add("git_bad_revision", "git log no-such-rev", "repo", coloured=False, needs=G)

# ls: types, flags and errors.
add("ls_plain", "ls", "tree")
add("ls_long", "ls -l", "tree")
add("ls_long_all", "ls -la", "tree", long=True)
add("ls_recursive", "ls -R", "tree", long=True)
add("ls_directories_only", "ls -d */", "tree")
add("ls_links", "ls -l link broken srclink", "tree")
add("ls_sticky_dir", "ls -ld sticky", "tree")
add("ls_missing_file", "ls no-such-file", "tree", coloured=False)
add("ls_plain_file", "ls -l README", "tree", coloured=False)

# grep: matches, context, counts, a binary match, no match.
add("grep_numbered", "grep -n slope log.txt", "text")
add("grep_recursive", "grep -rn slope src", "text")
add("grep_ignore_case", "grep -in error log.txt", "text")
add("grep_count", "grep -c INFO log.txt", "text", coloured=False)
add("grep_files_with_matches", "grep -rl slope src", "text", coloured=False)
add("grep_only_matching", "grep -on 'slope=[0-9.]*' log.txt", "text")
add("grep_invert", "grep -v INFO log.txt", "text", coloured=False)
add("grep_context", "grep -C1 ERROR log.txt", "text")
add("grep_no_match", "grep no-such-word log.txt", "text", coloured=False)
add("grep_binary_match", "grep slope blob.bin", "text", coloured=False)
add("grep_unicode", "grep -n slope unicode.txt", "text")
add("grep_include", "grep -rn --include='*.py' def .", "text")

# rg: sorted, so a multi-threaded search prints the same order in both runs.
R = ("rg",)
add("rg_default", "rg --sort path slope", "text", needs=R)
add("rg_heading", "rg --heading -n --sort path slope", "text", needs=R)
add("rg_files_with_matches", "rg -l --sort path slope", "text", needs=R)
add("rg_context", "rg -C1 ERROR log.txt", "text", needs=R)
add("rg_vimgrep", "rg --vimgrep --sort path slope src", "text", needs=R)
add("rg_only_matching", "rg -o 'slope=[0-9.]+' log.txt", "text", needs=R)
add("rg_files", "rg --files --sort path", "text", needs=R)
add("rg_no_match", "rg no-such-word", "text", needs=R, coloured=False)
add("rg_replace", "rg -n 'ERROR (.*)' -r 'E: $1' log.txt", "text", needs=R)
add("rg_multiline", "rg -U -n 'def plot\\(slope\\):\\n.*plt' src", "text", needs=R)
add("rg_hidden_ignored", "rg -uu --sort path hidden", "text", needs=R)
add("rg_pretty", "rg -p --sort path converged", "text", needs=R)
add("rg_binary_match", "rg -a slope blob.bin", "text", needs=R)

# fd: one thread keeps its walk in one order; the order is not promised, so compared as a set.
F = ("fd",)
add("fd_everything", "fd -j1", "tree", needs=F, unordered=True)
add("fd_hidden", "fd -j1 -H", "tree", needs=F, unordered=True)
add("fd_symlinks", "fd -j1 -t l", "tree", needs=F, unordered=True)
add("fd_executables", "fd -j1 -t x", "tree", needs=F, unordered=True)
add("fd_no_match", "fd -j1 no-such-file", "tree", needs=F, coloured=False)
add("fd_null_separated", "fd -j1 -0 -e py", "tree", needs=F)

# jq: pretty, compact, raw, sorted, errors.
J = ("jq",)
add("jq_pretty", "jq . data.json", "json", needs=J, long=True)
add("jq_compact", "jq -c . data.json", "json", needs=J)
add("jq_raw_string", "jq -r .notes data.json", "json", needs=J, coloured=False)
add("jq_field", "jq .fit data.json", "json", needs=J)
add("jq_sort_keys", "jq -S .fit data.json", "json", needs=J)
add("jq_tab_indent", "jq --tab .fit data.json", "json", needs=J)
add("jq_indent_one", "jq --indent 1 .points data.json", "json", needs=J)
add("jq_parse_error", "jq . bad.json", "json", needs=J, coloured=False)
add("jq_exit_status_null", "jq -e .missing data.json", "json", needs=J)
add("jq_stream_of_lines", "jq -c 'select(.ok)' lines.json", "json", needs=J)
add("jq_unicode", "jq .unit data.json", "json", needs=J)
add("jq_ascii_output", "jq -a .unit data.json", "json", needs=J)

# diff: the formats a model reads. Its file headers carry a tab before the date.
add("diff_normal", "diff old.txt new.txt", "cmp")
add("diff_unified", "diff -u old.txt new.txt", "cmp")
add("diff_context", "diff -c old.txt new.txt", "cmp")
add("diff_recursive", "diff -r a b", "cmp")
add("diff_recursive_new_file", "diff -ruN a b", "cmp")
add("diff_brief", "diff -q a b", "cmp", coloured=False)
add("diff_identical", "diff -u old.txt same.txt", "cmp", coloured=False)
add("diff_missing_file", "diff -u old.txt no-such.txt", "cmp", coloured=False)
add("diff_labels", "diff -u --label before --label after old.txt new.txt", "cmp")

# ruff and shellcheck: findings, code frames, a clean file, a syntax error.
U, S = ("ruff",), ("shellcheck",)
add("ruff_full", "ruff check --no-cache bad.py", "lint", needs=U, long=True)
add("ruff_concise", "ruff check --no-cache --output-format=concise bad.py", "lint", needs=U)
add("ruff_statistics", "ruff check --no-cache --statistics bad.py", "lint", needs=U)
add("ruff_clean", "ruff check --no-cache ok.py", "lint", needs=U)
add("ruff_syntax_error", "ruff check --no-cache broken.py", "lint", needs=U)
add("ruff_one_rule", "ruff check --no-cache --select E711 bad.py", "lint", needs=U, long=True)
add("ruff_format_diff", "ruff format --no-cache --diff messy.py", "lint", needs=U)
add("ruff_format_check", "ruff format --no-cache --check messy.py ok.py", "lint", needs=U)
add("shellcheck_tty", "shellcheck bad.sh", "lint", needs=S, long=True)
add("shellcheck_gcc", "shellcheck -f gcc bad.sh", "lint", needs=S, coloured=False)
add("shellcheck_diff", "shellcheck -f diff bad.sh", "lint", needs=S)
add("shellcheck_warnings_up", "shellcheck -S warning bad.sh", "lint", needs=S, long=True)
add("shellcheck_clean", "shellcheck ok.sh", "lint", needs=S, coloured=False)

# pytest: passing, failing, verbose, the report forms; no cache, so both runs start alike.
P = ("pytest",)
PT = "pytest -p no:cacheprovider"
add("pytest_quiet_pass", f"{PT} -q passing", "suites", needs=P)
add("pytest_quiet_fail", f"{PT} -q failing", "suites", needs=P, long=True)
add("pytest_verbose_fail", f"{PT} -v failing", "suites", needs=P, long=True)
add("pytest_report_all", f"{PT} -q -rA failing", "suites", needs=P, long=True)
add("pytest_short_tracebacks", f"{PT} -q --tb=short failing", "suites", needs=P, long=True)
add("pytest_line_tracebacks", f"{PT} -q --tb=line failing", "suites", needs=P, long=True)
add("pytest_no_tests_selected", f"{PT} -q -k nothing passing", "suites", needs=P)
add("pytest_as_module", "python3 -m pytest -p no:cacheprovider -q passing", "suites", needs=("pytest", "python3"))

# Not straight back to pi, or colour turned off: the output stays plain.
add("pipe_git_diff", "git diff | cat", "repo", coloured=False, needs=G)
add("file_then_cat", "git log --oneline > ../out/log.txt; cat ../out/log.txt", "repo", coloured=False, needs=G)
add("substitution_echo", 'x=$(ls src); echo "$x"', "tree", coloured=False)
add("no_color_inline", "NO_COLOR=1 git status --short", "repo", coloured=False, needs=G)
add("command_bypasses", "command grep -n slope log.txt", "text", coloured=False)
add("git_no_color_flag", "git diff --no-color", "repo", coloured=False, needs=G)
add("rg_color_never", "rg --color=never --sort path slope", "text", coloured=False, needs=R)
add("jq_monochrome", "jq -M .fit data.json", "json", coloured=False, needs=J)
add("child_shell", "bash -c 'git log --oneline -2'", "repo", coloured=False, needs=G)
add("ruff_piped", "ruff check --no-cache --output-format=concise bad.py | cat", "lint", coloured=False, needs=U)

# Several tools in one command, still printing straight to pi.
add("combo_status_and_ls", "git status -s && ls ../tree/src", "repo", needs=G)
add("combo_loop", "for f in log.txt src/fit.py; do grep -Hn slope \"$f\"; done", "text")
add("combo_subshell", "(cd src && ls -l)", "tree")
add("combo_mixed_plain_and_colour", "echo '== search =='; rg -n --sort path converged; echo '== done =='",
    "text", needs=R)

# Long enough that pi truncates the output and saves it whole.
LONG_CASES = []


def add_long(slug, cmd, where, needs=(), bugs=None):
    LONG_CASES.append(Case(slug, cmd, where, needs=needs, bugs=bugs))


# Cut by lines in both runs.
add_long("git_diff_no_index_big", "git diff --no-index ../old.txt ../new.txt", "big/repo", needs=G)
add_long("ls_many_dirs", "ls many", "big")
add_long("diff_big_unified", "diff -u --label old --label new old.txt new.txt", "big")
# Their colour codes take the coloured run past 50KB first.
add_long("git_show_big_commit", "git show", "big/repo", needs=G)
add_long("rg_many_lines", "rg -n slope lines.txt", "big", needs=R)
add_long("grep_many_lines", "grep -n fit lines.txt", "big")
add_long("jq_big_array", "jq . items.json", "big", needs=J)
# One line longer than 50KB: the model is shown its end.
add_long("jq_one_huge_line", "jq -c . items.json", "big", needs=J)


# ------------------------------------------------------------------ running

def missing(case):
    gone = [t for t in case.needs if t not in D["have"]]
    return f"needs {', '.join(gone)}" if gone else None


def run_commands(cases):
    """Every case twice - coloured and NO_COLOR=1 - in one bash process; stdout is this pipe."""
    parts = []
    for i, c in enumerate(cases):
        if missing(c):
            continue
        where = shlex.quote(str(D["dir"] / c.where))
        for mode in ("colour", "plain"):
            off = "export NO_COLOR=1\n" if mode == "plain" else ""
            parts.append(f"printf '\\n@@E2E{i}{mode}<@@\\n'\n(\ncd {where} || exit 99\n{off}{PREFIX}\n{c.cmd}\n) 2>&1\n"
                         f"printf '\\n@@E2E{i}{mode}>%d@@\\n' $?\n")
    env = {"HOME": str(D["home"]), "PATH": D["path"], "LANG": "en_US.UTF-8", "LC_ALL": "en_US.UTF-8",
           "TERM": "xterm-256color", "COLUMNS": "300", "PI_CODING_AGENT_DIR": str(D["agent"]),
           "GIT_CONFIG_NOSYSTEM": "1", "PYTHONDONTWRITEBYTECODE": "1", "TZ": "UTC"}
    # pi's bash tool gives a command no stdin; rg and grep would read an inherited one.
    proc = subprocess.run(["bash", "-c", "".join(parts)], stdin=subprocess.DEVNULL, capture_output=True,
                          env=env, timeout=300, check=False)
    runs = {}
    for i, c in enumerate(cases):
        if missing(c):
            continue
        got = {}
        for mode in ("colour", "plain"):
            m = re.search(rb"\n@@E2E%d%s<@@\n(.*?)\n@@E2E%d%s>(\d+)@@\n" % (i, mode.encode(), i, mode.encode()),
                          proc.stdout, re.DOTALL)
            assert m, f"case {c.slug} ({mode}) did not finish: {proc.stderr[-500:]!r}"
            got[mode] = (TIMING.sub(b" in 0.00s", m.group(1)), int(m.group(2)))
        runs[c.slug] = got
    return runs


# Builds each run's result as pi's bash tool does (dist/core/tools/bash.js), with
# its own OutputAccumulator, passes it through the extension's tool_result
# handler, and draws it with the extension's renderer.
RUNNER = r"""
import { readFileSync, existsSync } from "node:fs";
const [source, accumulator, truncate] = process.argv.slice(1);
const cases = JSON.parse(readFileSync(0, "utf8"));
const mod = await import(source);
const { OutputAccumulator } = await import(accumulator);
const { DEFAULT_MAX_BYTES, formatSize } = await import(truncate);
const { initTheme } = await import("@earendil-works/pi-coding-agent");
const { visibleWidth } = await import("@earendil-works/pi-tui");
initTheme("dark");
const BG = { toolSuccessBg: "\x1b[48;5;22m", toolErrorBg: "\x1b[48;5;52m" };
const theme = { fg: (c, s) => `<${c}>${s}</>`, bold: (s) => s, getBgAnsi: (c) => BG[c] };

let resolver;
const handlers = {};
mod.default({ registerToolRenderer: (f) => { resolver = f; }, on: (event, h) => { handlers[event] = h; } });
const bash = resolver("bash", () => ({ renderCall() {}, renderResult() { return "live"; } }));

async function piResult(bytes, exitCode) {
  const output = new OutputAccumulator({ tempFilePrefix: "pi-bash" });
  // A pipe delivers output in chunks; a chunk can end inside a character.
  for (let at = 0; at < bytes.length; at += 65536) output.append(bytes.subarray(at, at + 65536));
  output.finish();
  const snapshot = output.snapshot({ persistIfTruncated: true });
  await output.closeTempFile();
  const truncation = snapshot.truncation;
  let text = snapshot.content || "(no output)";
  let details;
  if (truncation.truncated) {
    details = { truncation, fullOutputPath: snapshot.fullOutputPath };
    const startLine = truncation.totalLines - truncation.outputLines + 1;
    const endLine = truncation.totalLines;
    if (truncation.lastLinePartial) {
      text += `\n\n[Showing last ${formatSize(truncation.outputBytes)} of line ${endLine} (line is ${formatSize(output.getLastLineBytes())}). Full output: ${snapshot.fullOutputPath}]`;
    } else if (truncation.truncatedBy === "lines") {
      text += `\n\n[Showing lines ${startLine}-${endLine} of ${truncation.totalLines}. Full output: ${snapshot.fullOutputPath}]`;
    } else {
      text += `\n\n[Showing lines ${startLine}-${endLine} of ${truncation.totalLines} (${formatSize(DEFAULT_MAX_BYTES)} limit). Full output: ${snapshot.fullOutputPath}]`;
    }
  }
  const full = await output.readFullOutput(1024 * 1024);
  const structuredContent = { output: full.content, truncated: full.truncated, exit_code: exitCode };
  if (exitCode !== 0) text = `${text ? `${text}\n\n` : ""}Command exited with code ${exitCode}`;
  return { toolName: "bash", isError: exitCode !== 0, content: [{ type: "text", text }], details, structuredContent };
}

function draw(result, isError, expanded, width) {
  const context = { isError, showImages: false, lastComponent: undefined };
  return bash.renderResult(result, { expanded, isPartial: false }, theme, context).render(width);
}

const panelOf = (lines) => lines.filter((line) => line.startsWith("\x1b[49m"));

const out = {};
for (const c of cases) {
  const one = {};
  for (const mode of ["colour", "plain"]) {
    const [b64, exitCode] = c[mode];
    const event = await piResult(Buffer.from(b64, "base64"), exitCode);
    const path = event.details?.fullOutputPath;
    const handled = (await handlers.tool_result(event)) ?? null;
    const result = handled ? { content: handled.content, details: handled.details, structuredContent: handled.structuredContent } : event;
    const r = {
      handled: handled !== null,
      text: result.content[0].text,
      parts: result.content.map((part) => part.text),
      structured: result.structuredContent?.output,
      colour: result.details?.colour ?? null,
      lines: mod.readResult(result, event.isError).lines,
      path: path ?? null,
      file: path && existsSync(path) ? readFileSync(path, "utf8") : null,
    };
    if (mode === "colour") {
      r.status = mod.readResult(result, event.isError).status;
      r.collapsed = draw(result, event.isError, false, c.long ? 160 : 400);
      if (!c.long) {
        r.wide = draw(result, event.isError, true, 400);
        r.narrow = panelOf(draw(result, event.isError, true, 40));
        r.wideWidths = panelOf(r.wide).map((line) => visibleWidth(line));
        r.narrowWidths = r.narrow.map((line) => visibleWidth(line));
      }
    }
    one[mode] = r;
  }
  out[c.slug] = one;
}
console.log(JSON.stringify(out));
"""


def run_node(runs, long_slugs):
    binary = node()
    if not binary or not (PACKAGES / "pi-tui").exists() or not ACCUMULATOR.exists():
        raise unittest.SkipTest("needs node and the installed pi packages (run bootstrap.sh)")
    work = D["dir"] / "node"
    (work / "node_modules").mkdir(parents=True)
    (work / "node_modules/@earendil-works").symlink_to(PACKAGES)
    shutil.copy(SOURCE, work / "command-output.ts")
    payload = [{"slug": slug, "long": slug in long_slugs,
                **{mode: [base64.b64encode(raw).decode(), code] for mode, (raw, code) in got.items()}}
               for slug, got in runs.items()]
    saved = D["dir"] / "saved"
    saved.mkdir()
    # pi saves long outputs to the temp directory: this one, so nothing is left behind.
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(D["home"]), "NO_COLOR": "1",
           "TERM": "xterm-256color", "TMPDIR": str(saved)}
    run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", RUNNER,
                          str(work / "command-output.ts"), str(ACCUMULATOR), str(TRUNCATE)],
                         input=json.dumps(payload), cwd=work, capture_output=True, text=True, env=env, timeout=300, check=False)
    if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
        raise unittest.SkipTest("this node cannot load TypeScript")
    if run.returncode != 0:
        raise RuntimeError(run.stderr[-3000:])
    return json.loads(run.stdout)


def setUpModule():
    if not shutil.which("bash") or not shutil.which("git"):
        raise unittest.SkipTest("needs bash and git")
    if not node() or not ACCUMULATOR.exists():
        raise unittest.SkipTest("needs node and the installed pi packages (run bootstrap.sh)")
    d = Path(tempfile.mkdtemp(prefix="colour-e2e-"))
    D["dir"] = d
    try:
        agent = d / "agent"
        (agent / "shell").mkdir(parents=True)
        shutil.copy(ROOT / "templates/shell/colour.sh", agent / "shell/colour.sh")
        D["agent"] = agent
        D["home"] = d / "home"
        D["home"].mkdir()
        (d / "out").mkdir()
        # Only the tools under test, the bundled ones first; nothing else from this machine's PATH.
        tools = d / "bin"
        tools.mkdir()
        have = set()
        for name in AGENT_TOOLS:
            found = ROOT / "agent/bin" / name
            found = str(found) if found.exists() else shutil.which(name)
            if found:
                (tools / name).symlink_to(found)
                have.add(name)
        for name in SYSTEM_TOOLS:
            if shutil.which(name, path="/usr/bin:/bin"):
                have.add(name)
        pytest = shutil.which("pytest")
        if pytest:
            (tools / "pytest").symlink_to(pytest)
            have.add("pytest")
            # `python3 -m pytest` needs the interpreter pytest itself runs under.
            shebang = Path(pytest).read_bytes()[:200].split(b"\n")[0]
            interpreter = shebang[2:].strip().decode() if shebang.startswith(b"#!") else ""
            if interpreter and Path(interpreter).exists() and " " not in interpreter:
                (tools / "python3").symlink_to(interpreter)
                have.add("python3")
        D["have"] = have
        D["path"] = f"{tools}:/usr/bin:/bin"
        env = {"HOME": str(D["home"]), "PATH": D["path"], "GIT_CONFIG_NOSYSTEM": "1", "TZ": "UTC"}
        build_repo(d, env)
        build_quirks(d, env)
        build_merge(d, env)
        build_tree(d)
        build_text(d)
        build_json(d)
        build_lint(d)
        build_suites(d)
        build_cmp(d)
        build_big(d, env)
        runs = run_commands(CASES + LONG_CASES)
        D["runs"] = runs
        D["results"] = run_node(runs, {c.slug for c in LONG_CASES})
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)
        D.clear()
        raise


def tearDownModule():
    if "dir" in D:
        shutil.rmtree(D["dir"], ignore_errors=True)


# ------------------------------------------------------------------ helpers

def panel_text(line):
    """A panel row's text: margin, padding, box tint, colour codes and theme tags off."""
    line = line.removeprefix("\x1b[49m ")
    for bg in BG.values():
        line = line.removesuffix(" " + bg)
    return TAGS.sub("", SGR.sub("", line)).rstrip()


def panel_rows(lines):
    return [line for line in lines if line.startswith("\x1b[49m")]


def display_lines(lines):
    """How the panel shows plain lines: a tab as three spaces, no control bytes, trailing blanks dropped."""
    return [CONTROL.sub("", line.replace("\t", "   ")).rstrip() for line in lines]


def norm_path(text, path):
    return text.replace(path, "<saved>") if path else text


class EndToEnd(unittest.TestCase):
    """One method per case; `invariant` names the bug key a case may carry."""

    invariant = ""

    def result(self, case):
        reason = missing(case)
        if reason:
            raise unittest.SkipTest(reason)
        return D["runs"][case.slug], D["results"][case.slug]

    def same_lines(self, case, got, expected):
        if case.unordered:
            self.assertEqual(sorted(expected), sorted(got))
        else:
            self.assertEqual(expected, got)


def generate(cls, cases):
    for c in cases:
        name = f"test_{c.slug}"
        assert not hasattr(cls, name), f"duplicate case {cls.__name__}.{name}"

        def test(self, c=c):
            self.check(c)
        test.__doc__ = c.cmd
        bug = c.bugs.get(cls.invariant)
        if bug:
            test.__doc__ += f" [known bug: {bug}]"
            test = unittest.expectedFailure(test)
        setattr(cls, name, test)
    return cls


# ------------------------------------------------------------------ invariants

class ModelCopyTests(EndToEnd):
    """The model reads exactly what the NO_COLOR run gave it, with no escape codes or \\r."""

    invariant = "model"

    def check(self, case):
        runs, got = self.result(case)
        colour, plain = got["colour"], got["plain"]
        text = norm_path(colour["text"], colour["path"])
        expected = norm_path(plain["text"], plain["path"])
        self.assertNotIn(ESC, text)
        self.assertNotIn("\r", text)
        self.same_lines(case, text.split("\n"), expected.split("\n"))
        # The copy codemode scripts read is cleaned the same way.
        self.assertNotIn(ESC, colour["structured"])
        self.same_lines(case, colour["structured"].split("\n"), plain["structured"].split("\n"))
        self.assertEqual(runs["plain"][1], runs["colour"][1])    # colour never changes the exit status


class DisplayColourTests(EndToEnd):
    """The tool's colour reaches the display exactly when it coloured, and says the model's text."""

    invariant = "display"

    def check(self, case):
        runs, got = self.result(case)
        colour = got["colour"]
        raw = runs["colour"][0]
        self.assertEqual(case.coloured, b"\x1b[" in raw, "the wrapper's colour, as printed")
        if case.coloured:
            self.assertTrue(colour["handled"])
            self.assertRegex(colour["colour"], SGR)
            self.assertEqual([colour["text"], COLOUR_NOTE], colour["parts"][:2])   # the model is told the user saw colour
            self.assertEqual(colour["text"], SGR.sub("", colour["colour"]))
        else:
            self.assertIsNone(colour["colour"])
            self.assertNotIn(COLOUR_NOTE, colour["parts"])
            # Nothing to clean: the result reaches the model as pi made it.
            self.assertEqual(b"\r" in raw, colour["handled"])


class PanelTests(EndToEnd):
    """Every drawn row sits on the terminal's background inside the box's tint, full width, showing the plain run's text.

    Expanded at 400 columns each row is one plain line; wrapped to 40 columns,
    no character is lost or invented.
    """

    invariant = "panel"

    def check(self, case):
        runs, got = self.result(case)
        colour, plain = got["colour"], got["plain"]
        exit_code = runs["plain"][1]
        lines = display_lines(plain["lines"])
        self.assertEqual(f"{'✗' if exit_code else '✓'} exit {exit_code} · {len(lines)} line{'' if len(lines) == 1 else 's'}",
                         colour["status"])
        tint = BG["error" if exit_code else "ok"]
        rows = panel_rows(colour["wide"])
        for row in rows + colour["narrow"]:
            self.assertTrue(row.startswith("\x1b[49m ") and row.endswith(" " + tint), repr(row))
        self.assertEqual([WIDE] * len(rows), colour["wideWidths"])
        self.assertEqual([NARROW] * len(colour["narrow"]), colour["narrowWidths"])
        self.same_lines(case, [panel_text(row) for row in rows], lines)
        for row in rows:
            body = row.removeprefix("\x1b[49m ").removesuffix(" " + tint).rstrip(" ")
            if not case.coloured:
                self.assertNotRegex(body, SGR)          # painted by the theme from what the line says
            elif SGR.search(body):
                self.assertTrue(body.endswith("\x1b[0m"), repr(row))   # the tool's colour is reset before the margin
            else:
                self.assertTrue(body.startswith("<toolOutput>"), repr(row))   # a line it left plain
        squeeze = lambda text: re.sub(r"\s+", "", text)
        shown = "".join(squeeze(panel_text(row)) for row in colour["narrow"])
        expected = "".join(squeeze(line) for line in display_lines(plain["lines"]))
        self.assertEqual(sorted(expected), sorted(shown)) if case.unordered else self.assertEqual(expected, shown)


class CollapsedTests(EndToEnd):
    """A long output collapses to the plain run's first and last lines around a count of the hidden ones."""

    invariant = "collapsed"

    def check(self, case):
        _, got = self.result(case)
        colour, plain = got["colour"], got["plain"]
        lines = display_lines(plain["lines"])
        self.assertGreater(len(lines), HEAD + TAIL + 1, "the case is meant to be long")
        rows = [panel_text(row) for row in panel_rows(colour["collapsed"])]
        self.assertEqual(HEAD + 1 + TAIL, len(rows))
        self.assertTrue(rows[HEAD].startswith(f"… {len(lines) - HEAD - TAIL} lines hidden"), rows[HEAD])
        self.same_lines(case, rows[:HEAD] + rows[HEAD + 1:], lines[:HEAD] + lines[-TAIL:])


class SavedOutputTests(EndToEnd):
    """pi saves a truncated output whole; the handler rewrites it to exactly the plain run's file."""

    invariant = "saved"

    def check(self, case):
        runs, got = self.result(case)
        colour, plain = got["colour"], got["plain"]
        self.assertIsNotNone(colour["path"], "pi was meant to truncate this output")
        self.assertIn(b"\x1b[", runs["colour"][0])
        self.assertNotIn(ESC, colour["file"])
        self.assertEqual(runs["plain"][0].decode(), colour["file"])
        # The plain run's own file, when it was long enough to get one, is what it printed.
        self.assertIn(plain["file"], (None, colour["file"]))


class TruncatedTailTests(EndToEnd):
    """The model's tail of a truncated output is plain, ends the plain run's output, and keeps pi's footer."""

    invariant = "tail"

    def check(self, case):
        runs, got = self.result(case)
        colour, plain = got["colour"], got["plain"]
        text = re.sub(r"\n\nCommand exited with code \d+$", "", colour["text"])
        self.assertNotIn(ESC, text)
        body, footer = text.rsplit("\n\n[", 1)
        self.assertTrue(footer.endswith(f"Full output: {colour['path']}]"), footer)
        whole = runs["plain"][0].decode()
        self.assertTrue(whole.endswith(body + "\n"), body[:120])
        self.assertGreater(len(body), 1000)
        # The whole output, as codemode scripts read it, is the plain run's byte for byte.
        self.assertEqual(whole, colour["structured"])
        if "limit)" not in footer and "of line" not in footer:     # cut by lines: both show the same last lines
            self.assertEqual(re.sub(r"\n\n\[[^\n]*\](?:\n\nCommand exited with code \d+)?$", "", plain["text"]), body)


class TruncatedRenderTests(EndToEnd):
    """The collapsed view of a truncated output names the saved file, counts the plain run's lines, and ends as it does."""

    invariant = "render"

    def check(self, case):
        runs, got = self.result(case)
        colour, plain = got["colour"], got["plain"]
        total = runs["plain"][0].decode().count("\n")
        lines = f"{total} line{'' if total == 1 else 's'}"
        self.assertTrue(colour["status"].endswith(f"· {lines}"), colour["status"])
        notes = [TAGS.sub("", SGR.sub("", line)).rstrip() for line in colour["collapsed"] if "full output" in line]
        self.assertEqual([f"full output ({lines}): {colour['path']}"], notes)
        rows = [panel_text(row) for row in panel_rows(colour["collapsed"])]
        shown = display_lines(plain["lines"])
        if len(shown) > 1:
            self.assertEqual(shown[-TAIL:], rows[-TAIL:])


generate(ModelCopyTests, CASES + LONG_CASES)
generate(DisplayColourTests, CASES)
generate(PanelTests, CASES)
generate(CollapsedTests, [c for c in CASES if c.long])
generate(SavedOutputTests, LONG_CASES)
generate(TruncatedTailTests, LONG_CASES)
generate(TruncatedRenderTests, LONG_CASES)


if __name__ == "__main__":
    unittest.main()
