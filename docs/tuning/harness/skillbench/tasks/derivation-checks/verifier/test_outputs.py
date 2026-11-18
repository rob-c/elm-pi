"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The fraction of photons leaving a uniformly emitting sphere unattenuated,
towards a distant detector, is f = 3/(8 tau^3) [2 tau^2 - 1 + (1 + 2 tau) exp(-2 tau)]
with tau = mu R. derivation.md ends with (1 - 2 tau) in the bracket: the
boundary term of the integration by parts in its step 5 has the wrong sign
(oracle/make_environment.py). mu = 0.0726 cm2/g x 8.96 g/cm3 = 0.6505 /cm.

    sphere A, 36 mm diameter: tau = 1.1709, f = 0.48200    as written 0.37679 (22% low)
    sphere B, 60 mm diameter: tau = 1.9515, f = 0.33886    as written 0.33091 (2.3% low)

Nothing statistical: the corrected formula and a numerical integration of the
derivation's step 2 agree to 1e-9. Half a per cent is allowed, eight standard
errors of a Monte Carlo with a million emission points.
"""
import json
import math
from pathlib import Path

RIGHT = {"escape_fraction_a": 0.481997, "escape_fraction_b": 0.338857}
AS_WRITTEN = {"escape_fraction_a": 0.376793, "escape_fraction_b": 0.330907}


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_two_fractions():
    data = result()
    for key in RIGHT:
        assert isinstance(data[key], (int, float)) and not isinstance(data[key], bool) and math.isfinite(data[key]), key
        assert 0 < data[key] < 1, key


def test_sphere_a():
    assert abs(result()["escape_fraction_a"] / RIGHT["escape_fraction_a"] - 1) < 0.005


def test_sphere_b():
    # The formula as written is only 2.3% out here: this sphere is where an error would go unnoticed.
    assert abs(result()["escape_fraction_b"] / RIGHT["escape_fraction_b"] - 1) < 0.005


def test_not_the_formula_as_written():
    data = result()
    for key, wrong in AS_WRITTEN.items():
        assert abs(data[key] / wrong - 1) > 0.01, key
