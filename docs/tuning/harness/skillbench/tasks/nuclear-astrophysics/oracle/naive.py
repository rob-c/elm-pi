"""What the task is built to catch: laboratory energies in formulas that need centre-of-mass ones.

The beam energy goes straight into the Sommerfeld factor and the S-factor, and the
resonance energy as quoted (278.1 keV, a proton beam energy) into the exponent. The rest
is done properly: S fitted and extrapolated, the integral numerical, the units right.
"""
import json

import numpy as np
from scipy.integrate import quad

mu = 1.007825 * 14.003074 / (1.007825 + 14.003074)
kt = 0.0861733 * 0.12
b = 2 * np.pi * 7 / 137.036 * np.sqrt(mu * 931.494 / 2)

data = np.loadtxt("cross_sections.csv", delimiter=",", skiprows=1)
energy = data[:, 0] * 1e-3
s_factor = data[:, 1] * 1e-9 * energy * np.exp(b / np.sqrt(energy))
slope, intercept = np.polyfit(energy, s_factor, 1)

e0 = (b * kt / 2) ** (2 / 3)
width = 4 * np.sqrt(e0 * kt / 3)
integral = quad(lambda e: (intercept + slope * e) * 1e-24 * np.exp(-e / kt - b / np.sqrt(e)), 1e-4, 1.0,
                points=[e0 - width, e0, e0 + width], limit=400)[0]
nonresonant = 6.02214e23 * np.sqrt(8 / (np.pi * mu * 931.494)) * 2.99792e10 * kt**-1.5 * integral
resonance = 1.5399e11 * (mu * 0.12) ** -1.5 * 13.1e-9 * np.exp(-11.605 * 0.2781 / 0.12)
json.dump({"gamow_peak_kev": e0 * 1e3, "gamow_width_kev": width * 1e3,
           "rate_nonresonant_cm3_mol_s": nonresonant, "rate_resonance_cm3_mol_s": resonance},
          open("result.json", "w"))
