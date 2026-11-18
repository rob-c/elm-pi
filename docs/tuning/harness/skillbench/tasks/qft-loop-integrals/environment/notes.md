# The scalar two-point function: our conventions

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
