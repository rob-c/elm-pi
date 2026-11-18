"""Writes environment/ for this task. The truth is printed here and copied to the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Events with zero to five muons: Z -> mu mu, alone, with one or two more muons, or twice in one
event; and events with no Z. The muons of an event are in no particular order. The truth is
counted here with plain loops over the values as they are stored (float32).
"""
import math
import sys
from pathlib import Path

import awkward as ak
import numpy as np
import uproot

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

N_EVENTS = 4800
PT_MIN, ETA_MAX, M_LOW, M_HIGH = 20.0, 2.4, 81.0, 101.0


def z_decay():
    """Two massless muons (pt, eta, phi, charge) from a Z with a Breit-Wigner mass, boosted to the laboratory."""
    mass = 0.0
    while not 40 < mass < 200:
        mass = 91.19 + 1.25 * rng.standard_cauchy()
    mass *= rng.normal(1.0, 0.012)
    pt, y, phi = rng.exponential(14.0), rng.normal(0.0, 1.5), rng.uniform(-np.pi, np.pi)
    mt = math.hypot(mass, pt)
    parent = np.array([mt * math.cosh(y), pt * math.cos(phi), pt * math.sin(phi), mt * math.sinh(y)])
    cos, angle = rng.uniform(-1, 1), rng.uniform(-np.pi, np.pi)
    sin = math.sqrt(1 - cos * cos)
    direction = np.array([sin * math.cos(angle), sin * math.sin(angle), cos])
    beta, gamma = parent[1:] / parent[0], parent[0] / mass
    muons = []
    for sign in (+1, -1):
        p = sign * mass / 2 * direction
        along = p @ beta
        lab = p + ((gamma - 1) * along / (beta @ beta) + gamma * mass / 2) * beta
        muons.append((math.hypot(lab[0], lab[1]), math.asinh(lab[2] / math.hypot(lab[0], lab[1])), math.atan2(lab[1], lab[0]), sign))
    return muons


def other_muon():
    return (3.0 + rng.exponential(16.0), rng.uniform(-2.6, 2.6), rng.uniform(-np.pi, np.pi), int(rng.choice([-1, 1])))


def pairs(muons):
    """Opposite-charge pairs of selected muons, as (mass with massless muons, the two muons)."""
    good = [m for m in muons if m[0] > PT_MIN and abs(m[1]) < ETA_MAX]
    found = []
    for i in range(len(good)):
        for j in range(i + 1, len(good)):
            a, b = good[i], good[j]
            if a[3] * b[3] < 0:
                found.append(math.sqrt(2 * a[0] * b[0] * (math.cosh(a[1] - b[1]) - math.cos(a[2] - b[2]))))
    return found


def stored(muons):
    """The muons as float32 will hold them."""
    return [(float(np.float32(m[0])), float(np.float32(m[1])), float(np.float32(m[2])), m[3]) for m in muons]


def clear_of_thresholds(muons):
    """No muon or pair within a hair of a cut: float32 or float64, massless or massive muons, give the same count."""
    if any(abs(m[0] - PT_MIN) < 0.02 or abs(abs(m[1]) - ETA_MAX) < 0.002 for m in muons):
        return False
    everything = [(m[0], m[1], m[2], m[3]) for m in muons]
    for i in range(len(everything)):
        for j in range(i + 1, len(everything)):
            a, b = everything[i], everything[j]
            mass = math.sqrt(2 * a[0] * b[0] * (math.cosh(a[1] - b[1]) - math.cos(a[2] - b[2])))
            if abs(mass - M_LOW) < 0.05 or abs(mass - M_HIGH) < 0.05:
                return False
    return True


events, weights = [], []
kinds = rng.choice(["z", "z+1", "z+2", "zz", "none"], size=N_EVENTS, p=[0.50, 0.20, 0.05, 0.05, 0.20])
for kind in kinds:
    while True:
        if kind == "none":
            muons = [other_muon() for _ in range(rng.choice([0, 1, 2, 3], p=[0.25, 0.40, 0.25, 0.10]))]
        else:
            muons = z_decay() + (z_decay() if kind == "zz" else []) + [other_muon() for _ in range({"z": 0, "z+1": 1, "z+2": 2, "zz": 0}[kind])]
        muons = stored(muons)
        if clear_of_thresholds(muons):
            break
    order = rng.permutation(len(muons))
    events.append([muons[i] for i in order])
    # Generator sign times pile-up and normalisation: about one event in twelve is negative.
    weights.append(float(np.float32((-1 if rng.random() < 0.08 else 1) * 0.42 * rng.lognormal(0.0, 0.30))))

pair_yield = event_yield = sum_w2 = 0.0
n_events = n_pairs = multi = 0
for muons, weight in zip(events, weights):
    inside = [m for m in pairs(muons) if M_LOW < m < M_HIGH]
    pair_yield += weight * len(inside)
    n_pairs += len(inside)
    if inside:
        event_yield += weight
        sum_w2 += weight**2
        n_events += 1
        multi += len(inside) > 1

muon = ak.zip({
    "pt": ak.values_astype(ak.Array([[m[0] for m in ev] for ev in events]), np.float32),
    "eta": ak.values_astype(ak.Array([[m[1] for m in ev] for ev in events]), np.float32),
    "phi": ak.values_astype(ak.Array([[m[2] for m in ev] for ev in events]), np.float32),
    "charge": ak.values_astype(ak.Array([[m[3] for m in ev] for ev in events]), np.int32),
})
with uproot.recreate(out / "events.root", compression=uproot.ZLIB(9)) as file:
    # mktree, not assignment: this uproot writes an RNTuple on assignment, and the note describes a TTree.
    tree = file.mktree("Events", {"event": np.int32, "weight": np.float32, "Muon": muon.type})
    tree.extend({"event": np.arange(1, N_EVENTS + 1, dtype=np.int32), "weight": np.array(weights, dtype=np.float32), "Muon": muon})

(out / "notes.md").write_text("""# events.root

A skim of the Drell-Yan plus diboson simulation for the dimuon study, written
with uproot. One tree, `Events`, %d entries.

| branch | type | meaning |
|---|---|---|
| event | int32 | event number |
| weight | float32 | event weight: generator weight (NLO, so some are negative) x pile-up weight x normalisation to 138 fb-1 |
| nMuon | int32 | number of muons in the event |
| Muon_pt | float32[nMuon] | transverse momentum [GeV] |
| Muon_eta | float32[nMuon] | pseudorapidity |
| Muon_phi | float32[nMuon] | azimuth [rad] |
| Muon_charge | int32[nMuon] | +1 or -1 |

All reconstructed muons passing the loose identification are kept, with no
kinematic cut, in the order of the reconstruction's own list. The muon mass is
0.10566 GeV.
""" % N_EVENTS)
print("PAIR_YIELD = %.4f   (%d pairs)" % (pair_yield, n_pairs))
print("EVENT_YIELD = %.4f   (%d events, %d with more than one pair)" % (event_yield, n_events, multi))
print("EVENT_YIELD_UNC = %.4f   (sqrt(yield) %.4f, sqrt(N) %.2f)" % (math.sqrt(sum_w2), math.sqrt(event_yield), math.sqrt(n_events)))
