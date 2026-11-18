"""What the task is built to catch: both files taken to be in MeV, pseudorapidity for the massive
system, and sqrt(s) = sqrt(2 m E) with the 3.5 GeV put in as the beam's energy."""
import json

import numpy as np

tracks = np.genfromtxt("tracks.csv", delimiter=",", names=True)
clusters = np.genfromtxt("clusters.csv", delimiter=",", names=True)
total = np.zeros(4)
for row in tracks:
    if abs(int(row["pdg_id"])) == 211:
        p = np.array([row["px"], row["py"], row["pz"]])
        total += np.concatenate([[np.sqrt(p @ p + 139.570**2)], p])
for row in clusters:
    e, theta, phi = row["energy"], row["theta"], row["phi"]
    total += e * np.array([1.0, np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)])
mass = np.sqrt(total[0] ** 2 - total[1:] @ total[1:]) / 1000.0
theta = np.arccos(total[3] / np.sqrt(total[1:] @ total[1:]))
eta = -np.log(np.tan(theta / 2))
sqrt_s = np.sqrt(2 * 0.938272 * 3.5)
json.dump({"mass_gev": mass, "rapidity": eta, "sqrt_s_gev": sqrt_s}, open("result.json", "w"), indent=1)
print(mass, eta, sqrt_s)
