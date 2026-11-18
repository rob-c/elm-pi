"""The reference solution: run in the project folder, writes result.json.

k of n per bin, the estimate k/n, and the central 68.3% Clopper-Pearson interval
from the beta quantiles, with lower = 0 at k = 0 and upper = 1 at k = n.
"""
import json

import numpy as np
from scipy.stats import beta

EDGES = [30, 40, 45, 48, 50, 52, 55, 60, 70, 90, 120, 200, 500]
data = np.loadtxt("probes.csv", delimiter=",", skiprows=1)
pt, fired = data[:, 1], data[:, 2] == 1
n = np.histogram(pt, EDGES)[0]
k = np.histogram(pt[fired], EDGES)[0]
tail = (1 - 0.683) / 2
lower = np.where(k == 0, 0.0, beta.ppf(tail, np.maximum(k, 1), n - k + 1))
upper = np.where(k == n, 1.0, beta.ppf(1 - tail, k + 1, np.maximum(n - k, 1)))
json.dump({"efficiency": (k / n).tolist(), "lower": lower.tolist(), "upper": upper.tolist()}, open("result.json", "w"), indent=1)
for row in zip(EDGES[:-1], EDGES[1:], k, n, k / n, lower, upper):
    print("%3d-%3d  %3d / %3d  %.4f  [%.4f, %.4f]" % row)
