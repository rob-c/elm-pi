"""command-output.ts, case by case: what each kind of line, escape code and bash result turns into.

test_command_output.py proves the extension's behaviour end to end; this file
pins it down over many real inputs - tool output lines and the colour they get,
SGR and other escape sequences, `\\r` redraws, collapse boundaries, exit
statuses, panel widths, the saved-output rewrite and the tool_result handler.

Every case is run in one node process (importing pi's packages costs seconds),
which returns one JSON object; each case then becomes its own test method. The
tests skip on a checkout that has not been bootstrapped.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "templates/extensions/command-output.ts"
COLOUR_NOTE = re.search(r'COLOUR_NOTE = "([^"]+)"', SOURCE.read_text()).group(1)
E = "\x1b"
R = "\x1b[0m"


def node():
    local = ROOT / ".node/bin/node"
    return str(local) if local.exists() else shutil.which("node")


# Loads the extension against a stub pi and evaluates each case by its op,
# printing {id: result}. The theme stub wraps each run of text in <colour>...</>
# so the colour of every part of a line can be read off.
RUNNER = r"""
import { readFileSync, writeFileSync, mkdirSync, statSync, existsSync, utimesSync, truncateSync, openSync, readSync, closeSync } from "node:fs";
import { join } from "node:path";
const [source, dir] = process.argv.slice(1);
const cases = JSON.parse(readFileSync(0, "utf8"));
const mod = await import(source);
const { initTheme } = await import("@earendil-works/pi-coding-agent");
const { Container } = await import("@earendil-works/pi-tui");
initTheme("dark");
const theme = { fg: (c, s) => `<${c}>${s}</>`, bold: (s) => s, getBgAnsi: (c) => `<bg:${c}>` };
const hint = () => "<hint>";

let resolver;
const handlers = {};
const registered = [];
mod.default({
  registerToolRenderer: (f) => { resolver = f; },
  on: (event, handler) => { registered.push(event); handlers[event] = handler; },
  registerTool: () => registered.push("tool"),
});

// The first bytes of a file, without reading a large one whole.
const head = (path, n) => { const fd = openSync(path, "r"); const b = Buffer.alloc(n); const got = readSync(fd, b, 0, n, 0); closeSync(fd); return b.subarray(0, got).toString("utf8"); };
const OLD = new Date(1_000_000_000_000);

