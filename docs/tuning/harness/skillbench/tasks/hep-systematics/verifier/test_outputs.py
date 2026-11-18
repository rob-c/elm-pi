"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Nothing here is statistical: the yields are the nominal ones times chosen shifts
(oracle/make_environment.py), and notes.md fixes the conventions, so the totals are arithmetic.
The 4% tolerance is for the choices the conventions leave open - the ratio's shift from the varied
ratio (6.44%) or linearised as the difference of the two regions' shifts (6.38%), the larger side
instead of half the difference (SR 11.8% for 11.6%), yields rounded to 0.1 event. The mistakes are
far outside it: the single variations halved gives 8.7% for SR and 5.8% for the ratio; the regions
added as if independent, 10.4% to 13.9% for the ratio; the b-tagging shifts subtracted without
their signs, 4.9%; the simulation statistics left out, 6.0%.
"""
import json
import math
from pathlib import Path

TRUE_TF = 412.6 / 2954.1
TRUE_SR_PERCENT = 11.578
TRUE_TF_PERCENT = 6.437


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_three_numbers():
    data = result()
    for key in ("transfer_factor", "tf_syst_percent", "sr_syst_percent"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_transfer_factor_is_the_nominal_ratio():
    assert abs(result()["transfer_factor"] / TRUE_TF - 1) < 0.005


def test_signal_region_total_takes_single_variations_in_full():
    assert abs(result()["sr_syst_percent"] / TRUE_SR_PERCENT - 1) < 0.04


def test_ratio_total_lets_common_sources_cancel_and_opposite_ones_add():
    assert abs(result()["tf_syst_percent"] / TRUE_TF_PERCENT - 1) < 0.04
