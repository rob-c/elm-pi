"""Writes environment/ for this task. The truth is printed here and copied to the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Data: events recorded through two primary datasets. One that fired both triggers is written once in
each, with the same run, luminosity block and event number. Event numbers restart in every run, so a
few distinct events share an event number across runs. Simulation: generator weights of +1 and -1.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

# run: (luminosity blocks recorded, good ranges). Run 392301 was bad throughout and is not in the list.
RUNS = {392117: (310, [[1, 142], [150, 310]]), 392164: (480, [[1, 73], [77, 395]]), 392205: (255, [[12, 255]]),
        392301: (190, []), 392338: (420, [[1, 204], [221, 409]]), 392391: (350, [[5, 350]])}
LUMI_PB, XSEC_PB = 4.7, 314.0
MC_PROCESSED, MC_SUMW = 6400, 3814.0          # before the skim: 5107 events of weight +1 and 1293 of -1
N_DATA, N_MC = 1900, 2400


def kinematics(n, top_like):
    """Columns common to data and simulation. `top_like` is the fraction of events with top-pair kinematics."""
    top = rng.random(n) < top_like
    flavour = np.where(rng.random(n) < 0.55, 13, 11)
    pt = np.round(25.0 + rng.exponential(np.where(top, 30.0, 22.0)), 1)
    eta = np.round(rng.uniform(-2.5, 2.5, n), 2)
    n_jets = 2 + rng.poisson(np.where(top, 2.1, 0.9))
    n_btag = rng.binomial(np.minimum(n_jets, 2), np.where(top, 0.62, 0.07))
    met = np.round(rng.gamma(2.0, np.where(top, 28.0, 20.0)), 1)
    # Nothing sits on a threshold: > and >= give the same events.
    pt[pt == 30.0] = 30.1
    met[met == 40.0] = 40.1
    eta[np.abs(eta) == 2.40] = 2.39
    # The lepton's own trigger fires on its plateau most of the time; the other one now and then.
    own = rng.random(n) < np.where(pt > 32, 0.93, 0.55)
    other = rng.random(n) < 0.09
    hlt_mu = np.where(flavour == 13, own, other)
    hlt_el = np.where(flavour == 11, own, other)
    return {"lep_flavour": flavour, "lep_pt": pt, "lep_eta": eta, "n_jets": n_jets, "n_btag": n_btag, "met": met,
            "hlt_mu": hlt_mu.astype(int), "hlt_el": hlt_el.astype(int)}


def passes(row):
    """The six cuts of notes.md after data quality, as a list of booleans in order."""
    trigger = (row["lep_flavour"] == 13 and row["hlt_mu"] == 1) or (row["lep_flavour"] == 11 and row["hlt_el"] == 1)
    return [trigger, row["lep_pt"] > 30 and abs(row["lep_eta"]) < 2.4, row["n_jets"] >= 4, row["n_btag"] >= 1, row["met"] > 40]


# --- data ---------------------------------------------------------------------------
events = []
columns = kinematics(4 * N_DATA, 0.30)
runs = list(RUNS)
share = np.array([RUNS[r][0] for r in runs], dtype=float)
taken = set()
i = 0
while len(events) < N_DATA:
    row = {key: value[i].item() for key, value in columns.items()}
    i += 1
    if not (row["hlt_mu"] or row["hlt_el"]):
        continue                                   # fired neither trigger: in no dataset
    run = int(rng.choice(runs, p=share / share.sum()))
    row.update(run=run, lumi=int(rng.integers(1, RUNS[run][0] + 1)), event=int(rng.integers(1, 40_000_000)))
    if (row["run"], row["event"]) in taken:
        continue
    taken.add((row["run"], row["event"]))
    events.append(row)
# Event numbers restart with each run: give 24 events the event number of an event in another run.
for a, b in rng.choice(len(events), size=(24, 2), replace=False):
    if events[a]["run"] != events[b]["run"] and (events[a]["run"], events[b]["event"]) not in taken:
        events[a]["event"] = events[b]["event"]
        taken.add((events[a]["run"], events[a]["event"]))

written = []
for row in events:
    if row["hlt_mu"]:
        written.append(dict(row, dataset="SingleMuon"))
    if row["hlt_el"]:
        written.append(dict(row, dataset="EGamma"))
# As after a merge of the two datasets' files: sorted by dataset, then by run and block.
written.sort(key=lambda r: (r["dataset"] != "SingleMuon", r["run"], r["lumi"], r["event"]))
header = ["run", "lumi", "event", "dataset", "hlt_mu", "hlt_el", "lep_flavour", "lep_pt", "lep_eta", "n_jets", "n_btag", "met"]
(out / "data.csv").write_text(",".join(header) + "\n" + "".join(",".join(str(row[key]) for key in header) + "\n" for row in written))
(out / "good_runs.json").write_text(json.dumps({str(run): ranges for run, (_, ranges) in RUNS.items() if ranges}, indent=1) + "\n")


def good(row):
    return any(low <= row["lumi"] <= high for low, high in RUNS[row["run"]][1])


data_flow = [0] * 6
for row in events:                                 # each event once: this is the truth
    alive = good(row)
    data_flow[0] += alive
    for step, ok in enumerate(passes(row), 1):
        alive = alive and ok
        data_flow[step] += alive
double = sum(1 for row in events if row["hlt_mu"] and row["hlt_el"])

# --- simulation ---------------------------------------------------------------------
columns = kinematics(N_MC, 1.0)
columns["gen_weight"] = np.where(rng.random(N_MC) < 0.202, -1, 1)
columns["pu_weight"] = np.round(np.clip(rng.normal(1.0, 0.18, N_MC), 0.4, 1.8), 3)
columns["sf_lepton"] = np.round(rng.normal(0.972, 0.015, N_MC), 3)
columns["sf_btag"] = np.round(rng.normal(0.955, 0.045, N_MC), 3)
columns["event"] = rng.choice(np.arange(1, MC_PROCESSED + 1), size=N_MC, replace=False)
order = np.argsort(columns["event"])
header = ["event", "gen_weight", "pu_weight", "sf_lepton", "sf_btag", "hlt_mu", "hlt_el", "lep_flavour", "lep_pt", "lep_eta", "n_jets", "n_btag", "met"]
mc_rows = [{key: columns[key][j].item() for key in header} for j in order]
(out / "ttbar.csv").write_text(",".join(header) + "\n" + "".join(",".join(str(row[key]) for key in header) + "\n" for row in mc_rows))

norm = XSEC_PB * LUMI_PB / MC_SUMW
mc_flow, final_w2, final_raw = [0.0] * 6, 0.0, 0
for row in mc_rows:
    weight = row["gen_weight"] * row["pu_weight"] * row["sf_lepton"] * row["sf_btag"] * norm
    alive = True
    mc_flow[0] += weight                           # no data-quality mask in simulation
    for step, ok in enumerate(passes(row), 1):
        alive = alive and ok
        mc_flow[step] += weight * alive
    final_w2 += weight**2 * alive
    final_raw += alive

(out / "notes.md").write_text("""# Lepton+jets selection, first 2026 collisions

