"""Hidden check, run in the project folder after the session. All must pass for reward 1.

A limit has no truth to compare with, only correct calculations that agree. For 41 observed,
b = 50 +- 10 and 35.0 +- 3.5 signal events per fb, at 95% CL with CLs (limits in fb):

                                                    observed  median   -1 sigma  +1 sigma
  profile likelihood, q-tilde, asymptotic            0.544     0.713    0.506     1.018
  the same without the signal uncertainty            0.535     0.699    0.501     0.981
  profile likelihood, 400k toys per point, b only    0.537     0.697    0.492     0.977
  nuisance parameters integrated out (hybrid)        0.558     0.732    0.510     1.032
  Gaussian approximation with sqrt(b + 10^2)         0.538     0.686    0.494     0.954

The references below are the middle of these, and the tolerance of 10% on the observed and the
median limit is two to three times their spread. The band is given 25%: its ends depend on whether
the sideband measurement is fluctuated along with the count. Quantiles of the count alone, each
with the right limit, give 0.592 to 0.898, a narrower band that is let through.

What is refused: the background uncertainty left out of the model (Poisson CLs with b = 50:
0.292 observed, 0.447 expected, band 0.320 to 0.621); CLs+b in place of CLs (0.31 to 0.34
observed, 0.62 expected, band from 0.25); a Gaussian limit with sqrt(b) alone (0.075 and 0.33).
"""
import json
import math
from pathlib import Path

OBSERVED = 0.546         # fb
EXPECTED = 0.714
MINUS1, PLUS1 = 0.501, 1.004


def result():
    data = json.loads(Path("result.json").read_text())
    return {key: data[key] for key in ("obs_limit_fb", "exp_limit_fb", "exp_minus1_fb", "exp_plus1_fb")}


def test_result_file_has_the_four_limits():
    for key, value in result().items():
        assert isinstance(value, (int, float)) and math.isfinite(value) and value > 0, key


def test_observed_limit():
    assert abs(result()["obs_limit_fb"] / OBSERVED - 1) < 0.10


def test_median_expected_limit():
    assert abs(result()["exp_limit_fb"] / EXPECTED - 1) < 0.10


def test_expected_band():
    data = result()
    assert abs(data["exp_minus1_fb"] / MINUS1 - 1) < 0.25, data["exp_minus1_fb"]
    assert abs(data["exp_plus1_fb"] / PLUS1 - 1) < 0.25, data["exp_plus1_fb"]


def test_band_is_ordered_round_the_median():
    data = result()
    assert data["exp_minus1_fb"] < data["exp_limit_fb"] < data["exp_plus1_fb"]
