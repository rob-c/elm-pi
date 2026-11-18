"""What the task is built to catch: the same loop with pseudorapidity where rapidity belongs - in the
distance between objects and for the jet that is reported. Hadrons of a few GeV near the edge of a
jet sit at a different place in eta than in y, and a jet has a mass."""
import json

import numpy as np

table = np.loadtxt("event.csv", delimiter=",", skiprows=1)
p = table[~np.isin(np.abs(table[:, 0]), (12, 14, 16)), 1:]


def pseudorapidity(v):
    momentum = np.sqrt(v[..., 0] ** 2 + v[..., 1] ** 2 + v[..., 2] ** 2)
    return np.arctanh(v[..., 2] / momentum)


jets = []
while len(p):
    pt2 = p[:, 0] ** 2 + p[:, 1] ** 2
    eta = pseudorapidity(p)
    phi = np.arctan2(p[:, 1], p[:, 0])
    dphi = np.abs(phi[:, None] - phi[None, :])
    dphi = np.where(dphi > np.pi, 2 * np.pi - dphi, dphi)
    d = np.minimum(1 / pt2[:, None], 1 / pt2[None, :]) * ((eta[:, None] - eta[None, :]) ** 2 + dphi**2) / 0.4**2
    np.fill_diagonal(d, 1 / pt2)
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
json.dump({"n_jets": int(np.sum(pt > 25)), "lead_pt_gev": float(pt.max()), "lead_rapidity": float(pseudorapidity(lead)),
           "lead_mass_gev": float(np.sqrt(lead[3] ** 2 - lead[0] ** 2 - lead[1] ** 2 - lead[2] ** 2))}, open("result.json", "w"), indent=1)
print(open("result.json").read())
