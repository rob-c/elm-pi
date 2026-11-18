"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Truth (oracle/make_environment.py): the cross sections were generated from
S(E) = 1.62 + 8.0e-4 E[keV] keV b, E in the centre of mass, with 3% scatter; reduced
mass 0.94016 u, T9 = 0.12, kT = 10.341 keV.

  Gamow peak   (b kT / 2)^(2/3) = 106.44 keV; the maximum of the integrand found
               numerically is 106.44 keV, 106.78 keV with S(E) in it
  1/e width    4 sqrt(E0 kT / 3) = 76.62 keV; measured on the true peak, 77.3 keV
  non-resonant N_A<sigma v> = 4.238e-6 cm3/mol/s, the true S(E) integrated by quad and
               on a 2e6-point grid. From the file: straight-line fit of S +0.5%,
               constant +2.9%, quadratic +2.8%, the saddle-point formula -1.7%. The
               straight-line fit scatters by 1.7% over noise draws: tolerance 10%.
  resonance    E_r = 278.1 x 14.003074/15.010899 = 259.43 keV in the centre of mass,
               omega-gamma = 1.31e-8 MeV: 6.77e-7 cm3/mol/s (6.68e-7 with 14/15).

Beam energies used as centre-of-mass energies give 2.3e-6 (45% low) and 1.1e-7 (a
factor 6 low); the cross section integrated over the measured range only, 1.6e-6; ln
sigma extrapolated linearly, six times too much.
"""
import json
import math
from pathlib import Path

GAMOW_PEAK_KEV = 106.44
GAMOW_WIDTH_KEV = 76.62
RATE_NONRESONANT = 4.238e-6
RATE_RESONANCE = 6.77e-7


def result():
    # Keys compared without case: both arms of the first run wrote "..._keV", and the unit's spelling is not the task.
    return {key.lower(): value for key, value in json.loads(Path("result.json").read_text()).items()}


def test_result_file_has_the_four_numbers():
    data = result()
    for key in ("gamow_peak_kev", "gamow_width_kev", "rate_nonresonant_cm3_mol_s", "rate_resonance_cm3_mol_s"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_gamow_peak_energy():
    assert abs(result()["gamow_peak_kev"] / GAMOW_PEAK_KEV - 1) < 0.015


def test_gamow_width_is_the_full_width_at_1_over_e():
    assert abs(result()["gamow_width_kev"] / GAMOW_WIDTH_KEV - 1) < 0.05


def test_nonresonant_rate():
    assert abs(result()["rate_nonresonant_cm3_mol_s"] / RATE_NONRESONANT - 1) < 0.10


def test_resonance_energy_is_in_the_centre_of_mass():
    # 278.1 keV is a beam energy; in the exponent it costs exp(-11.605 x 0.0187 / 0.12) = 0.16.
    assert result()["rate_resonance_cm3_mol_s"] > 0.5 * RATE_RESONANCE


def test_resonance_rate():
    assert abs(result()["rate_resonance_cm3_mol_s"] / RATE_RESONANCE - 1) < 0.06
