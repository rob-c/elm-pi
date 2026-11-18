"""What the task is built to catch: the golden JSON applied to the events but the luminosity
taken for the whole of the certified runs, the two primary datasets simply added, and the
simulation normalised by the weights that are in the skim."""
import csv
import json

import awkward as ak
import numpy as np
import uproot

golden = {int(run): ranges for run, ranges in json.load(open("golden.json")).items()}


def z_candidate(events):
    pt, eta, phi = (ak.to_numpy(events["Muon_" + name][:, :2]).astype(np.float64) for name in ("pt", "eta", "phi"))
    charge = ak.to_numpy(events["Muon_charge"][:, :2])
    mass = np.sqrt(2 * pt[:, 0] * pt[:, 1] * (np.cosh(eta[:, 0] - eta[:, 1]) - np.cos(phi[:, 0] - phi[:, 1])))
    return np.all(pt > 25, axis=1) & np.all(np.abs(eta) < 2.4, axis=1) & (charge.sum(1) == 0) & (mass > 80) & (mass < 100)


lumi_pb = sum(float(row["recorded_per_ub"]) for row in csv.DictReader(open("lumi_by_ls.csv")) if int(row["run"]) in golden) / 1e6
n_data = 0
for name in ("SingleMuon.root", "DoubleMuon.root"):
    events = uproot.open(name)["Events"].arrays()
    good = np.array([any(a <= ls <= b for a, b in golden.get(run, [])) for run, ls in zip(ak.to_list(events["run"]), ak.to_list(events["luminosityBlock"]))])
    n_data += int(np.sum(z_candidate(events) & good))
events = uproot.open("DYJetsToLL_skim.root")["Events"].arrays()
weights = ak.to_numpy(events["genWeight"]).astype(np.float64)
n_mc = 6077.22 * lumi_pb * weights[z_candidate(events)].sum() / weights.sum()
json.dump({"n_data": n_data, "lumi_pb": lumi_pb, "n_mc_expected": n_mc}, open("result.json", "w"))
