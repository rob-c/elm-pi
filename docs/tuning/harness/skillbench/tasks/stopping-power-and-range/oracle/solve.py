"""The reference solution: run in the project folder, writes result.json.

The plate takes more than half the beam energy, so the loss is not S(E0) x thickness.
Build the CSDA range R(E) = integral of dE/S from the table, then R(E_out) = R(E_in) - t.
"""
import json

import numpy as np
from scipy.integrate import cumulative_trapezoid
from scipy.interpolate import interp1d

BEAM_MEV, PLATE_MG_CM2, DENSITY, WANTED_MEV = 17.0, 270.0, 2.699, 5.0      # notes.md

table = np.loadtxt("stopping_power.csv", delimiter=",", skiprows=1)
log_s = interp1d(np.log(table[:, 0]), np.log(table[:, 1]), kind="cubic")

energy = np.geomspace(table[0, 0], table[-1, 0], 20001)
stopping = np.exp(log_s(np.log(energy)))
# Below the first row S goes as sqrt(E), so the range up to it is 2 E / S.
range_g_cm2 = 2 * energy[0] / stopping[0] + cumulative_trapezoid(1 / stopping, energy, initial=0)


def range_of(e):
    return float(np.interp(e, energy, range_g_cm2))


def energy_at(r):
    return float(np.interp(r, range_g_cm2, energy))


plate = PLATE_MG_CM2 / 1000.0                                   # g/cm2
after = energy_at(range_of(BEAM_MEV) - plate)
needed = range_of(BEAM_MEV) - range_of(WANTED_MEV)              # g/cm2
result = {
    "range_mm": range_of(BEAM_MEV) / DENSITY * 10,
    "energy_after_degrader_mev": after,
    "thickness_for_5mev_mm": needed / DENSITY * 10,
}
json.dump(result, open("result.json", "w"), indent=1)
print("range %.4f g/cm2 = %.3f mm; after the plate %.3f MeV; for %.1f MeV %.4f g/cm2 = %.3f mm"
      % (range_of(BEAM_MEV), result["range_mm"], after, WANTED_MEV, needed, result["thickness_for_5mev_mm"]))
