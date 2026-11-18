"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Expected values: the CSDA integral of stopping_power.csv. The oracle (cubic in log-log)
and the smooth function the table was written from agree to 0.01%; linear interpolation
of the table, by quadrature or as an ODE, gives 1.569 mm, 9.545 MeV and 1.383 mm, 0.4%
away at most. The tolerance is 1.5%. The plate taken as thin (loss = S(17 MeV) x
270 mg/cm2) leaves 10.89 MeV, 14% out, and asks for 1.96 mm, 42% out.
"""
import json
import math
from pathlib import Path

RANGE_MM = 1.574            # 0.4249 g/cm2 at 17.0 MeV, density 2.699 g/cm3
ENERGY_AFTER_MEV = 9.584    # behind 270.0 mg/cm2
THICKNESS_MM = 1.387        # 0.3744 g/cm2 takes 17.0 MeV to 5.0 MeV
THIN_PLATE_MEV = 10.89      # 17.0 - S(17.0) x 0.2700 g/cm2, S = 22.6 MeV cm2/g
TOLERANCE = 0.015


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_three_numbers():
    data = result()
    for key in ("range_mm", "energy_after_degrader_mev", "thickness_for_5mev_mm"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_range_of_the_beam_in_mm():
    assert abs(result()["range_mm"] / RANGE_MM - 1) < TOLERANCE


def test_plate_is_not_treated_as_thin():
    # The stopping power rises from 22.6 to 35 MeV cm2/g across the plate: the loss is 7.4 MeV, not 6.1.
    assert result()["energy_after_degrader_mev"] < THIN_PLATE_MEV - 0.6


def test_energy_behind_the_plate():
    assert abs(result()["energy_after_degrader_mev"] / ENERGY_AFTER_MEV - 1) < TOLERANCE


def test_thickness_that_leaves_5_mev():
    assert abs(result()["thickness_for_5mev_mm"] / THICKNESS_MM - 1) < TOLERANCE


def test_new_plate_is_thicker_than_the_old_and_thinner_than_the_range():
    data = result()
    assert 1.0004 < data["thickness_for_5mev_mm"] < data["range_mm"]
