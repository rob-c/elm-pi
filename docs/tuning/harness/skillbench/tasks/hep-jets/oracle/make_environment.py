"""Writes environment/ for this task. The truth is printed here and copied to the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

One particle-level event: five sprays of particles (two hard, one near the second, one just above
and one just below the 25 GeV cut), an underlying event, massive hadrons planted near the edge of
each jet - inside R of the axis in rapidity, outside it in pseudorapidity - and three neutrinos.
The leading jet straddles phi = pi.

The seed is the first from 20261117 on for which every wrong route listed in the verifier misses
by three times its tolerance, and no jet is within 2 GeV of the 25 GeV cut.
"""
import math
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261143)

MASS = {211: 0.13957, 22: 0.0, 321: 0.49368, 130: 0.49761, 2212: 0.93827, 2112: 0.93957, 13: 0.10566, 12: 0.0, 14: 0.0, 16: 0.0}
SPECIES = [211, -211, 22, 321, -321, 130, 2212, -2212, 2112, -2112]
PROBABILITY = [0.27, 0.27, 0.22, 0.05, 0.05, 0.04, 0.03, 0.02, 0.03, 0.02]
R, PT_CUT = 0.4, 25.0

particles = []        # (pdg, pt, rapidity, phi)


def spray(pt, y, phi, n, width=0.17):
    for z in rng.dirichlet(np.full(n, 0.55)):
        r = width * rng.random() ** 2.0 * (1.0 if z > 0.08 else 1.6)
        angle = rng.uniform(0, 2 * math.pi)
        pdg = int(rng.choice(SPECIES, p=PROBABILITY))
        particles.append((pdg, max(pt * z, 0.15), y + r * math.cos(angle), phi + r * math.sin(angle)))


spray(96.0, 1.62, 3.02, 22, width=0.20)
spray(88.0, -0.55, -0.35, 20)
spray(46.0, -1.25, 0.25, 14)
spray(23.2, 2.35, 1.30, 10)
spray(20.8, -2.10, -2.20, 9)
for _ in range(70):
    pdg = int(rng.choice(SPECIES, p=PROBABILITY))
    particles.append((pdg, 0.2 + rng.exponential(0.7), rng.uniform(-4.2, 4.2), rng.uniform(-math.pi, math.pi)))
for jet_y, jet_phi, side in ((1.62, 3.02, +1), (1.62, 3.02, +1), (-0.55, -0.35, -1), (2.35, 1.30, +1), (-2.10, -2.20, -1), (-1.25, 0.25, -1)):
    pdg = int(rng.choice([2212, 2112, -2212, 321, 130]))
    pt = rng.uniform(1.6, 3.4)
    dy = side * rng.uniform(0.30, 0.39)
    dphi = rng.uniform(-0.12, 0.12)
    particles.append((pdg, pt, jet_y + dy, jet_phi + dphi))
particles.append((14, rng.uniform(7, 10), 1.62 + rng.uniform(-0.1, 0.1), 3.02 + rng.uniform(-0.1, 0.1)))
particles.append((13, rng.uniform(5, 8), 1.62 + rng.uniform(-0.15, 0.15), 3.02 + rng.uniform(-0.15, 0.15)))
particles.append((-12, rng.uniform(2.5, 3.5), -2.10 + rng.uniform(-0.1, 0.1), -2.20 + rng.uniform(-0.1, 0.1)))
particles.append((16, rng.uniform(28, 33), 0.4, 2.0))

rows = []
for pdg, pt, y, phi in particles:
    phi = (phi + math.pi) % (2 * math.pi) - math.pi
    mt = math.hypot(pt, MASS[abs(pdg)])
    rows.append((pdg, round(pt * math.cos(phi), 6), round(pt * math.sin(phi), 6), round(mt * math.sinh(y), 6), round(mt * math.cosh(y), 6)))
rows = [rows[i] for i in rng.permutation(len(rows))]
(out / "event.csv").write_text("pdg_id,px,py,pz,e\n" + "".join("%d,%.6f,%.6f,%.6f,%.6f\n" % row for row in rows))
(out / "notes.md").write_text("""# Event 48213, particle level

`event.csv` has the stable particles (c tau > 10 mm) of one simulated
proton-proton event at 13.6 TeV with |y| < 4.5: one row per particle, its PDG
code and its four-momentum px, py, pz, e in GeV. The z axis is along the beam.

## Particle-level jets, as defined in the analysis

- Inputs: all stable particles except neutrinos (PDG codes 12, 14, 16 and
  their antiparticles). Muons are kept.
- Algorithm: anti-kT with R = 0.4.
- Recombination: E-scheme (four-momenta are added).
- Jets are counted if pT > 25 GeV; there is no rapidity cut in this check.

The leading jet is the one with the highest pT.
""")

# The truth, by the textbook loop: d_ij = min(1/pT_i^2, 1/pT_j^2) dR_ij^2 / R^2 with dR from rapidity
# and azimuth, d_iB = 1/pT_i^2; merge the closest pair by adding four-momenta, or call i a jet.
objects = [(px, py, pz, e) for pdg, px, py, pz, e in rows if abs(pdg) not in (12, 14, 16)]
jets = []
while objects:
    kin = [(px * px + py * py, 0.5 * math.log((e + pz) / (e - pz)), math.atan2(py, px)) for px, py, pz, e in objects]
    best, bi, bj = float("inf"), -1, -1
    for i, (pt2, y, phi) in enumerate(kin):
        if 1 / pt2 < best:
            best, bi, bj = 1 / pt2, i, -1
        for j in range(i + 1, len(kin)):
            dphi = abs(phi - kin[j][2])
            dphi = min(dphi, 2 * math.pi - dphi)
            d = min(1 / pt2, 1 / kin[j][0]) * ((y - kin[j][1]) ** 2 + dphi**2) / R**2
            if d < best:
                best, bi, bj = d, i, j
    if bj < 0:
        jets.append(objects.pop(bi))
    else:
        objects[bi] = tuple(a + b for a, b in zip(objects[bi], objects[bj]))
        objects.pop(bj)
jets.sort(key=lambda v: -math.hypot(v[0], v[1]))
px, py, pz, e = jets[0]
print("%d particles, %d neutrinos" % (len(rows), sum(abs(row[0]) in (12, 14, 16) for row in rows)))
print("jet pT:", ["%.2f" % math.hypot(v[0], v[1]) for v in jets[:7]])
print("N_JETS = %d" % sum(math.hypot(v[0], v[1]) > PT_CUT for v in jets))
print("LEAD_PT = %.4f\nLEAD_RAPIDITY = %.5f\nLEAD_MASS = %.4f" % (math.hypot(px, py), 0.5 * math.log((e + pz) / (e - pz)), math.sqrt(e * e - px * px - py * py - pz * pz)))
