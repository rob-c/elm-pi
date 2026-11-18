"""What the task is built to catch: the first two muons of each event taken as the pair, so a candidate
made with a third or fourth muon is never seen and no event has two; and sqrt(yield) as the error
of a sum of weights."""
import json

import awkward as ak
import numpy as np
import uproot

events = uproot.open("events.root:Events").arrays(library="ak")
events = events[events.nMuon >= 2]
pt1, pt2 = events.Muon_pt[:, 0], events.Muon_pt[:, 1]
eta1, eta2 = events.Muon_eta[:, 0], events.Muon_eta[:, 1]
phi1, phi2 = events.Muon_phi[:, 0], events.Muon_phi[:, 1]
mass = np.sqrt(2 * pt1 * pt2 * (np.cosh(eta1 - eta2) - np.cos(phi1 - phi2)))
selected = ((pt1 > 20) & (pt2 > 20) & (abs(eta1) < 2.4) & (abs(eta2) < 2.4)
            & (events.Muon_charge[:, 0] != events.Muon_charge[:, 1]) & (mass > 81) & (mass < 101))
total = float(ak.sum(events.weight[selected]))
json.dump({"pair_yield": total, "event_yield": total, "event_yield_unc": float(np.sqrt(total))}, open("result.json", "w"), indent=1)
print(total, int(ak.sum(selected)))
