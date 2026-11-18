"""What the task is built to catch: the response matrix inverted as it stands. With a resolution of one
bin width the inverse multiplies the statistical fluctuations of the data many times over, and the
answer swings up and down from one bin to the next. The errors are the Poisson ones put through
the same inverse - correct for this estimator, and enormous."""
import json

import numpy as np

spectra = np.genfromtxt("spectra.csv", delimiter=",", names=True)
matrix = np.loadtxt("response.csv", delimiter=",", skiprows=1)[:, 1:]
response = matrix / spectra["mc_truth"]
signal = spectra["data"] * (1 - spectra["mc_reco_fake"] / spectra["mc_reco"])
inverse = np.linalg.inv(response)
unfolded = inverse @ signal
uncertainty = np.sqrt((inverse**2) @ spectra["data"])
json.dump({"unfolded": unfolded.tolist(), "uncertainty": uncertainty.tolist()}, open("result.json", "w"), indent=1)
print(np.round(unfolded), np.round(uncertainty))
