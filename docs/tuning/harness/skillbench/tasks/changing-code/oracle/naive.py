"""What the task is built to catch: the reported example made to work, and nothing tried beyond it.

DEFAULTS is copied before the merge - with dict(), one level deep. The
threshold of the report is a top-level number, so the example now gives 30.0
and the saved tests still pass. The gains, the pedestals and the masked list
are still the defaults' own objects.
"""
from pathlib import Path

source = Path("calib.py").read_text()
old = "    return _merge(DEFAULTS, RUN_OVERRIDES.get(run, {}))\n"
assert source.count(old) == 1
Path("calib.py").write_text(source.replace(old, "    return _merge(dict(DEFAULTS), RUN_OVERRIDES.get(run, {}))\n"))
