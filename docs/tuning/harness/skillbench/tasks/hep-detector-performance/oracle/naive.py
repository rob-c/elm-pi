"""What the task is built to catch: the standard deviation of everything at each energy,
upstream showers and all, taken as the resolution."""
import json

import numpy as np
import pandas as pd
from scipy import optimize

data = pd.read_csv("testbeam.csv")
groups = data.groupby("beam_energy_gev")["e_reco_gev"]
energy = np.array(list(groups.groups), dtype=float)
width = (groups.std() / groups.mean()).to_numpy()


def model(e, a, b, c):
    return np.sqrt(a**2 / e + (b / e) ** 2 + c**2)


(a, b, c), _ = optimize.curve_fit(model, energy, width, p0=(0.1, 0.2, 0.01), maxfev=20000)
json.dump({"stochastic_term": abs(a), "noise_term_gev": abs(b), "constant_term": abs(c),
           "resolution_at_300gev": float(model(300.0, a, b, c))}, open("result.json", "w"))
