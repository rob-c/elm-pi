"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

The cross sections are generated from a smooth S-factor, S(E) = S0 + S1 E with E the
centre-of-mass energy, and tabulated against the proton beam (laboratory) energy with 3%
scatter. The Gamow window at T9 = 0.12 (68 to 145 keV) lies mostly below the lowest
point (121 keV in the centre of mass), so the rate needs S extrapolated, not sigma.
The numbers are in the neighbourhood of 14N(p,gamma)15O but are not an evaluation.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

M_P, M_N14 = 1.007825, 14.003074           # atomic masses, u
Z1, Z2 = 1, 7
ALPHA, U_KEV = 1 / 137.036, 931494.0
S0, S1 = 1.62, 8.0e-4                      # keV b, and keV b per keV: the truth
SCATTER = 0.03

mu = M_P * M_N14 / (M_P + M_N14)
e_lab = np.arange(130.0, 251.0, 10.0)
e_cm = e_lab * M_N14 / (M_P + M_N14)
two_pi_eta = 2 * np.pi * Z1 * Z2 * ALPHA * np.sqrt(mu * U_KEV / (2 * e_cm))
sigma_nb = (S0 + S1 * e_cm) / e_cm * np.exp(-two_pi_eta) * 1e9
measured = sigma_nb * (1 + SCATTER * rng.standard_normal(len(e_lab)))
rows = ["E_p_lab_keV,sigma_nb,dsigma_nb"] + ["%.0f,%.4g,%.2g" % (e, s, SCATTER * s) for e, s in zip(e_lab, measured)]
(out / "cross_sections.csv").write_text("\n".join(rows) + "\n")
(out / "notes.md").write_text("""# 14N(p,gamma)15O: capture cross sections below the resonance

## cross_sections.csv

Total capture cross section from the autumn runs on the solid TiN target.
E_p_lab_keV is the proton beam energy in the laboratory, already corrected to
the effective energy in the target; sigma_nb is the cross section in nanobarn
and dsigma_nb its statistical uncertainty (one standard deviation). The 14N is
at rest. Electron screening is below 1% at these energies and is not
corrected for.

## The resonance

From the literature, as quoted there: proton energy at resonance
E_p(lab) = 278.1 keV, strength omega-gamma = 13.1 meV, total width about
1 keV. Our points stop below it and its tail is negligible in them.

## Masses and constants

- Atomic masses: 1H 1.007825 u, 14N 14.003074 u.
- u c^2 = 931.494 MeV; fine-structure constant 1/137.036; hbar c = 197.327 MeV fm.
- Boltzmann constant 8.61733e-5 eV/K; Avogadro constant 6.02214e23 per mol;
  c = 2.99792e10 cm/s.
- Temperature wanted: T9 = 0.12 (the rate is for the CNO cycle in the
  hydrogen-burning shell models).
""")
print("mu = %.5f u; E_cm %.1f to %.1f keV; sigma %.3g to %.3g nb" % (mu, e_cm[0], e_cm[-1], measured[0], measured[-1]))
