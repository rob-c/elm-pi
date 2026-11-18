"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

The cross sections are made up, with the structure real ones have: a Hessian
set whose eigenvector directions move the observable by different amounts up
and down, some of them the same way in both directions, and a replica set.
"""
import sys
from pathlib import Path

import numpy as np
from scipy.stats import norm

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

# --- the Hessian set: 29 eigenvector pairs, uncertainties at 90% CL -------------------
CENTRAL = 4472.31                          # pb
SYMMETRIC_90 = 0.024 * CENTRAL             # what (1/2) sqrt(sum (X+ - X-)^2) comes to, before rounding
pairs = 29
linear = rng.choice([-1.0, 1.0], pairs) * rng.uniform(0.2, 1.0, pairs) * np.exp(-np.arange(pairs) / 12.0)
linear *= SYMMETRIC_90 / np.sqrt(np.sum(linear**2))
# Curvature: on average upwards, so the up and down uncertainties differ.
curvature = np.abs(linear) * (0.10 + 0.15 * rng.standard_normal(pairs))
# Three directions in which both members land on the same side of the central value, by
# (+52, +24), (-20, -45) and (+4, +9) pb: large enough that counting both members of such a
# pair, instead of the larger one, moves the up and the down uncertainty by 2%.
for k, (first, second) in ((9, (52.0, 24.0)), (17, (-20.0, -45.0)), (24, (4.0, 9.0))):
    linear[k], curvature[k] = (first - second) / 2, (first + second) / 2
hessian = [CENTRAL]
for a, b in zip(linear, curvature):
    hessian += [CENTRAL + a + b, CENTRAL - a + b]
(out / "ct18nlo_members.csv").write_text("member,sigma_pb\n" + "".join("%d,%.2f\n" % row for row in enumerate(hessian)))

# --- the replica set: 100 replicas, member 0 their average ---------------------------
MEAN, SPREAD = 4541.87, 38.4
# Normal quantiles in a shuffled order: the standard deviation and the central 68% interval
# of the replicas then agree to 1%, so either convention gives the same answer.
replicas = MEAN + SPREAD * norm.ppf((rng.permutation(100) + 0.5) / 100.0)
# The cross section of the average PDF is not quite the average cross section.
members = [MEAN - 0.42] + list(replicas)
(out / "nnpdf31_members.csv").write_text("member,sigma_pb\n" + "".join("%d,%.2f\n" % row for row in enumerate(members)))

(out / "notes.md").write_text("""# PDF uncertainty on the fiducial W+ cross section

Observable: fiducial cross section for p p -> W+ -> mu+ nu at 13 TeV, NLO QCD,
from our interpolation grid. One convolution per PDF member, each with that
member's own alpha_s; scales, cuts and everything else are the same in every
row.

## Files

Columns: member (the LHAPDF member number), sigma_pb.

- ct18nlo_members.csv: CT18NLO. Member 0 is the central fit; members 1 to 58
  are the 29 eigenvector pairs in LHAPDF order (2k-1 and 2k are the two
  directions of eigenvector k).
- nnpdf31_members.csv: NNPDF31_nlo_as_0118. Member 0 is the average of the
  replicas; members 1 to 100 are the replicas.

## From the sets' .info files

CT18NLO.info

    NumMembers: 59
    ErrorType: hessian
    ErrorConfLevel: 90

NNPDF31_nlo_as_0118.info

    NumMembers: 101
    ErrorType: replicas
""")
same_side = sum(1 for a, b in zip(linear, curvature) if abs(b) > abs(a))
print("hessian: %d pairs, %d with both members on one side; replicas: %d" % (pairs, same_side, len(replicas)))
