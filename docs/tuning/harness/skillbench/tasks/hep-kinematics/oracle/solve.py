"""The reference solution: run in the project folder, writes result.json.

Everything to GeV; pion masses for the two pion tracks; four-vectors added, then the mass;
rapidity from E and pz; s = m_b^2 + m_t^2 + 2 E m_t with E the beam's total energy.
"""
import json

import numpy as np

M_P, M_PI = 0.938272, 0.139570       # GeV, from the table in notes.md (given there in MeV)
T_BEAM = 3.500                       # GeV, kinetic

tracks = np.genfromtxt("tracks.csv", delimiter=",", names=True)
clusters = np.genfromtxt("clusters.csv", delimiter=",", names=True)

total = np.zeros(4)                  # E, px, py, pz in GeV
for row in tracks:
    if abs(int(row["pdg_id"])) != 211:
        continue
    p = np.array([row["px"], row["py"], row["pz"]]) / 1000.0            # MeV to GeV
    total += np.concatenate([[np.sqrt(p @ p + M_PI**2)], p])
for row in clusters:
    e, theta, phi = row["energy"], row["theta"], row["phi"]             # already GeV
    total += e * np.array([1.0, np.sin(theta) * np.cos(phi), np.sin(theta) * np.sin(phi), np.cos(theta)])

mass = np.sqrt(total[0] ** 2 - total[1:] @ total[1:])
rapidity = 0.5 * np.log((total[0] + total[3]) / (total[0] - total[3]))
e_beam = T_BEAM + M_P
sqrt_s = np.sqrt(2 * M_P**2 + 2 * e_beam * M_P)
json.dump({"mass_gev": mass, "rapidity": rapidity, "sqrt_s_gev": sqrt_s}, open("result.json", "w"), indent=1)
print("mass %.4f GeV, rapidity %.4f, sqrt(s) %.4f GeV" % (mass, rapidity, sqrt_s))
