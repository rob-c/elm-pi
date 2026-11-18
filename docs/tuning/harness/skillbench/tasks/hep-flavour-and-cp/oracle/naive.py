"""What the task is built to catch: S and C fitted to the raw asymmetry, the mistag dilution
forgotten, and the tagging power taken from the total efficiency and the average mistag."""
import json

import numpy as np
import pandas as pd
from scipy import optimize

counts = pd.read_csv("counts.csv")
efficiency = {"A": 0.0439, "B": 0.1098, "C": 0.2154}
mistag = {"A": 0.08, "B": 0.24, "C": 0.40}
total = sum(efficiency.values())
average = sum(efficiency[k] * mistag[k] for k in efficiency) / total

merged = counts.groupby(["t_low_ps", "t_high_ps"], as_index=False)[["n_b0_tag", "n_b0bar_tag"]].sum()
t = 0.5 * (merged["t_low_ps"] + merged["t_high_ps"]).to_numpy()
n = (merged["n_b0bar_tag"] + merged["n_b0_tag"]).to_numpy()
asymmetry = ((merged["n_b0bar_tag"] - merged["n_b0_tag"]) / n).to_numpy()
error = np.sqrt((1 - asymmetry**2) / n)
(s, c), covariance = optimize.curve_fit(lambda x, s, c: s * np.sin(0.5065 * x) - c * np.cos(0.5065 * x), t, asymmetry,
                                        sigma=error, absolute_sigma=True)
json.dump({"tagging_power": total * (1 - 2 * average) ** 2, "S": s, "S_uncertainty": float(np.sqrt(covariance[0, 0])),
           "C": c, "C_uncertainty": float(np.sqrt(covariance[1, 1]))}, open("result.json", "w"))
