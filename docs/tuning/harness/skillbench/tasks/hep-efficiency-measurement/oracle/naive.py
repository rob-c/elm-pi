"""What the task is built to catch: k/n with the normal-approximation error sqrt(e(1-e)/n) as the interval.

It is zero wide where no probe or every probe passes, and too narrow next to those bins.
"""
import json

import numpy as np

EDGES = [30, 40, 45, 48, 50, 52, 55, 60, 70, 90, 120, 200, 500]
data = np.loadtxt("probes.csv", delimiter=",", skiprows=1)
pt, fired = data[:, 1], data[:, 2] == 1
n = np.histogram(pt, EDGES)[0]
k = np.histogram(pt[fired], EDGES)[0]
eff = k / n
err = np.sqrt(eff * (1 - eff) / n)
json.dump({"efficiency": eff.tolist(), "lower": (eff - err).tolist(), "upper": (eff + err).tolist()}, open("result.json", "w"), indent=1)
