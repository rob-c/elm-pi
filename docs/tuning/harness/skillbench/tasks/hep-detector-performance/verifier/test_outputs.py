"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# The core resolution the data were drawn with (oracle/make_environment.py):
# sigma/E = 0.105/sqrt(E) (+) 0.28/E (+) 0.0075, which is 0.00969 at 300 GeV.
STOCHASTIC, NOISE, CONSTANT, AT_300 = 0.105, 0.28, 0.0075, 0.00969
# Tolerances: four times the fit's own errors with 2000 electrons at each of seven energies
# (0.0038, 0.014, 0.00044, and 0.00023 on the 300 GeV value). Tried against them and inside:
# a truncated-Gaussian likelihood fit of the core, a binned Gaussian fit over +-3 and +-4
# widths and over the full range, 2.5 sigma clipping, 1.48 x MAD and the smallest 68.3%
# interval, each with a weighted and an unweighted fit of the three terms.


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_four_numbers():
    data = result()
    for key in ("stochastic_term", "noise_term_gev", "constant_term", "resolution_at_300gev"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_stochastic_term():
    # Terms added linearly give 0.04 to 0.06 from the same widths; a fit without the noise
    # term 0.134; the value in per cent, 10.5.
    assert abs(abs(result()["stochastic_term"]) - STOCHASTIC) < 0.016


def test_noise_term():
    assert abs(abs(result()["noise_term_gev"]) - NOISE) < 0.06


def test_constant_term_is_the_cores():
    # The r.m.s. of everything, upstream showers included, is 6% of E at every energy and
    # comes out as a constant term of 0.059. Without the noise term the fit gives 0.0028.
    assert abs(abs(result()["constant_term"]) - CONSTANT) < 0.0018


def test_resolution_at_300_gev():
    # 0.060 from the r.m.s.; 0.0083 without the noise term; 0.97 if given in per cent.
    assert abs(result()["resolution_at_300gev"] - AT_300) < 0.001
