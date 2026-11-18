"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

One exclusive event p p -> p p X, X -> pi+ pi- pi0, pi0 -> gamma gamma, generated in the
centre-of-mass frame and boosted to the laboratory, where the target proton is at rest.
Tracks are written in MeV, calorimeter clusters in GeV.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

M_P, M_PI, M_PI0 = 0.938272, 0.139570, 0.134977       # GeV
T_BEAM = 3.500                                        # GeV, kinetic
M_X = 0.7814                                          # GeV: what the task asks for


def two_body(parent, m1, m2):
    """Decay a four-vector (E, px, py, pz) isotropically into masses m1 and m2."""
    mass = np.sqrt(parent[0] ** 2 - parent[1:] @ parent[1:])
    p = np.sqrt((mass**2 - (m1 + m2) ** 2) * (mass**2 - (m1 - m2) ** 2)) / (2 * mass)
    cos, phi = rng.uniform(-1, 1), rng.uniform(-np.pi, np.pi)
    direction = np.array([np.sqrt(1 - cos**2) * np.cos(phi), np.sqrt(1 - cos**2) * np.sin(phi), cos])
    first = np.concatenate([[np.hypot(p, m1)], p * direction])
    second = np.concatenate([[np.hypot(p, m2)], -p * direction])
    return boost(first, parent), boost(second, parent)


def boost(vector, frame):
    """Take a four-vector from the rest frame of `frame` to the frame `frame` is given in."""
    mass = np.sqrt(frame[0] ** 2 - frame[1:] @ frame[1:])
    beta = frame[1:] / frame[0]
    gamma = frame[0] / mass
    along = vector[1:] @ beta
    b2 = beta @ beta
    if b2 == 0:
        return vector.copy()
    energy = gamma * (vector[0] + along)
    momentum = vector[1:] + ((gamma - 1) * along / b2 + gamma * vector[0]) * beta
    return np.concatenate([[energy], momentum])


e_beam = T_BEAM + M_P
p_beam = np.sqrt(e_beam**2 - M_P**2)
lab = np.array([e_beam + M_P, 0.0, 0.0, p_beam])      # beam plus target, laboratory frame
sqrt_s = np.sqrt(lab[0] ** 2 - p_beam**2)

while True:
    # Three-body phase space as two two-body steps: (p p) recoiling against X, then p p.
    m_pp = rng.uniform(2 * M_P, sqrt_s - M_X)
    x, pp = two_body(lab, M_X, m_pp)
    proton1, proton2 = two_body(pp, M_P, M_P)
    m_pipi = rng.uniform(2 * M_PI, M_X - M_PI0)
    pipi, pi0 = two_body(x, m_pipi, M_PI0)
    pip, pim = two_body(pipi, M_PI, M_PI)
    gamma1, gamma2 = two_body(pi0, 0.0, 0.0)
    pt_x = np.hypot(x[1], x[2])
    theta = [np.degrees(np.arccos(v[3] / np.sqrt(v[1:] @ v[1:]))) for v in (proton1, proton2, pip, pim, gamma1, gamma2)]
    # Everything inside the spectrometer, photons well above the cluster threshold, and a candidate
    # with enough transverse momentum that its rapidity and pseudorapidity are far apart but finite.
    if max(theta) < 80 and min(theta) > 3 and min(gamma1[0], gamma2[0]) > 0.15 and 0.25 < pt_x < 0.6:
        break

tracks = [(1, +1, 2212, proton1), (2, +1, 2212, proton2), (3, +1, 211, pip), (4, -1, -211, pim)]
(out / "tracks.csv").write_text("track,charge,pdg_id,px,py,pz\n" + "".join(
    "%d,%+d,%d,%.2f,%.2f,%.2f\n" % (i, q, pdg, 1000 * v[1], 1000 * v[2], 1000 * v[3]) for i, q, pdg, v in tracks))
clusters = []
for i, v in enumerate((gamma1, gamma2), 1):
    clusters.append("%d,%.5f,%.5f,%.5f\n" % (i, v[0], np.arccos(v[3] / v[0]), np.arctan2(v[2], v[1])))
(out / "clusters.csv").write_text("cluster,energy,theta,phi\n" + "".join(clusters))
(out / "notes.md").write_text("""# Run 4127, event 880213: exclusive p p -> p p pi+ pi- pi0 candidate

Fixed-target run: proton beam of 3.500 GeV kinetic energy on the liquid-hydrogen
target (protons at rest). The z axis is along the beam.

The event passed the exclusive selection: four charged tracks from the primary
vertex and two photon clusters, nothing else. The kinematic fit identifies the
tracks as below; the two clusters are the photons of the pi0.

## tracks.csv (spectrometer)

One row per track at the primary vertex. Momentum components px, py, pz are in
MeV/c, the tracking software's unit. `pdg_id` is the particle hypothesis from
the kinematic fit and time of flight (2212 proton, 211 pi+, -211 pi-).

## clusters.csv (electromagnetic calorimeter)

One row per photon cluster: `energy` in GeV after calibration, and the direction
from the primary vertex as polar angle `theta` (from the beam axis) and azimuth
`phi`, both in radians.

## Masses (PDG, MeV)

| particle | mass |
|---|---|
| proton | 938.272 |
| pi+- | 139.570 |
| pi0 | 134.977 |
""")
rapidity = 0.5 * np.log((x[0] + x[3]) / (x[0] - x[3]))
p_x = np.sqrt(x[1:] @ x[1:])
print("sqrt(s) %.4f GeV; X: mass %.4f GeV, pT %.4f GeV, rapidity %.4f, pseudorapidity %.4f" %
      (sqrt_s, np.sqrt(x[0] ** 2 - p_x**2), pt_x, rapidity, np.arctanh(x[3] / p_x)))
