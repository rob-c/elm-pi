"""Hidden check, run in the project folder after the session. All must pass for reward 1.

scan.csv has 720 readings; 676 are written in nA and the 44 at or above
1000 nA in uA (the `unit` column). In nA, all of them:

    mean 961.7628, standard error 4.5506 (4.5474 with n in place of n - 1), median 941.7180

    68% interval of the median, by bootstrap (200 000 resamples, three seeds):
        percentile [939.88, 943.17]   basic [940.26, 943.55]   median +- sd [940.24, 943.19]
        with 200 to 1000 resamples the ends move by up to 0.2; order statistics give [939.88, 943.49]

With the current column taken as nA throughout: mean 882.21, standard error
8.42, median 937.29, interval about [936.2, 938.8].

The mean, standard error and median are arithmetic on the file and are held
tightly. The interval's ends are allowed 0.65 nA either side of the middle of
the valid methods, a fifth of the interval's width.
"""
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

KEYS = ("mean_na", "sem_na", "median_na", "median_lo_na", "median_hi_na")
SCAN_SHA256 = "d0e72ffaa2da79454da127255d9c289a97ab1a8015e7f1a622dbfca6e616c9bb"


def result(folder="."):
    return json.loads((Path(folder) / "result.json").read_text())


def test_result_file_has_the_five_numbers():
    data = result()
    for key in KEYS:
        assert isinstance(data[key], (int, float)) and not isinstance(data[key], bool) and math.isfinite(data[key]), key


def test_mean_and_standard_error_are_of_currents_in_one_unit():
    data = result()
    assert abs(data["mean_na"] - 961.7628) < 0.01
    assert abs(data["sem_na"] / 4.5506 - 1) < 0.01


def test_median():
    assert abs(result()["median_na"] - 941.718) < 0.01


def test_bootstrap_interval_of_the_median():
    data = result()
    assert 939.3 < data["median_lo_na"] < 940.6
    assert 942.6 < data["median_hi_na"] < 943.95


def test_rerunning_analysis_py_gives_the_same_numbers(tmp_path):
    # The script was asked for so that it can be rerun: on the same log it must give the same
    # numbers. A bootstrap drawn without a fixed seed moves the interval's ends by about 0.1.
    assert Path("analysis.py").is_file()
    before = result()
    work = tmp_path / "project"
    shutil.copytree(".", work, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", ".pi", ".venv", "__pycache__", ".pytest_cache", "node_modules"))
    (work / "result.json").unlink()
    env = {**os.environ, "MPLBACKEND": "Agg", "PYTHONDONTWRITEBYTECODE": "1"}
    for arguments in ([], ["scan.csv"]):                      # a script may take the log's name
        ran = subprocess.run([sys.executable, "analysis.py"] + arguments, cwd=str(work), capture_output=True, text=True,
                             timeout=300, env=env)
        if ran.returncode == 0 and (work / "result.json").is_file():
            break
    assert (work / "result.json").is_file(), "analysis.py did not write result.json where it was run: " + ran.stderr[-300:]
    after = result(work)
    for key in KEYS:
        assert abs(after[key] - before[key]) <= 1e-9 * abs(before[key]), key


def test_the_log_itself_was_not_changed():
    assert hashlib.sha256(Path("scan.csv").read_bytes()).hexdigest() == SCAN_SHA256
