"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# From oracle/solve.py with the numbers of notes.md:
#   Gamma(S -> a a)        = (1/2) |p_a| kappa^2 / (8 pi M_S^2)                    = 0.0323561 GeV
#   Gamma(S -> chi chibar) = |p_chi| 2 y^2 (M_S^2 - 4 m_chi^2) / (8 pi M_S^2)      = 0.2232882 GeV
#   sigma(chi chibar -> a a) = (1/2) <|M|^2> |p_a| / (16 pi s |p_chi|) at sqrt(s) = 400 GeV
# with 1/2 for the identical a, the flux 4 |p_chi| sqrt(s) of massive beams, hbar and (hbar c)^2
# as given. The code reproduces sigma(e+ e- -> mu+ mu-) = 86.8 nb GeV^2/s and the two-body
# phase space from its defining integral.
TRUE = {"width_gev": 0.2556443, "lifetime_s": 2.574718e-24, "br_aa": 0.1265668, "sigma_pb": 0.2935025}
# 5e-4 takes hbar and (hbar c)^2 rounded to four figures (5e-5) and nothing else; a missing
# 1/2 is 13% in the width and 78% in the branching ratio, the massless flux 34% in sigma.
TOLERANCE = 5e-4
BETA_BEAM = math.sqrt(1 - 4 * 150.0**2 / 400.0**2)      # 2 lambda^(1/2)(s, m^2, m^2) = 2 s beta


def result():
    return json.loads(Path("result.json").read_text())


def close(key):
    return abs(result()[key] / TRUE[key] - 1) < TOLERANCE


def test_result_file_has_the_four_numbers():
    data = result()
    for key in TRUE:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]) and data[key] > 0, key


def test_total_width():
    assert close("width_gev")


def test_lifetime_is_hbar_over_the_total_width():
    assert close("lifetime_s")


def test_branching_ratio_counts_identical_particles_once():
    assert close("br_aa"), "without the 1/2 for two identical a it is 0.2247"


def test_cross_section_in_pb():
    assert close("sigma_pb")


def test_flux_factor_is_for_massive_beams():
    ratio = result()["sigma_pb"] / TRUE["sigma_pb"]
    for symmetry in (1.0, 2.0):
        assert abs(ratio / (symmetry * BETA_BEAM) - 1) > 0.01, "the flux is 2 s only for massless beams"


def test_cross_section_is_converted_from_gev_to_pb():
    ratio = result()["sigma_pb"] / TRUE["sigma_pb"]
    assert 1e-2 < ratio < 1e2, "1 GeV^-2 = 0.3894 mb = 3.894e8 pb"
