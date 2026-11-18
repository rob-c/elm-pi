"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The expected values are exact: the traces over the left-handed Weyl fermions
of model.md (right-handed fields conjugated; colour, weak-isospin and
generation multiplicities counted; T(fundamental) = 1/2; Y as in the table,
Q = T3 + Y/2), computed in fractions by oracle/solve.py in two ways.

Assignment A, per generation with (q, u, d, l, e, n) = (1/3, 1, -2/3, -2, -3, -1),
times three (the vector-like T adds nothing):
    a_ccx = (2q - u - d)/2            = 1/6   -> 1/2
    a_wwx = (3q + l)/2                = -1/2  -> -3/2
    a_yyx = 2q/3 - 16u/3 - 4d/3 + 2l - 4e     -> 34/3
    a_yxx = 2q^2 - 4u^2 + 2d^2 - 2l^2 + 2e^2  -> 64/3
    a_xxx = 6q^3 - 3u^3 - 3d^3 + 2l^3 - e^3 - n^3 -> 91/3
    a_ggx = 6q - 3u - 3d + 2l - e - n         -> 3
Assignment B is 3Y + 3(B-L): all six vanish at z = -6 only, and x_H = x_Q - x_d = 3.

The tolerance (0.5%) only allows for three significant figures in the file.
The slips this is built to catch are far outside it: a missing colour or
isospin multiplicity (a_ccx 0, a_wwx -5/2, z = -2), right-handed fields not
conjugated (a_ccx 5/2, a_ggx -9), the index normalised to 1 (a_ccx 1,
a_wwx -3), one generation instead of three (everything a third), Y in the
other convention (a_yyx 17/6).
"""
import json
import math
from fractions import Fraction
from pathlib import Path

A = {"a_ccx": Fraction(1, 2), "a_wwx": Fraction(-3, 2), "a_yyx": Fraction(34, 3),
     "a_yxx": Fraction(64, 3), "a_xxx": Fraction(91, 3), "a_ggx": Fraction(3)}
Z_B = -6.0
X_HIGGS_B = 3.0


def result():
    return json.loads(Path("result.json").read_text())


def number(value):
    """A JSON number, or a fraction written as a string ("34/3")."""
    if isinstance(value, bool):
        raise AssertionError("a truth value where a number is wanted")
    if isinstance(value, str):
        value = float(Fraction(value.strip()))
    assert isinstance(value, (int, float)) and math.isfinite(value), value
    return float(value)


def close(got, want):
    return abs(number(got) - float(want)) <= 5e-3 * abs(float(want))


def test_result_file_has_every_key():
    data = result()
    for key in list(A) + ["z_b", "x_higgs_b"]:
        number(data[key])
    assert "anomaly_free_a" in data


def test_colour_and_weak_coefficients_of_assignment_a():
    data = result()
    assert close(data["a_ccx"], A["a_ccx"]), "a_ccx: 3 generations x (2 x_Q - x_u - x_d)/2"
    assert close(data["a_wwx"], A["a_wwx"]), "a_wwx: 3 generations x (3 x_Q + x_L)/2"


def test_hypercharge_coefficients_of_assignment_a():
    data = result()
    assert close(data["a_yyx"], A["a_yyx"])
    assert close(data["a_yxx"], A["a_yxx"])


def test_cubic_and_gravitational_coefficients_of_assignment_a():
    data = result()
    assert close(data["a_xxx"], A["a_xxx"])
    assert close(data["a_ggx"], A["a_ggx"])


def test_assignment_a_is_reported_anomalous():
    verdict = result()["anomaly_free_a"]
    if isinstance(verdict, str):
        verdict = {"false": False, "no": False, "true": True, "yes": True}[verdict.strip().lower()]
    assert verdict is False or verdict == 0


def test_open_charge_of_assignment_b():
    assert abs(number(result()["z_b"]) - Z_B) < 1e-3, "all six traces vanish only at z = -6"


def test_higgs_charge_of_assignment_b():
    assert abs(number(result()["x_higgs_b"]) - X_HIGGS_B) < 1e-3, "x_H = x_u - x_Q = x_Q - x_d = x_L - x_e = 3"
