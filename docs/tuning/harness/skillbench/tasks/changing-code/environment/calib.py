"""Calibration constants for the hodoscope, run by run.

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
