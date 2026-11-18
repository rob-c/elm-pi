"""What the task is built to catch: everything added in quadrature as if independent.

The diagonal errors of A and sigma for each run's statistical error (the
covariance term left out), each run given the target and efficiency
uncertainties as its own, the two runs then averaged and compared as
independent measurements.
"""
import json

import numpy as np

beam = {1: 1.10e11, 2: 1.70e11}
target, efficiency = 2.40e19, 0.0183
syst_rel = np.hypot(0.04, 0.025)

x, stat, syst = [], [], []
for run in (1, 2):
    fit = json.load(open("fit_run%d.json" % run))
    A, mu, sigma, c = fit["values"]
    eA, emu, esigma, ec = fit["errors"]
    xsec = A * sigma * np.sqrt(2 * np.pi) / 2.0 / (beam[run] * target * efficiency) / 1e-27
    x.append(xsec)
    stat.append(xsec * np.hypot(eA / A, esigma / sigma))
    syst.append(xsec * syst_rel)
x, stat, syst = map(np.array, (x, stat, syst))
total = np.hypot(stat, syst)
w = 1 / total**2
mean = np.sum(w * x) / w.sum()
json.dump({
    "xsec_mb": mean,
    "stat_mb": np.sum(1 / stat**2) ** -0.5,
    "syst_mb": np.sum(1 / syst**2) ** -0.5,
    "runs_differ_sigma": abs(x[0] - x[1]) / np.hypot(*total),
}, open("result.json", "w"), indent=1)
