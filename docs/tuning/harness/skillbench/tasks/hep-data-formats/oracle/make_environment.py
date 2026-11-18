"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A small CMS-style dimuon analysis: two primary datasets that share most of
their events, a golden JSON that drops one run and parts of the others, a
luminosity table per luminosity section in /ub, and a skimmed NanoAOD-like
simulation whose sum of generator weights is in its Runs tree. The numbers are
fixed by the seed; the ROOT files' bytes are not (uproot stamps them with the
time and a UUID).
"""
import json
import sys
from pathlib import Path

import awkward as ak
import numpy as np
import uproot

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

MUON_MASS = 0.105658
SIGMA_DY_PB = 6077.22            # DY -> ll, all three flavours, m(ll) > 50 GeV
N_GENERATED = 7500
GEN_WEIGHT = 23641.2             # |genWeight| of an aMC@NLO event; 16% are negative
NTUPLE_PB = 1320.0               # what the data are drawn with: dimuons reaching the ntuple, 93% of them Z -> mumu.
                                 # The simulation puts 1390 pb there before any efficiency correction.
RUNS = {279760: 96, 279766: 120, 279794: 88, 279823: 104, 279841: 72}     # run: luminosity sections
GOLDEN = {279760: [[1, 38], [44, 96]], 279766: [[12, 120]], 279823: [[1, 57], [63, 88], [95, 104]], 279841: [[5, 72]]}
PT_SKIM, PT_CUT, ETA_CUT, M_LOW, M_HIGH = 20.0, 25.0, 2.4, 80.0, 100.0


def dimuons(n, signal_fraction):
    """n dimuon events: (pt, eta, phi, charge) arrays of shape (n, 2), leading muon first."""
    signal = rng.random(n) < signal_fraction
    mass = np.where(signal, 91.19 + 1.25 * rng.standard_cauchy(n) + rng.normal(0, 1.4, n), 50 + rng.exponential(35, n))
    mass = np.clip(mass, 40, 200)
    pt_z, y_z, phi_z = rng.exponential(7.0, n), rng.normal(0, 1.5, n), rng.uniform(-np.pi, np.pi, n)
    cos_t, phi_s = rng.uniform(-1, 1, n), rng.uniform(-np.pi, np.pi, n)
    p_star = np.sqrt(np.clip(mass**2 / 4 - MUON_MASS**2, 0, None))
    sin_t = np.sqrt(1 - cos_t**2)
    rest = np.stack([p_star * sin_t * np.cos(phi_s), p_star * sin_t * np.sin(phi_s), p_star * cos_t], axis=1)
    m_t = np.hypot(mass, pt_z)
    boson = np.stack([pt_z * np.cos(phi_z), pt_z * np.sin(phi_z), m_t * np.sinh(y_z)], axis=1)
    energy = m_t * np.cosh(y_z)
    muons = []
    for sign in (1, -1):
        p, e = sign * rest, mass / 2
        along = np.sum(p * boson, axis=1)
        lab = p + boson * ((along / (energy + mass) + e) / mass)[:, None]
        pt = np.hypot(lab[:, 0], lab[:, 1])
        muons.append((pt, np.arcsinh(lab[:, 2] / pt), np.arctan2(lab[:, 1], lab[:, 0])))
    charge = np.where(rng.random(n) < 0.5, 1, -1)
    same_sign = ~signal & (rng.random(n) < 0.25)           # fakes in the continuum
    pt = np.stack([muons[0][0], muons[1][0]], axis=1).astype(np.float32)
    eta = np.stack([muons[0][1], muons[1][1]], axis=1).astype(np.float32)
    phi = np.stack([muons[0][2], muons[1][2]], axis=1).astype(np.float32)
    q = np.stack([charge, np.where(same_sign, charge, -charge)], axis=1).astype(np.int32)
    order = np.argsort(-pt, axis=1)
    return tuple(np.take_along_axis(x, order, axis=1) for x in (pt, eta, phi, q))


def in_ntuple(pt, eta):
    """The ntuple's own acceptance: both muons above the skim threshold and inside the muon system."""
    return np.all(pt > PT_SKIM, axis=1) & np.all(np.abs(eta) < ETA_CUT, axis=1)


