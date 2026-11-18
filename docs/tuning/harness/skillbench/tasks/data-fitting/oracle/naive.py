"""What the task is built to catch: least squares with sigma = sqrt(N) on channels that mostly hold a few counts.

The model is right (exponential plus constant) and so is the bookkeeping; the
estimator is the habit. curve_fit refuses sigma = 0, so the empty channels are
given sigma = 1 - the usual patch.
"""
import json

import numpy as np
from scipy.optimize import curve_fit

data = np.loadtxt("decay.csv", delimiter=",", skiprows=1)
t, n = data[:, 0] + 1.0, data[:, 1]
sigma = np.sqrt(np.maximum(n, 1))


def model(t, first, lam, background):
    return first * np.exp(-lam * t) + background


popt, pcov = curve_fit(model, t, n, p0=[n[0], np.log(2) / 50, n[-50:].mean()], sigma=sigma, absolute_sigma=True)
half_life = np.log(2) / popt[1]
chi2 = float(np.sum(((n - model(t, *popt)) / sigma) ** 2))
json.dump({
    "half_life_s": half_life,
    "half_life_unc_s": half_life * np.sqrt(pcov[1, 1]) / popt[1],
    "background_cps": popt[2] / 2.0,
    "chi2": chi2,
    "ndf": len(n) - 3,
}, open("result.json", "w"), indent=1)
print(half_life, popt[2] / 2.0, chi2 / (len(n) - 3))
