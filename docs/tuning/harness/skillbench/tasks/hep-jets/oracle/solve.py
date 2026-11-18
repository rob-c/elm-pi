"""The reference solution: run in the project folder, writes result.json.

Neutrinos dropped, as the jet definition says. Sequential recombination with the anti-kT measure,
d_ij = min(pT_i^-2, pT_j^-2) dR_ij^2 / R^2 and d_iB = pT_i^-2, where dR is in rapidity and
azimuth (wrapped); the closest pair is merged by adding four-momenta, or the object nearest the
beam becomes a jet. Not FastJet: the full distance matrix is recomputed at every step.
"""
import json

import numpy as np

R, PT_CUT = 0.4, 25.0

table = np.loadtxt("event.csv", delimiter=",", skiprows=1)
p = table[~np.isin(np.abs(table[:, 0]), (12, 14, 16)), 1:]          # px, py, pz, E
print("%d particles, %d after removing neutrinos" % (len(table), len(p)))

jets = []
while len(p):
    pt2 = p[:, 0] ** 2 + p[:, 1] ** 2
    y = 0.5 * np.log((p[:, 3] + p[:, 2]) / (p[:, 3] - p[:, 2]))
    phi = np.arctan2(p[:, 1], p[:, 0])
    dphi = np.abs(phi[:, None] - phi[None, :])
    dphi = np.where(dphi > np.pi, 2 * np.pi - dphi, dphi)
    d = np.minimum(1 / pt2[:, None], 1 / pt2[None, :]) * ((y[:, None] - y[None, :]) ** 2 + dphi**2) / R**2
    np.fill_diagonal(d, 1 / pt2)                                    # the diagonal holds the beam distances
    i, j = np.unravel_index(np.argmin(d), d.shape)
    if i == j:
        jets.append(p[i])
        p = np.delete(p, i, axis=0)
    else:
        p[i] = p[i] + p[j]
        p = np.delete(p, j, axis=0)

jets = np.array(jets)
pt = np.hypot(jets[:, 0], jets[:, 1])
lead = jets[np.argmax(pt)]
answer = {
    "n_jets": int(np.sum(pt > PT_CUT)),
    "lead_pt_gev": float(pt.max()),
    "lead_rapidity": float(0.5 * np.log((lead[3] + lead[2]) / (lead[3] - lead[2]))),
    "lead_mass_gev": float(np.sqrt(lead[3] ** 2 - lead[0] ** 2 - lead[1] ** 2 - lead[2] ** 2)),
}
json.dump(answer, open("result.json", "w"), indent=1)
print("jet pT:", np.round(np.sort(pt)[::-1][:7], 2))
print(answer)
