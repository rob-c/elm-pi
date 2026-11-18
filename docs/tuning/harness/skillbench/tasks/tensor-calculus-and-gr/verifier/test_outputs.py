"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The expected values are exact. For ds^2 = -f dt^2 + dr^2/f + r (r - Q^2/M) dOmega^2
with f = 1 - 2M/r, in the conventions notes.md writes out (Weinberg's:
R^l_{mnk} = d_k Gamma^l_{mn} - ..., R_{mk} = R^l_{mlk}; a unit sphere has
R = -2), coordinate components:

    R_tt          = -M Q^2 (r - 2M) / (r^4 (M r - Q^2))
    R_rr          = Q^2 (2 M^2 - Q^2) / (2 r (r - 2M) (M r - Q^2)^2)
    R_theta,theta = -Q^2 / r^2,   R_phi,phi = sin^2(theta) R_theta,theta
    R             = -Q^4 (r - 2M) / (2 r^3 (M r - Q^2)^2)
    K             = (192 M^6 r^4 - 576 M^5 Q^2 r^3 + 720 M^4 Q^4 r^2 - 432 M^3 Q^6 r - 32 M^3 Q^4 r^3
                     + 108 M^2 Q^8 + 40 M^2 Q^6 r^2 - 20 M Q^8 r + 3 Q^8 r^2) / (4 r^6 (M r - Q^2)^4)

oracle/solve.py derives them twice (the definitions of the note, and
sympy.diffgeom with its sign fixed on the unit sphere) and checks them against
the dilaton equation, R = -2 g^{rr} (phi')^2, and the Schwarzschild limit
K = 48 M^2 / r^6. At M = 1, Q = 0.8, r = 3, theta = pi/3:

    R_tt = -0.00334798   R_rr = +0.0260462   R_theta,theta = -0.0711111   R_phi,phi = -0.0533333
    R    = -0.00136189   K    = 0.0847515

The tolerance is 0.5%: room for three significant figures in the file, nothing
else. With the Misner-Thorne-Wheeler definition of the Riemann tensor (the
textbook default, and sympy.diffgeom's) the four Ricci components and R have
the opposite sign; in an orthonormal frame R_tt, R_rr, R_theta,theta and
R_phi,phi are -0.0100, +0.0087, -0.0100, -0.0100.
"""
import json
import math
from pathlib import Path

M, Q, R, THETA = 1.0, 0.8, 3.0, math.pi / 3
D = M * R - Q ** 2
EXPECTED = {
    "ricci_tt": -M * Q ** 2 * (R - 2 * M) / (R ** 4 * D),
    "ricci_rr": Q ** 2 * (2 * M ** 2 - Q ** 2) / (2 * R * (R - 2 * M) * D ** 2),
    "ricci_thth": -Q ** 2 / R ** 2,
    "ricci_phph": -Q ** 2 * math.sin(THETA) ** 2 / R ** 2,
    "ricci_scalar": -Q ** 4 * (R - 2 * M) / (2 * R ** 3 * D ** 2),
    "kretschmann": (192 * M ** 6 * R ** 4 - 576 * M ** 5 * Q ** 2 * R ** 3 + 720 * M ** 4 * Q ** 4 * R ** 2
                    - 432 * M ** 3 * Q ** 6 * R - 32 * M ** 3 * Q ** 4 * R ** 3 + 108 * M ** 2 * Q ** 8
                    + 40 * M ** 2 * Q ** 6 * R ** 2 - 20 * M * Q ** 8 * R + 3 * Q ** 8 * R ** 2) / (4 * R ** 6 * D ** 4),
}


def result():
    data = json.loads(Path("result.json").read_text())
    for key in EXPECTED:
        assert isinstance(data[key], (int, float)) and not isinstance(data[key], bool) and math.isfinite(data[key]), key
    return data


def close(data, key):
    return abs(data[key] - EXPECTED[key]) <= 5e-3 * abs(EXPECTED[key])


def test_result_file_has_six_numbers():
    result()


def test_ricci_signs_are_those_of_the_stated_convention():
    data = result()
    assert data["ricci_tt"] < 0 and data["ricci_rr"] > 0 and data["ricci_thth"] < 0 and data["ricci_scalar"] < 0


def test_time_and_radial_components():
    data = result()
    assert close(data, "ricci_tt"), "R_tt = %.6g" % EXPECTED["ricci_tt"]
    assert close(data, "ricci_rr"), "R_rr = %.6g" % EXPECTED["ricci_rr"]


def test_angular_components_are_coordinate_components():
    data = result()
    assert close(data, "ricci_thth"), "R_theta,theta = -Q^2/r^2 = %.6g" % EXPECTED["ricci_thth"]
    assert close(data, "ricci_phph"), "R_phi,phi = sin^2(theta) R_theta,theta = %.6g" % EXPECTED["ricci_phph"]


def test_ricci_scalar():
    assert close(result(), "ricci_scalar"), "R = %.6g" % EXPECTED["ricci_scalar"]


def test_kretschmann_scalar():
    assert close(result(), "kretschmann"), "K = %.6g" % EXPECTED["kretschmann"]
