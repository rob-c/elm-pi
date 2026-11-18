"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The expected values are the converged solution of the Boltzmann equation of
relic.md (oracle/solve.py: ln Y with Radau and Y with BDF, tolerance, start and
end varied, all agreeing to 1e-4; a hand-written backward-Euler integrator
agrees to 1e-4 as well):

    x_f = 24.380      Y today = 2.9661e-12      Omega h^2 = 0.12208

Tolerances, and what moves the answer by how much:
- Legitimate choices: the exact (Bessel K_2) equilibrium density instead of the
  non-relativistic one in the note, x_f +0.07 and Omega h^2 +0.5%; stopping at
  x = 1000 without the analytic tail, +1%; the rounded 0.264 and 1.22e19 GeV of
  the textbook form, 0.1%. Hence 0.25 on x_f and 4% on the yield and on
  Omega h^2.
- The slips: the reduced Planck mass in a formula written for the full one,
  x_f -1.5 and Omega h^2 x 4.5; cm^3/s converted without the factor c, off by
  ten orders of magnitude; <v^2> = 3/x for the p-wave term, x_f -0.44 and
  Omega h^2 +39%; the p-wave term dropped, x 2.3; stopping at x = 100, where
  the p-wave annihilation is still going on, +14%.
"""
import json
import math
from pathlib import Path

X_F, Y_TODAY, OMEGA_H2 = 24.380, 2.9661e-12, 0.12208
MASS, S_TODAY, RHO_CRIT = 150.0, 2891.2, 1.0537e-5       # GeV, cm^-3, GeV cm^-3 per h^2: relic.md


def result():
    data = json.loads(Path("result.json").read_text())
    for key in ("x_f", "y_today", "omega_h2"):
        assert isinstance(data[key], (int, float)) and not isinstance(data[key], bool) and math.isfinite(data[key]), key
    return data


def test_result_file_has_three_numbers():
    data = result()
    assert data["x_f"] > 0 and data["y_today"] > 0 and data["omega_h2"] > 0


def test_freeze_out_point():
    assert abs(result()["x_f"] - X_F) < 0.25, "Y = 2.5 Y_eq at x = 24.38"


def test_yield_today():
    assert abs(result()["y_today"] / Y_TODAY - 1) < 0.04


def test_relic_abundance():
    assert abs(result()["omega_h2"] / OMEGA_H2 - 1) < 0.04


def test_abundance_follows_from_the_yield():
    data = result()
    assert abs(data["omega_h2"] / (MASS * data["y_today"] * S_TODAY / RHO_CRIT) - 1) < 0.01, "Omega h^2 = m Y s_0 / (rho_c / h^2)"
