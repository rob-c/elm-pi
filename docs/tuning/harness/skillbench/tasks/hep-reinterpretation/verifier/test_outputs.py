"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# From oracle/make_environment.py. Yield = sigma [pb] x 1000 x 139 fb^-1 x 0.70^2 x map; the
# region is the one with the larger yield / s95_expected, and r is yield / s95_observed there.
# p2 and p3 sit on nodes of the map, so they are arithmetic (3% is room for rounding); p1 is
# halfway between two nodes, where a linear and a smooth interpolation differ by 2.5% in
# SR-2j and 1.1% in SR-4j, hence 6%.
YIELDS = {"p1": (3.72, 38.66), "p2": (44.10, 10.42), "p3": (47.97, 1.03)}       # SR-2j, SR-4j
R = {"p1": 2.842, "p2": 0.766, "p3": 1.411}
EXCLUDED = {"p1": True, "p2": False, "p3": True}
TOLERANCE = {"p1": 0.06, "p2": 0.03, "p3": 0.03}


def result():
    return json.loads(Path("result.json").read_text())


def flag(value):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "excluded")
    return bool(value)


def test_result_file_has_four_entries_a_point():
    data = result()
    for point in YIELDS:
        for key in ("_n_sr2j", "_n_sr4j", "_r"):
            assert isinstance(data[point + key], (int, float)) and math.isfinite(data[point + key]), point + key
        assert point + "_excluded" in data


def test_yields_on_the_map_nodes():
    # Without the branching fraction they are 2.04 times larger, with it applied once 1.43 times;
    # with pb x fb^-1 taken as events, 1000 times smaller.
    data = result()
    for point in ("p2", "p3"):
        assert abs(data[point + "_n_sr2j"] / YIELDS[point][0] - 1) < 0.03, point
        assert abs(data[point + "_n_sr4j"] / YIELDS[point][1] - 1) < 0.03, point


def test_yields_between_the_map_nodes():
    data = result()
    assert abs(data["p1_n_sr2j"] / YIELDS["p1"][0] - 1) < 0.06
    assert abs(data["p1_n_sr4j"] / YIELDS["p1"][1] - 1) < 0.06


def test_r_is_from_the_region_with_the_best_expected_limit():
    # p2: SR-4j is the more sensitive (expected r 1.27 against 0.79) and gives r = 0.77.
    # The largest observed r is SR-2j's 1.30, from a region that saw 262 events on 301 expected.
    assert abs(result()["p2_r"] / R["p2"] - 1) < TOLERANCE["p2"]


def test_r_of_the_other_points():
    data = result()
    for point in ("p1", "p3"):
        assert abs(data[point + "_r"] / R[point] - 1) < TOLERANCE[point], point


def test_exclusion_verdicts():
    data = result()
    for point, expected in EXCLUDED.items():
        assert flag(data[point + "_excluded"]) is expected, point
