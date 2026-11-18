"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# What the counts were drawn with (oracle/make_environment.py), and the tagging table's own sum.
S_TRUE, C_TRUE = -0.58, 0.14
TAGGING_POWER = 0.06927          # 0.0439 x 0.84^2 + 0.1098 x 0.52^2 + 0.2154 x 0.20^2
# A fit of all categories, each with its dilution, has errors of 0.022 on S and 0.021 on C
# (29500 tagged candidates). Tried: a binomial likelihood (S -0.591, C 0.149), chi-square
# fits of the asymmetries per category (-0.595, 0.148), the merged sample divided by its
# average dilution (-0.596 +- 0.026, 0.132 +- 0.025), the best category alone (-0.624 +- 0.030).
# Tolerances on the values are four standard errors.


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_five_numbers():
    data = result()
    for key in ("tagging_power", "S", "S_uncertainty", "C", "C_uncertainty"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_tagging_power_is_summed_over_categories():
    # Total efficiency times the square of the average dilution gives 0.0509; the efficiency alone 0.369.
    assert abs(result()["tagging_power"] / TAGGING_POWER - 1) < 0.02


def test_s_is_corrected_for_the_mistag():
    # Fitted to the raw asymmetry S comes out at -0.22; with the tags the wrong way round, +0.59.
    assert abs(result()["S"] - S_TRUE) < 0.09


def test_c_is_corrected_and_has_the_stated_sign():
    # Raw: 0.05. In the other convention (A = -C): -0.15.
    assert abs(result()["C"] - C_TRUE) < 0.085


def test_uncertainties_include_the_dilution():
    # 0.022 and 0.021 from the full fit; 0.010 and 0.009 if the raw asymmetry's errors are quoted.
    data = result()
    assert 0.015 < data["S_uncertainty"] < 0.035
    assert 0.014 < data["C_uncertainty"] < 0.035
