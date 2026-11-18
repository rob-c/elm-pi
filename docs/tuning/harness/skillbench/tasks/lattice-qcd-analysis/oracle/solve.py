"""The reference solution: run in the project folder, writes result.json.

1. Monte Carlo history: the integrated autocorrelation time of C(t) at t = T/4,
   then bins at least four times as long (and the binned error is shown to
   have stopped rising there).
2. The correlator is periodic: fold C(t) with C(T - t) and fit
   A [exp(-m t) + exp(-m (T - t))].
3. Correlated fit, covariance of the mean from the bins. The window: the
   smallest t_min at which the correlated chi^2 is acceptable (p > 0.1) and
   stays so one step later; the result is then stable against t_min.
4. Error from the jackknife over bins, the whole fit redone in each sample.
5. Cross-checks, the second route to the same number: an uncorrelated fit in
   the same window with jackknife errors, and a bootstrap over the same bins.
6. MeV with hbar c / a, the uncertainty of a carried along.
"""
import json
import re

import h5py
import numpy as np
from scipy.optimize import least_squares
from scipy.stats import chi2 as chi2_distribution

notes = open("notes.md", encoding="utf-8").read()
spacing, digits = re.search(r"a = ([\d.]+)\((\d+)\) fm", notes).groups()
a_fm, a_err = float(spacing), int(digits) * 10.0 ** -len(spacing.split(".")[1])
hbarc = float(re.search(r"hbar c = ([\d.]+) MeV fm", notes).group(1))
with h5py.File("corr.h5", "r") as handle:
    data = handle["c2pt"][:]
N, T = data.shape
half = T // 2

folded = np.empty((N, half + 1))
folded[:, 0], folded[:, half] = data[:, 0], data[:, half]
folded[:, 1:half] = 0.5 * (data[:, 1:half] + data[:, :half:-1])


def binned(values, size):
    usable = (len(values) // size) * size
    return values[:usable].reshape(usable // size, size, -1).mean(axis=1)


# 1. Autocorrelation of C(T/4): tau_int with the window where the sum stops growing (W >= 6 tau).
series = folded[:, half // 2] - folded[:, half // 2].mean()
rho = np.array([np.mean(series[: N - k] * series[k:]) for k in range(N // 10)]) / np.mean(series ** 2)
tau = 0.5
for window in range(1, len(rho)):
    tau = 0.5 + rho[1:window + 1].sum()
    if window >= 6 * tau:
        break
BIN = next(size for size in range(1, N) if N % size == 0 and size >= 4 * tau)
naive_error = folded[:, half // 2].std(ddof=1) / np.sqrt(N)
print("tau_int = %.1f configurations; bins of %d (%d bins)" % (tau, BIN, N // BIN))
for size in (1, 2, 5, 10, BIN, 2 * BIN):
    blocks = binned(folded, size)[:, half // 2]
    print("  bin %3d: error of C(%d) is %.2f x the unbinned one" % (size, half // 2, blocks.std(ddof=1) / np.sqrt(len(blocks)) / naive_error))

bins = binned(folded, BIN)
NB = len(bins)


def model(parameters, t):
    return parameters[0] * (np.exp(-parameters[1] * t) + np.exp(-parameters[1] * (T - t)))


def fit(mean, weight, t, start):
    found = least_squares(lambda p: weight @ (model(p, t) - mean), start, method="lm")
    return found.x, float(np.sum(found.fun ** 2))


def analyse(samples, tmin, tmax, correlated=True):
    """am, its jackknife error, chi^2 and degrees of freedom for a cosh fit to t = tmin .. tmax."""
    t = np.arange(tmin, tmax + 1)
    window = samples[:, tmin:tmax + 1]
    count = len(window)
    mean = window.mean(axis=0)
    covariance = np.cov(window, rowvar=False) / count
    if not correlated:
        covariance = np.diag(np.diag(covariance))
    weight = np.linalg.cholesky(np.linalg.inv(covariance)).T
    best, chi2 = fit(mean, weight, t, (mean[0] * np.exp(0.3 * tmin), 0.3))
    total = window.sum(axis=0)
    leave_one_out = np.array([fit((total - row) / (count - 1), weight, t, best)[0][1] for row in window])
    error = np.sqrt((count - 1) / count * np.sum((leave_one_out - leave_one_out.mean()) ** 2))
    return best[1], error, chi2, len(t) - 2


# 3. The window. The midpoint t = T/2 is the noisiest point and is left out.
TMAX = half - 1
scan = {tmin: analyse(bins, tmin, TMAX) for tmin in range(2, TMAX - 2)}
for tmin, (am, error, chi2, dof) in scan.items():
    print("  t = %2d .. %d: a m = %.5f +- %.5f, chi2/dof = %.1f/%d, p = %.3f" % (tmin, TMAX, am, error, chi2, dof, chi2_distribution.sf(chi2, dof)))
acceptable = lambda tmin: chi2_distribution.sf(scan[tmin][2], scan[tmin][3]) > 0.1
TMIN = next(tmin for tmin in scan if tmin + 1 in scan and acceptable(tmin) and acceptable(tmin + 1))
am, am_err, chi2, dof = scan[TMIN]
assert abs(scan[TMIN + 1][0] - am) < scan[TMIN + 1][1], "not stable against t_min"

# 5. Second routes.
am_uncorrelated, err_uncorrelated, _, _ = analyse(bins, TMIN, TMAX, correlated=False)
assert abs(am_uncorrelated - am) < am_err, (am, am_uncorrelated)
assert 0.7 < err_uncorrelated / am_err < 1.5
rng = np.random.default_rng(1)
t = np.arange(TMIN, TMAX + 1)
weight = np.linalg.cholesky(np.linalg.inv(np.cov(bins[:, TMIN:TMAX + 1], rowvar=False) / NB)).T
resampled = [fit(bins[rng.integers(0, NB, NB), TMIN:TMAX + 1].mean(axis=0), weight, t, (1.0, am))[0][1] for _ in range(400)]
assert 0.7 < np.std(resampled, ddof=1) / am_err < 1.4, "jackknife and bootstrap disagree"
unbinned_error = analyse(folded, TMIN, TMAX)[1]

# 6. Physical units.
mass = am * hbarc / a_fm
mass_err = mass * np.hypot(am_err / am, a_err / a_fm)
json.dump({"am": am, "am_err": am_err, "mass_mev": mass, "mass_mev_err": mass_err, "tmin": TMIN, "tmax": TMAX},
          open("result.json", "w"), indent=1)
print("t = %d .. %d: a m = %.5f +- %.5f (chi2/dof %.1f/%d); uncorrelated fit %.5f +- %.5f; bootstrap error %.5f; "
      "without binning the error would be %.5f" % (TMIN, TMAX, am, am_err, chi2, dof, am_uncorrelated, err_uncorrelated,
                                                    np.std(resampled, ddof=1), unbinned_error))
print("m = %.1f +- %.1f MeV (statistical %.1f, scale %.1f)" % (mass, mass_err, mass * am_err / am, mass * a_err / a_fm))
