"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# From oracle/make_environment.py. The inputs are given numbers, so every one of these is
# arithmetic and a correct answer agrees to rounding: 1% on the values, 3% on the relative
# uncertainties. The yield was drawn for a true total of 395000 pb (fiducial 2468.6 pb); the
# measured values are 0.8 statistical standard deviations below.
FID_PB = 2452.06         # (27113 - 7250) / (13.333 pb^-1 x 0.60754)
TOT_PB = 392355.0        # FID_PB / (0.2520 x 0.0248)
STAT = 0.00829           # sqrt(27113) / 19863
SYST = 0.02809           # background 290/19863 and scale factors 2.4%, in quadrature
LUMI = 0.023
EXTRAP = 0.06805         # acceptance 6.5% and branching fraction 0.05/2.48, in quadrature
KEYS = ("fid_pb", "fid_stat_pb", "fid_syst_pb", "fid_lumi_pb", "tot_pb", "tot_stat_pb", "tot_syst_pb", "tot_lumi_pb", "tot_extrap_pb")


def result():
    return json.loads(Path("result.json").read_text())


def close(value, expected, tolerance):
    return abs(value / expected - 1) < tolerance


def test_result_file_has_the_nine_numbers():
    data = result()
    for key in KEYS:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_fiducial_cross_section():
    # With the recorded 800 pb^-1 instead of the 13.33 pb^-1 the prescaled trigger saw, it is 60
    # times too small; with fb^-1 left as it is, 1000 times off; with the efficiency of the
    # events that stay in the fiducial region (586300/1008000) instead of C, 4.5% too large;
    # divided by the acceptance or the branching fraction as well, 4 or 40 times too large.
    assert close(result()["fid_pb"], FID_PB, 0.01)


def test_total_cross_section():
    assert close(result()["tot_pb"], TOT_PB, 0.01)


def test_statistical_uncertainty_is_from_the_observed_count():
    # sqrt(N)/(N - B) = 0.83%; sqrt(N - B)/(N - B) = 0.71% leaves out the background's fluctuation.
    data = result()
    assert close(data["fid_stat_pb"] / data["fid_pb"], STAT, 0.03)
    assert close(data["tot_stat_pb"] / data["tot_pb"], STAT, 0.03)


def test_systematic_uncertainty_is_background_and_scale_factors_only():
    # 2.81%. With the luminosity folded in it is 3.63%; added linearly, 3.86%; with the
    # extrapolation folded in, 7.4%.
    data = result()
    assert close(data["fid_syst_pb"] / data["fid_pb"], SYST, 0.03)
    assert close(data["tot_syst_pb"] / data["tot_pb"], SYST, 0.03)


def test_luminosity_uncertainty_is_quoted_apart():
    data = result()
    assert close(data["fid_lumi_pb"] / data["fid_pb"], LUMI, 0.03)
    assert close(data["tot_lumi_pb"] / data["tot_pb"], LUMI, 0.03)


def test_extrapolation_uncertainty_of_the_total():
    # 6.5% and 2.0% in quadrature; linearly they would give 8.5%.
    data = result()
    assert close(data["tot_extrap_pb"] / data["tot_pb"], EXTRAP, 0.03)
