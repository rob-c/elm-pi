"""The reference solution: run in the project folder, writes result.json.

Each channel is an on/off counting experiment: n_on in the window, n_off in
sidebands tau times as wide, flat background, so b = n_off / tau with a Poisson
uncertainty of its own.

Significance (ee): the exact test of "no signal" given both counts. Under it
each of the n_on + n_off events falls in the window with probability
1 / (1 + tau), so p = P(Binomial >= n_on): no Gaussian approximation and the
background uncertainty is in it. Li-Ma's formula 17 is the asymptotic version.

Upper limit (mumu): CLs at 95%, the background averaged over what the sidebands
say about it (a flat prior on b gives Gamma(n_off + 1, 1/tau)). For a counting
experiment this is also the Bayesian limit with a flat prior on the signal.
"""
import csv
import json
import re

import numpy as np
from scipy import integrate, optimize, stats

regions = {}
for line in open("notes.md"):
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    numbers = [float(x) for x in re.findall(r"\d+\.\d+", line)]
    if line.startswith("|") and len(numbers) == 6:
        regions[cells[0]] = {"window": numbers[0:2], "sidebands": [numbers[2:4], numbers[4:6]]}

counts = {}
for channel, region in regions.items():
    masses = [float(row["mass_gev"]) for row in csv.DictReader(open("candidates.csv")) if row["channel"] == channel]
    inside = lambda low_high: sum(low_high[0] <= m < low_high[1] for m in masses)
    n_on, n_off = inside(region["window"]), sum(inside(band) for band in region["sidebands"])
    tau = sum(high - low for low, high in region["sidebands"]) / (region["window"][1] - region["window"][0])
    counts[channel] = (n_on, n_off, tau)
    print("%s: n_on %d, n_off %d, tau %.2f, background %.2f +- %.2f" % (channel, n_on, n_off, tau, n_off / tau, np.sqrt(n_off) / tau))

# --- significance of the ee excess
n_on, n_off, tau = counts["ee"]
p_value = stats.binom.sf(n_on - 1, n_on + n_off, 1 / (1 + tau))
significance = stats.norm.isf(p_value)
alpha = 1 / tau
li_ma = np.sqrt(2 * (n_on * np.log((1 + alpha) / alpha * n_on / (n_on + n_off)) + n_off * np.log((1 + alpha) * n_off / (n_on + n_off))))
print("ee: p = %.4f, Z = %.2f (exact); Li-Ma %.2f; with the background taken as known %.2f" % (
    p_value, significance, li_ma, stats.norm.isf(stats.poisson.sf(n_on - 1, n_off / tau))))

# --- 95% CL upper limit on the mumu signal
n_on, n_off, tau = counts["mumu"]


def averaged(signal):
    """P(N <= n_on | signal + b), averaged over b from the sidebands."""
    return integrate.quad(lambda b: stats.poisson.cdf(n_on, signal + b) * stats.gamma.pdf(b, n_off + 1, scale=1 / tau), 0, np.inf)[0]


limit = optimize.brentq(lambda s: averaged(s) / averaged(0.0) - 0.05, 0.0, 50.0)
known = optimize.brentq(lambda s: stats.poisson.cdf(n_on, s + n_off / tau) / stats.poisson.cdf(n_on, n_off / tau) - 0.05, 0.0, 50.0)
print("mumu: 95%% CL upper limit %.2f events (CLs, background averaged); %.2f with the background taken as known" % (limit, known))

json.dump({"significance_ee_sigma": float(significance), "upper_limit_mumu_events": float(limit)}, open("result.json", "w"), indent=1)
