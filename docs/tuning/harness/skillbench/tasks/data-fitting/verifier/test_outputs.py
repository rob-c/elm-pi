"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The data were drawn from a half-life of 61.3 s on a background of 0.225 /s
(oracle/make_environment.py). A Poisson likelihood fit of this dataset gives
61.8 +- 2.8 s and 0.229 +- 0.026 /s whichever way it is done (iminuit on the
bin integrals, scipy on the bin centres, ExtendedBinnedNLL: all within 0.02 s),
and over 200 toy datasets it is unbiased with a spread of 2.7 s and 0.023 /s.
"""
import json
import math
from pathlib import Path

TRUE_HALF_LIFE = 61.3        # s
TRUE_BACKGROUND = 0.225      # counts per second
CHANNELS = 400


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_five_numbers():
    data = result()
    for key in ("half_life_s", "half_life_unc_s", "background_cps", "chi2", "ndf"):
        assert isinstance(data[key], (int, float)) and not isinstance(data[key], bool) and math.isfinite(data[key]), key


def test_half_life_is_within_the_statistics():
    # 4.5 s is 1.6 standard deviations of the likelihood fit, which is 0.5 s from the truth on
    # this dataset. Least squares with sigma = sqrt(max(N, 1)) gives 52.6 s here (8.5 +- 2.0 s
    # low over the toys), with sqrt(N + 1) 55.4 s, with the empty channels dropped 47.3 s.
    assert abs(result()["half_life_s"] - TRUE_HALF_LIFE) < 4.5


def test_uncertainty_is_the_statistical_one():
    # HESSE gives 2.80 s, MINOS +2.89 -2.71 s, the spread over toys 2.7 s: 2.8 s within 20%.
    assert 2.25 < result()["half_life_unc_s"] < 3.4


def test_background_rate_is_within_the_statistics():
    # 0.055 /s is 2.4 standard deviations (0.023 /s over the toys); the likelihood fit is
    # 0.004 /s from the truth. sqrt(N + 1) weights give 0.129 /s, five channels summed and
    # then sqrt(N) weights 0.153 /s.
    assert abs(result()["background_cps"] - TRUE_BACKGROUND) < 0.055


def test_ndf_counts_the_three_free_parameters():
    # Amplitude, decay constant and background from 400 channels: 397, or fewer if channels were summed.
    ndf = result()["ndf"]
    assert ndf == int(ndf) and 1 <= ndf <= CHANNELS - 3


def test_chi2_agrees_with_ndf():
    # The data come from the model, so chi2/ndf is 1 within three times sqrt(2/ndf); 0.15 more is
    # allowed for the choice of statistic at these counts. At the likelihood fit Pearson's
    # chi-square is 362/397 = 0.91, the deviance 392/397 = 0.99, and with the channels summed in
    # tens 47/37. The sqrt(max(N, 1)) fit's own chi2/ndf is 0.59, six standard deviations low.
    data = result()
    ndf = data["ndf"]
    assert ndf >= 1
    assert abs(data["chi2"] / ndf - 1) < 3 * math.sqrt(2 / ndf) + 0.15
