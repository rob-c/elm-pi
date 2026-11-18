"""Writes environment/ for this task. The truth (k and n per bin) is here and in the verifier only.

    python make_environment.py <environment dir>
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

EDGES = [30, 40, 45, 48, 50, 52, 55, 60, 70, 90, 120, 200, 500]
# (probes, passing) per bin: nothing below the threshold, a turn-on round 50 GeV, a plateau near
# 0.975, and three plateau bins where every probe passes - 41, 17 and 5 of them.
COUNTS = [(180, 0), (150, 2), (96, 11), (71, 29), (64, 47), (83, 76), (102, 99), (127, 124), (88, 86), (41, 41), (17, 17), (5, 5)]
BELOW, ABOVE = 37, 2            # probes outside the binned range: 20-30 GeV (none pass) and above 500 (both pass)

rows = []
for (lo, hi), (n, k) in zip(zip(EDGES[:-1], EDGES[1:]), COUNTS):
    # A falling spectrum inside the bin, kept 0.02 GeV off the edges so no probe sits on one.
    pt = lo + 0.02 + (hi - lo - 0.04) * rng.beta(1.0, 1.6, size=n)
    passed = np.zeros(n, dtype=int)
    passed[rng.choice(n, size=k, replace=False)] = 1
    rows += list(zip(pt, passed))
rows += [(pt, 0) for pt in rng.uniform(20.0, 29.98, size=BELOW)]
rows += [(pt, 1) for pt in rng.uniform(500.5, 800.0, size=ABOVE)]
order = rng.permutation(len(rows))
lines = ["probe,pt,hlt_mu50\n"] + ["%d,%.2f,%d\n" % (i + 1, rows[j][0], rows[j][1]) for i, j in enumerate(order)]
(out / "probes.csv").write_text("".join(lines))
(out / "notes.md").write_text("""# HLT_Mu50 efficiency from the MET-triggered reference sample

The reference sample is 2025 data recorded by the missing-momentum triggers,
which do not use the muon system, so it is unbiased for a muon trigger.

`probes.csv` has one row per probe: an offline muon passing the tight
identification and isolation, |eta| < 2.4, in an event with exactly one such
muon.

| column | meaning |
|---|---|
| probe | running number |
| pt | offline muon pT [GeV] |
| hlt_mu50 | 1 if HLT_Mu50 fired and its trigger object matches the probe (deltaR < 0.1), else 0 |

## Binning

The efficiency is quoted in these offline pT bins [GeV], the ones the
scale-factor file uses:

30, 40, 45, 48, 50, 52, 55, 60, 70, 90, 120, 200, 500

Twelve bins. Probes below 30 GeV or above 500 GeV are not used.
""")
print("%d probes written" % len(rows))
