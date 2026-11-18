"""The reference solution: run in the project folder, writes result.json.

Data: one row per (run, luminosity block, event) - events that fired both triggers are in both
primary datasets - then the good-run list and the cuts in order. Simulation: the product of the
weights times sigma L / sum of generator weights of all processed events; error sqrt(sum w^2).
"""
import json

import numpy as np
import pandas as pd

LUMI_PB, XSEC_PB, SUMW_PROCESSED = 4.7, 314.0, 3814.0        # notes.md


def cuts(t):
    trigger = ((t.lep_flavour == 13) & (t.hlt_mu == 1)) | ((t.lep_flavour == 11) & (t.hlt_el == 1))
    return [trigger, (t.lep_pt > 30) & (t.lep_eta.abs() < 2.4), t.n_jets >= 4, t.n_btag >= 1, t.met > 40]


data = pd.read_csv("data.csv")
rows = len(data)
data = data.drop_duplicates(subset=["run", "lumi", "event"])
print("%d rows, %d duplicates removed, %d events" % (rows, rows - len(data), len(data)))
good_runs = json.load(open("good_runs.json"))
good = np.array([any(low <= lumi <= high for low, high in good_runs.get(str(run), [])) for run, lumi in zip(data.run, data.lumi)])
alive = pd.Series(good, index=data.index)
data_flow = [int(alive.sum())]
for cut in cuts(data):
    alive &= cut
    data_flow.append(int(alive.sum()))

mc = pd.read_csv("ttbar.csv")
weight = mc.gen_weight * mc.pu_weight * mc.sf_lepton * mc.sf_btag * XSEC_PB * LUMI_PB / SUMW_PROCESSED
alive = pd.Series(True, index=mc.index)
mc_flow = [float(weight.sum())]
for cut in cuts(mc):
    alive &= cut
    mc_flow.append(float(weight[alive].sum()))
error = float(np.sqrt((weight[alive] ** 2).sum()))

json.dump({"data": data_flow, "ttbar": mc_flow, "ttbar_final_unc": error}, open("result.json", "w"), indent=1)
print("data ", data_flow)
print("ttbar", [round(v, 2) for v in mc_flow], "+-", round(error, 2), "(%d raw)" % alive.sum())
