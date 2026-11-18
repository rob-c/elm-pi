"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Expected values: the analytic square-well solution for notes.md (oracle/solve.py), with
mu = 750.409 MeV, hbar^2/2mu = 25.9445 MeV fm^2, E_cm = 25.0 x 3727.379/4666.944 =
19.967 MeV, k = 0.87727 /fm, k R = 2.28. Confirmed by integrating the radial equation
(scipy's solve_ivp matched at 3 and at 6 fm, and Numerov matched at two pairs of radii):
all agree to 1e-4 degrees. The s wave also from tan(delta_0 + k R) = (k/K) tan(K R).

  delta_0 58.80, delta_1 68.00, delta_2 14.19, delta_3 0.93 degrees
  sigma   0.5899 b; s and p alone 0.5406 b (8% low), with d 0.5896 b
  a       -3.376 fm in the notes' convention k cot(delta_0) = +1/a (the well binds one
          s state: +3.376 fm in the nuclear convention); r = 1.766 fm from the closed
          form and from a fit below 0.2 MeV

Nothing is statistical. The tolerances cover relativistic kinematics for k (58.65,
67.92 degrees, 0.5873 b), mass numbers for the masses (58.75, 68.06, 0.5891 b) and a
straight-line fit of k cot(delta) up to 2 MeV (r 2.4% high). The beam energy used as
the centre-of-mass energy gives 51.97 and 63.61 degrees; the neutron mass for the
reduced mass, a = 2.93 and r = 1.62 fm. Phases are compared modulo 180 degrees.
"""
import json
import math
from pathlib import Path

DELTA0_DEG, DELTA1_DEG = 58.80, 68.00
SIGMA_B = 0.5899
SIGMA_S_AND_P_B = 0.5406
SCATTERING_LENGTH_FM = -3.376
EFFECTIVE_RANGE_FM = 1.766


def result():
    return json.loads(Path("result.json").read_text())


def apart(angle, reference):
    """Difference of two phases in degrees, modulo 180."""
    return abs((angle - reference + 90.0) % 180.0 - 90.0)


def test_result_file_has_the_five_numbers():
    data = result()
    for key in ("delta0_deg", "delta1_deg", "sigma_b", "scattering_length_fm", "effective_range_fm"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_s_wave_phase_shift():
    assert apart(result()["delta0_deg"], DELTA0_DEG) < 1.0


def test_p_wave_phase_shift():
    assert apart(result()["delta1_deg"], DELTA1_DEG) < 1.0


def test_partial_wave_sum_has_converged():
    assert result()["sigma_b"] > SIGMA_S_AND_P_B + 0.02, "k R = 2.28: the d wave is 8% of the cross section"


def test_total_cross_section_in_barn():
    assert abs(result()["sigma_b"] / SIGMA_B - 1) < 0.015


def test_scattering_length_has_the_sign_of_the_notes_convention():
    assert result()["scattering_length_fm"] < 0, "k cot(delta_0) = +1/a: a well with a bound s state has a < 0"


def test_scattering_length():
    assert abs(result()["scattering_length_fm"] / SCATTERING_LENGTH_FM - 1) < 0.01


def test_effective_range():
    assert abs(result()["effective_range_fm"] / EFFECTIVE_RANGE_FM - 1) < 0.03
