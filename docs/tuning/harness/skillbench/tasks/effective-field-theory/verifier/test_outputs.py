"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# From oracle/solve.py with the numbers of notes.md (M = 3 TeV, g_e = 0.40, g_tau = 0.60,
# Lambda = 1 TeV, alpha = 1/128). Integrating out the Z' gives L_eff = -J.J/(2 M^2):
#   C_etau = - g_e g_tau Lambda^2/M^2 = -0.24/9        C_ee = - g_e^2 Lambda^2/(2 M^2) = -0.16/18
# and with x = C_etau s/(4 pi alpha Lambda^2), sigma/sigma_SM = (1 + x)^2: r_lin = 2x,
# r_quad = x^2 at sqrt(s) = 1 TeV, and |r_quad| = 0.2 |r_lin| where |x| = 0.4. The oracle gets
# the coefficients from the equation of motion and again from the Feynman rules, and checks
# that the EFT cross section approaches the full theory's as s/M^2 -> 0.
TRUE = {"c_ee": -0.00888888889, "c_etau": -0.0266666667, "r_lin": -0.543248872, "r_quad": 0.0737798343,
        "sqrt_s_max_gev": 1213.51620}
# Closed forms of given numbers, asked for to six digits: 1e-4 passes a value rounded to five
# digits or six decimals and nothing else. A wrong sign or a missing 1/2 in the matching is a
# factor of -1 or 2.
TOLERANCE = 1e-4


def result():
    return json.loads(Path("result.json").read_text())


def close(key):
    return abs(result()[key] / TRUE[key] - 1) < TOLERANCE


def test_result_file_has_the_five_numbers():
    data = result()
    for key in TRUE:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_coefficient_of_the_electron_tau_operator():
    assert close("c_etau")


def test_coefficient_of_the_four_electron_operator():
    assert close("c_ee")


def test_matching_has_the_sign_of_the_heavy_propagator():
    data = result()
    assert data["c_etau"] < 0 and data["c_ee"] < 0, "1/(q^2 - M^2) -> -1/M^2: same-sign couplings give negative C"


def test_operator_with_two_identical_currents_has_its_half():
    data = result()
    assert abs(data["c_ee"] / data["c_etau"] - 1.0 / 3.0) < 1e-4, "C_ee/C_etau = g_e/(2 g_tau)"


def test_linear_term():
    assert close("r_lin"), "interference with the photon is destructive below the Z' pole: 2x = -0.5432"


def test_quadratic_term():
    assert close("r_quad")


def test_validity_limit():
    assert close("sqrt_s_max_gev")
