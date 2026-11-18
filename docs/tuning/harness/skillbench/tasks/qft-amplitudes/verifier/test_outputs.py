"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

import pytest

# <|M|^2> for g g -> t tbar at the three points of points.csv, alpha_s = 0.118, m_t = 173 GeV:
# physical polarisations only, averaged over 4 polarisation and 64 colour states. From
# oracle/solve.py, which sums the three diagrams with explicit spinors, polarisation vectors and
# Gell-Mann matrices and agrees to 1e-15 with the closed form
#   g^4 [1/(6 t1 t2) - 3/8] [t1^2 + t2^2 + rho - rho^2/(4 t1 t2)],  t_i = 2 k_i.p3/s, rho = 4 m^2/s
# (Ellis, Stirling and Webber). When the task was written the same numbers also came from the
# Particle Data Group's d(sigma)/dt and from the same diagrams with the polarisation sum
# -g_{mu nu} + (k_mu n_nu + k_nu n_mu)/(k.n) for each gluon, for two choices of n.
TRUE = {"msq_1": 0.446987281526, "msq_2": 0.623370121976, "msq_3": 0.425278967594}
# The same diagrams with -g_{mu nu} for both gluon polarisation sums and no ghosts (oracle/naive.py).
UNPHYSICAL = {"msq_1": 0.549471684930, "msq_2": 0.714620204016, "msq_3": 0.522248226767}


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_three_numbers():
    data = result()
    for key in TRUE:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


@pytest.mark.parametrize("key", sorted(TRUE))
def test_squared_matrix_element(key):
    # Exact arithmetic on given numbers, asked for to six digits: 1e-4 passes a value rounded
    # to five digits or six decimals and nothing else. The unphysical sum is 15 to 23% out.
    assert abs(result()[key] / TRUE[key] - 1) < 1e-4


def test_only_physical_gluon_polarisations_are_summed():
    data = result()
    for key in TRUE:
        assert abs(data[key] / UNPHYSICAL[key] - 1) > 0.01, "%s is the -g_mu_nu sum without ghosts" % key


def test_average_is_over_colours_and_polarisations_of_both_gluons():
    # Left-out averages are whole factors: 4 (polarisations), 64 (colours), 256 (both).
    data = result()
    for key in TRUE:
        assert 0.5 < data[key] / TRUE[key] < 2.0, key
