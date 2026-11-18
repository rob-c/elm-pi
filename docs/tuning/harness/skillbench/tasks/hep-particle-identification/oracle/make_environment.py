"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A kaon-identification cut whose efficiency falls and whose pion
misidentification rises with momentum, a calibration sample that is soft
(mean 25 GeV) and an analysis sample that is hard (mean 42 GeV). The numbers
integrated over the calibration sample - efficiency 0.85, misidentification
0.03 - are not the analysis sample's.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
# Of the seeds 20261117 to 20261127 the one whose finely binned estimates land nearest the truth
# (both within one standard error), so that coarse and fine binnings alike sit inside the verifier's window.
rng = np.random.default_rng(20261126)

P_MIN, P_MAX = 3.0, 100.0        # GeV: the momentum range both samples are restricted to
N_CALIBRATION, N_ANALYSIS = 10_000, 2_500     # tracks of each species


def kaon_efficiency(p):
    return 0.50 + 0.46 / (1 + np.exp((p - 42.0) / 11.0))


def pion_misid(p):
    return 0.006 + 0.20 / (1 + np.exp(-(p - 55.0) / 12.0))


def momenta(n, shape, scale):
    """n momenta from P_MIN + Gamma(shape, scale), below P_MAX, to 0.1 GeV."""
    p = np.empty(0)
    while len(p) < n:
        draw = P_MIN + rng.gamma(shape, scale, 2 * n)
        p = np.concatenate([p, draw[draw < P_MAX - 0.05]])
    return np.round(p[:n], 1)


calibration, analysis, truth, integrated = [], [], {}, {}
for species, response in (("K", kaon_efficiency), ("pi", pion_misid)):
    p = momenta(N_CALIBRATION, 1.6, 14.0)
    passed = rng.random(N_CALIBRATION) < response(p)
    calibration += [(species, a, int(b)) for a, b in zip(p, passed)]
    integrated[species] = passed.mean()
    p = momenta(N_ANALYSIS, 3.0, 13.0)
    analysis += [(species, a) for a in p]
    truth[species] = response(p).mean()
for rows in (calibration, analysis):
    order = rng.permutation(len(rows))
    rows[:] = [rows[i] for i in order]
(out / "calibration.csv").write_text("species,p_gev,passed\n" + "".join("%s,%.1f,%d\n" % row for row in calibration))
(out / "analysis_tracks.csv").write_text("species,p_gev\n" + "".join("%s,%.1f\n" % row for row in analysis))

(out / "notes.md").write_text("""# Kaon identification cut DLL(K - pi) > 5: calibration and analysis samples

## calibration.csv

Tracks from D*+ -> D0 (-> K- pi+) pi+ and the charge conjugate in the 2025
data, selected on kinematics alone. The charge of the slow pion says which D0
daughter is the kaon and which the pion, so no identification requirement was
put on them. The D0 mass window is tight: the background under the peak is
below 0.5%% and is ignored.

| column | |
|---|---|
| species | K or pi, from the slow pion's charge |
| p_gev | track momentum, GeV |
| passed | 1 if the track has DLL(K - pi) > 5, else 0 |

## analysis_tracks.csv

The kaons and pions of our B -> h h' signal simulation after the full
selection except the identification cut: true species and momentum. The
simulation's own DLL is not trusted, which is why the cut's performance is
taken from data.

Both samples are restricted to %.0f < p < %.0f GeV, where the RICH radiators cover
kaons and pions, and to the same pseudorapidity range and data-taking period.
""" % (P_MIN, P_MAX))

print("kaon efficiency: analysis sample %.4f, integrated over calibration %.4f" % (truth["K"], integrated["K"]))
print("pion misidentification: analysis sample %.4f, integrated over calibration %.4f" % (truth["pi"], integrated["pi"]))