`data.csv` is the lepton+jets skim of the first stable-beam runs, from the
SingleMuon and EGamma primary datasets (column `dataset`). The skim keeps
events with exactly one electron or muon candidate of pT > 25 GeV and at least
two jets. `ttbar.csv` is the same skim of the tt-bar simulation.

## Columns

| column | meaning |
|---|---|
| run, lumi, event | run number, luminosity block, event number (data) |
| event | event number (simulation) |
| hlt_mu, hlt_el | 1 if the single-muon / single-electron trigger fired |
| lep_flavour | 13 for a muon, 11 for an electron |
| lep_pt, lep_eta | the lepton's pT [GeV] and pseudorapidity |
| n_jets | jets with pT > 30 GeV and abs(eta) < 2.4, after removing jets within deltaR < 0.4 of the lepton |
| n_btag | how many of those jets are b-tagged (medium working point) |
| met | missing transverse momentum [GeV] |
| gen_weight, pu_weight, sf_lepton, sf_btag | simulation only: generator weight, pile-up weight, lepton and b-tagging scale factors |

## Selection, in this order

1. Data quality (data only): the luminosity block is in `good_runs.json`,
   which lists for each good run its ranges of good blocks, first and last
   included. Simulated events all pass.
2. Trigger: muon events (lep_flavour 13) need hlt_mu, electron events need hlt_el.
3. Lepton: pT > 30 GeV and abs(eta) < 2.4.
4. Jets: n_jets >= 4.
5. b-tag: n_btag >= 1.
6. Missing momentum: met > 40 GeV.

## Normalisation of the simulation

The good blocks correspond to an integrated luminosity of LUMI pb-1. The
tt-bar sample (lepton+jets, NLO generator with weights of +1 and -1) has a
cross-section times branching fraction of XSEC pb. PROCESSED events were
processed before the skim, with a sum of generator weights of SUMW. An event's
weight is the product of its four weight columns, normalised to the data's
luminosity.
""".replace("LUMI", "%.1f" % LUMI_PB).replace("XSEC", "%.1f" % XSEC_PB).replace("PROCESSED", str(MC_PROCESSED)).replace("SUMW", "%.0f" % MC_SUMW))

print("data: %d events, %d rows, %d in both datasets" % (len(events), len(written), double))
print("DATA_FLOW =", data_flow)
print("MC_FLOW =", [round(v, 3) for v in mc_flow])
print("MC_FINAL_UNC = %.3f   (raw %d; sqrt(yield) %.3f; yield/sqrt(raw) %.3f)" % (math.sqrt(final_w2), final_raw, math.sqrt(mc_flow[5]), mc_flow[5] / math.sqrt(final_raw)))
