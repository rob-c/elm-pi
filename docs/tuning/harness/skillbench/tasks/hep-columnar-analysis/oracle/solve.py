"""The reference solution: run in the project folder, writes result.json.

Object cuts on the muons (every event kept, its list shortened), all pairs within an event with
ak.combinations, each once; charge and mass cuts on the pairs; then one number per event - how many
pairs it has - against the per-event weight. Weighted error: sqrt(sum of squared weights).
"""
import json

import awkward as ak
import numpy as np
import uproot

M_MU = 0.10566

tree = uproot.open("events.root:Events")
events = tree.arrays(["weight", "Muon_pt", "Muon_eta", "Muon_phi", "Muon_charge"], library="ak")
assert len(events) == tree.num_entries
muons = ak.zip({"pt": events.Muon_pt, "eta": events.Muon_eta, "phi": events.Muon_phi, "charge": events.Muon_charge})
muons = muons[(muons.pt > 20) & (abs(muons.eta) < 2.4)]
weight = ak.to_numpy(events.weight).astype(np.float64)

pair = ak.combinations(muons, 2, fields=["a", "b"])


def four_vector(mu):
    pt, eta, phi = (ak.values_astype(mu[name], np.float64) for name in ("pt", "eta", "phi"))
    px, py, pz = pt * np.cos(phi), pt * np.sin(phi), pt * np.sinh(eta)
    return np.sqrt(px**2 + py**2 + pz**2 + M_MU**2), px, py, pz


ea, xa, ya, za = four_vector(pair.a)
eb, xb, yb, zb = four_vector(pair.b)
mass = np.sqrt((ea + eb) ** 2 - (xa + xb) ** 2 - (ya + yb) ** 2 - (za + zb) ** 2)
candidate = (pair.a.charge * pair.b.charge < 0) & (mass > 81) & (mass < 101)
per_event = ak.to_numpy(ak.sum(candidate, axis=1))            # one count per event, same length as the weights
assert len(per_event) == len(weight)

has = per_event > 0
answer = {"pair_yield": float(np.sum(weight * per_event)), "event_yield": float(np.sum(weight[has])),
          "event_yield_unc": float(np.sqrt(np.sum(weight[has] ** 2)))}
json.dump(answer, open("result.json", "w"), indent=1)
print("%d events read, %d with a candidate, %d with more than one, %d pairs" % (len(weight), has.sum(), (per_event > 1).sum(), per_event.sum()))
print(answer)
