"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Five independent runs of one validation problem and a sixth that repeats the
fifth's seed, so is the same run again. Each history scores with probability
1/300^2, so the two short runs rest on about 20 and 60 scoring histories.
"""
import math
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
# This seed: a realisation in which the short runs sit low, so that an unweighted mean of the
# runs is 3 to 7% from the history-weighted one, and no run is more than 1.7 sigma from the truth.
rng = np.random.default_rng(921)

MU_OVER_RHO, DENSITY = 0.1101, 11.35          # cm2/g, g/cm3: lead at 661.7 keV
THICKNESS, DISTANCE = 4.00, 100.0             # cm
ACTIVITY, EMISSION = 1.85e9, 0.851            # Bq, photons per decay
TRUE_TALLY = math.exp(-MU_OVER_RHO * DENSITY * THICKNESS) / (4 * math.pi * DISTANCE**2)   # 1/cm2 per source photon
SCORE_PROBABILITY = 1 / 300.0**2
HISTORIES = [2_000_000, 5_000_000, 20_000_000, 100_000_000, 400_000_000]
SEEDS = [1001, 1003, 1005, 1007, 1009]

rows = []
for seed, histories in zip(SEEDS, HISTORIES):
    scoring = rng.poisson(histories * SCORE_PROBABILITY)
    tracks = rng.gamma(shape=1 / 0.35**2, scale=0.35**2, size=scoring)       # track lengths in the cell: mean 1, spread 35%
    tally = tracks.sum() * TRUE_TALLY / SCORE_PROBABILITY / histories
    relative = math.sqrt((tracks**2).sum() / tracks.sum() ** 2 - 1 / histories)
    rows.append((seed, histories, "%.4e" % tally, "%.4f" % relative))
rows.append(rows[-1])                                                         # the job that reused seed 1009

lines = ["run,seed,histories,tally_per_cm2,rel_err"]
for run, row in enumerate(rows, start=1):
    lines.append("%d,%d,%d,%s,%s" % ((run,) + row))
(out / "runs.csv").write_text("\n".join(lines) + "\n")

(out / "notes.md").write_text("""# Cs-137 behind lead: Monte Carlo validation runs

## Model

- Point isotropic source; the source card emits 661.657 keV photons only.
- Lead slab, %.2f cm thick, density %.2f g/cm3, across the line from the
  source to the detector. Everything else is void.
- Detector: a small cell centred %.1f cm from the source.
- Tally: track-length photon flux in the detector cell, energy bin 0.6610 to
  0.6620 MeV only (photons that have not scattered), in 1/cm2 per source
  particle.
- runs.csv: one line per job as the code printed it - the seed, the number of
  histories, the tally mean and its relative error (one standard deviation).

## Source

- Cs-137, %.2f GBq on the day of the measurement we compare with.
- Emission probability of the 661.657 keV photon: %.3f per decay (ENSDF).

## Attenuation data

- Lead at 661.7 keV: mu/rho = %.4f cm2/g (NIST XCOM, total attenuation with
  coherent scattering).

## Group rule

- A tally with a relative error above 0.10 is not reliable and is never
  quoted on its own (MCNP manual).
""" % (THICKNESS, DENSITY, DISTANCE, ACTIVITY / 1e9, EMISSION, MU_OVER_RHO))
print("true tally %.4e /cm2 per photon; true flux %.3f /cm2/s" % (TRUE_TALLY, TRUE_TALLY * ACTIVITY * EMISSION))
