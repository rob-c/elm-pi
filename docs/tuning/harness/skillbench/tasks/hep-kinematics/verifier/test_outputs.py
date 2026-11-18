"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The event was generated from a system of mass 0.7814 GeV (oracle/make_environment.py) and written
to 0.01 MeV and 1e-5 rad, which moves the mass and the rapidity recomputed from the files by less
than 1e-4. The tolerances are fifty times that, so the choice of mass values or of formula cannot
matter, and still far inside the errors the task is about: clusters read as MeV give 0.351 GeV,
the pseudorapidity is 2.03 (the unit mix-up moves it to 1.73), and the usual wrong forms of
sqrt(s) give 2.56, 2.89, 4.08 or 8.88 GeV.
"""
import json
import math
from pathlib import Path

TRUE_MASS = 0.7814           # GeV
TRUE_RAPIDITY = 1.5344       # laboratory frame
TRUE_SQRT_S = 3.1764         # GeV: s = 2 m_p^2 + 2 (T + m_p) m_p with T = 3.5 GeV


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_three_numbers():
    data = result()
    for key in ("mass_gev", "rapidity", "sqrt_s_gev"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_mass_of_the_three_pion_system_in_gev():
    assert abs(result()["mass_gev"] - TRUE_MASS) < 0.005


def test_rapidity_of_the_massive_system_in_the_laboratory():
    assert abs(result()["rapidity"] - TRUE_RAPIDITY) < 0.005


def test_centre_of_mass_energy_for_a_target_at_rest():
    assert abs(result()["sqrt_s_gev"] - TRUE_SQRT_S) < 0.005
