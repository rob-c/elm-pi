# hodoscope calibration

`calib.py` gives the calibration constants of a run: `calib.load_overrides()`
once, then `calib.calibration(run)`. The defaults are in `calib.py`, the runs
that differ from them in `overrides.json`.

Tests: `python3 -m unittest`
