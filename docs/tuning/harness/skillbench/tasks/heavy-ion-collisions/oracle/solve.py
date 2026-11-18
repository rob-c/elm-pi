"""The reference solution: run in the project folder, writes result.json.

Event-plane method with two equal sub-events. Each event's tracks are split in two
(alternate tracks: they come in no order). A track is correlated with the plane of the
half it is not in, so it is never in its own plane, and the result is divided by the
sub-event resolution sqrt(<cos 2(Psi_a - Psi_b)>). The uncertainty is a jackknife over
events, which carries the uncertainty of the resolution with it. The two-particle
cumulant v2{2} is printed as a cross-check: this sample has no non-flow.

Fixed target: s_NN = 2 m^2 + 2 m E, with E the total beam energy per nucleon = T + m.
"""
import json
import math

import numpy as np

KINETIC_GEV, NUCLEON_GEV = 30.0, 0.9389            # notes.md

events = [np.array(line.split(), dtype=float) for line in open("events.txt") if line.strip()]
tracks = np.array([len(phi) for phi in events])
observed = np.empty(len(events))                   # sum over tracks of cos 2(phi - Psi of the other half)
planes = np.empty(len(events))                     # cos 2(Psi_a - Psi_b)
pairs = np.empty(len(events))                      # sum over distinct pairs of cos 2(phi_i - phi_j)
for i, phi in enumerate(events):
    a, b = phi[0::2], phi[1::2]
    psi_a = 0.5 * math.atan2(np.sin(2 * a).sum(), np.cos(2 * a).sum())
    psi_b = 0.5 * math.atan2(np.sin(2 * b).sum(), np.cos(2 * b).sum())
    observed[i] = np.cos(2 * (a - psi_b)).sum() + np.cos(2 * (b - psi_a)).sum()
    planes[i] = math.cos(2 * (psi_a - psi_b))
    pairs[i] = abs(np.exp(2j * phi).sum()) ** 2 - len(phi)


def v2_of(keep):
    return observed[keep].sum() / tracks[keep].sum() / math.sqrt(planes[keep].mean())


everything = np.ones(len(events), dtype=bool)
v2 = v2_of(everything)
left_out = np.array([v2_of(np.arange(len(events)) != i) for i in range(len(events))])
v2_stat = math.sqrt((len(events) - 1) / len(events) * ((left_out - left_out.mean()) ** 2).sum())

total_energy = KINETIC_GEV + NUCLEON_GEV
sqrt_snn = math.sqrt(2 * NUCLEON_GEV**2 + 2 * NUCLEON_GEV * total_energy)

json.dump({"v2": v2, "v2_stat": v2_stat, "sqrt_snn_gev": sqrt_snn}, open("result.json", "w"), indent=1)
print("%d events, %d tracks; observed %.4f, sub-event resolution %.3f, v2 = %.4f +- %.4f"
      % (len(events), tracks.sum(), observed.sum() / tracks.sum(), math.sqrt(planes.mean()), v2, v2_stat))
print("cross-check v2{2} = %.4f; sqrt(s_NN) = %.4f GeV"
      % (math.sqrt(pairs.sum() / (tracks * (tracks - 1)).sum()), sqrt_snn))
