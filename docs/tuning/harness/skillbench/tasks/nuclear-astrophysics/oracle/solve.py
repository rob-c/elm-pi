"""The reference solution: run in the project folder, writes result.json.

Beam energies to the centre of mass, cross sections to S-factors, a straight line
through S(E) extrapolated under the Gamow peak, the rate integral done numerically, and
the narrow-resonance rate with the resonance energy in the centre of mass and the
strength in MeV. Masses and constants as in notes.md.
"""
import json

import numpy as np
from scipy.integrate import quad

M_P, M_T, Z1, Z2 = 1.007825, 14.003074, 1, 7
U_MEV, ALPHA, HBARC_MEV_CM = 931.494, 1 / 137.036, 197.327e-13
K_MEV_PER_GK, N_A, C_CM_S = 8.61733e-5 * 1e9 / 1e6, 6.02214e23, 2.99792e10
T9 = 0.12
E_RES_LAB_MEV, STRENGTH_MEV = 278.1e-3, 13.1e-9

mu = M_P * M_T / (M_P + M_T)                         # u
to_cm = M_T / (M_P + M_T)
kt = K_MEV_PER_GK * T9                               # MeV
b = 2 * np.pi * Z1 * Z2 * ALPHA * np.sqrt(mu * U_MEV / 2)        # 2 pi eta = b / sqrt(E), E in MeV


def two_pi_eta(energy):
    return b / np.sqrt(energy)


data = np.loadtxt("cross_sections.csv", delimiter=",", skiprows=1)
energy = data[:, 0] * 1e-3 * to_cm                   # MeV, centre of mass
s_factor = data[:, 1] * 1e-9 * energy * np.exp(two_pi_eta(energy))          # MeV b
s_error = s_factor * data[:, 2] / data[:, 1]
slope, intercept = np.polyfit(energy, s_factor, 1, w=1 / s_error)

e0 = (b * kt / 2) ** (2 / 3)
width = 4 * np.sqrt(e0 * kt / 3)


def integrand(e):
    return (intercept + slope * e) * 1e-24 * np.exp(-e / kt - two_pi_eta(e))        # MeV cm2


edges = [e0 + n * width for n in (-1.2, -0.6, 0, 0.6, 1.2, 2.5) if e0 + n * width > 0]
integral = quad(integrand, 1e-4, e0 + 12 * width, points=edges, limit=400)[0]
mean_speed_factor = np.sqrt(8 / (np.pi * mu * U_MEV)) * C_CM_S                       # cm/s MeV^-1/2
nonresonant = N_A * mean_speed_factor * kt**-1.5 * integral

e_res = E_RES_LAB_MEV * to_cm
resonance = (N_A * (2 * np.pi / (mu * U_MEV * kt)) ** 1.5 * HBARC_MEV_CM**2 * C_CM_S
             * STRENGTH_MEV * np.exp(-e_res / kt))

json.dump({"gamow_peak_kev": e0 * 1e3, "gamow_width_kev": width * 1e3,
           "rate_nonresonant_cm3_mol_s": nonresonant, "rate_resonance_cm3_mol_s": resonance},
          open("result.json", "w"), indent=1)
print("mu %.5f u, kT %.3f keV, E0 %.2f keV, 1/e width %.2f keV" % (mu, kt * 1e3, e0 * 1e3, width * 1e3))
print("S(E) = %.3f + %.2e E[keV] keV b; non-resonant %.4g; resonance at %.2f keV (c.m.) %.4g cm3/mol/s"
      % (intercept * 1e3, slope, nonresonant, e_res * 1e3, resonance))
