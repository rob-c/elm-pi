"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Nothing is statistical. With the project's own constants (constants.py:
TAU_N = 877.75 s, G_LOCAL = 9.80297 m/s2), the wall potential of 213 neV from
trap.md, and the CODATA 2022 neutron mass and magnetic moment as scipy 1.18
has them (e and h are exact):

    v_crit 6.38354596 m/s   wavelength 61.9723588 nm   h_max 2.07843435 m
    B 3.53188492 T          survival 0.71050239

Six significant figures were asked for. A correctly rounded answer is within
2.1e-6 of these (the worst is h_max, 2.07843), CODATA 2018 instead of 2022
within 2e-8, so 4e-6 is allowed. What remembered values do:

    m_n = 1.675e-27 kg      v 2e-5, wavelength 2e-5, h_max 4e-5
    e = 1.602e-19 C         v 6e-5, h_max and B 1.1e-4
    h = 6.626e-34 J s       wavelength 1.1e-5
    60.3 neV/T              B 1.3e-4
    g = 9.80665 or 9.81     h_max 3.8e-4 or 7.2e-4
    tau_n = 878.4 s         survival 2.5e-4
"""
import json
import math
from pathlib import Path

EXACT = {"v_crit_m_s": 6.38354596, "wavelength_nm": 61.9723588, "h_max_m": 2.07843435, "b_reflect_t": 3.53188492,
         "survival_fraction": 0.71050239}
TOLERANCE = 4e-6


def result():
    return json.loads(Path("result.json").read_text())


def off(key):
    return abs(result()[key] / EXACT[key] - 1)


def sources_text():
    return json.dumps(result().get("sources", "")).lower()


def test_result_file_has_the_five_numbers():
    data = result()
    for key in EXACT:
        assert isinstance(data[key], (int, float)) and not isinstance(data[key], bool) and math.isfinite(data[key]), key


def test_velocity_and_wavelength_to_six_figures():
    # Neutron mass, e and h.
    assert off("v_crit_m_s") < TOLERANCE and off("wavelength_nm") < TOLERANCE


def test_height_uses_the_gravity_measured_in_the_hall():
    assert off("h_max_m") < TOLERANCE


def test_field_to_six_figures():
    # The neutron's magnetic moment, 9.6623653e-27 J/T.
    assert off("b_reflect_t") < TOLERANCE


def test_survival_uses_the_lifetime_the_analysis_adopted():
    assert off("survival_fraction") < TOLERANCE


def test_sources_name_the_project_file():
    # The file, or the names of the two values taken from it.
    text = sources_text()
    assert "constants.py" in text or "tau_n" in text or "g_local" in text


def test_sources_say_where_the_codata_values_came_from():
    text = sources_text()
    assert "scipy" in text or "codata" in text or "nist" in text
