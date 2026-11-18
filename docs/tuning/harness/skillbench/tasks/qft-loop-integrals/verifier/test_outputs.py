"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

import pytest

# MS-bar B0 at the four points of points.csv: -Int_0^1 dx ln[(x m1^2 + (1-x) m2^2 - x(1-x) p^2 - i0)/mu^2].
# From oracle/solve.py: the Feynman-parameter integral done numerically, equal to 1e-9 to
# the closed form; the imaginary parts are pi sqrt(lambda(p^2, m1^2, m2^2))/p^2, the
# optical theorem's sign. Points 1 (spacelike) and 3 (below threshold) are real.
TRUE = {
    "re_1": -0.497496629, "im_1": 0.0,
    "re_2": 2.017451289, "im_2": 3.134558710,
    "re_3": 0.844730372, "im_3": 0.0,
    "re_4": -0.896568753, "im_4": 2.661402399,
}
# Any sound evaluation, closed form or quadrature across the logarithmic end points, is far
# inside this; a wrong sign of the imaginary part is 5 to 6 out, MS for MS-bar 1.95.
TOLERANCE = 2e-4
MS_MINUS_MSBAR = math.log(4 * math.pi) - 0.5772156649015329


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_eight_numbers():
    data = result()
    for key in TRUE:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


@pytest.mark.parametrize("key", ["re_1", "re_2", "re_3", "re_4"])
def test_real_part(key):
    assert abs(result()[key] - TRUE[key]) < TOLERANCE


@pytest.mark.parametrize("key", ["im_2", "im_4"])
def test_imaginary_part_above_threshold(key):
    assert abs(result()[key] - TRUE[key]) < TOLERANCE


@pytest.mark.parametrize("key", ["im_1", "im_3"])
def test_no_imaginary_part_below_threshold(key):
    assert abs(result()[key]) < TOLERANCE


def test_imaginary_part_has_the_sign_the_i0_gives():
    data = result()
    assert data["im_2"] > 0 and data["im_4"] > 0, "ln(D - i0) = ln|D| - i pi for D < 0, so Im B0 > 0"


def test_the_subtraction_is_msbar_not_ms():
    data = result()
    for key in ("re_1", "re_2", "re_3", "re_4"):
        assert abs(abs(data[key] - TRUE[key]) - MS_MINUS_MSBAR) > 0.1, "%s still has ln 4 pi - gamma_E in it" % key
