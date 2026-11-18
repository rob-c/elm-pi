"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Both runs were simulated from a cross-section of 37.5 mb (oracle/make_environment.py).
From the two fit results, propagated with their covariance matrices:

    run 1   37.95 +- 0.97 mb (stat)      without the A-sigma covariance: +- 1.46
    run 2   36.87 +- 0.76 mb (stat)                                      +- 1.15
    common to both: target 4.0% and efficiency 2.5%, 4.72% together

    combined 37.29 +- 0.60 (stat) +- 1.76 (syst) mb; the runs differ by 0.88 sigma

The combination is 0.35 statistical standard deviations from the truth. The
same from a BLUE with the full 2x2 covariance in absolute errors:
37.22 +- 0.60 +- 1.76. With everything in quadrature as if independent:
37.36 +- 0.90 +- 1.25, and a difference of 0.35 sigma.

chi2 of the two runs about their mean is 0.78 for one degree of freedom, so no
convention scales the error up.
"""
import json
import math
from pathlib import Path


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_four_numbers():
    data = result()
    for key in ("xsec_mb", "stat_mb", "syst_mb", "runs_differ_sigma"):
        assert isinstance(data[key], (int, float)) and not isinstance(data[key], bool) and math.isfinite(data[key]), key


def test_combined_cross_section():
    # Half a statistical standard deviation: the two ways of weighting above are 0.06 mb apart,
    # and the unweighted mean of the runs is 37.41.
    assert abs(result()["xsec_mb"] - 37.29) < 0.30


def test_statistical_error_uses_the_fit_covariance():
    # 0.60 mb within 8% (linear propagation, sampling and the BLUE agree to 1%). Leaving out
    # the covariance of height and width (rho = -0.59) gives 0.90.
    assert 0.551 < result()["stat_mb"] < 0.647


def test_common_systematic_is_not_averaged_down():
    # 4.72% of the combined value, 1.76 mb, within 8%. Treated as independent between the
    # runs it comes out as 1.25.
    assert 1.618 < result()["syst_mb"] < 1.900


def test_runs_are_compared_without_the_common_uncertainty():
    # (37.95 - 36.87) / sqrt(0.97^2 + 0.76^2) = 0.88, within 10%. With the common 4.72% counted
    # in each run as its own: 0.39; with the diagonal fit errors as well: 0.35.
    assert 0.792 < result()["runs_differ_sigma"] < 0.968
