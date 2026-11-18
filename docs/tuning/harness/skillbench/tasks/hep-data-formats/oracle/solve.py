"""The reference solution: run in the project folder, writes result.json.

Events and luminosity from the same golden sections; an event that is in both
primary datasets counted once; the simulation normalised by the sum of
generator weights of everything generated (the Runs tree), not by what the
skim kept.
"""
import csv
import json
import re

import awkward as ak
import numpy as np
import uproot

notes = open("notes.md").read()
sigma_pb = float(re.search(r"Cross section ([0-9.]+) pb", notes).group(1))
pt_cut = float(re.search(r"both with pT > ([0-9.]+) GeV", notes).group(1))
eta_cut = float(re.search(r"abs\(eta\) < ([0-9.]+), and", notes).group(1))
m_low, m_high = (float(x) for x in re.search(r"([0-9.]+) < m\(mu mu\) < ([0-9.]+) GeV", notes).groups())
muon_mass = float(re.search(r"Muon mass ([0-9.]+) GeV", notes).group(1))
golden = {int(run): ranges for run, ranges in json.load(open("golden.json")).items()}


def certified(run, section):
    return any(first <= section <= last for first, last in golden.get(int(run), []))


def z_candidate(events):
    """Mask: the two leading muons pass the Z selection of notes.md."""
    pt, eta, phi = (ak.to_numpy(events["Muon_" + name][:, :2]).astype(np.float64) for name in ("pt", "eta", "phi"))
    charge = ak.to_numpy(events["Muon_charge"][:, :2])
    energy = np.sqrt((pt * np.cosh(eta)) ** 2 + muon_mass**2)
    px, py, pz = pt * np.cos(phi), pt * np.sin(phi), pt * np.sinh(eta)
    mass = np.sqrt(energy.sum(1) ** 2 - px.sum(1) ** 2 - py.sum(1) ** 2 - pz.sum(1) ** 2)
    return (np.all(pt > pt_cut, axis=1) & np.all(np.abs(eta) < eta_cut, axis=1) & (charge.sum(1) == 0)
            & (mass > m_low) & (mass < m_high))


# Luminosity: recorded, in the golden sections only; /ub to /pb.
lumi_pb = sum(float(row["recorded_per_ub"]) for row in csv.DictReader(open("lumi_by_ls.csv"))
              if certified(row["run"], int(row["ls"]))) / 1e6

# Data: both primary datasets, each event once, golden sections only.
seen = set()
for name in ("SingleMuon.root", "DoubleMuon.root"):
    events = uproot.open(name)["Events"].arrays()
    passed = z_candidate(events)
    for run, section, event, ok in zip(ak.to_list(events["run"]), ak.to_list(events["luminosityBlock"]), ak.to_list(events["event"]), passed):
        if ok and certified(run, section):
            seen.add((run, section, event))
n_data = len(seen)

# Simulation: sigma x L x (selected weights) / (weights of everything generated).
with uproot.open("DYJetsToLL_skim.root") as file:
    sum_w = float(np.sum(file["Runs"]["genEventSumw"].array(library="np")))
    events = file["Events"].arrays()
selected_w = float(np.sum(ak.to_numpy(events["genWeight"]).astype(np.float64)[z_candidate(events)]))
n_mc = sigma_pb * lumi_pb * selected_w / sum_w

json.dump({"n_data": n_data, "lumi_pb": lumi_pb, "n_mc_expected": n_mc}, open("result.json", "w"), indent=1)
print("luminosity %.4f pb^-1; %d Z candidates; simulation predicts %.1f (sum of weights %.4g, selected %.4g)"
      % (lumi_pb, n_data, n_mc, sum_w, selected_w))
