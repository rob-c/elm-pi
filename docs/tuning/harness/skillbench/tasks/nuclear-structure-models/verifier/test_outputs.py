"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The expected values follow from environment/notes.md alone (nothing is generated
at random): E(2+) = 81.976 keV, E(4+) = 266.79 keV, T1/2 = 3.10 ns, alpha = 4.94,
Z = 62, A = 154, and the constants written there (oracle/solve.py):

    mean life          = 3.10 / ln 2                         = 4.472 ns
    gamma-ray rate     = 1 / (4.472 ns x 5.94)               = 3.764e7 /s
    B(E2; 2+ -> 0+)    = rate / (1.223e9 x 0.081976^5)       = 8314 e2 fm4 = 169.6 W.u. (one W.u. is 49.03 e2 fm4)
    B(E2; 0+ -> 2+)    = 5 x that                            = 4.157 e2 b2
    beta2              = 4 pi / (3 x 62 x 6.432^2) x sqrt(41570) = 0.3330
    R(4/2)             = 266.79 / 81.976                     = 3.2545
    I / hbar^2         = 3 / E(2+)                           = 36.60 /MeV

Arithmetic only, so 1.5% on the strengths (which covers 1.22e9 or 1.225e9 for
the constant) and 1% elsewhere. What that shuts out: the 2+ -> 0+ value given
as the 0+ -> 2+ one (a factor 5; beta2 a factor 2.24), the half-life used as
the mean life (+44%), conversion ignored (a factor 5.94), e2 fm4 for e2 b2
(1e4), and the table value for Sm-154 (4.36 e2 b2, 5% away: the half-life here
is this measurement's, not the adopted one).
"""
import json
import math
from pathlib import Path

EXPECTED = {
    "be2_up_e2b2": 4.1571,
    "be2_down_wu": 169.57,
    "beta2": 0.33295,
    "r42": 3.25449,
    "moment_of_inertia_hbar2_per_mev": 36.596,
}


def result():
    return json.loads(Path("result.json").read_text())


def ratio(key):
    return result()[key] / EXPECTED[key]


def test_result_file_has_the_five_numbers():
    data = result()
    for key in EXPECTED:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_be2_is_the_excitation_value_in_e2b2():
    assert abs(ratio("be2_up_e2b2") - 1) < 0.015, "the lifetime gives B(E2; 2+ -> 0+) = 0.831 e2 b2; 0+ -> 2+ is five times that"


def test_decay_strength_in_weisskopf_units():
    assert abs(ratio("be2_down_wu") - 1) < 0.015, "8314 e2 fm4 over 49.03 e2 fm4"


def test_beta2_uses_the_excitation_value():
    assert abs(ratio("beta2") - 1) < 0.01


def test_r42():
    assert abs(ratio("r42") - 1) < 0.002


def test_moment_of_inertia():
    assert abs(ratio("moment_of_inertia_hbar2_per_mev") - 1) < 0.01, "E(2+) = 6 hbar^2 / (2 I)"