const ops = {
  classify: (a) => mod.classify(a.line, a.diff ?? false),
  diffKinds: (a) => a.lines.map((line) => mod.classify(line, mod.isDiff(a.lines))),
  isDiff: (a) => mod.isDiff(a.lines),
  paint: (a) => mod.paintLine(a.line, a.kind, theme),
  colourText: (a) => mod.colourText(a.raw),
  separate: (a) => mod.separate(a.text),
  carry: (a) => mod.carryColour(a.lines),
  readResult: (a) => mod.readResult(a.result, a.isError ?? false, a.durationMs ?? undefined),
  body: (a) => mod.bodyLines(a.lines, a.expanded ?? false, theme, hint, a.colour),
  panel: (a) => new mod.TerminalPanel(a.rows, "<BG>").render(a.width),
  panelCache: () => {
    const panel = new mod.TerminalPanel(["abc"], "<BG>");
    const first = panel.render(10);
    const again = panel.render(10);
    const wider = panel.render(12);
    const back = panel.render(10);
    panel.invalidate();
    const fresh = panel.render(10);
    return { sameWidthCached: first === again, otherWidthRedrawn: wider !== first && wider[0].length === first[0].length + 2,
             widthChangeRedraws: back !== first, invalidateRedraws: fresh !== back && JSON.stringify(fresh) === JSON.stringify(first) };
  },
  plainFile: (a, id) => {
    const path = join(dir, `${id}.log`);
    if (a.directory) mkdirSync(path);
    else if (a.content !== undefined) {
      writeFileSync(path, a.content);
      if (a.size) truncateSync(path, a.size);
      utimesSync(path, OLD, OLD);
    }
    mod.plainFile(path);
    if (a.directory) return { directory: statSync(path).isDirectory() };
    if (!existsSync(path)) return { exists: false };
    return { text: a.size ? head(path, 64) : readFileSync(path, "utf8"), rewritten: statSync(path).mtimeMs !== OLD.getTime(),
             ...(a.size ? { size: statSync(path).size } : {}) };
  },
  handle: async (a, id) => {
    let event = JSON.stringify(a.event);
    let path;
    if (a.file !== undefined) {
      path = join(dir, `${id}.log`);
      writeFileSync(path, a.file);
      event = event.replaceAll("$FILE", path);
    }
    let result = (await handlers.tool_result(JSON.parse(event))) ?? null;
    if (path) result = { returned: JSON.parse(JSON.stringify(result).replaceAll(path, "$FILE")), file: readFileSync(path, "utf8") };
    if (a.parts) {
      // The model's text, how it was cut, and the display's colour read as text.
      const got = result.returned;
      const cut = got.details?.truncation;
      return { text: got.content[0].text, colourPlain: got.details?.colour?.replace(/\x1b\[[0-9;:]*m/g, "") ?? null,
               truncation: cut ? { truncated: cut.truncated, truncatedBy: cut.truncatedBy, totalLines: cut.totalLines,
                                   outputLines: cut.outputLines, lastLinePartial: cut.lastLinePartial } : null,
               fullOutputPath: got.details?.fullOutputPath ?? null };
    }
    return result;
  },
  render: (a) => {
    const base = a.noBaseRender ? { renderCall() { return "base call"; } }
                               : { renderCall() { return "base call"; }, renderResult() { return "base live view"; } };
    const bash = resolver("bash", () => base);
    const last = a.last === "container" ? new Container() : a.last === "object" ? {} : undefined;
    const context = { isError: a.isError ?? false, durationMs: a.durationMs ?? undefined, showImages: a.showImages ?? false, lastComponent: last };
    if (a.keyHint) context.keyHint = (key, text) => `[${key}|${text}]`;
    const component = bash.renderResult(a.result, { expanded: a.expanded ?? false, isPartial: a.partial ?? false }, theme, context);
    if (typeof component === "string") return { live: component };
    const lines = component.render(a.width ?? 120);
    return {
      // Read off the text: the panel's background, margin and padding come off.
      text: lines.map((line) => line.replace(/^\x1b\[49m /, "").replace(/ *<bg:\w+>$/, "").trimEnd()).filter(Boolean),
      panel: lines.filter((line) => line.startsWith("\x1b[49m")),
      reused: component === last,
    };
  },
  resolve: (a) => {
    const got = resolver(a.tool, () => (a.next === "none" ? undefined : { renderCall() {} }));
    return got === undefined ? "undefined" : typeof got.renderResult;
  },
  registered: () => registered,
};

const out = {};
for (const [id, c] of Object.entries(cases)) {
  try {
    const value = await ops[c.op](c.args, id);
    out[id] = value === undefined ? null : value;
  } catch (error) {
    out[id] = { __error__: String(error && error.stack || error) };
  }
}
console.log(JSON.stringify(out));
"""


CASES = {}      # "Class.test_name" -> {"op": ..., "args": ...}
_results = None


def run_all():
    """Every case in one node process; the result is shared by all the classes."""
    global _results
    if _results is not None:
        return _results
    binary = node()
    packages = ROOT / "node_modules/@earendil-works"
    if not binary or not (packages / "pi-tui").exists():
        raise unittest.SkipTest("needs node and the installed pi packages (run bootstrap.sh)")
    work = Path(tempfile.mkdtemp())
    try:
        (work / "node_modules").mkdir()
        (work / "node_modules/@earendil-works").symlink_to(packages)
        shutil.copy(SOURCE, work / "command-output.ts")
        files = work / "files"
        files.mkdir()
        home = work / "home"
        home.mkdir()
        # A home of its own, so nothing reads the user's ~/.pi; images forced on
        # so the "not shown" note depends only on the result's showImages.
        env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home), "NO_COLOR": "1",
               "TERM": "xterm-256color", "PI_IMAGE_PROTOCOL": "kitty"}
        run = subprocess.run([binary, "--no-warnings", "--input-type=module", "-e", RUNNER,
                              str(work / "command-output.ts"), str(files)],
                             input=json.dumps(CASES), cwd=work, capture_output=True, text=True, env=env, timeout=300)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if run.returncode != 0 and "ERR_UNKNOWN_FILE_EXTENSION" in run.stderr:
        raise unittest.SkipTest("this node cannot load TypeScript")
    if run.returncode != 0:
        raise RuntimeError(run.stderr)
    _results = json.loads(run.stdout)
    return _results


class Cases(unittest.TestCase):
    """A table of cases, one test method each, all answered by one node run."""

    @classmethod
    def setUpClass(cls):
        cls.results = run_all()

    def check(self, key, expected, pick):
        got = self.results[key]
        if isinstance(got, dict) and "__error__" in got:
            self.fail(got["__error__"])
        if pick is not None:
            got = got[pick]
        self.assertEqual(expected, got)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:70] or "empty"


def add(cls, name, op, args, expected, bug=None, pick=None):
    """One test method on cls: the case's result (or its `pick` field) must equal expected.
    A bug (one line naming it) marks the case as an expected failure."""
    name = "test_" + slug(name)
    assert not hasattr(cls, name), f"duplicate case {cls.__name__}.{name}"
    key = f"{cls.__name__}.{name}"
    CASES[key] = {"op": op, "args": args}

    def test(self):
        self.check(key, expected, pick)
    test.__doc__ = f"{op}: {json.dumps(args)[:120]}"
    if bug:
        test.__doc__ += f" [known bug: {bug}]"
        test = unittest.expectedFailure(test)
    setattr(cls, name, test)


# ---------------------------------------------------------------- classify

class ClassifyTests(Cases):
    """Real tool output lines and the kind (colour) each one gets outside a diff."""


# (tool, line, kind[, bug]): the tool names where the line comes from.
LINES = [
    # pytest
    ("pytest", "tests/test_io.py::test_read FAILED                         [ 50%]", "error"),
    ("pytest", "tests/test_io.py::test_write PASSED                        [100%]", "success"),
    ("pytest", "==== 3 failed, 10 passed, 1 warning in 2.10s ====", "error"),
    ("pytest", "==== 5 passed, 1 skipped in 0.12s ====", "success"),
    ("pytest", "==== 2 xfailed, 3 passed in 0.50s ====", "success"),      # xfailed is expected, not a failure
    ("pytest", "==== no tests ran in 0.01s ====", "plain"),
    ("pytest", "==== 1 error in 0.20s ====", "error"),
    ("pytest", "==== warnings summary ====", "warning"),
    ("pytest", "==== short test summary info ====", "plain"),
    ("pytest", "E       AssertionError: assert 1 == 2", "error"),
    ("pytest", "E   ModuleNotFoundError: No module named 'lmfit'", "error"),
    ("pytest", ">       assert result == expected", "plain"),
    ("pytest", "tests/test_fit.py:12: AssertionError", "error"),
    ("pytest", "collected 12 items", "plain"),
    ("pytest", "tests/test_fit.py ..F.s                                   [100%]", "plain"),
    ("pytest", "ERROR tests/test_db.py - sqlite3.OperationalError: no such table", "error"),
    ("pytest", "platform linux -- Python 3.12.3, pytest-8.3.2, pluggy-1.5.0", "plain"),
    ("pytest", "rootdir: /home/u/fit", "plain"),
    # unittest
    ("unittest", "Ran 12 tests in 0.034s", "plain"),
    ("unittest", "OK (skipped=2)", "success"),
    ("unittest", "FAILED (failures=1, errors=2)", "error"),
    ("unittest", "OK (expected failures=1)", "success"),
    ("unittest", "ERROR: test_load (tests.test_io.LoadTests.test_load)", "error"),
    ("unittest", "FAIL: test_slope (tests.test_fit.FitTests.test_slope)", "error"),
    ("unittest", "AssertionError: 2.48 != 2.5", "error"),
    ("unittest", "-" * 70, "plain"),
    ("unittest", "test_slope (tests.test_fit.FitTests.test_slope) ... skipped 'needs node'", "plain"),
    # ruff, flake8: a finding is a warning even without the word
    ("ruff", "src/app.py:10:1: E302 expected 2 blank lines, found 1", "warning"),
    ("ruff", "src/app.py:12:80: E501 Line too long (88 > 79)", "warning"),
    ("ruff", "app.py:1:1: D100 Missing docstring in public module", "warning"),
    ("ruff", "app.py:5:5: PLR0913 Too many arguments in function definition (6 > 5)", "warning"),
    ("ruff", "Found 3 errors.", "error"),
    ("ruff", "[*] 2 fixable with the `--fix` option.", "plain"),
    ("flake8", "./fit.py:7:1: W291 trailing whitespace", "warning"),
    ("flake8", "fit.py:2:1: C901 'fit' is too complex (11)", "warning"),
    # mypy
    ("mypy", "src/fit.py:12: error: Incompatible types in assignment", "error"),
    ("mypy", 'src/fit.py:3: note: Revealed type is "builtins.int"', "plain"),
    ("mypy", "Found 2 errors in 1 file (checked 5 source files)", "error"),
    ("mypy", "Success: no issues found in 5 source files", "success"),
    ("mypy", 'src/fit.py:8: warning: unused "type: ignore" comment', "warning"),
    # gcc, clang, the linker
    ("gcc", "fit.c:12:5: error: expected ';' before 'return'", "error"),
    ("gcc", "fit.c:3:10: fatal error: lmfit.h: No such file or directory", "error"),
    ("gcc", "fit.c:7:9: warning: unused variable 'x' [-Wunused-variable]", "warning"),
    ("gcc", "fit.c:20:1: note: declared here", "plain"),
    ("gcc", "/usr/bin/ld: fit.o: in function `main': undefined reference to `cblas_dgemm'", "error"),
    ("gcc", "collect2: error: ld returned 1 exit status", "error"),
    ("gcc", "In file included from fit.c:1:", "plain"),
    ("clang", "1 warning generated.", "warning"),
    ("clang", "2 warnings and 1 error generated.", "error"),
    ("clang", "clang: error: linker command failed with exit code 1 (use -v to see invocation)", "error"),
    ("clang", "   12 |     return x", "plain"),
    ("clang", "      |     ^~~~~~", "plain"),
    # rustc, cargo
    ("rustc", "error[E0382]: borrow of moved value: `v`", "error"),
    ("rustc", "warning: unused variable: `x`", "warning"),
    ("rustc", "  --> src/main.rs:4:9", "plain"),
    ("rustc", "error: aborting due to 1 previous error", "error"),
    ("cargo", "   Compiling fit v0.1.0 (/home/u/fit)", "plain"),
    ("cargo", "    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.20s", "plain"),
    ("cargo", 'error: could not compile `fit` (bin "fit") due to 2 previous errors', "error"),
    ("cargo", 'warning: `fit` (bin "fit") generated 1 warning', "warning"),
    ("cargo", "thread 'main' panicked at src/main.rs:5:5:", "error"),
    ("cargo", "test result: ok. 3 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s", "success"),
    ("cargo", "test result: FAILED. 2 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out", "error"),
    ("cargo", "test tests::slope ... FAILED", "error"),
    ("cargo", "running 3 tests", "plain"),
    ("cargo", "note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace", "plain"),
    # go
    ("go", "--- FAIL: TestSlope (0.00s)", "error"),
    ("go", "FAIL\tgithub.com/u/fit\t0.012s", "error"),
    ("go", "ok  \tgithub.com/u/fit\t0.012s", "success"),
    ("go", "panic: runtime error: index out of range [5] with length 3", "error"),
    ("go", "goroutine 1 [running]:", "plain"),
    ("go", "=== RUN   TestSlope", "plain"),
    # npm
    ("npm", "npm ERR! A complete log of this run can be found in:", "error"),
    ("npm", "npm WARN deprecated inflight@1.0.6: This module is not supported", "warning"),
    ("npm", "npm warn deprecated glob@7.2.3: Glob versions prior to v9 are no longer supported", "warning"),
    ("npm", "added 120 packages, and audited 121 packages in 3s", "plain"),
    ("npm", "found 0 vulnerabilities", "plain"),
    ("npm", "npm error code ENOENT", "error"),
    ("npm", "npm error enoent Could not read package.json", "error"),
    ("npm", "> fit@1.0.0 test", "plain"),
    # pip
    ("pip", "ERROR: Could not find a version that satisfies the requirement lmfit==9.9", "error"),
    ("pip", "Successfully installed lmfit-1.3.2 numpy-2.1.0", "success"),
    ("pip", "Requirement already satisfied: numpy in ./agent/python", "plain"),
    ("pip", "WARNING: You are using pip version 23.0; however, version 24.2 is available.", "warning"),
    ("pip", "Collecting lmfit", "plain"),
    ("pip", "error: externally-managed-environment", "error"),
    ("pip", "  Downloading numpy-2.1.0.tar.gz (18.9 MB)", "plain"),
    ("pip", "Successfully built fit", "success"),
    ("pip", "  error: subprocess-exited-with-error", "error"),
    # make, cmake
    ("make", "make: *** [Makefile:12: fit] Error 1", "error"),
    ("make", "make[1]: Entering directory '/home/u/fit'", "plain"),
    ("make", "make: Nothing to be done for 'all'.", "plain"),
    ("make", "cc -O2 -Wall -Werror -o fit fit.c -lm", "plain"),          # -Werror is a flag, not an error
    ("cmake", "CMake Error at CMakeLists.txt:5 (find_package):", "error"),
    ("cmake", "CMake Warning (dev) at CMakeLists.txt:3 (project):", "warning"),
    ("cmake", "-- Configuring done (0.4s)", "plain"),
    ("cmake", "-- Build files have been written to: /home/u/fit/build", "plain"),
    ("cmake", "[100%] Built target fit", "plain"),
    ("cmake", "-- Could NOT find BLAS (missing: BLAS_LIBRARIES)", "error"),
    ("cmake", "-- Looking for pthread.h - found", "plain"),
    # shellcheck
    ("shellcheck", "In run.sh line 3:", "plain"),
    ("shellcheck", "^-- SC2086 (info): Double quote to prevent globbing and word splitting.", "warning"),
    ("shellcheck", "^-- SC2034 (warning): foo appears unused. Verify use (or export if used externally).", "warning"),
    ("shellcheck", "run.sh:3:6: error: Couldn't parse this function. [SC1073]", "error"),
    # Python
    ("python", '  File "/usr/lib/python3.12/runpy.py", line 198, in _run_module_as_main', "plain"),
    ("python", "KeyError: 'slope'", "error"),
    ("python", "ZeroDivisionError: division by zero", "error"),
    ("python", "FileNotFoundError: [Errno 2] No such file or directory: 'data.csv'", "error"),
    ("python", "During handling of the above exception, another exception occurred:", "error"),
    ("python", "RuntimeWarning: invalid value encountered in divide", "warning"),
    ("python", "PendingDeprecationWarning: the matrix subclass is not recommended", "warning"),
    ("python", "  warnings.warn(", "warning"),
    ("python", "UserWarning: Matplotlib is currently using agg", "warning"),
    ("python", "FutureWarning: The default of observed=False is deprecated", "warning"),
    ("python", "SyntaxError: invalid syntax", "error"),
    ("python", "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)", "error"),
    ("python", "OSError: [Errno 28] No space left on device", "error"),
    ("python", "RecursionError: maximum recursion depth exceeded", "error"),
    ("python", "StopIteration", "plain"),
    ("python", "KeyboardInterrupt", "plain"),
    ("python", "    return np.trapz(y, x)", "plain"),
    ("python", "    ^^^^^^^^^", "plain"),
    # Java
    ("java", 'Exception in thread "main" java.lang.IllegalStateException: closed', "error"),
    ("java", "\tat com.example.Main.main(Main.java:5)", "plain"),
    ("java", "Caused by: java.lang.NullPointerException", "error"),
    ("java", "Caused by: java.io.IOException: Stream closed", "error"),
    # git
    ("git", "fatal: not a git repository (or any of the parent directories): .git", "error"),
    ("git", "error: pathspec 'x' did not match any file(s) known to git", "error"),
    ("git", "hint: Updates were rejected because the remote contains work that you do not", "plain"),
    ("git", "Switched to a new branch 'feature'", "plain"),
    ("git", "Already up to date.", "plain"),
    ("git", " 3 files changed, 12 insertions(+), 4 deletions(-)", "plain"),
    ("git", "Automatic merge failed; fix conflicts and then commit the result.", "error"),
    ("git", "warning: LF will be replaced by CRLF in fit.py.", "warning"),
    ("git", "\tmodified:   src/errors.rs", "plain"),
    ("git", "nothing to commit, working tree clean", "plain"),
    ("git", "Your branch is ahead of 'origin/main' by 1 commit.", "plain"),
    ("git", "error: failed to push some refs to 'github.com:u/fit.git'", "error"),
    # valgrind
    ("valgrind", "==1234== ERROR SUMMARY: 0 errors from 0 contexts (suppressed: 0 from 0)", "plain"),
    ("valgrind", "==1234== ERROR SUMMARY: 3 errors from 3 contexts (suppressed: 0 from 0)", "error"),
    ("valgrind", "==1234== All heap blocks were freed -- no leaks are possible", "plain"),
    ("valgrind", "==1234==    definitely lost: 40 bytes in 1 blocks", "plain"),
    # LaTeX
    ("latex", "! LaTeX Error: File `foo.sty' not found.", "error"),
    ("latex", "! Undefined control sequence.", "error"),
    ("latex", "LaTeX Warning: Reference `fig:1' on page 2 undefined on input line 30.", "warning"),
    ("latex", "Package hyperref Warning: Token not allowed in a PDF string", "warning"),
    ("latex", "Overfull \\hbox (12.0pt too wide) in paragraph at lines 10--12", "plain"),
    ("latex", "Output written on paper.pdf (3 pages, 45678 bytes).", "plain"),
    ("latex", "Transcript written on paper.log.", "plain"),
    # JavaScript tools
    ("eslint", "✖ 3 problems (1 error, 2 warnings)", "error"),
    ("eslint", "  12:5  error  'x' is defined but never used  no-unused-vars", "error"),
    ("eslint", "  3:1   warning  Unexpected console statement  no-console", "warning"),
    ("tsc", "src/a.ts(3,7): error TS2322: Type 'string' is not assignable to type 'number'.", "error"),
    ("tsc", "Found 0 errors. Watching for file changes.", "plain"),
    ("jest", "Tests:       1 failed, 4 passed, 5 total", "error"),
    ("jest", "Tests:       5 passed, 5 total", "success"),
    ("webpack", "webpack 5.94.0 compiled with 2 warnings in 812 ms", "warning"),
    ("webpack", "webpack 5.94.0 compiled successfully in 812 ms", "success"),
    ("vite", "✓ built in 1.20s", "success"),
    ("gradle", "FAILURE: Build failed with an exception.", "error"),
    # the shell, the network
    ("shell", "bash: ./run.sh: Permission denied", "error"),
    ("shell", "ls: cannot access 'x': No such file or directory", "error"),
    ("shell", "zsh: segmentation fault  ./fit", "error"),
    ("shell", "Segmentation fault (core dumped)", "error"),
    ("shell", "Aborted (core dumped)", "error"),
    ("shell", "Killed", "plain"),
    ("shell", "python3: can't open file '/x.py': [Errno 2] No such file or directory", "error"),
    ("curl", "curl: (6) Could not resolve host: example.invalid", "error"),
    ("curl", "curl: (7) Failed to connect to localhost port 8080 after 0 ms: Connection refused", "error"),
    ("ssh", "git@github.com: Permission denied (publickey).", "error"),
    ("dns", "lookup: host not found", "error"),
    # marks and bare words
    ("mark", "✗ lint", "error"),
    ("mark", "✘ 2 problems", "error"),
    ("mark", "✔ Compiled", "success"),
    ("mark", "⚠ 3 peer dependency issues", "warning"),
    ("mark", "Deprecated: use fit2 instead", "warning"),
    ("mark", "Warn: low disk space", "warning"),
    ("mark upper", "ERROR", "error"),
    ("mark", "Error", "error"),
    ("mark", "ok", "success"),
    ("mark", "E", "plain"),                   # pytest's E marks a line only with space after it
    ("mark", "Exiting cleanly", "plain"),
    ("mark", "Build succeeded.", "success"),
    ("mark", "Compiled successfully.", "success"),
    # words that only look like problems
    ("word", "error_handler.py", "plain"),
    ("word", "warnings_test passed", "success"),
    ("word", "The terror of the deep", "plain"),
    ("word", "fatalism is a philosophy", "plain"),
    ("word", "warned the user once", "plain"),
    ("word", "OKAY then", "plain"),
    ("word", "exceptional results", "plain"),
    ("word", "a panicky moment", "plain"),
    ("word", "found it", "plain"),
    ("word", "errors_total 0", "plain"),
    ("word", "unsuccessful attempt", "plain"),
    # an error outranks a warning, a warning a pass
    ("order", "1 error, 3 warnings", "error"),
    ("order", "3 warnings, 5 passed", "warning"),
    ("order", "fit.py:3:8: F401 imported but unused, 5 passed", "warning"),
    # a count of nothing
    ("nothing", "0 errors, 0 warnings", "plain"),
    ("nothing", "No errors found", "plain"),
    ("nothing", "zero failures", "plain"),
    ("nothing", "0 Errors, 1 Warning", "warning"),
    ("nothing", "0 warnings, 2 errors", "error"),
    ("nothing", "no failures, 1 error", "error"),
    ("nothing", "10 errors", "error"),         # the 0 of 10 is not nothing
    ("nothing", "100 warnings", "warning"),
    ("nothing", "0 failed, 3 passed", "success"),
    ("nothing", "zero \t warnings", "plain"),
    ("nothing", "no error", "plain"),
    ("nothing", "Found 0 warnings", "plain"),
    ("nothing", "0 errors found, build succeeded", "success"),
]
for tool, line, kind, *bug in LINES:
    add(ClassifyTests, f"{tool} {line}", "classify", {"line": line}, kind, bug[0] if bug else None)


# ---------------------------------------------------------------- diffs

class DiffTests(Cases):
    """Inside a diff a line is read as a change, never as an error or a pass."""


DIFF_LINES = [
    ("meta git header", "diff --git a/fit.py b/fit.py", "meta"),
    ("meta index", "index 3b18e51..a2c4f9d 100644", "meta"),
    ("hunk combined", "@@@ -1,2 -1,2 +1,3 @@@", "hunk"),
    ("hunk bare", "@@", "hunk"),
    ("added error", "+error: x", "added"),
    ("removed failed", "-FAILED test", "removed"),
    ("context error stays plain", " error in context", "plain"),
    ("no newline marker", "\\ No newline at end of file", "plain"),
    ("new file mode", "new file mode 100644", "plain"),
    ("similarity index", "similarity index 90%", "plain"),
    ("binary files", "Binary files a/x.png and b/x.png differ", "plain"),
    ("lone plus", "+", "added"),
    ("lone minus", "-", "removed"),
    ("empty line", "", "plain"),
    ("rename from", "rename from old.py", "plain"),
]
for name, line, kind in DIFF_LINES:
    add(DiffTests, name, "classify", {"line": line, "diff": True}, kind)

IS_DIFF = [
    ("hunk header", ["@@ -1 +1 @@"], True),
    ("git header", ["diff --git a/x b/x"], True),
    ("hunk without minus", ["@@ +1 @@"], False),
    ("indented hunk", ["  @@ -1,2 +1,2 @@"], False),
    ("file headers alone", ["--- a/x", "+++ b/x"], False),
    ("no lines", [], False),
    ("header after other output", ["log line", "diff --git a/b b/b"], True),
    ("diff git without space", ["diff --git"], False),
    ("hunk with letters", ["@@ -a +b @@"], False),
    ("plus minus list", ["-x", "+y"], False),
]
for name, lines, expected in IS_DIFF:
    add(DiffTests, f"is diff {name}", "isDiff", {"lines": lines}, expected)

# One hunk anywhere makes every +/- line in the output a change.
add(DiffTests, "a hunk turns list items into changes", "diffKinds",
    {"lines": ["- item", "+ note", "@@ -1 +1 @@"]}, ["removed", "added", "hunk"])
add(DiffTests, "in a diff failed is plain", "diffKinds",
    {"lines": ["FAILED x", "@@ -1 +1 @@", "-a"]}, ["plain", "hunk", "removed"])


# ---------------------------------------------------------------- paintLine

class PaintTests(Cases):
    """paintLine: the kind's colour in runs, with file:line locations in the accent colour."""


PAINT = [
    ("location then message", "src/fit.py:42:7: oops", "error", "<accent>src/fit.py:42:7</><error>: oops</>"),
    ("dot slash path", "./run.sh:3", "plain", "<accent>./run.sh:3</>"),
    ("windows drive", "C:/proj/fit.c:12:5: error", "error", "<accent>C:/proj/fit.c:12:5</><error>: error</>"),
    ("home path", "see ~/fit/run.py:9", "plain", "<toolOutput>see </><accent>~/fit/run.py:9</>"),
    ("version number is not a location", "version 1.2:3", "plain", "<toolOutput>version 1.2:3</>"),
    ("host port without dot", "localhost:8080", "plain", "<toolOutput>localhost:8080</>"),
    ("java frame", "at Main.main(Main.java:5)", "plain",
     "<toolOutput>at Main.main(</><accent>Main.java:5</><toolOutput>)</>"),
    ("two locations", "a.py:1 and b.py:2", "warning", "<accent>a.py:1</><warning> and </><accent>b.py:2</>"),
    ("added line is one run", "+fit.py:3 x", "added", "<toolDiffAdded>+fit.py:3 x</>"),
    ("removed line is one run", "-fit.py:3 x", "removed", "<toolDiffRemoved>-fit.py:3 x</>"),
    ("hunk is accent", "@@ -1 +1 @@ def f():", "hunk", "<accent>@@ -1 +1 @@ def f():</>"),
    ("meta is muted", "--- a/fit.py", "meta", "<muted>--- a/fit.py</>"),
    ("empty line", "", "plain", ""),
    ("python stdin frame", 'File "<stdin>", line 1', "error", '<accent>File "<stdin>", line 1</>'),
    ("trailing colon", "fit.py:12:", "success", "<accent>fit.py:12</><success>:</>"),
    ("makefile has no extension", "Makefile:12: recipe", "plain", "<toolOutput>Makefile:12: recipe</>"),
    ("scoped package path", "pkg/@scope/x.ts:4:2", "plain", "<accent>pkg/@scope/x.ts:4:2</>"),
    ("double extension", "archive.tar.gz:10", "plain", "<accent>archive.tar.gz:10</>"),
    ("dashed name", "run-me.sh:7 ran", "plain", "<accent>run-me.sh:7</><toolOutput> ran</>"),
    ("clock time", "time 10:30:45", "plain", "<toolOutput>time 10:30:45</>"),
    ("third number not part of location", "x.py:1:2:3", "plain", "<accent>x.py:1:2</><toolOutput>:3</>"),
    ("no digits", "foo.bar:baz", "plain", "<toolOutput>foo.bar:baz</>"),
]
for name, line, kind, expected in PAINT:
    add(PaintTests, name, "paint", {"line": line, "kind": kind}, expected)


# ---------------------------------------------------------------- colourText, separate

class ColourTextTests(Cases):
    """colourText: what a terminal would leave on screen, with only colour (SGR) codes kept.

    Its text is what the same output printed without colour turns into, so tabs
    and control bytes stay: the display draws those."""


COLOUR_TEXT = [
    ("carriage return redraw", "a\rb", "b"),
    ("progress bar", "10%\r20%\r100%", "100%"),
    ("crlf line ending", "done\r\n", "done\n"),
    ("trailing carriage return", "line\r", "line"),
    ("trailing carriage returns", "abc\r\r", "abc"),
    ("sgr kept", f"{E}[31mred{R}", f"{E}[31mred{R}"),
    ("erase then redraw", f"{E}[2K\rdone", "done"),
    ("erase line removed", f"{E}[2Kdone", "done"),
    ("erase to end removed", f"{E}[Kx", "x"),
    ("cursor up removed", f"{E}[1A{E}[2Kup", "up"),
    ("cursor hide show removed", f"{E}[?25lhidden{E}[?25h", "hidden"),
    ("bracketed paste removed", f"{E}[?2004hprompt", "prompt"),
    ("osc title bel removed", f"{E}]0;title\x07text", "text"),
    ("osc hyperlink st removed", f"{E}]8;;http://x{E}\\link{E}]8;;{E}\\", "link"),
    ("tab kept", "a\tb", "a\tb"),
    ("bel kept", "bell\x07", "bell\x07"),
    ("backspace kept", "back\x08space", "back\x08space"),
    ("nul kept", "x\x00y", "x\x00y"),
    ("del kept", "x\x7fy", "x\x7fy"),
    ("form feed and vertical tab kept", "a\x0cb\x0bc", "a\x0cb\x0bc"),
    ("lone escape at end removed", f"end{E}", "end"),
    ("reverse index removed", f"{E}Mup", "up"),
    ("tput sgr0 charset reset", f"{E}(B{E}[mplain", f"{E}[mplain"),
    ("truecolor kept", f"{E}[38;2;255;0;0mtrue", f"{E}[38;2;255;0;0mtrue"),
    ("colon 256 colour kept", f"{E}[38:5:196mcolon", f"{E}[38:5:196mcolon"),
    ("bare reset kept", f"{E}[mbare", f"{E}[mbare"),
    ("bold underline red kept", f"{E}[1;4;31mx{R}", f"{E}[1;4;31mx{R}"),
    ("clear scrollback removed", f"{E}[3Jclear", "clear"),
    ("cursor position removed", f"{E}[10;20Hpos", "pos"),
    ("crlf lines", "a\r\nb\r\n", "a\nb\n"),
    # git colours a CRLF line's \r as trailing whitespace and resets after it.
    ("crlf after reset", f" alpha{E}[m\r", f" alpha{E}[m"),
    ("crlf coloured then reset", f"{E}[32m+BETA{E}[m{E}[41m\r{E}[m", f"{E}[32m+BETA{E}[m{E}[41m{E}[m"),
    ("redraw before a coloured line end", f"10%\r{E}[32mdone\r{E}[m", f"{E}[32mdone{E}[m"),
    ("erase after carriage return still redraws", f"busy\r{E}[K", ""),
    ("colour redraw keeps last colour", f"{E}[31m10%\r{E}[32m100%", f"{E}[32m100%"),
    ("unicode untouched", "naïve ✓ 日本", "naïve ✓ 日本"),
    ("blank lines kept", "a\n\n\nb", "a\n\n\nb"),
]
for name, raw, expected, *bug in COLOUR_TEXT:
    add(ColourTextTests, name, "colourText", {"raw": raw}, expected, bug[0] if bug else None)


class SeparateTests(Cases):
    """separate: the model's plain copy, and a colour copy only when colour was printed."""


SEPARATE = [
    ("no escapes unchanged", "plain", {"plain": "plain"}),
    ("tab without escapes is left alone", "a\tb", {"plain": "a\tb"}),
    ("colour", f"{E}[31mx{R}", {"plain": "x", "colour": f"{E}[31mx{R}"}),
    ("redraw only has no colour", "a\rb", {"plain": "b"}),
    ("erase only has no colour", f"{E}[2Kx", {"plain": "x"}),
    ("bare reset counts as colour", f"{E}[mx", {"plain": "x", "colour": f"{E}[mx"}),
    ("osc only has no colour", f"{E}]0;t\x07x", {"plain": "x"}),
    ("colon truecolor", f"{E}[38:2:1:2:3mc", {"plain": "c", "colour": f"{E}[38:2:1:2:3mc"}),
    ("tab with colour kept in both", f"{E}[1ma\tb", {"plain": "a\tb", "colour": f"{E}[1ma\tb"}),
    ("nul with colour kept in both", f"{E}[1ma\x00b", {"plain": "a\x00b", "colour": f"{E}[1ma\x00b"}),
    ("progress then colour", f"5%\r{E}[32mdone{R}\nnext",
     {"plain": "done\nnext", "colour": f"{E}[32mdone{R}\nnext"}),
]
for name, text, expected in SEPARATE:
    add(SeparateTests, name, "separate", {"text": text}, expected)


# ---------------------------------------------------------------- carryColour

class CarryColourTests(Cases):
    """carryColour: each line opens in the colour the last one left and ends reset."""


CARRY = [
    ("colour carries to next line", [f"{E}[31mred", "next"], [f"{E}[31mred{R}", f"{E}[31mnext{R}"]),
    ("reset stops the carry", [f"{E}[31mred{R}", "next"], [f"{E}[31mred{R}{R}", "next"]),
    ("bare m resets", [f"{E}[32mgo{E}[m", "plain"], [f"{E}[32mgo{E}[m{R}", "plain"]),
    ("zero semicolon replaces", [f"{E}[1m{E}[31mA", f"{E}[0;33mB", "C"],
     [f"{E}[1m{E}[31mA{R}", f"{E}[1m{E}[31m{E}[0;33mB{R}", f"{E}[0;33mC{R}"]),
    ("codes accumulate", [f"{E}[1m", f"{E}[4mx", "y"], [f"{E}[1m{R}", f"{E}[1m{E}[4mx{R}", f"{E}[1m{E}[4my{R}"]),
    ("only the last eight kept", ["".join(f"{E}[38;5;{i}m" for i in range(10)) + "x", "y"],
     ["".join(f"{E}[38;5;{i}m" for i in range(10)) + "x" + R,
      "".join(f"{E}[38;5;{i}m" for i in range(2, 10)) + "y" + R]),
    ("plain lines untouched", ["a", "b"], ["a", "b"]),
    ("colon truecolor carried", [f"{E}[38:2::255:0:0mx", "y"], [f"{E}[38:2::255:0:0mx{R}", f"{E}[38:2::255:0:0my{R}"]),
    ("empty line keeps colour", [f"{E}[35mx", ""], [f"{E}[35mx{R}", f"{E}[35m{R}"]),
    ("reset mid line then colour", [f"{E}[31ma{R}b{E}[32mc", "d"], [f"{E}[31ma{R}b{E}[32mc{R}", f"{E}[32md{R}"]),
    ("carry skips across plain line", [f"{E}[36mx", "y", "z"], [f"{E}[36mx{R}", f"{E}[36my{R}", f"{E}[36mz{R}"]),
    ("no lines", [], []),
]
for name, lines, expected in CARRY:
    add(CarryColourTests, name, "carry", {"lines": lines}, expected)


# ---------------------------------------------------------------- readResult

class ReadResultTests(Cases):
    """readResult: the exit line, the output's own lines, notes and images, read from pi's bash result."""


def text(*parts, **rest):
    return {"content": [{"type": "text", "text": p} for p in parts], **rest}


def outcome(lines, status, failed=False, total=None, notes=(), images=0, **extra):
    return {"lines": lines, "totalLines": len(lines) if total is None else total, "status": status,
            "failed": failed, "notes": list(notes), "images": images, **extra}


TRUNC = {"truncation": {"truncated": True, "totalLines": 5000}, "fullOutputPath": "/tmp/f.log"}
READ = [
    ("plain success", text("a\nb"), False, None, outcome(["a", "b"], "✓ exit 0 · 2 lines")),
    ("exit code", text("out\n\nCommand exited with code 2"), True, None, outcome(["out"], "✗ exit 2 · 1 line", True)),
    ("exit zero status", text("x\n\nCommand exited with code 0"), False, None, outcome(["x"], "✓ exit 0 · 1 line")),
    ("status alone", text("Command exited with code 1"), True, None, outcome([], "✗ exit 1 · 0 lines", True)),
    ("aborted", text("partial\n\nCommand aborted"), True, None, outcome(["partial"], "✗ aborted · 1 line", True)),
    ("terminated", text("Command terminated without an exit code"), True, None,
     outcome([], "✗ terminated without an exit code · 0 lines", True)),
    ("timed out minutes", text("Command timed out after 120 seconds"), True, 120500,
     outcome([], "✗ timed out after 120s · 2m1s · 0 lines", True)),
    ("timed out one second", text("x\n\nCommand timed out after 1 seconds"), True, None,
     outcome(["x"], "✗ timed out after 1s · 1 line", True)),
    ("exit 130", text("^C\n\nCommand exited with code 130"), True, None, outcome(["^C"], "✗ exit 130 · 1 line", True)),
    ("structured exit code without status", text("boom", structuredContent={"exit_code": 3}), True, None,
     outcome(["boom"], "✗ exit 3 · 1 line", True)),
    ("structured exit code wins over text", text("x\n\nCommand exited with code 2", structuredContent={"exit_code": 0}),
     False, None, outcome(["x"], "✓ exit 0 · 1 line")),
    ("is error with exit 0 still fails", text("x", structuredContent={"exit_code": 0}), True, None,
     outcome(["x"], "✗ exit 0 · 1 line", True)),
    ("string exit code ignored", text("x\n\nCommand exited with code 4", structuredContent={"exit_code": "2"}), True, None,
     outcome(["x"], "✗ exit 4 · 1 line", True)),
    ("null exit code ignored", text("x", structuredContent={"exit_code": None}), False, None, outcome(["x"], "✓ exit 0 · 1 line")),
    ("error without status", text("x\ny"), True, None, outcome(["x", "y"], "✗ failed · 2 lines", True)),
    ("non zero exit without is error fails", text("x\n\nCommand exited with code 5"), False, None,
     outcome(["x"], "✗ exit 5 · 1 line", True)),
    ("status mid output is output", text("Command exited with code 2\nmore"), False, None,
     outcome(["Command exited with code 2", "more"], "✓ exit 0 · 2 lines")),
    ("status without blank line is output", text("out\nCommand exited with code 2"), True, None,
     outcome(["out", "Command exited with code 2"], "✗ failed · 2 lines", True)),
    ("truncated footer", text("tail\n\n[Showing lines 4001-5000 of 5000. Full output: /tmp/f.log]", details=TRUNC), False, None,
     outcome(["tail"], "✓ exit 0 · 5000 lines", total=5000, fullOutputPath="/tmp/f.log")),
    ("footer naming another file kept", text("x\n\n[see /tmp/b.log]", details={"fullOutputPath": "/tmp/a.log"}), False, None,
     outcome(["x", "", "[see /tmp/b.log]"], "✓ exit 0 · 3 lines", fullOutputPath="/tmp/a.log")),
    ("footer then status", text("x\n\n[Full output: /tmp/f.log]\n\nCommand exited with code 1", details={"fullOutputPath": "/tmp/f.log"}),
     True, None, outcome(["x"], "✗ exit 1 · 1 line", True, fullOutputPath="/tmp/f.log")),
    ("only the last footer removed", text("a\n\n[x]\nb\n\n[Full output: /tmp/f.log]", details={"fullOutputPath": "/tmp/f.log"}),
     False, None, outcome(["a", "", "[x]", "b"], "✓ exit 0 · 4 lines", fullOutputPath="/tmp/f.log")),
    ("truncated without total", text("a\nb", details={"truncation": {"truncated": True}}), False, None,
     outcome(["a", "b"], "✓ exit 0 · 2 lines")),
    ("not truncated ignores total", text("a", details={"truncation": {"truncated": False, "totalLines": 999}}), False, None,
     outcome(["a"], "✓ exit 0 · 1 line")),
    ("notes trimmed blank and colour note dropped", text("out", "  Installed lmfit  ", "   ", COLOUR_NOTE), False, None,
     outcome(["out"], "✓ exit 0 · 1 line", notes=["Installed lmfit"])),
    ("two images", {"content": [{"type": "text", "text": "x"}, {"type": "image"}, {"type": "image"}]}, False, None,
     outcome(["x"], "✓ exit 0 · 1 line", images=2)),
    ("image without text", {"content": [{"type": "image"}]}, False, None, outcome([], "✓ exit 0 · 0 lines", images=1)),
    ("empty content", {"content": []}, False, None, outcome([], "✓ exit 0 · 0 lines")),
    ("text part without text", {"content": [{"type": "text"}]}, False, None, outcome([], "✓ exit 0 · 0 lines")),
    ("trailing whitespace dropped", text("a\n\n\n  "), False, None, outcome(["a"], "✓ exit 0 · 1 line")),
    ("leading blank lines kept", text("\n\na"), False, None, outcome(["", "", "a"], "✓ exit 0 · 3 lines")),
    ("escape codes stripped", text(f"{E}[31mred{R}\n{E}]0;t\x07a\tb"), False, None,
     outcome(["red", "a   b"], "✓ exit 0 · 2 lines")),
    ("colour sliced to the lines", text("a\nb\n\nCommand exited with code 1", details={"colour": f"{E}[31ma\nb\n\nCommand exited with code 1"}),
     True, None, outcome(["a", "b"], "✗ exit 1 · 2 lines", True, colour=[f"{E}[31ma", "b"])),
    ("non string colour ignored", text("a", details={"colour": 7}), False, None, outcome(["a"], "✓ exit 0 · 1 line")),
    # The model reads tabs and control bytes as printed; the panel draws them as a terminal would.
    ("control bytes not drawn", text("a\x00b\x07\tc"), False, None, outcome(["ab   c"], "✓ exit 0 · 1 line")),
    ("colour drawn with tabs as spaces", text("a\tb\x00", details={"colour": f"{E}[31ma\tb\x00"}), False, None,
     outcome(["a   b"], "✓ exit 0 · 1 line", colour=[f"{E}[31ma   b"])),
]
for name, result, is_error, duration, expected in READ:
    add(ReadResultTests, name, "readResult", {"result": result, "isError": is_error, "durationMs": duration}, expected)

DURATIONS = [
    (0, "0ms"), (999, "999ms"), (1000, "1.0s"), (1500, "1.5s"), (59000, "59.0s"),
    (60000, "1m0s"), (61000, "1m1s"), (90000, "1m30s"), (3_600_000, "60m0s"),
    (119_999, "2m0s"), (59_949, "59.9s"), (59_960, "1m0s"),
]
for ms, shown, *bug in DURATIONS:
    add(ReadResultTests, f"duration {ms}ms", "readResult", {"result": text("x"), "isError": False, "durationMs": ms},
        f"✓ exit 0 · {shown} · 1 line", bug[0] if bug else None, pick="status")


# ---------------------------------------------------------------- bodyLines

class BodyLinesTests(Cases):
    """bodyLines: everything up to 17 lines, else the first 4, a count of the rest, and the last 12."""


def steps(n, **swap):
    lines = [f"step {i}" for i in range(n)]
    for i, line in swap.items():
        lines[int(i[1:])] = line
    return lines


def painted(lines):
    return [f"<toolOutput>{line}</>" for line in lines]


def gap(n, flagged=""):
    return f"<muted>… {n} lines hidden</>{flagged}<muted> (</><hint><muted>)</>"


BODY = [
    ("no lines", [], False, None, []),
    ("sixteen lines all shown", steps(16), False, None, painted(steps(16))),
    ("seventeen lines all shown", steps(17), False, None, painted(steps(17))),
    ("eighteen lines collapse", steps(18), False, None, painted(steps(4)) + [gap(2)] + painted(steps(18)[6:])),
    ("nineteen lines hide three", steps(19), False, None, painted(steps(4)) + [gap(3)] + painted(steps(19)[7:])),
    ("expanded shows all", steps(100), True, None, painted(steps(100))),
    ("hidden error and warning counted", steps(18, l4="error: x", l5="warning: y"), False, None,
     painted(steps(4)) + [gap(2, "<error>, 1 error and 1 warning lines among them</>")] + painted(steps(18)[6:])),
    ("one hidden error", steps(18, l5="FAILED"), False, None,
     painted(steps(4)) + [gap(2, "<error>, 1 error line among them</>")] + painted(steps(18)[6:])),
    ("hidden warnings only", steps(18, l4="warning: a", l5="warning: b"), False, None,
     painted(steps(4)) + [gap(2, "<warning>, 2 warning lines among them</>")] + painted(steps(18)[6:])),
    ("three hidden errors", steps(19, l4="error a", l5="error b", l6="error c"), False, None,
     painted(steps(4)) + [gap(3, "<error>, 3 error lines among them</>")] + painted(steps(19)[7:])),
    ("errors shown are not counted", steps(18, l0="error first", l17="error last"), False, None,
     ["<error>error first</>"] + painted(steps(4)[1:]) + [gap(2)] + painted(steps(18)[6:17]) + ["<error>error last</>"]),
    ("location painted", ["src/a.py:3: error: boom"], False, None, ["<accent>src/a.py:3</><error>: error: boom</>"]),
    ("diff lines painted", ["@@ -1 +1 @@", "-old", "+new"], False, None,
     ["<accent>@@ -1 +1 @@</>", "<toolDiffRemoved>-old</>", "<toolDiffAdded>+new</>"]),
    ("hidden diff lines are not errors", ["@@ -1,20 +1,20 @@"] + [f"+error {i}" for i in range(17)], False, None,
     ["<accent>@@ -1,20 +1,20 @@</>"] + [f"<toolDiffAdded>+error {i}</>" for i in range(3)] + [gap(2)]
     + [f"<toolDiffAdded>+error {i}</>" for i in range(5, 17)]),
    # With the command's own colour, its lines are shown as it printed them.
    ("own colour and plain line", ["ignored"], False, [f"{E}[31merror: x{R}", "error: plain"],
     [f"{E}[31merror: x{R}{R}", "<toolOutput>error: plain</>"]),
    ("own colour carried", ["a", "b"], False, [f"{E}[33ma", "b"], [f"{E}[33ma{R}", f"{E}[33mb{R}"]),
    ("own colour hidden errors read from text", steps(18), False, [f"{E}[2m{line}{R}" for line in steps(18, l5="error: x")],
     [f"{E}[2m{line}{R}{R}" for line in steps(4)] + [gap(2, "<error>, 1 error line among them</>")]
     + [f"{E}[2m{line}{R}{R}" for line in steps(18)[6:]]),
]
for name, lines, expanded, colour, expected in BODY:
    add(BodyLinesTests, name, "body", {"lines": lines, "expanded": expanded, "colour": colour}, expected)


# ---------------------------------------------------------------- TerminalPanel

class TerminalPanelTests(Cases):
    """TerminalPanel: rows wrapped to the width less a margin each side, padded, the box tint after."""


def row(content, pad, bg="<BG>"):
    return f"\x1b[49m {content}{' ' * pad} {bg}"


PANEL = [
    ("short row padded", ["abc"], 10, [row("abc", 5)]),
    ("empty row", [""], 10, [row("", 8)]),
    ("exact fit no padding", ["abcd"], 6, [row("abcd", 0)]),
    ("long word broken", ["abcdefghij"], 6, [row("abcd", 0), row("efgh", 0), row("ij", 2)]),
    ("words wrap", ["aa bb cc"], 7, [row("aa bb", 0), row("cc", 3)]),
    ("colour codes have no width", [f"{E}[31mred{R}"], 10, [row(f"{E}[31mred{R}", 5)]),
    ("wide characters count double", ["日本"], 10, [row("日本", 4)]),
    ("rows in order", ["a", "", "b"], 5, [row("a", 2), row("", 3), row("b", 2)]),
    ("no rows", [], 10, []),
    ("width two keeps one column", ["ab"], 2, [row("a", 0), row("b", 0)]),
    ("width one keeps one column", ["ab"], 1, [row("a", 0), row("b", 0)]),
]
for name, rows, width, expected in PANEL:
    add(TerminalPanelTests, name, "panel", {"rows": rows, "width": width}, expected)

add(TerminalPanelTests, "render is cached per width", "panelCache", {},
    {"sameWidthCached": True, "otherWidthRedrawn": True, "widthChangeRedraws": True, "invalidateRedraws": True})


# ---------------------------------------------------------------- plainFile

class PlainFileTests(Cases):
    """plainFile: pi's saved copy of a long output is rewritten plain, and only when it changes."""


PLAIN_FILE = [
    ("colour removed", {"content": f"{E}[31mred{R}\n"}, {"text": "red\n", "rewritten": True}),
    ("plain file not rewritten", {"content": "abc\n"}, {"text": "abc\n", "rewritten": False}),
    ("progress collapsed", {"content": "a\rb\n"}, {"text": "b\n", "rewritten": True}),
    ("tabs kept with escapes", {"content": f"a\tb{E}[1m"}, {"text": "a\tb", "rewritten": True}),
    ("tabs alone left", {"content": "a\tb"}, {"text": "a\tb", "rewritten": False}),
    ("missing file ignored", {}, {"exists": False}),
    ("directory ignored", {"directory": True}, {"directory": True}),
    # Over 64 MB (sparse, so nothing is written): left as printed.
    ("over 64mb left alone", {"content": f"{E}[31mred", "size": 64 * 1024 * 1024 + 1},
     {"text": f"{E}[31mred" + "\x00" * 56, "rewritten": False, "size": 64 * 1024 * 1024 + 1}),
]
for name, args, expected in PLAIN_FILE:
    add(PlainFileTests, name, "plainFile", args, expected)


# ---------------------------------------------------------------- tool_result

class ToolResultTests(Cases):
    """The tool_result handler: the model's copy made plain, the colour kept in details for the display."""


def event(*parts, tool="bash", **rest):
    return {"toolName": tool, "isError": False, "content": list(parts), **rest}


def t(s, **extra):
    return {"type": "text", "text": s, **extra}


IMG = {"type": "image", "data": "", "mimeType": "image/png"}
NOTE = t(COLOUR_NOTE)
HANDLE = [
    ("other tool untouched", event(t(f"{E}[31mx"), tool="read"), None),
    ("plain output untouched", event(t("x"), details={"a": 1}), None),
    ("no text part untouched", event(IMG), None),
    ("colour adds note and details", event(t(f"{E}[31mx{R}"), details={"a": 1}),
     {"content": [t("x"), NOTE], "details": {"a": 1, "colour": f"{E}[31mx{R}"}}),
    ("colour without details", event(t(f"{E}[1mx")),
     {"content": [t("x"), NOTE], "details": {"colour": f"{E}[1mx"}}),
    ("redraw only no note", event(t("1\r2"), details={"a": 1}), {"content": [t("2")], "details": {"a": 1}}),
    ("osc only no note", event(t(f"{E}]0;t\x07x")), {"content": [t("x")]}),
    ("note follows the first text part", event(IMG, t(f"{E}[31mx"), t("later")),
     {"content": [IMG, t("x"), NOTE, t("later")], "details": {"colour": f"{E}[31mx"}}),
    ("only the first text part cleaned", event(t(f"{E}[1mA"), t(f"{E}[2mB")),
     {"content": [t("A"), NOTE, t(f"{E}[2mB")], "details": {"colour": f"{E}[1mA"}}),
    ("other fields of the part kept", event(t(f"{E}[1mA", extra=1)),
     {"content": [t("A", extra=1), NOTE], "details": {"colour": f"{E}[1mA"}}),
    ("structured output cleaned", event(t(f"{E}[1mA"), structuredContent={"output": f"{E}[1mA\rB", "exit_code": 0}),
     {"content": [t("A"), NOTE], "structuredContent": {"output": "B", "exit_code": 0}, "details": {"colour": f"{E}[1mA"}}),
    ("structured without output passed on", event(t(f"{E}[1mA"), structuredContent={"exit_code": 1}),
     {"content": [t("A"), NOTE], "structuredContent": {"exit_code": 1}, "details": {"colour": f"{E}[1mA"}}),
    ("structured non string output passed on", event(t("a\rb"), structuredContent={"output": 5}),
     {"content": [t("b")], "structuredContent": {"output": 5}}),
]
for name, ev, expected in HANDLE:
    add(ToolResultTests, name, "handle", {"event": ev}, expected)

# The saved full output is cleaned even when the result's own text is plain.
add(ToolResultTests, "saved output cleaned when text is plain", "handle",
    {"event": event(t("x"), details={"fullOutputPath": "$FILE"}), "file": f"{E}[31mred{R}\nx\n"},
    {"returned": None, "file": "red\nx\n"})
add(ToolResultTests, "saved output and text both cleaned", "handle",
    {"event": event(t(f"{E}[32mok{R}"), details={"fullOutputPath": "$FILE"}), "file": f"a\r{E}[32mok{R}\n"},
    {"returned": {"content": [t("ok"), NOTE], "details": {"fullOutputPath": "$FILE", "colour": f"{E}[32mok{R}"}}, "file": "ok\n"})
# pi cuts at 2000 lines or 50KB counting colour codes; the cut is made again on the plain text.
def numbered(n, colour=False):
    return "".join(f"{E}[32m{i:05d}{R}{E}[K\n" if colour else f"{i:05d}\n" for i in range(n))


def pi_cut(printed, kept, by="bytes", status=""):
    """The text and details pi's bash tool gives for an output it cut to `kept` lines."""
    lines = printed.split("\n")[:-1]
    total = len(lines)
    limit = " (50.0KB limit)" if by == "bytes" else ""
    footer = f"\n\n[Showing lines {total - kept + 1}-{total} of {total}{limit}. Full output: $FILE]"
    return "\n".join(lines[-kept:]) + footer + status, {"truncated": True, "truncatedBy": by, "totalLines": total,
                                                       "maxLines": 2000, "maxBytes": 51200}


def recut_case(name, printed, kept, expected_text, expected_truncation, status="", saved="$FILE"):
    text_, truncation = pi_cut(printed, kept, status=status)
    args = {"event": event(t(text_), details={"fullOutputPath": "$FILE", "truncation": truncation}), "file": printed, "parts": True}
    add(ToolResultTests, name, "handle", args, expected_text, pick="text")
    add(ToolResultTests, name + " truncation", "handle", args, expected_truncation, pick="truncation")
    add(ToolResultTests, name + " colour has its text", "handle", args, expected_text, pick="colourPlain")
    # A result pi would not have cut names no saved file.
    add(ToolResultTests, name + " saved file named", "handle", args, saved, pick="fullOutputPath")


# 3000 lines of 6 bytes: plain, pi keeps the last 2000; coloured, 18 bytes a line, it kept the last 2844 by bytes.
recut_case("coloured output recut by lines as plain", numbered(3000, True), 2844,
           "\n".join(f"{i:05d}" for i in range(1000, 3000)) + "\n\n[Showing lines 1001-3000 of 3000. Full output: $FILE]",
           {"truncated": True, "truncatedBy": "lines", "totalLines": 3000, "outputLines": 2000, "lastLinePartial": False})
recut_case("recut keeps the exit status", numbered(3000, True), 2844,
           "\n".join(f"{i:05d}" for i in range(1000, 3000))
           + "\n\n[Showing lines 1001-3000 of 3000. Full output: $FILE]\n\nCommand exited with code 1",
           {"truncated": True, "truncatedBy": "lines", "totalLines": 3000, "outputLines": 2000, "lastLinePartial": False},
           status="\n\nCommand exited with code 1")
# 1500 lines of 31 bytes fit whole plain, as pi would have left them; coloured (39 bytes) pi cut them to 1312.
recut_case("plain output that fits is not cut", "".join(f"{E}[1m{i:05d}{R}" + "x" * 25 + "\n" for i in range(1500)), 1312,
           "\n".join(f"{i:05d}" + "x" * 25 for i in range(1500)) + "\n",
           None, saved=None)
# One line of 60000 characters, half of them coloured: pi kept less of its text.
HUGE = "".join(f"{E}[31m{c}{R}" if i % 2 else c for i, c in enumerate("ab" * 30000)) + "\n"
HUGE_ARGS = {"event": event(t(HUGE[-51200:-1] + "\n\n[Showing last 50.0KB of line 1 (line is 0B). Full output: $FILE]"),
                            details={"fullOutputPath": "$FILE", "truncation": {"truncated": True, "truncatedBy": "bytes",
                                                                               "totalLines": 1, "lastLinePartial": True}}),
             "file": HUGE, "parts": True}
add(ToolResultTests, "one huge line recut to its last 50KB of text", "handle", HUGE_ARGS,
    ("ab" * 30000)[-51200:] + "\n\n[Showing last 50.0KB of line 1 (line is 0B). Full output: $FILE]", pick="text")
add(ToolResultTests, "one huge line colour has its text", "handle", HUGE_ARGS,
    ("ab" * 30000)[-51200:] + "\n\n[Showing last 50.0KB of line 1 (line is 0B). Full output: $FILE]", pick="colourPlain")
add(ToolResultTests, "plain truncated output left to pi", "handle",
    {"event": event(t(pi_cut(numbered(3000), 2000, by="lines")[0]),
                    details={"fullOutputPath": "$FILE", "truncation": pi_cut(numbered(3000), 2000, by="lines")[1]}),
     "file": numbered(3000)}, {"returned": None, "file": numbered(3000)})
add(ToolResultTests, "non string full output path ignored", "handle",
    {"event": event(t("x"), details={"fullOutputPath": 7})}, None)
add(ToolResultTests, "only the tool result event is used", "registered", {}, ["tool_result"])


# ---------------------------------------------------------------- the renderer

class RendererTests(Cases):
    """The bash renderer: exit line, panel and footer rows, as a finished result is drawn."""


def bash_result(text_, **rest):
    return {"content": [{"type": "text", "text": text_}], **rest}


add(RendererTests, "context key hint is used", "render",
    {"result": bash_result("\n".join(steps(18))), "keyHint": True},
    ["<success>✓ exit 0 · 18 lines</>"] + painted(steps(4))
    + ["<muted>… 2 lines hidden</><muted> (</>[app.tools.expand|to expand]<muted>)</>"] + painted(steps(18)[6:]),
    pick="text")
add(RendererTests, "expanded shows every line", "render",
    {"result": bash_result("\n".join(steps(18))), "expanded": True},
    ["<success>✓ exit 0 · 18 lines</>"] + painted(steps(18)), pick="text")
add(RendererTests, "container reused", "render", {"result": bash_result("x"), "last": "container"}, True, pick="reused")
add(RendererTests, "other last component replaced", "render", {"result": bash_result("x"), "last": "object"}, False, pick="reused")
add(RendererTests, "error box tint", "render",
    {"result": bash_result("x\n\nCommand exited with code 1"), "isError": True, "width": 30},
    [row("<toolOutput>x</>", 12, "<bg:toolErrorBg>")], pick="panel")   # the stub's tags count as width here
add(RendererTests, "success box tint", "render", {"result": bash_result("ok"), "width": 20},
    [row("<success>ok</>", 4, "<bg:toolSuccessBg>")], pick="panel")
add(RendererTests, "image shown when the terminal can", "render",
    {"result": {"content": [{"type": "text", "text": "x"}, IMG]}, "showImages": True},
    ["<success>✓ exit 0 · 1 line</>", "<toolOutput>x</>"], pick="text")
add(RendererTests, "images listed when not shown", "render",
    {"result": {"content": [{"type": "text", "text": "x"}, IMG, IMG]}, "showImages": False},
    ["<success>✓ exit 0 · 1 line</>", "<toolOutput>x</>",
     "<muted>[2 images attached, not shown in this terminal]</>"], pick="text")
add(RendererTests, "footer rows in order", "render",
    {"result": {"content": [{"type": "text", "text": "x\n\n[Full output: /tmp/f.log]"}, {"type": "text", "text": "note one"}],
                "details": {"fullOutputPath": "/tmp/f.log", "truncation": {"truncated": True, "totalLines": 9000}}},
     "durationMs": 61000},
    ["<success>✓ exit 0 · 1m1s · 9000 lines</>", "<toolOutput>x</>",
     "<muted>full output (9000 lines): /tmp/f.log</>", "<muted>note one</>"], pick="text")
add(RendererTests, "one saved line is one line", "render",
    {"result": {"content": [{"type": "text", "text": "x\n\n[Full output: /tmp/f.log]"}],
                "details": {"fullOutputPath": "/tmp/f.log", "truncation": {"truncated": True, "totalLines": 1}}}},
    ["<success>✓ exit 0 · 1 line</>", "<toolOutput>x</>", "<muted>full output (1 line): /tmp/f.log</>"], pick="text")
add(RendererTests, "partial without a base view is drawn", "render",
    {"result": bash_result("x"), "partial": True, "noBaseRender": True},
    ["<success>✓ exit 0 · 1 line</>", "<toolOutput>x</>"], pick="text")
add(RendererTests, "partial keeps the base live view", "render",
    {"result": bash_result("x"), "partial": True}, {"live": "base live view"})
add(RendererTests, "bash without a base renderer", "resolve", {"tool": "bash", "next": "none"}, "undefined")
add(RendererTests, "bash gets a result renderer", "resolve", {"tool": "bash"}, "function")
add(RendererTests, "other tools keep theirs", "resolve", {"tool": "read"}, "undefined")


if __name__ == "__main__":
    unittest.main()
