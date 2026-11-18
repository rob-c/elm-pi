"""What the task is built to catch: sqrt(N) errors on a histogram of weighted events.

The weights are used for the background's size, and the normalisation and the
efficiency are propagated correctly. The background's error in a bin is taken
as sqrt(expected events), as if the simulation were a count: with events that
each stand for three, it is half the real one.
"""
import json

import numpy as np

edges = np.linspace(95, 155, 7)
scale = 61.5 * 36.1e3 / 7.403e5
data = np.loadtxt("data.csv", skiprows=1)
mc = np.loadtxt("background_mc.csv", delimiter=",", skiprows=1)
counts = np.histogram(data, edges)[0]
background = scale * np.histogram(mc[:, 0], edges, weights=mc[:, 1])[0]
signal = counts - background
signal_err = np.sqrt(counts + background)
total, total_err = signal.sum(), np.sqrt(np.sum(signal_err**2))
corrected = total / 0.584
json.dump({"signal": list(signal), "signal_unc": list(signal_err), "corrected_yield": corrected,
           "corrected_yield_unc": corrected * np.hypot(total_err / total, 0.032 / 0.584)}, open("result.json", "w"), indent=1)
