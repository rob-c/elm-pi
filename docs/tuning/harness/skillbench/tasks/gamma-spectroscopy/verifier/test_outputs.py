"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

TRUE_ACTIVITY = 41_300.0     # Bq on the reference date (oracle/make_environment.py)


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_both_numbers():
    data = result()
    for key in ("activity_bq", "uncertainty_bq"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_activity_is_right_to_three_per_cent():
    # Counting statistics are 0.2% and the efficiency 1.5%; real time for live time is 17% out
    # and no decay correction 23%.
    assert abs(result()["activity_bq"] / TRUE_ACTIVITY - 1) < 0.03


def test_activity_is_at_the_reference_date_not_the_count():
    assert result()["activity_bq"] > 0.9 * TRUE_ACTIVITY


def test_uncertainty_includes_the_efficiency():
    data = result()
    relative = data["uncertainty_bq"] / data["activity_bq"]
    assert 0.012 < relative < 0.04, "counting statistics alone are 0.2%; with the 1.5% efficiency, about 1.5%"
