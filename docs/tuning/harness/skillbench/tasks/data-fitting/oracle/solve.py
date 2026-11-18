"""The reference solution: run in the project folder, writes result.json.

An exponential plus a constant, fitted to the counts in every channel by a
Poisson likelihood (most channels hold fewer than ten counts, a third none).
The expected counts in a channel are the model integrated over it. The half
life and its error follow from the decay constant; the goodness of fit is
Pearson's chi-square with the fitted expectation as the variance.
"""
import json

import numpy as np
from iminuit import Minuit
from scipy import stats

data = np.loadtxt("decay.csv", delimiter=",", skiprows=1)
start, n = data[:, 0], data[:, 1]
dwell = float(start[1] - start[0])
stop = start + dwell


def expected(first, lam, background):
    """Counts per channel: `first` from the activity in a channel at t = 0, `background` per channel."""
    return first / (lam * dwell) * (np.exp(-lam * start) - np.exp(-lam * stop)) + background


def cash(first, lam, background):
    mu = expected(first, lam, background)
    return 2 * np.sum(mu - n * np.log(mu))


results = []
for half_life_start in (20.0, 60.0, 200.0):          # the same minimum from three starts
    fit = Minuit(cash, first=float(n[:5].mean()), lam=np.log(2) / half_life_start, background=float(n[-50:].mean()) + 0.05)
    fit.errordef = 1.0
    fit.limits["first"] = fit.limits["lam"] = fit.limits["background"] = (1e-9, None)
    fit.migrad()
    fit.hesse()
    assert fit.valid, fit.fmin
    results.append(fit)
fit = min(results, key=lambda f: f.fval)
assert max(abs(f.values["lam"] / fit.values["lam"] - 1) for f in results) < 1e-3, "the starts disagree"

lam, lam_err = fit.values["lam"], fit.errors["lam"]
half_life = np.log(2) / lam
mu = expected(*fit.values)
chi2 = float(np.sum((n - mu) ** 2 / mu))
ndf = len(n) - 3
result = {
    "half_life_s": half_life,
    "half_life_unc_s": half_life * lam_err / lam,
    "background_cps": fit.values["background"] / dwell,
    "chi2": chi2,
    "ndf": ndf,
}
json.dump(result, open("result.json", "w"), indent=1)
print("half-life %.1f +- %.1f s, background %.3f +- %.3f /s, chi2/ndf %.0f/%d (p = %.2f)" % (
    half_life, result["half_life_unc_s"], result["background_cps"], fit.errors["background"] / dwell,
    chi2, ndf, stats.chi2.sf(chi2, ndf)))
