"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A small calibration module. calibration(run) merges the run's overrides into
DEFAULTS itself, so every run looked up leaves its overrides behind for the
next. The report is about a top-level number (threshold_mv), which a shallow
copy of DEFAULTS puts right. The same cause reaches further than the report:

- the gains and pedestals are dicts inside DEFAULTS, shared by a shallow copy,
  so a run's gain override still leaks into every later run;
- the caller is allowed to change what it gets (the docstring says so, and
  mask_channel does): with the defaults' inner dicts and list shared, that
  changes the defaults;
- an override that is a list (masked) is put into the result as the stored
  object itself, so masking a channel in one result changes the stored
  override and every later lookup of that run.

The saved tests pass before and after: none looks up two runs and compares.
"""
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])

(out / "calib.py").write_text('''"""Calibration constants for the hodoscope, run by run.

DEFAULTS are the constants of a run nobody has had to correct. overrides.json
has, for the runs that needed it, the constants that differ: a PMT swapped, a
threshold raised, a dead channel. calibration(run) puts the two together.
"""
import json
from pathlib import Path

DEFAULTS = {
    "threshold_mv": 30.0,
    "gain": {"A": 1.00, "B": 1.00, "C": 1.00, "D": 1.00},
    "pedestal": {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0},
    "masked": [],
}

RUN_OVERRIDES = {}


def load_overrides(path=None):
    """Read the per-run overrides (run number -> the constants that differ) and return them."""
    path = Path(path) if path else Path(__file__).with_name("overrides.json")
    RUN_OVERRIDES.clear()
    for run, changes in json.loads(path.read_text()).items():
        RUN_OVERRIDES[int(run)] = changes
    return RUN_OVERRIDES


def _merge(base, changes):
    """Put `changes` into `base`: a dict inside a dict is merged key by key, anything else replaces."""
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def calibration(run):
    """The constants for one run: the defaults with that run's overrides merged in.

    The result is the caller's to change (mask_channel does): changing it
    changes neither the defaults, nor the stored overrides, nor what a later
    call returns.
    """
    return _merge(DEFAULTS, RUN_OVERRIDES.get(run, {}))


def mask_channel(constants, channel):
    """Mark a channel dead in one run's constants, as calibration() returned them."""
    if channel not in constants["masked"]:
        constants["masked"].append(channel)
    return constants


def corrected(run, channel, adc):
    """The pedestal-subtracted, gain-corrected amplitude of one channel in one run."""
    constants = calibration(run)
    return (adc - constants["pedestal"][channel]) * constants["gain"][channel]
''')

(out / "overrides.json").write_text(json.dumps({
    "1041": {"threshold_mv": 45.0, "gain": {"B": 1.07}},
    "1043": {"masked": ["D"], "pedestal": {"C": 12.5}},
    "1047": {"gain": {"A": 0.96, "C": 1.02}},
}, indent=1) + "\n")

(out / "test_calib.py").write_text('''"""Run with: python3 -m unittest"""
import unittest

import calib


class CalibrationTest(unittest.TestCase):
    def setUp(self):
        calib.load_overrides()

    def test_a_run_without_overrides_has_the_defaults(self):
        constants = calib.calibration(1040)
        self.assertEqual(constants["threshold_mv"], 30.0)
        self.assertEqual(constants["gain"], {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0})
        self.assertEqual(constants["masked"], [])

    def test_corrected_amplitude(self):
        self.assertAlmostEqual(calib.corrected(1043, "C", 100.0), 87.5)
        self.assertAlmostEqual(calib.corrected(1043, "A", 100.0), 100.0)

    def test_overrides_are_merged_into_the_defaults(self):
        constants = calib.calibration(1041)
        self.assertEqual(constants["threshold_mv"], 45.0)
        self.assertEqual(constants["gain"]["B"], 1.07)
        self.assertEqual(constants["gain"]["D"], 1.0)

    def test_unknown_channel(self):
        with self.assertRaises(KeyError):
            calib.corrected(1041, "Z", 1.0)


if __name__ == "__main__":
    unittest.main()
''')

(out / "README.md").write_text("""# hodoscope calibration

`calib.py` gives the calibration constants of a run: `calib.load_overrides()`
once, then `calib.calibration(run)`. The defaults are in `calib.py`, the runs
that differ from them in `overrides.json`.

Tests: `python3 -m unittest`
""")
print("wrote calib.py, overrides.json, test_calib.py, README.md")
