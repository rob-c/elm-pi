"""Hidden check, run in the project folder after the session. All must pass for reward 1.

calib.py is imported afresh for every test and given overrides written here
(other runs than the project's own file, so nothing depends on what the
session did to it). As shipped, calibration() merges each run's overrides into
DEFAULTS itself (oracle/make_environment.py). Each test below is something
the function's docstring promises; none is a matter of tolerance.

    the report                      a top-level number leaks to the next run
    the neighbours                  a nested gain or pedestal, or the masked list, leaks to the next run
    twice and in another order      every run gives the same constants whenever it is asked for
    what is inside                  a caller editing its result (as mask_channel does) changes
                                    neither the defaults, nor the stored overrides, nor a later result

A one-level copy of DEFAULTS passes the first and the last of the tests
only; a deep copy of DEFAULTS alone still hands out the stored
override's own `masked` list.
"""
import copy
import importlib
import json
import sys
from pathlib import Path

import pytest

DEFAULTS = {
    "threshold_mv": 30.0,
    "gain": {"A": 1.00, "B": 1.00, "C": 1.00, "D": 1.00},
    "pedestal": {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0},
    "masked": [],
}
OVERRIDES = {
    "2101": {"threshold_mv": 45.0},
    "2103": {"gain": {"B": 1.07, "D": 0.91}},
    "2104": {"pedestal": {"C": 12.5}, "masked": ["D"]},
    "2107": {"threshold_mv": 38.0, "gain": {"A": 0.96}, "masked": ["B", "C"]},
}
PLAIN = 2102          # a run with no override


def expected(run):
    constants = copy.deepcopy(DEFAULTS)
    for key, value in OVERRIDES.get(str(run), {}).items():
        if isinstance(value, dict):
            constants[key].update(value)
        else:
            constants[key] = copy.deepcopy(value)
    return constants


@pytest.fixture()
def calib(tmp_path):
    sys.modules.pop("calib", None)
    sys.path.insert(0, str(Path.cwd()))
    try:
        module = importlib.import_module("calib")
    finally:
        sys.path.remove(str(Path.cwd()))
    path = tmp_path / "overrides.json"
    path.write_text(json.dumps(OVERRIDES))
    module.load_overrides(path)
    return module


def test_the_reported_example(calib):
    calib.calibration(2101)
    assert calib.calibration(PLAIN)["threshold_mv"] == 30.0


def test_a_nested_override_does_not_reach_the_next_run(calib):
    calib.calibration(2103)
    calib.calibration(2104)
    after = calib.calibration(PLAIN)
    assert after["gain"] == DEFAULTS["gain"]
    assert after["pedestal"] == DEFAULTS["pedestal"]
    assert after["masked"] == []


def test_every_run_gives_the_same_constants_in_any_order_and_twice(calib):
    runs = [2101, PLAIN, 2103, 2104, 2107]
    for order in (runs, runs[::-1], runs, [2107, 2107, 2103, PLAIN, 2104, 2101, PLAIN]):
        for run in order:
            assert calib.calibration(run) == expected(run), run


def test_the_defaults_are_left_as_they_were(calib):
    for run in (2101, 2103, 2104, 2107, PLAIN):
        calib.calibration(run)
    assert calib.DEFAULTS == DEFAULTS


def test_a_caller_changing_its_result_changes_nothing_else(calib):
    mine = calib.calibration(PLAIN)
    mine["gain"]["A"] = 9.0
    mine["pedestal"]["B"] = -3.0
    calib.mask_channel(mine, "C")
    assert calib.DEFAULTS == DEFAULTS
    assert calib.calibration(PLAIN) == expected(PLAIN)
    assert calib.calibration(2103) == expected(2103)


def test_masking_a_channel_does_not_change_the_stored_override(calib):
    mine = calib.calibration(2104)
    calib.mask_channel(mine, "A")
    assert mine["masked"] == ["D", "A"]
    assert calib.RUN_OVERRIDES[2104]["masked"] == ["D"]
    assert calib.calibration(2104) == expected(2104)


def test_what_was_not_broken_still_works(calib):
    # The merge is key by key inside gain and pedestal, a list replaces, corrected() uses both.
    assert calib.calibration(2107) == expected(2107)
    assert isinstance(calib.calibration(2107), dict)
    assert calib.corrected(2104, "C", 100.0) == pytest.approx(87.5)
    assert calib.corrected(2103, "D", 100.0) == pytest.approx(91.0)
    with pytest.raises(KeyError):
        calib.corrected(2101, "Z", 1.0)
