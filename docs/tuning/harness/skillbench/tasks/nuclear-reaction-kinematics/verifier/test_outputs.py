"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The expected values follow from environment/notes.md alone (nothing is generated
at random). oracle/solve.py, relativistic, with the non-relativistic value
beside it:

    E_cm                         1.8833 MeV     (1.8835)
    neutron energies at 10 deg   2.7692 MeV     (2.7798)   theta_cm  39.2 deg, dOmega_cm/dOmega_lab 15.18 (15.12)
                                 0.7484 MeV     (0.7425)   theta_cm 160.8 deg, dOmega_cm/dOmega_lab  4.10  (3.97)
    beam                         60 nA / (3 e)             = 1.2483e11 /s
    hydrogen                     50 ug/cm2 x N_A/14.027 x 2 = 4.2932e18 /cm2
    rate = beam x hydrogen x 24 mb/sr x (15.18 + 4.10) x 0.5 msr = 124.0 /s   (122.8)

The tolerances - 0.5% on E_cm, 2% on each energy, 5% on the rate - are set so
that a correct non-relativistic calculation passes (it is 0.8% out on the slow
group and 1.0% on the rate) and each of these does not: the slow group left
out of the rate (-21%), no Jacobian (a factor 9.6), current over e instead of
over 3e (a factor 3), one hydrogen per CH2 (a factor 2). The detector's 0.72
degree half-angle changes the rate by 0.01%.
"""
import json
import math
from pathlib import Path

E_CM = 1.8833
FAST, SLOW = 2.7692, 0.7484
RATE = 124.0


def result():
    return json.loads(Path("result.json").read_text())


def energies():
    listed = result()["neutron_energies_mev"]
    if isinstance(listed, (int, float)):
        listed = [listed]
    return [float(value) for value in listed]


def test_result_file_has_the_three_entries():
    data = result()
    for key in ("e_cm_mev", "rate_per_s"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key
    assert energies() and all(math.isfinite(value) for value in energies())


def test_centre_of_mass_energy():
    assert abs(result()["e_cm_mev"] / E_CM - 1) < 0.005


def test_fast_neutron_group():
    assert any(abs(value / FAST - 1) < 0.02 for value in energies())


def test_slow_neutron_group_is_reported_too():
    assert any(abs(value / SLOW - 1) < 0.02 for value in energies()), "inside the cone each lab angle has two energies"


def test_nothing_else_is_listed():
    assert len(energies()) == 2


def test_rate_into_the_detector():
    assert abs(result()["rate_per_s"] / RATE - 1) < 0.05, "both groups, each with its Jacobian; 1.248e11 ions/s; 4.293e18 H/cm2"
