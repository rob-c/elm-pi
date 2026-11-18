"""The reference solution: run in the project folder, writes result.json.

At each beam energy the Gaussian core is fitted (likelihood of a Gaussian
truncated to [mean - 2 sigma, mean + 2.5 sigma], iterated until the window
stops moving), which leaves the upstream-shower tail out. sigma/mean against
beam energy is then fitted with a/sqrt(E) (+) b/E (+) c, the terms in quadrature.
"""
import json

import numpy as np
import pandas as pd
from iminuit import Minuit
from scipy import optimize, stats

data = pd.read_csv("testbeam.csv")


def core(values):
    """Mean, sigma and sigma's error of the Gaussian core."""
    mean = np.median(values)
    sigma = 1.4826 * np.median(np.abs(values - mean))
    for _ in range(40):
        low, high = mean - 2.0 * sigma, mean + 2.5 * sigma
        inside = values[(values > low) & (values < high)]

        def nll(parameters):
            m, s = parameters
            if s <= 0:
                return 1e30
            fraction = stats.norm.cdf(high, m, s) - stats.norm.cdf(low, m, s)
            return -np.sum(stats.norm.logpdf(inside, m, s)) + len(inside) * np.log(fraction)

        best = optimize.minimize(nll, [mean, sigma], method="Nelder-Mead", options={"xatol": 1e-8, "fatol": 1e-8})
        moved = abs(best.x[1] - sigma) / sigma
        mean, sigma = best.x
        if moved < 1e-6:
            break
    step = 1e-3 * sigma
    curvature = (nll([mean, sigma + step]) - 2 * nll([mean, sigma]) + nll([mean, sigma - step])) / step**2
    return mean, sigma, 1 / np.sqrt(curvature)


energy, width, error = [], [], []
for beam, group in data.groupby("beam_energy_gev"):
    mean, sigma, sigma_error = core(group["e_reco_gev"].to_numpy())
    energy.append(float(beam))
    width.append(sigma / mean)                      # resolution relative to where the peak is
    error.append(sigma_error / mean)
    print("%5.0f GeV: peak %.4f of beam, sigma/E = %.4f +- %.4f" % (beam, mean / beam, sigma / mean, sigma_error / mean))
energy, width, error = (np.array(x) for x in (energy, width, error))


def model(e, a, b, c):
    return np.sqrt(a**2 / e + (b / e) ** 2 + c**2)


def chi2(a, b, c):
    return np.sum(((width - model(energy, a, b, c)) / error) ** 2)


fit = Minuit(chi2, a=0.1, b=0.2, c=0.01)
fit.errordef = 1.0
fit.limits = [(0, 1), (0, 5), (0, 0.2)]
fit.migrad()
fit.hesse()
a, b, c = fit.values
json.dump({"stochastic_term": a, "noise_term_gev": b, "constant_term": c, "resolution_at_300gev": float(model(300.0, a, b, c))},
          open("result.json", "w"), indent=1)
print("a = %.4f +- %.4f sqrt(GeV), b = %.3f +- %.3f GeV, c = %.5f +- %.5f; chi2 = %.1f for %d points"
      % (a, fit.errors["a"], b, fit.errors["b"], c, fit.errors["c"], fit.fval, len(energy)))
print("correlations: a-b %.2f, a-c %.2f, b-c %.2f; at 300 GeV %.5f"
      % (fit.covariance.correlation()[0, 1], fit.covariance.correlation()[0, 2], fit.covariance.correlation()[1, 2], model(300.0, a, b, c)))
