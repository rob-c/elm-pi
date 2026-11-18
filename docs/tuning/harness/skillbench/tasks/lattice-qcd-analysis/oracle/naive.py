"""What the task is built to catch: a quick exponential fit to the averaged correlator.

A single exp(-m t) from where the effective mass first looks roughly flat by
eye to the middle of the lattice, each time slice weighted by its standard
error over the 1000 configurations as if they were independent and the slices
uncorrelated, the error taken from the fit's covariance matrix, and the MeV
value given the same relative error.
"""
import json

import h5py
import numpy as np
from scipy.optimize import curve_fit

with h5py.File("corr.h5", "r") as handle:
    data = handle["c2pt"][:]
mean = data.mean(axis=0)
sem = data.std(axis=0, ddof=1) / np.sqrt(len(data))
TMIN, TMAX = 5, 16
t = np.arange(TMIN, TMAX + 1)
best, covariance = curve_fit(lambda t, amplitude, mass: amplitude * np.exp(-mass * t), t, mean[t], p0=(mean[0], 0.3),
                             sigma=sem[t], absolute_sigma=True)
am, am_err = best[1], np.sqrt(covariance[1, 1])
to_mev = 197.3269804 / 0.0847
json.dump({"am": am, "am_err": am_err, "mass_mev": am * to_mev, "mass_mev_err": am_err * to_mev, "tmin": TMIN, "tmax": TMAX},
          open("result.json", "w"), indent=1)
