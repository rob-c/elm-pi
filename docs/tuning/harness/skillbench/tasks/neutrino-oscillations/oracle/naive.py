"""What the task is built to catch: the survival probability worked out once per analysis
bin, at its central energy, and multiplied by the bin's unoscillated events."""
import json

import numpy as np
import pandas as pd

spectrum = pd.read_csv("unoscillated.csv")
sin2_2theta = 4 * 0.545 * (1 - 0.545)
result = {}
for number, (first, last) in enumerate([(200, 400), (400, 600), (600, 800), (800, 1200), (1200, 2000), (2000, 3000)], 1):
    inside = (spectrum["e_low_mev"] >= first) & (spectrum["e_high_mev"] <= last)
    centre_gev = 0.5 * (first + last) / 1000.0
    survival = 1 - sin2_2theta * np.sin(1.267 * 2.47e-3 * 295.0 / centre_gev) ** 2
    result["n_osc_%d" % number] = float(spectrum.loc[inside, "events"].sum() * survival)
result["n_osc_total"] = float(sum(result.values()))
json.dump(result, open("result.json", "w"))
