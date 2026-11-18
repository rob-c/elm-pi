"""The reference solution: run in the project folder, writes result.json.

Target A: Li and Ma's likelihood-ratio significance, with alpha the ratio of ON
to OFF live time. Target B: the Feldman-Cousins construction for a Poisson
count with known background, for the observed count and for the median count
expected from background alone; then the limit over area x time x containment.
"""
import csv
import json
import re

import numpy as np
from scipy import stats

notes = open("notes.md").read()
cl = float(re.search(r"at (\d+)% CL", notes).group(1)) / 100
area_cm2 = float(re.search(r"([0-9.]+e[+-]?\d+) m\^2", notes).group(1)) * 1e4
containment = float(re.search(r"puts (\d+)% of its gamma rays", notes).group(1)) / 100
targets = {row["target"]: {key: float(value) for key, value in row.items() if key != "target"}
           for row in csv.DictReader(open("counts.csv"))}

a = targets["A"]
alpha = a["t_on_h"] / a["t_off_h"]
n_on, n_off = a["n_on"], a["n_off"]
significance = np.sqrt(2 * (n_on * np.log((1 + alpha) / alpha * n_on / (n_on + n_off))
                            + n_off * np.log((1 + alpha) * n_off / (n_on + n_off))))


def unified_upper_limit(n_observed, background, step=0.001):
    """Feldman and Cousins: for each signal s, counts are accepted in decreasing order of
    P(n | s + b) / P(n | best physical s + b) until they hold the confidence level; the upper
    limit is the largest s that accepts the observed count."""
    n = np.arange(100)
    best = stats.poisson.pmf(n, np.maximum(n, background))
    limit = 0.0
    for signal in np.arange(0.0, 20.0, step):
        p = stats.poisson.pmf(n, signal + background)
        order = np.argsort(-p / best, kind="stable")
        if n_observed in order[: np.searchsorted(np.cumsum(p[order]), cl) + 1]:
            limit = signal
    return limit


b = targets["B"]
background = b["n_off"] * b["t_on_h"] / b["t_off_h"]
limit = unified_upper_limit(int(b["n_on"]), background)
expected = unified_upper_limit(int(stats.poisson.ppf(0.5, background)), background)
exposure = area_cm2 * b["t_on_h"] * 3600.0 * containment

json.dump({"significance_sigma": float(significance), "limit_counts": limit, "expected_limit_counts": expected,
           "flux_limit_cm2_s": limit / exposure}, open("result.json", "w"), indent=1)
print("A: alpha = %.3f, background %.1f, significance %.2f sigma" % (alpha, alpha * n_off, significance))
print("B: background %.2f, limit %.2f events (expected %.2f), exposure %.3e cm^2 s, flux < %.3e cm^-2 s^-1"
      % (background, limit, expected, exposure, limit / exposure))
