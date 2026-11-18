"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The truth is the mass the correlator was generated with (oracle/make_environment.py):
a m0 = 0.2985, with a = 0.0847(12) fm that is 695.4 MeV.

Where the tolerances come from (120 replica ensembles generated like the data,
and every fit window on the data themselves):

- Mass. A cosh fit starting at t_min >= 7 scatters around the truth with a
  standard deviation of 0.0014 (t_min 7, 8) to 0.0023 (t_min 11); on this
  ensemble every window with t_min 7..13 and t_max 14..16, correlated or not,
  and a two-state fit from t = 1..4, lands within 0.0021 of the truth. The
  tolerance is 0.0045 (three standard deviations). Excited states push a
  correlated fit from t_min <= 4 up by 0.013 or more, and a plain exponential
  that ignores the backward-running term comes out 0.03 low.

- Uncertainty. The configurations are autocorrelated (tau_int = 6.2 by
  construction), so an error computed as if they were independent is about
  three times too small. Which error is right depends on the window, so the
  session reports its window and the check redoes a binned jackknife (bins of
  25 configurations, correlated cosh fit) in that window: the reported error
  must be at least half of it. Bins of 10 give 0.8 to 0.9 of it, bins of 5
  0.6 to 0.75, an uncorrelated fit or a bootstrap 1.0 to 1.2, no binning 0.3
  to 0.4. And no analysis of these data determines a m0 better than 0.0013
  (true scatter of the best fits, one- or two-state), so anything below
  0.00075 is refused whatever the window: unbinned two-state fits give 0.0004
  to 0.0007, binned ones 0.0009 or more. Above 0.009 (3%) it is not a
  determination: the worst sensible window gives 0.0035.

- MeV. m = a m x 197.327 / 0.0847. The scale is known to 1.4%, three times the
  statistical error, and belongs in the uncertainty of the MeV value: the
  quadrature sum is required to within 10%, and a linear sum is accepted.
"""
import json
import math
from pathlib import Path

import h5py
import numpy as np
from scipy.optimize import least_squares

TRUE_AM = 0.2985
A_FM, A_ERR, HBARC = 0.0847, 0.0012, 197.3269804
T = 32
KEYS = ("am", "am_err", "mass_mev", "mass_mev_err", "tmin", "tmax")


def result():
    data = json.loads(Path("result.json").read_text())
    for key in KEYS:
        assert isinstance(data[key], (int, float)) and not isinstance(data[key], bool) and math.isfinite(data[key]), key
    return data


def window(data):
    """The reported fit window on the folded correlator: t = tmin .. tmax with tmax at most T/2."""
    tmin, tmax = int(round(data["tmin"])), int(round(data["tmax"]))
    if tmax > T // 2:                    # a fit to the unfolded correlator, t and T - t both in the window
        tmax = T // 2
    assert 1 <= tmin and tmin + 2 <= tmax, "a window of at least three time slices between 1 and T/2"
    return tmin, tmax


def binned_jackknife_error(tmin, tmax, size=25):
    """Jackknife error of a m from a correlated cosh fit to t = tmin .. tmax, over bins of `size` configurations."""
    with h5py.File("corr.h5", "r") as handle:
        raw = handle["c2pt"][:]
    half = T // 2
    folded = np.empty((len(raw), half + 1))
    folded[:, 0], folded[:, half] = raw[:, 0], raw[:, half]
    folded[:, 1:half] = 0.5 * (raw[:, 1:half] + raw[:, :half:-1])
    bins = folded.reshape(len(raw) // size, size, half + 1).mean(axis=1)[:, tmin:tmax + 1]
    count = len(bins)
    t = np.arange(tmin, tmax + 1)
    weight = np.linalg.cholesky(np.linalg.inv(np.cov(bins, rowvar=False) / count)).T

    def mass(mean, start):
        model = lambda p: p[0] * (np.exp(-p[1] * t) + np.exp(-p[1] * (T - t)))
        return least_squares(lambda p: weight @ (model(p) - mean), start, method="lm").x

    best = mass(bins.mean(axis=0), (bins.mean(axis=0)[0] * math.exp(0.3 * tmin), 0.3))
    total = bins.sum(axis=0)
    samples = np.array([mass((total - row) / (count - 1), best)[1] for row in bins])
    return float(np.sqrt((count - 1) / count * np.sum((samples - samples.mean()) ** 2)))


def test_result_file_has_every_number():
    data = result()
    assert data["am"] > 0 and data["am_err"] > 0 and data["mass_mev"] > 0 and data["mass_mev_err"] > 0
    window(data)


def test_mass_is_the_ground_state():
    assert abs(result()["am"] - TRUE_AM) < 0.0045, "a m0 = 0.2985; excited states or the periodicity bias the fit"


def test_uncertainty_allows_for_autocorrelation():
    data = result()
    reference = binned_jackknife_error(*window(data))
    assert data["am_err"] >= 0.5 * reference, "binned jackknife in the reported window gives %.5f" % reference


def test_uncertainty_is_not_below_what_the_data_can_give():
    assert result()["am_err"] >= 0.00075, "the best fits to these data scatter by 0.0013"


def test_uncertainty_is_a_determination():
    assert result()["am_err"] <= 0.009


def test_mev_value_follows_from_the_lattice_value():
    data = result()
    assert abs(data["mass_mev"] / (data["am"] * HBARC / A_FM) - 1) < 2e-3


def test_mev_uncertainty_carries_the_scale():
    data = result()
    statistical, scale = data["am_err"] / data["am"], A_ERR / A_FM
    relative = data["mass_mev_err"] / data["mass_mev"]
    assert 0.9 * math.hypot(statistical, scale) <= relative <= 1.1 * (statistical + scale)
