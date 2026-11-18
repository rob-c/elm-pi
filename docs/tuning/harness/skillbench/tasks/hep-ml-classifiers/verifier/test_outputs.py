"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
import re
from pathlib import Path

# From oracle/make_environment.py: validation's best working point, and what the test set
# gives there. All of it is arithmetic on the file, so a correct answer agrees to rounding;
# 1% is room for weights summed in single precision or read back rounded.
CUT = 0.70
ON_TEST = {"signal_events": 30.024, "background_events": 76.131, "significance": 3.2456, "signal_efficiency": 0.6672}
# For comparison, at the same cut validation gives s 31.18, b 66.09, Z 3.58, efficiency 0.693;
# train gives Z 4.36; all rows together s 95.5, b 193.6, Z 6.39.


def result():
    data = json.loads(Path("result.json").read_text())
    # "score > 0.75" names the same cut as 0.75: a run was failed on the spelling alone.
    if isinstance(data.get("cut"), str):
        found = re.findall(r"\d*\.\d+|\d+", data["cut"])
        if len(found) == 1:
            data["cut"] = float(found[0])
    return data


def test_result_file_has_the_five_numbers():
    data = result()
    for key in ("cut", *ON_TEST):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_working_point_is_the_one_validation_prefers():
    # Validation: 0.70 (Z 3.58, 2.5% above its second best, and s/sqrt(b) agrees).
    # Test's own best is 0.75, train's 0.80, all rows together 0.75.
    assert abs(result()["cut"] - CUT) < 0.001


def test_yields_are_the_test_sets():
    data = result()
    assert abs(data["signal_events"] / ON_TEST["signal_events"] - 1) < 0.01            # validation: 3.9% higher
    assert abs(data["background_events"] / ON_TEST["background_events"] - 1) < 0.01    # validation: 13% lower


def test_significance_is_the_test_sets():
    # Validation's own figure for its best point is 10% higher, test's own best point 5.5% higher.
    assert abs(result()["significance"] / ON_TEST["significance"] - 1) < 0.01


def test_signal_efficiency_is_the_test_sets():
    # Relative to the preselection: 30.024 of 45 expected events. Validation gives 0.693.
    assert abs(result()["signal_efficiency"] - ON_TEST["signal_efficiency"]) < 0.007
