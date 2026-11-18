"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The expected values follow from environment/mass_excess.csv and notes.md alone
(oracle/solve.py; nothing is generated at random):

    Q(beta-)             = D(Cu-64) - D(Zn-64)                    =   579.60 keV
    Q(EC)                = D(Cu-64) - D(Ni-64)                    =  1674.62 keV
    beta+ endpoint       = Q(EC) - 2 x 510.999                    =   652.62 keV
    K-capture neutrino   = Q(EC) - 8.333 (- 0.02 recoil)          =  1666.27 keV
    Q(alpha)             = D(Gd-148) - D(Sm-144) - D(He-4)        =  3271.21 keV
    alpha kinetic energy = Q M(Sm-144) / (M(Sm-144) + M(He-4))    =  3182.66 keV (exact), 3182.69 (non-relativistic),
                                                                     3182.80 with (A-4)/A
    threshold            = -Q (m_p + m_4He + m_d + m_3He)/(2 m_4He) = 23018.1 keV with nuclear masses,
                                                                      23019.4 with atomic ones

The inputs are given to 0.01 keV or better, so the tolerances are arithmetic
ones: 0.5 keV, and 6 keV on the threshold to take both choices of mass. What
they shut out: no 2 m_e (1022 keV), the K binding energy ignored (8.3 keV),
Q for the alpha's energy (88.5 keV), the non-relativistic threshold (45 keV low).
"""
import json
import math
from pathlib import Path

EXPECTED = {
    "q_beta_minus_kev": 579.60,
    "beta_plus_endpoint_kev": 652.62,
    "k_capture_neutrino_kev": 1666.28,
    "q_alpha_kev": 3271.21,
    "alpha_energy_kev": 3182.70,
    "threshold_kev": 23018.8,
}


def result():
    return json.loads(Path("result.json").read_text())


def off(key):
    return result()[key] - EXPECTED[key]


def test_result_file_has_the_six_numbers():
    data = result()
    for key in EXPECTED:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_beta_minus_q_value():
    assert abs(off("q_beta_minus_kev")) < 0.5


def test_beta_plus_endpoint_has_the_two_electron_masses():
    assert abs(off("beta_plus_endpoint_kev")) < 0.5, "Q(EC) is 1674.62 keV; the positron endpoint is 1022 keV below it"


def test_k_capture_neutrino_has_no_electron_masses_and_loses_the_k_binding():
    assert abs(off("k_capture_neutrino_kev")) < 0.5


def test_alpha_q_value():
    assert abs(off("q_alpha_kev")) < 0.5


def test_alpha_energy_is_less_than_q_by_the_recoil():
    assert abs(off("alpha_energy_kev")) < 0.5, "the Sm-144 recoil takes 88.5 keV of Q"


def test_threshold_is_the_exact_one():
    assert abs(off("threshold_kev")) < 6.0, "exact 23018 to 23019 keV; -Q (m_p + m_He)/m_He gives 22973 to 22974"
