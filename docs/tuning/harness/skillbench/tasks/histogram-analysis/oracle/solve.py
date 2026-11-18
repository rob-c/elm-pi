"""The reference solution: run in the project folder, writes result.json.

The simulation is normalised to the data's luminosity: each event counts
weight x cross-section x luminosity / (sum of generated weights). Per bin the
background is that scale times the sum of weights, and its statistical error
the scale times sqrt(sum of squared weights). Signal = data - background, with
error sqrt(N + background error^2); a bin that comes out negative stays
negative. The corrected yield is the summed signal over the efficiency, the
efficiency's own uncertainty propagated (it is independent of these samples).
"""
import json
import re

import numpy as np

notes = open("notes.md").read()
low, high, nbins = re.search(r"(\d+) to (\d+) GeV in (\w+) bins", notes).groups()
edges = np.linspace(float(low), float(high), {"six": 6}[nbins] + 1)
xsec_pb = float(re.search(r"background process: ([\d.]+) pb", notes).group(1))
lumi_pb = float(re.search(r"data: ([\d.]+) fb\^-1", notes).group(1)) * 1000.0
sumw_generated = float(re.search(r"before any selection, is ([\d.e+]+)\.", notes).group(1))
eff, eff_err = [float(x) for x in re.search(r"is ([\d.]+) \+- ([\d.]+), from", notes).groups()]
scale = xsec_pb * lumi_pb / sumw_generated

data = np.loadtxt("data.csv", skiprows=1)
mc = np.loadtxt("background_mc.csv", delimiter=",", skiprows=1)
counts = np.histogram(data, edges)[0]
sumw = np.histogram(mc[:, 0], edges, weights=mc[:, 1])[0]
sumw2 = np.histogram(mc[:, 0], edges, weights=mc[:, 1] ** 2)[0]

background, background_err = scale * sumw, scale * np.sqrt(sumw2)
signal = counts - background
signal_err = np.sqrt(counts + background_err**2)
total, total_err = signal.sum(), np.sqrt(np.sum(signal_err**2))
corrected = total / eff
corrected_err = corrected * np.hypot(total_err / total, eff_err / eff)

print("scale %.4f events per unit weight; data outside the histogram: %d below, %d above" % (scale, (data < edges[0]).sum(), (data >= edges[-1]).sum()))
for i in range(len(counts)):
    print("%3.0f-%3.0f GeV: data %5d  background %7.1f +- %5.1f  signal %7.1f +- %5.1f" % (
        edges[i], edges[i + 1], counts[i], background[i], background_err[i], signal[i], signal_err[i]))
print("signal %.0f +- %.0f, corrected %.0f +- %.0f" % (total, total_err, corrected, corrected_err))
json.dump({"signal": [float(x) for x in signal], "signal_unc": [float(x) for x in signal_err],
           "corrected_yield": float(corrected), "corrected_yield_unc": float(corrected_err)}, open("result.json", "w"), indent=1)
