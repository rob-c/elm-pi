"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# The response curves the calibration sample was drawn from, averaged over the analysis
# sample's own momenta (oracle/make_environment.py).
KAON_EFFICIENCY = 0.7514
PION_MISID = 0.0646
# Tolerances: over 120 other draws of the two samples an estimate binned in momentum scatters
# by 0.006 (kaons) and 0.0036 (pions), and four or five wide bins pull it by up to +0.012 and
# -0.003. On this draw, 4 to 20 equal bins, 8 logarithmic bins, 5 and 10 equal-population
# bins and a logistic fit give 0.748 to 0.763 and 0.059 to 0.065.


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_both_numbers():
    data = result()
    for key in ("kaon_efficiency", "pion_misid_rate"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_both_are_fractions():
    data = result()
    assert 0 < data["pion_misid_rate"] < data["kaon_efficiency"] < 1


def test_kaon_efficiency_is_for_the_analysis_momenta():
    # The calibration sample as a whole gives 0.854: its kaons are softer, where the cut is more efficient.
    assert abs(result()["kaon_efficiency"] - KAON_EFFICIENCY) < 0.03


def test_pion_misid_rate_is_for_the_analysis_momenta():
    # The calibration sample as a whole gives 0.033, half the rate at the analysis sample's momenta.
    assert abs(result()["pion_misid_rate"] - PION_MISID) < 0.015
