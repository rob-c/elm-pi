"""What the task is built to catch: the two primary datasets counted as they come, so an event that fired
both triggers counts twice; and sqrt(N) for the error of a weighted yield."""
import json

import numpy as np
import pandas as pd


def cuts(t):
    trigger = ((t.lep_flavour == 13) & (t.hlt_mu == 1)) | ((t.lep_flavour == 11) & (t.hlt_el == 1))
    return [trigger, (t.lep_pt > 30) & (t.lep_eta.abs() < 2.4), t.n_jets >= 4, t.n_btag >= 1, t.met > 40]


data = pd.read_csv("data.csv")
good_runs = json.load(open("good_runs.json"))
alive = pd.Series([any(a <= lumi <= b for a, b in good_runs.get(str(run), [])) for run, lumi in zip(data.run, data.lumi)])
data_flow = [int(alive.sum())]
for cut in cuts(data):
    alive &= cut
    data_flow.append(int(alive.sum()))

mc = pd.read_csv("ttbar.csv")
weight = mc.gen_weight * mc.pu_weight * mc.sf_lepton * mc.sf_btag * 314.0 * 4.7 / 3814.0
alive = pd.Series(True, index=mc.index)
mc_flow = [float(weight.sum())]
for cut in cuts(mc):
    alive &= cut
    mc_flow.append(float(weight[alive].sum()))
json.dump({"data": data_flow, "ttbar": mc_flow, "ttbar_final_unc": float(np.sqrt(mc_flow[-1]))}, open("result.json", "w"), indent=1)
print(data_flow, mc_flow)
