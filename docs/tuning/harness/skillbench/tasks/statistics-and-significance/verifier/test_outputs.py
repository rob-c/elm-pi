"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The counts (oracle/make_environment.py):

    ee      9 in the window, 3 in sidebands 1.5 times as wide: background 2.0 +- 1.2
    mumu    1 in the window, 2 in sidebands 4 times as wide:   background 0.5 +- 0.35

Nothing here is statistical: each number below is what a named method gives for
those counts, and the bands are drawn between the methods that are valid at
these counts and the ones that are not.
"""
import json
import math
from pathlib import Path


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_both_numbers():
    data = result()
    for key in ("significance_ee_sigma", "upper_limit_mumu_events"):
        assert isinstance(data[key], (int, float)) and not isinstance(data[key], bool) and math.isfinite(data[key]), key


def test_significance_allows_for_the_background_uncertainty():
    # With the sideband count as a Poisson number of its own: exact binomial test 2.16,
    # Li-Ma 2.46, profile likelihood with a Gaussian constraint on b 2.75.
    # With b = 2.0 taken as exact: Poisson 3.49, Asimov formula 3.62, s/sqrt(b) 4.95;
    # s/sqrt(b + sigma_b^2), Gaussian at nine events, 3.83.
    assert result()["significance_ee_sigma"] < 2.95


def test_significance_is_not_understated():
    # The lowest of the valid ones is the exact test, 2.16 (p = 0.0153, one-sided).
    assert result()["significance_ee_sigma"] > 1.95


def test_upper_limit_uses_the_poisson_distribution():
    # Classical Poisson 4.24, CLs 4.36, CLs with b averaged over the sidebands (the Bayesian
    # limit with a flat prior) 4.30, Feldman-Cousins 4.64.
    # Gaussian: 0.5 + 1.645 sqrt(1) = 2.15, with 1.96 and the background error 2.58.
    # Wilks' asymptotic formula, with one event, 3.2.
    assert result()["upper_limit_mumu_events"] > 3.9


def test_upper_limit_is_at_95_per_cent_one_sided():
    # The upper end of a central 95% interval (97.5% one-sided) is 5.07; 4.64 is the highest
    # of the 95% limits above.
    assert result()["upper_limit_mumu_events"] < 4.95
