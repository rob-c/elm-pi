"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Nothing is random: a thermal relic whose abundance has to be computed from the
note alone. What the note is built around:
- the Planck mass it gives is the reduced one, 2.4353e18 GeV, and its expansion
  rate is written with it; the textbook freeze-out formulas (H = 1.66 sqrt(g*)
  T^2 / M_Pl, lambda = 0.264 ...) want 1.2209e19 GeV, a factor sqrt(8 pi) = 5.01;
- the cross section is in cm^3/s and has to become GeV^-2 with (hbar c)^2 c;
- it has a p-wave part as large as the s-wave part at freeze-out, whose thermal
  average is 6 b / x and which keeps annihilating long after freeze-out, so the
  yield must be followed to large x;
- the equation is stiff while Y tracks its equilibrium value.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

(out / "relic.md").write_text("""# Singlet Majorana dark matter: inputs and conventions for the relic abundance

## The particle

- chi is a Majorana fermion (its own antiparticle) with mass m = 150 GeV and
  g = 2 internal degrees of freedom.
- Annihilation chi chi -> Standard Model, expanded at low velocity as
  sigma v = a + b v^2, with v the relative velocity of the two particles:
  a = 0.8e-26 cm^3/s, b = 9.0e-26 cm^3/s.
- chi stays in kinetic equilibrium with the plasma; there is no coannihilation
  and no resonance or threshold nearby.

## Cosmology (hbar = c = k_B = 1)

- Radiation domination: H^2 = rho / (3 Mbar_Pl^2) with rho = (pi^2/30) g_* T^4,
  and entropy density s = (2 pi^2/45) g_*s T^3.
- Mbar_Pl = (8 pi G)^(-1/2) = 2.4353e18 GeV, the reduced Planck mass.
- g_* = g_*s = 86.25, to be taken constant (freeze-out is at a few GeV).
- Equilibrium number density n_eq = g (m T / (2 pi))^(3/2) exp(-m/T).
- Boltzmann equation dn/dt + 3 H n = -<sigma v> (n^2 - n_eq^2); we use
  Y = n/s and x = m/T.
- We quote the freeze-out point x_f as the x at which Y = 2.5 Y_eq.
- No entropy is produced after freeze-out: the yield today is the late-time
  limit of Y.

## Constants

- hbar c = 1.973270e-14 GeV cm
- c = 2.997925e10 cm/s
- entropy density today s_0 = 2891.2 cm^-3
- critical density today rho_c / h^2 = 1.0537e-5 GeV cm^-3
""")
print("wrote relic.md")
