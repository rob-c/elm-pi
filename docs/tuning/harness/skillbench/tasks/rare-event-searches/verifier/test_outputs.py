"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# From oracle/make_environment.py. Nothing here is statistical: the counts are given, and the
# Feldman-Cousins construction on a 0.001 grid reproduces the paper's table (n = 2 and 3 at
# b = 3.0: 3.04 and 4.42; n = 0 at b = 0: 2.44). 3% on the limits is room for a coarser grid.
LIMIT = 3.035                    # events, n = 2 on b = 3.0
EXPECTED = 4.424                 # events, n = 3: the median count for b = 3.0 (the mean limit is 4.41)
EXPOSURE = 1.1794e13             # cm^2 s: 5.2e8 cm^2 x 32400 s x 0.70


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_four_numbers():
    data = result()
    for key in ("significance_sigma", "limit_counts", "expected_limit_counts", "flux_limit_cm2_s"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_significance_counts_the_off_measurements_fluctuation():
    # Li and Ma: 4.149; the exact binomial test: 4.105. Excess / sqrt(background) gives 5.02,
    # excess / sqrt(N_on) 3.97, the known-background formula 4.61, excess / sqrt(alpha (N_on + N_off)) 4.37.
    assert 4.05 < result()["significance_sigma"] < 4.25


def test_limit_is_feldman_cousins():
    # The classical one-sided limit is 2.32, CLs (and the flat-prior Bayesian) 3.52,
    # n - b + 1.28 sqrt(n) 0.81, and 2.30 or 2.44 are the limits for no events and no background.
    assert abs(result()["limit_counts"] / LIMIT - 1) < 0.03


def test_expected_limit():
    # The limit for the median background-only count, n = 3. For n = 2 it is the observed 3.04.
    assert abs(result()["expected_limit_counts"] / EXPECTED - 1) < 0.03


def test_exposure_has_area_time_and_containment():
    # Independent of the limit itself: flux limit over count limit is 1 / exposure. Without
    # the 70% containment the exposure is 1.43 times larger; m^2 left as they are, 10^4 smaller.
    data = result()
    assert abs(data["flux_limit_cm2_s"] / data["limit_counts"] * EXPOSURE - 1) < 0.01


def test_flux_limit():
    assert abs(result()["flux_limit_cm2_s"] / (LIMIT / EXPOSURE) - 1) < 0.03
