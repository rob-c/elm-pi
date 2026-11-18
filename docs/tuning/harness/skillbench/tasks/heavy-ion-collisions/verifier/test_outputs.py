"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Truth (oracle/make_environment.py): the tracks were generated with v2 = 0.100 and
nothing else. What correct methods get from the 750 events in the file:

  two sub-events, alternate tracks, sub-event resolution 0.42   0.0959 +- 0.0059 (the oracle)
  the same with four random splits                              0.096 to 0.099
  full plane less the track, resolution carried up from 0.42    0.094 to 0.100
  scalar product                                                0.096 to 0.098
  two-particle cumulant v2{2}                                   0.0976 +- 0.0045
  four-particle cumulant v2{4}                                  0.0975

so the statistical error is 0.005 to 0.006 and the tolerance is 0.015, three of them.
What the careless ones get: a sub-event plane with no resolution correction 0.041; the
full plane less the track, uncorrected, 0.056; the track left in its own plane 0.145,
and 0.26 once that is divided by the resolution.

sqrt(s_NN) = sqrt(2 m^2 + 2 m (T + m)) = 7.737 GeV with T = 30.0 and m = 0.9389 GeV
(7.734 with the proton mass); T taken as the total energy gives 7.622, 1.5% low.
"""
import json
import math
from pathlib import Path

TRUE_V2 = 0.100
SQRT_SNN_GEV = 7.737


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_three_numbers():
    data = result()
    for key in ("v2", "v2_stat", "sqrt_snn_gev"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_v2_is_corrected_for_the_event_plane_resolution():
    assert result()["v2"] > 0.075, "uncorrected values are 0.04 to 0.06"


def test_no_track_is_in_its_own_event_plane():
    assert result()["v2"] < 0.125, "autocorrelation gives 0.145 or more"


def test_v2_within_three_standard_errors_of_the_truth():
    assert abs(result()["v2"] - TRUE_V2) < 0.015


def test_statistical_uncertainty_is_of_the_right_size():
    # 0.0045 (cumulant, bootstrap) to 0.008 (sub-event plane, error of the mean over the resolution).
    assert 0.002 < result()["v2_stat"] < 0.012


def test_sqrt_snn_for_a_fixed_target():
    assert abs(result()["sqrt_snn_gev"] / SQRT_SNN_GEV - 1) < 0.004
