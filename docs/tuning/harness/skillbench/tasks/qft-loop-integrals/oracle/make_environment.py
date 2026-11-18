"""Writes environment/ for this task. The truth is in oracle/solve.py and the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

# (p^2 in GeV^2, m1, m2, mu in GeV). One spacelike point; one above threshold with equal
# masses; one between the pseudo-threshold (m1 - m2)^2 and the threshold (m1 + m2)^2, where a
# closed form written for one region goes wrong; one above threshold with unequal masses and
# mu away from every mass.
POINTS = [
    (-40000.0, 80.4, 91.2, 91.2),
    (15625.0, 4.18, 4.18, 125.0),
    (22500.0, 173.0, 80.4, 173.0),
    (250000.0, 173.0, 80.4, 91.2),
]

(out / "points.csv").write_text("point,p2_gev2,m1_gev,m2_gev,mu_gev\n" + "".join(
    "%d,%.1f,%s,%s,%s\n" % (number, *point) for number, point in enumerate(POINTS, 1)))

(out / "notes.md").write_text("""# The scalar two-point function: our conventions

For the self-energy cross-check we need numbers for B0 in exactly the
conventions of the paper draft.

- Dimensional regularisation, d = 4 - 2 eps. Metric (+,-,-,-).
- Definition, with the usual Feynman prescription in both propagators:

      i/(16 pi^2) B0(p^2; m1, m2)
          = mu^(2 eps) Int d^dk/(2 pi)^d  1 / { [k^2 - m1^2 + i0] [(k + p)^2 - m2^2 + i0] }

- Scheme: MS-bar at the renormalisation scale mu. The number wanted is the
  finite B0 left after the MS-bar subtraction, at eps = 0.

## points.csv

One row per kinematic point: p^2 in GeV^2 (negative is spacelike), the two
masses and mu in GeV.
""")
print("wrote %d points" % len(POINTS))
