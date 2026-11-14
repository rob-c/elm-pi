"""Eight harder tasks for the tuning runs: multi-file, debugging, tests that must catch a bug.

Imported by ab6.py. Each task: (prompt, check, extra files for that task's project).
"""
import json
import subprocess
import sys
import textwrap

BINNING = textwrap.dedent('''\
    def bin_edges(lo, hi, n):
        """n equal bins between lo and hi: n + 1 edges, lo first and hi last."""
        width = (hi - lo) / n
        return [lo + i * width for i in range(n)]


    def bin_index(x, lo, hi, n):
        """The bin x falls in, or None outside [lo, hi)."""
        if not lo <= x < hi:
            return None
        return int((x - lo) / ((hi - lo) / n))
    ''')
BINNING_TEST = textwrap.dedent('''\
    import unittest

    from src.binning import bin_edges, bin_index


    class BinningTests(unittest.TestCase):
        def test_edges(self):
            self.assertEqual([0.0, 2.5, 5.0, 7.5, 10.0], bin_edges(0, 10, 4))

        def test_index(self):
            self.assertEqual(1, bin_index(3, 0, 10, 4))
            self.assertIsNone(bin_index(10, 0, 10, 4))
    ''')


def run(project, *args, cwd_python=sys.executable):
    return subprocess.run([cwd_python, *args], cwd=project, capture_output=True, text=True, timeout=120)


def unit(project, *names):
    return run(project, "-m", "unittest", *names).returncode == 0


def check_move(project, reply):
    conv = project / "src/conversions.py"
    units = (project / "src/units.py").read_text()
    report = (project / "src/report.py").read_text()
    return (conv.exists() and "def kmh(" in conv.read_text() and "def kmh(" not in units
            and "conversions" in report and unit(project, "tests.test_units"))


def check_debug(project, reply):
    return ((project / "tests/test_binning.py").read_text() == BINNING_TEST
            and unit(project, "tests.test_binning"))


def check_tests_catch(project, reply):
    """Their tests pass on the real code and fail on a broken clean()."""
    test = project / "tests/test_pipeline.py"
    if not test.exists() or test.read_text().count("def test") < 3:
        return False
    if not unit(project, "tests.test_pipeline"):
        return False
    pipeline = project / "src/pipeline.py"
    real = pipeline.read_text()
    try:
        pipeline.write_text(real.replace('r["counts"] >= 0', 'r["counts"] >= -100'))
        caught = not unit(project, "tests.test_pipeline")
    finally:
        pipeline.write_text(real)
    return caught


def check_fit(project, reply):
    try:
        tau = float((project / "results/tau.txt").read_text().strip())
    except (OSError, ValueError):
        return False
    return 4.9 <= tau <= 5.1


def check_cli(project, reply):
    r = run(project, "-m", "src.report", "car", "10")
    return r.stdout.strip() == "car: 36.0 km/h" and unit(project, "tests.test_units")


def check_mph(project, reply):
    r = run(project, "-c", textwrap.dedent('''\
        from src.report import speed_line
        assert speed_line("car", 10) == "car: 36.0 km/h", speed_line("car", 10)
        assert speed_line("car", 10, units="mph") == "car: 22.4 mph", speed_line("car", 10, units="mph")
        print("ok")
        '''))
    test = (project / "tests/test_units.py").read_text()
    return r.stdout.strip() == "ok" and "mph" in test and unit(project, "tests.test_units")


def check_zero(project, reply):
    text = reply.strip().strip("`").replace(" ", "")
    return text in ("src/stats.py:mean", "stats.py:mean", "src/stats.py:mean()")


def check_pipeline_run(project, reply):
    try:
        data = json.loads((project / "results/background.json").read_text())
    except (OSError, ValueError):
        return False
    return data == {"rows": 3, "total": 32} and "32" in reply


HARD = {
    "x_move": ("Move the function `kmh` out of src/units.py into a new module src/conversions.py (same name, same "
               "behaviour), update every import of it, and run `python3 -m unittest tests.test_units`. Reply with "
               "its last line.", check_move, {}),
    "x_debug": ("tests/test_binning.py fails. Find the bug in src/ and fix it without changing the test, then run "
                "`python3 -m unittest tests.test_binning` and reply with its last line.", check_debug,
                {"src/binning.py": BINNING, "tests/test_binning.py": BINNING_TEST}),
    "x_tests": ("Write tests/test_pipeline.py: at least three unittest tests covering load, clean and summarise in "
                "src/pipeline.py, using a temporary directory for files. They must pass. Reply with the command you "
                "ran and its last line.", check_tests_catch, {}),
    "x_fit": ("Fit N(t) = N0 * exp(-t / tau) to data/decay.csv (columns t, counts) by least squares on the counts "
              "themselves, not their logarithm. Write tau to results/tau.txt with two decimal places, and reply with "
              "the value.", check_fit, {}),
    "x_cli": ("Make `python3 -m src.report car 10` print `car: 36.0 km/h` (name, then speed in m/s). speed_line must "
              "keep working as it does. Run it and reply with what it printed.", check_cli, {}),
    "x_mph": ("Give speed_line in src/report.py a keyword argument `units`: 'kmh' (the default, as now) or 'mph' "
              "(1 m/s = 2.236936 mph, one decimal, labelled mph, e.g. `car: 22.4 mph`). Add a test for mph to "
              "tests/test_units.py and run that test file. Reply with its last line.", check_mph, {}),
    "x_zero": ("One function in src/ raises ZeroDivisionError when given a list with one element. Find it. Reply "
               "exactly as `file:function`, for example `src/x.py:f`.", check_zero, {}),
    "x_run": ("Use the functions in src/pipeline.py to load data/background.csv, clean it, and summarise it into "
              "results/background.json (create the folder). Reply with the total it wrote.", check_pipeline_run, {}),
}
