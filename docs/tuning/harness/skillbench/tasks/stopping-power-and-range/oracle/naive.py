"""What the task is built to catch: the loss in a thick plate taken as S(E0) x thickness.

The range itself is integrated properly; the two plate numbers use the stopping power at
the beam energy all the way through, as if the plate were thin.
"""
import json

import numpy as np

table = np.loadtxt("stopping_power.csv", delimiter=",", skiprows=1)
energy, stopping = table[:, 0], table[:, 1]
beam, plate, density, wanted = 17.0, 0.2700, 2.699, 5.0

fine = np.linspace(energy[0], beam, 5001)
range_g_cm2 = np.trapezoid(1 / np.interp(fine, energy, stopping), fine)
s_beam = np.interp(beam, energy, stopping)
json.dump({
    "range_mm": range_g_cm2 / density * 10,
    "energy_after_degrader_mev": beam - s_beam * plate,
    "thickness_for_5mev_mm": (beam - wanted) / s_beam / density * 10,
}, open("result.json", "w"))
