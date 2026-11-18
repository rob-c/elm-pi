"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# From oracle/make_environment.py. The yield is arithmetic on the card and the file, so every
# correct method gets the same number; the model the sample was drawn from gives 616.4, and
# the sample's estimate is 1.6 of its own standard errors below that.
EXPECTED = 579.86        # events: 0.050222 pb x 140 fb^-1 x 1148 / 13920
MC_ERROR = 23.16         # events: the same scale x sqrt(2102), the weights being +1 and -1


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_both_numbers():
    data = result()
    for key in ("expected_events", "mc_stat_uncertainty"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_expected_events_to_two_per_cent():
    # 2% is room for rounded inputs only. Without the k-factor the answer is 11% low; without
    # the filter efficiency 71% high; without the branching ratio ten times too large.
    assert abs(result()["expected_events"] / EXPECTED - 1) < 0.02


def test_not_normalised_by_the_number_of_events():
    # Dividing by the 40000 events written instead of their sum of weights, 13920, gives 0.35 of the answer.
    assert result()["expected_events"] > 0.6 * EXPECTED


def test_not_normalised_by_the_skimmed_file():
    # Dividing by the file's own sum of weights (5054) gives 2.75 times the answer; by its 9418 rows, 1.48 times.
    assert result()["expected_events"] < 1.3 * EXPECTED


def test_uncertainty_is_from_the_sum_of_squared_weights():
    # 2102 events of weight +1 and -1 sum to 1148: the relative error is sqrt(2102)/1148 = 4.0%,
    # not 1/sqrt(2102) = 2.2% and not 1/sqrt(1148) = 3.0%. 10% of it is room for how the
    # denominator's own fluctuation is treated.
    data = result()
    assert abs(data["mc_stat_uncertainty"] / MC_ERROR - 1) < 0.10
    assert 0.036 < data["mc_stat_uncertainty"] / data["expected_events"] < 0.044
