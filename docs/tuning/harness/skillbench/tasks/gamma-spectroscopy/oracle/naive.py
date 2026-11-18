"""What the task is built to catch: gross counts in the peak, real time, no decay correction."""
import json

import numpy as np

data = np.loadtxt("spectrum.csv", delimiter=",", skiprows=1)
energy = 0.4 + 0.5 * data[:, 0]
gross = data[(energy > 1328) & (energy < 1337), 1].sum()
activity = gross / (0.002280 * 0.999826 * 3600.0)
json.dump({"activity_bq": activity, "uncertainty_bq": activity / np.sqrt(gross)}, open("result.json", "w"))