def candidate(pt, eta, phi, q):
    """The Z selection of notes.md, on the stored (single-precision) values."""
    pt, eta, phi = (x.astype(np.float64) for x in (pt, eta, phi))
    e = np.sqrt((pt * np.cosh(eta)) ** 2 + MUON_MASS**2)
    px, py, pz = pt * np.cos(phi), pt * np.sin(phi), pt * np.sinh(eta)
    mass = np.sqrt(np.clip(e.sum(1) ** 2 - px.sum(1) ** 2 - py.sum(1) ** 2 - pz.sum(1) ** 2, 0, None))
    near_edge = (np.abs(mass - M_LOW) < 0.02) | (np.abs(mass - M_HIGH) < 0.02) | np.any(np.abs(pt - PT_CUT) < 0.005, axis=1)
    passed = np.all(pt > PT_CUT, axis=1) & np.all(np.abs(eta) < ETA_CUT, axis=1) & (q.sum(1) == 0) & (mass > M_LOW) & (mass < M_HIGH)
    return passed, near_edge


def write_tree(file, name, columns):
    """A TTree (uproot's plain assignment writes an RNTuple since 5.7); a record array becomes nMuon and Muon_*."""
    tree = file.mktree(name, {key: (value.type if isinstance(value, ak.Array) else value.dtype) for key, value in columns.items()})
    tree.extend(columns)


def with_soft_muons(pt, eta, phi, q):
    """About one event in twenty has a third, soft muon: the arrays are jagged, as in NanoAOD."""
    n = len(pt)
    extra = rng.random(n) < 0.05
    soft = (rng.uniform(3, 12, n).astype(np.float32), rng.uniform(-2.4, 2.4, n).astype(np.float32),
            rng.uniform(-np.pi, np.pi, n).astype(np.float32), np.where(rng.random(n) < 0.5, 1, -1).astype(np.int32))
    counts = np.where(extra, 3, 2)
    fields = {}
    for name, two, third in zip(("pt", "eta", "phi", "charge"), (pt, eta, phi, q), soft):
        full = np.concatenate([two, third[:, None]], axis=1)
        keep = np.arange(3)[None, :] < counts[:, None]
        fields[name] = ak.unflatten(full[keep], counts)
    return ak.zip(fields)


# --- luminosity per luminosity section, and the golden JSON ---------------------------
lumi_rows, recorded = [], {}
for run, sections in RUNS.items():
    start = rng.uniform(2100, 2900)                         # /ub per section at the start of the fill: low pile-up
    for ls in range(1, sections + 1):
        rec = start * np.exp(-ls / 400.0) * rng.uniform(0.97, 1.03)
        recorded[(run, ls)] = round(rec, 1)
        lumi_rows.append("%d,%d,%.1f,%.1f\n" % (run, ls, rec / rng.uniform(0.92, 0.96), rec))
(out / "lumi_by_ls.csv").write_text("run,ls,delivered_per_ub,recorded_per_ub\n" + "".join(lumi_rows))
(out / "golden.json").write_text(json.dumps({str(run): ranges for run, ranges in GOLDEN.items()}) + "\n")
good = {(run, ls) for run, ranges in GOLDEN.items() for first, last in ranges for ls in range(first, last + 1)}
lumi_good_pb = sum(recorded[key] for key in good) / 1e6
lumi_all_pb = sum(recorded.values()) / 1e6

# --- data: events in every section, good or not, spread over two primary datasets -----
run_col, ls_col = [], []
for (run, ls), rec in recorded.items():
    n = rng.poisson(NTUPLE_PB * rec / 1e6)
    run_col += [run] * n
    ls_col += [ls] * n
n = len(run_col)
run_col, ls_col = np.array(run_col, dtype=np.uint32), np.array(ls_col, dtype=np.uint32)
pt, eta, phi, q = dimuons(3 * n, 0.93)
keep = in_ntuple(pt, eta) & ~candidate(pt, eta, phi, q)[1]  # nothing within 20 MeV of a mass cut or 5 MeV of the pT cut
pt, eta, phi, q = (x[keep][:n] for x in (pt, eta, phi, q))
assert len(pt) == n
event_col = rng.choice(np.arange(10_000_000, 90_000_000), size=n, replace=False).astype(np.uint64)
order = np.lexsort((event_col, ls_col, run_col))
run_col, ls_col, event_col, pt, eta, phi, q = (x[order] for x in (run_col, ls_col, event_col, pt, eta, phi, q))
muons = with_soft_muons(pt, eta, phi, q)
single = rng.random(n) < 0.93                               # fired the single-muon trigger
double = ~single | (rng.random(n) < 0.62)                   # fired the double-muon trigger: every event fires one of them
for name, fired in (("SingleMuon", single), ("DoubleMuon", double)):
    with uproot.recreate(out / (name + ".root"), compression=uproot.ZLIB(6)) as file:
        write_tree(file, "Events", {"run": run_col[fired], "luminosityBlock": ls_col[fired], "event": event_col[fired],
                                    "Muon": muons[fired]})

passed, _ = candidate(pt, eta, phi, q)
is_good = np.array([(int(r), int(l)) in good for r, l in zip(run_col, ls_col)])
n_data = int(np.sum(passed & is_good))

