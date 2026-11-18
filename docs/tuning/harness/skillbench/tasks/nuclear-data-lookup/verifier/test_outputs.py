"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The expected values follow from environment/ag110_ensdf.txt alone (nothing is
generated at random; oracle/solve.py parses the file):

    isomer: the 117.59 keV 6+ level, "249.83 D 4"   = 21 585 312 s +- 3456 s   (the ground state is "24.56 S 11")
    its data set: NR = 0.9565(9), BR = 0.9867(8)    -> 0.94378 photons per 100 decays per unit RI, +-0.12%
    884.6781 keV, RI "78.4 3"       -> 0.73992 per decay, +-0.0030  (RI alone 0.0028; added linearly 0.0041)
    1562.294 keV, RI "1.28 +5-3"    -> 0.012080 per decay, +0.00047 -0.00028
    sum of E x photons per decay over the 15 lines  = 2748.1 keV

Values are held to 0.3% (they are products of numbers read from the file) and
uncertainties to windows that take any sensible propagation. What that shuts
out: RI taken as per cent of decays (6.0% high), NR without BR (1.3% high), the
ground state's half-life or normalisation, "D 4" read as 4 d or 0.4 d, "78.4 3"
as +-3 or +-0.03, and "+5-3" halved, swapped or made symmetric.
"""
import json
import math
from pathlib import Path

HALF_LIFE, HALF_LIFE_UNC = 249.83 * 86400, 0.04 * 86400
P_885 = 0.73992
P_1562 = 0.012080
ENERGY = 2748.06


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_eight_numbers():
    data = result()
    for key in ("half_life_s", "half_life_unc_s", "p_885", "p_885_unc", "p_1562", "p_1562_unc_plus",
                "p_1562_unc_minus", "gamma_energy_per_decay_kev"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_half_life_is_the_isomers_in_seconds():
    assert abs(result()["half_life_s"] / HALF_LIFE - 1) < 1e-4, "249.83 d, not the ground state's 24.56 s"


def test_half_life_uncertainty_is_in_the_last_digit():
    assert abs(result()["half_life_unc_s"] / HALF_LIFE_UNC - 1) < 0.02, "'249.83 D 4' is +-0.04 d"


def test_885_photons_per_decay_are_normalised():
    assert abs(result()["p_885"] / P_885 - 1) < 0.003, "RI 78.4 x NR 0.9565 x BR 0.9867 / 100"


def test_885_uncertainty():
    assert 0.0026 < result()["p_885_unc"] < 0.0045, "'78.4 3' is +-0.3, with 0.12% from the normalisation"


def test_1562_photons_per_decay():
    assert abs(result()["p_1562"] / P_1562 - 1) < 0.003


def test_1562_uncertainty_is_asymmetric_and_the_right_way_up():
    data = result()
    assert 0.00044 < abs(data["p_1562_unc_plus"]) < 0.00051, "'1.28 +5-3': +0.05 on RI"
    assert 0.00026 < abs(data["p_1562_unc_minus"]) < 0.00031, "'1.28 +5-3': -0.03 on RI"


def test_photon_energy_per_decay():
    assert abs(result()["gamma_energy_per_decay_kev"] / ENERGY - 1) < 0.003
