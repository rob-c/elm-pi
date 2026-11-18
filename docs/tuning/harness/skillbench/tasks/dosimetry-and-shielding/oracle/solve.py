"""The reference solution: run in the project folder, writes result.json.

Activity decayed to the date of the estimate, photons per second with the emission
probability, fluence rate at 250 cm, absorbed dose rate in soft tissue with its own
energy-absorption coefficient, then the wall as a broad-beam shield: build-up factor
times exp(-mu x), with the thickness for the target found by solving that equation.
Every number is read off notes.md; the build-up table is parsed from it.

A planning estimate, not a safety assessment.
"""
import json
import math
import re
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

ACTIVITY_CI, CI_BQ, YEARS, HALF_LIFE_Y = 2.00, 3.7e10, 10.0, 30.05
ENERGY_MEV, EMISSION = 0.6617, 0.851
DISTANCE_CM, WALL_CM, DENSITY = 250.0, 30.0, 2.30
MU_RHO_CONCRETE, MU_EN_RHO_TISSUE = 0.0775, 0.0323           # cm2/g
MEV_PER_G_TO_GY = 1.602177e-13 * 1000
TARGET_UGY_H = 2.0

table = Path("notes.md").read_text().split("| mean free paths | build-up factor |")[1]
pairs = np.array(re.findall(r"^\| ([\d.]+) \| ([\d.]+) \|$", table, re.M), dtype=float)


def buildup(mfp):
    """Interpolated in ln B, which is smoother than B over the table's steps."""
    return float(np.exp(np.interp(mfp, pairs[:, 0], np.log(pairs[:, 1]))))


activity = ACTIVITY_CI * CI_BQ * 0.5 ** (YEARS / HALF_LIFE_Y)
fluence_rate = activity * EMISSION / (4 * math.pi * DISTANCE_CM**2)            # photons / cm2 / s
unshielded = fluence_rate * ENERGY_MEV * MU_EN_RHO_TISSUE * MEV_PER_G_TO_GY * 3600 * 1e6     # uGy/h
mu = MU_RHO_CONCRETE * DENSITY                                                 # 1/cm


def behind(thickness_cm):
    return unshielded * buildup(mu * thickness_cm) * math.exp(-mu * thickness_cm)


shielded = behind(WALL_CM)
thickness = brentq(lambda x: behind(x) - TARGET_UGY_H, WALL_CM, 20 / mu)
json.dump({"unshielded_ugy_per_h": unshielded, "shielded_ugy_per_h": shielded, "thickness_cm": thickness},
          open("result.json", "w"), indent=1)
print("activity %.4g Bq, fluence rate %.4g /cm2/s, unshielded %.1f uGy/h" % (activity, fluence_rate, unshielded))
print("wall: %.3f mean free paths, B = %.2f, behind it %.2f uGy/h (narrow beam %.2f)"
      % (mu * WALL_CM, buildup(mu * WALL_CM), shielded, unshielded * math.exp(-mu * WALL_CM)))
print("for %.1f uGy/h: %.1f cm = %.2f mean free paths, B = %.1f (narrow beam %.1f cm)"
      % (TARGET_UGY_H, thickness, mu * thickness, buildup(mu * thickness), math.log(unshielded / TARGET_UGY_H) / mu))