# --- simulation: DY -> ll, skimmed to two muons; the sum of weights is in Runs --------
gen_weight = np.where(rng.random(N_GENERATED) < 0.16, -GEN_WEIGHT, GEN_WEIGHT).astype(np.float32)
is_mumu = rng.random(N_GENERATED) < 1 / 3                   # ee and tautau leave no two muons
pt, eta, phi, q = dimuons(N_GENERATED, 1.0)
kept = is_mumu & in_ntuple(pt, eta) & ~candidate(pt, eta, phi, q)[1]
files = np.sort(rng.integers(0, 3, N_GENERATED))            # the skim was merged from three files
with uproot.recreate(out / "DYJetsToLL_skim.root", compression=uproot.ZLIB(6)) as file:
    write_tree(file, "Events", {"genWeight": gen_weight[kept], "Muon": with_soft_muons(pt[kept], eta[kept], phi[kept], q[kept])})
    write_tree(file, "Runs", {"run": np.ones(3, dtype=np.uint32),
                              "genEventCount": np.array([np.sum(files == i) for i in range(3)], dtype=np.int64),
                              "genEventSumw": np.array([gen_weight[files == i].astype(np.float64).sum() for i in range(3)])})
passed_mc, _ = candidate(pt, eta, phi, q)
sum_w = gen_weight.astype(np.float64).sum()
n_mc = SIGMA_DY_PB * lumi_good_pb * gen_weight[kept & passed_mc].astype(np.float64).sum() / sum_w

(out / "notes.md").write_text("""# Z -> mu mu check on the low-pile-up runs

## Data

`SingleMuon.root` and `DoubleMuon.root`: our ntuples from the two primary
datasets, NanoAOD layout, one `Events` tree each with `run`, `luminosityBlock`,
`event` and the muons (`nMuon`, `Muon_pt`, `Muon_eta`, `Muon_phi`,
`Muon_charge`), highest pT first. The ntuple job kept events with two muons of
pT > %(skim).0f GeV inside abs(eta) < %(eta).1f, from all of runs %(runs)s.
For this selection every event fires at least one of the two triggers.

`golden.json`: the certification for these runs, in the usual format - run to
a list of [first, last] luminosity-section ranges, both ends included.

`lumi_by_ls.csv`: brilcalc output by luminosity section for the same runs,
delivered and recorded luminosity in /ub.

## Simulation

`DYJetsToLL_skim.root`: DYJetsToLL (aMC@NLO, all three lepton flavours,
m(ll) > 50 GeV), same layout, with `genWeight` in `Events` and the usual `Runs`
tree. It is a skim - only events with two reconstructed muons as above were
kept - merged from three files. Cross section %(sigma).2f pb (NNLO, for the
sample as generated). No efficiency scale factors are applied to it yet.

## Z selection

The two highest-pT muons, of opposite charge, both with pT > %(pt).0f GeV and
abs(eta) < %(eta).1f, and %(lo).0f < m(mu mu) < %(hi).0f GeV. Muon mass %(mass).6f GeV.
""" % dict(skim=PT_SKIM, eta=ETA_CUT, runs=", ".join(str(r) for r in RUNS), sigma=SIGMA_DY_PB, pt=PT_CUT,
           lo=M_LOW, hi=M_HIGH, mass=MUON_MASS))

both = int(np.sum(single & double))
rows_passing = int(np.sum(passed & single) + np.sum(passed & double))
print("luminosity: golden %.5f pb^-1, all sections %.5f, golden runs whole %.5f" % (
    lumi_good_pb, lumi_all_pb, sum(v for (run, _), v in recorded.items() if run in GOLDEN) / 1e6))
print("data: %d events (%d SingleMuon, %d DoubleMuon, %d in both)" % (n, single.sum(), double.sum(), both))
print("Z candidates: %d in golden sections; %d in all sections; %d rows over both files, %d of them golden"
      % (n_data, passed.sum(), rows_passing, np.sum(passed & is_good & single) + np.sum(passed & is_good & double)))
print("simulation: %d generated, sum of weights %.1f; %d in the skim, sum %.1f; %d candidates"
      % (N_GENERATED, sum_w, kept.sum(), gen_weight[kept].astype(np.float64).sum(), np.sum(kept & passed_mc)))
print("predicted: %.2f events, %.2f pb visible; data over prediction %.3f" % (n_mc, n_mc / lumi_good_pb, n_data / n_mc))
delivered = sum(float(row.split(",")[2]) for row in lumi_rows if (int(row.split(",")[0]), int(row.split(",")[1])) in good) / 1e6
print("delivered in the golden sections: %.5f pb^-1" % delivered)
