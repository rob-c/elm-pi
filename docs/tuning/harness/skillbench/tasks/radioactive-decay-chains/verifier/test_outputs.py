"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The expected values follow from environment/notes.md alone (nothing is generated
at random): R = 2.60e11 /s for 144.0 h, 30.0 h to loading, half-lives 65.924 h
and 6.0067 h, 87.6% of Mo-99 decays to Tc-99m. oracle/solve.py gets them from
the matrix exponential of the decay matrix and again from the closed forms:

    A(Mo-99, end of irradiation) = R (1 - exp(-l1 144))           = 2.0280e11 Bq
    A(Mo-99, loading)            = that x exp(-l1 30)             = 1.4793e11 Bq
    t_max = ln(l2/l1)/(l2 - l1)                                   = 22.841 h
    A(Tc-99m, t_max) = 0.876 x A(Mo-99, t_max)                    = 1.0192e11 Bq
    N(Tc-99, t_max)  = Mo-99 decayed since loading - N(Tc-99m)    = 7.634e15

The inputs have four or five figures, so 1% is an arithmetic tolerance. What it
shuts out: rate x time with no decay during the irradiation (+94%), a mean life
taken for a half-life (+14% and t_max 15.8 h), the branch ignored (Tc-99m +14%,
Tc-99 -6%), the transient-equilibrium ratio used at the maximum (+10%), Tc-99
counted only through Tc-99m (-18%) or with the Tc-99m still there (+42%).
"""
import json
import math
from pathlib import Path

EXPECTED = {
    "a_mo99_eob_bq": 2.02796e11,
    "a_mo99_load_bq": 1.47935e11,
    "t_max_h": 22.8413,
    "a_tc99m_max_bq": 1.01923e11,
    "n_tc99_atoms": 7.6343e15,
}


def result():
    return json.loads(Path("result.json").read_text())


def ratio(key):
    return result()[key] / EXPECTED[key]


def test_result_file_has_the_five_numbers():
    data = result()
    for key in EXPECTED:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]) and data[key] > 0, key


def test_mo99_at_end_of_irradiation_has_decay_during_it():
    assert abs(ratio("a_mo99_eob_bq") - 1) < 0.01, "rate x time is 1.94 times too many atoms after 2.2 half-lives"


def test_mo99_at_loading():
    assert abs(ratio("a_mo99_load_bq") - 1) < 0.01


def test_time_of_the_tc99m_maximum():
    assert abs(ratio("t_max_h") - 1) < 0.01


def test_tc99m_activity_has_the_branching_fraction():
    assert abs(ratio("a_tc99m_max_bq") - 1) < 0.01, "87.6% of Mo-99 decays feed Tc-99m; without it this is 14% high"


def test_tc99_atoms_come_by_both_routes():
    assert abs(ratio("n_tc99_atoms") - 1) < 0.01, "12.4% directly, the rest through Tc-99m, less the Tc-99m still there"
