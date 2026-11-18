"""Writes environment/ for this task. The truth is in oracle/solve.py and the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>
"""
import math
import sys
from pathlib import Path

out = Path(sys.argv[1])

M_TOP = 173.0
# (sqrt(s-hat) in GeV, cos(theta) of the top to gluon 1, azimuth): central angles, where the
# unphysical gluon polarisations that a -g_{mu nu} sum lets in are 15 to 23% of the answer.
POINTS = [(400.0, 0.15, 0.7), (650.0, -0.40, 2.3), (1500.0, 0.25, 4.1)]

rows = ["point,particle,E,px,py,pz"]
for number, (roots, cos_theta, phi) in enumerate(POINTS, 1):
    energy = roots / 2
    p = math.sqrt(energy**2 - M_TOP**2)
    sin_theta = math.sqrt(1 - cos_theta**2)
    top = (p * sin_theta * math.cos(phi), p * sin_theta * math.sin(phi), p * cos_theta)
    momenta = {
        "g1": (energy, 0.0, 0.0, energy),
        "g2": (energy, 0.0, 0.0, -energy),
        "t": (energy, *top),
        "tbar": (energy, *(-x for x in top)),
    }
    for particle, four in momenta.items():
        rows.append("%d,%s,%s" % (number, particle, ",".join("%.9f" % (x + 0.0) for x in four)))
(out / "points.csv").write_text("\n".join(rows) + "\n")

(out / "notes.md").write_text("""# g g -> t tbar at leading order: the matrix-element check

We are checking the hard matrix element of the t tbar generator against an
independent calculation. Process: g(k1) g(k2) -> t(p3) tbar(p4) at tree level
in QCD.

## Conventions

- Metric (+,-,-,-).
- Colour SU(3), generators T^a = lambda^a / 2, [T^a, T^b] = i f^{abc} T^c.
- Covariant derivative D_mu = d_mu - i g_s T^a A^a_mu.
- Spinors normalised to ubar u = 2 m.
- Strong coupling fixed at alpha_s = 0.118 (no running); g_s^2 = 4 pi alpha_s.
- Top-quark mass m_t = 173.0 GeV.

## What to compare

|M|^2 summed over the colours and spins of the final state and averaged over
the colours and polarisations of the initial state. It is dimensionless; no
flux or phase-space factor.

## points.csv

Three phase-space points in the partonic centre-of-mass frame. One row per
particle: g1 and g2 incoming, t and tbar outgoing; E, px, py, pz in GeV.
""")
print("wrote %d points" % len(POINTS))
