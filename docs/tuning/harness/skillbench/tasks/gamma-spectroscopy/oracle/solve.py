"""The reference solution: run in the project folder, writes result.json.

Net peak area from a Gaussian on a linear background (Poisson likelihood), live
time, efficiency interpolated in ln-ln, decay-corrected to the reference date.
"""
import json

import numpy as np
from iminuit import Minuit

data = np.loadtxt("spectrum.csv", delimiter=",", skiprows=1)
channel, counts = data[:, 0], data[:, 1]
energy = 0.4 + 0.5 * channel
window = (energy > 1312) & (energy < 1353)
x, n = energy[window], counts[window]


def model(area, mean, sigma, b0, b1):
    width = 0.5      # keV per channel
    return area * width * np.exp(-0.5 * ((x - mean) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi)) + b0 + b1 * (x - 1332.5)


def nll(area, mean, sigma, b0, b1):
    mu = np.clip(model(area, mean, sigma, b0, b1), 1e-9, None)
    return 2 * np.sum(mu - n * np.log(mu))


fit = Minuit(nll, area=n.sum(), mean=1332.5, sigma=0.8, b0=float(np.median(n)), b1=0.0)
fit.errordef = 1.0
fit.limits["sigma"] = (0.2, 3.0)
fit.migrad()
fit.hesse()
area, area_err = fit.values["area"], fit.errors["area"]

points = {600.0: 0.004350, 900.0: 0.003120, 1100.0: 0.002650, 1250.0: 0.002390, 1400.0: 0.002180, 1700.0: 0.001860}
coeffs = np.polyfit(np.log(list(points)), np.log(list(points.values())), 2)
eff = float(np.exp(np.polyval(coeffs, np.log(1332.492))))

live, intensity = 3000.0, 0.999826
half_life_s = 5.2711 * 365.25 * 86400
lam = np.log(2) / half_life_s
activity_at_count = area / (eff * intensity * live)
during = lam * 3600.0 / (1 - np.exp(-lam * 3600.0))            # decay during the count: 1.0000
since = np.exp(lam * 2.0 * 365.25 * 86400)                     # back to the reference date
activity = activity_at_count * during * since
relative = np.hypot(area_err / area, 0.015)
json.dump({"activity_bq": activity, "uncertainty_bq": activity * relative}, open("result.json", "w"), indent=1)
print("net area %.0f +- %.0f, efficiency %.6f, activity %.0f +- %.0f Bq" % (area, area_err, eff, activity, activity * relative))
