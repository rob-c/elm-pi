"""The reference solution: run in the project folder, writes result.json.

In a category with mistag fraction w the measured asymmetry is (1 - 2w) times
S sin(dm t) - C cos(dm t). S and C are fitted to all categories and bins at
once, each bin's anti-B0-tagged count being binomial in the bin's total. The
tagging power is the sum over categories of efficiency x (1 - 2w)^2.
"""
import json
import re

import numpy as np
import pandas as pd
from iminuit import Minuit

notes = open("notes.md").read()
tagging = {name: (float(eff), float(mistag)) for name, eff, mistag in re.findall(r"\| (\w) \| ([0-9.]+) \| ([0-9.]+) \|", notes)}
dm = float(re.search(r"dm_d = ([0-9.]+) ps", notes).group(1))
resolution_ps = float(re.search(r"resolution: ([0-9.]+) fs", notes).group(1)) / 1000

power = sum(eff * (1 - 2 * mistag) ** 2 for eff, mistag in tagging.values())

counts = pd.read_csv("counts.csv")
t = 0.5 * (counts["t_low_ps"] + counts["t_high_ps"]).to_numpy()          # 0.5 ps bins: the centre is good to 0.3%
dilution = counts["category"].map(lambda name: 1 - 2 * tagging[name][1]).to_numpy()
dilution = dilution * np.exp(-0.5 * (dm * resolution_ps) ** 2)             # decay-time resolution: 0.9996 here
n_bbar, n_b = counts["n_b0bar_tag"].to_numpy(), counts["n_b0_tag"].to_numpy()


def nll(s, c):
    p = 0.5 * (1 + dilution * (s * np.sin(dm * t) - c * np.cos(dm * t)))      # probability of an anti-B0 tag
    return -2 * np.sum(n_bbar * np.log(p) + n_b * np.log(1 - p))


fit = Minuit(nll, s=0.0, c=0.0)
fit.errordef = 1.0
fit.limits = [(-1.5, 1.5), (-1.5, 1.5)]
fit.migrad()
fit.hesse()
result = {"tagging_power": power, "S": fit.values["s"], "S_uncertainty": fit.errors["s"],
          "C": fit.values["c"], "C_uncertainty": fit.errors["c"]}
json.dump(result, open("result.json", "w"), indent=1)
print("tagging power %.4f" % power)
print("S = %.3f +- %.3f, C = %.3f +- %.3f, correlation %.2f"
      % (result["S"], result["S_uncertainty"], result["C"], result["C_uncertainty"], fit.covariance.correlation()[0, 1]))
