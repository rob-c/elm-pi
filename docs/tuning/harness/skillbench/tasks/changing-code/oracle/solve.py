"""The reference solution: run in the project folder, changes calib.py and adds to its saved tests.

The cause, in one sentence: calibration() merges the run's overrides into
DEFAULTS itself, so each lookup rewrites the defaults for every later one.
The fix is in calibration(): merge into a deep copy of the defaults, and merge
a deep copy of the overrides, so that nothing in the result - not the inner
gain and pedestal dicts, not a `masked` list taken from an override - is the
same object as anything stored. Then the cases the report did not give are
added to the saved tests and run.
"""
import subprocess
import sys
from pathlib import Path

source = Path("calib.py").read_text()
old = "    return _merge(DEFAULTS, RUN_OVERRIDES.get(run, {}))\n"
new = "    return _merge(copy.deepcopy(DEFAULTS), copy.deepcopy(RUN_OVERRIDES.get(run, {})))\n"
assert source.count(old) == 1 and source.count("import json\n") == 1
Path("calib.py").write_text(source.replace(old, new).replace("import json\n", "import copy\nimport json\n"))

tests = Path("test_calib.py").read_text()
marker = '\n\nif __name__ == "__main__":'
assert tests.count(marker) == 1
added = '''
    def test_a_run_does_not_inherit_the_run_looked_up_before_it(self):
        calib.calibration(1041)                      # threshold 45.0, gain B 1.07
        calib.calibration(1043)                      # pedestal C 12.5, channel D masked
        after = calib.calibration(1042)
        self.assertEqual(after["threshold_mv"], 30.0)
        self.assertEqual(after["gain"]["B"], 1.0)
        self.assertEqual(after["pedestal"]["C"], 0.0)
        self.assertEqual(after["masked"], [])

    def test_the_order_of_lookups_does_not_matter(self):
        runs = [1040, 1041, 1043, 1047]
        forward = {run: calib.calibration(run) for run in runs}
        backward = {run: calib.calibration(run) for run in reversed(runs)}
        again = {run: calib.calibration(run) for run in runs}
        self.assertEqual(forward, backward)
        self.assertEqual(forward, again)

    def test_changing_a_result_changes_nothing_else(self):
        constants = calib.calibration(1043)
        calib.mask_channel(constants, "A")
        constants["gain"]["B"] = 2.0
        self.assertEqual(calib.calibration(1043)["masked"], ["D"])
        self.assertEqual(calib.calibration(1043)["gain"]["B"], 1.0)
        self.assertEqual(calib.RUN_OVERRIDES[1043]["masked"], ["D"])
        self.assertEqual(calib.DEFAULTS["masked"], [])
        self.assertEqual(calib.DEFAULTS["gain"]["B"], 1.0)
'''
Path("test_calib.py").write_text(tests.replace(marker, added + marker))
ran = subprocess.run([sys.executable, "-m", "unittest", "-v"], capture_output=True, text=True)
print(ran.stderr.strip().splitlines()[-1])
assert ran.returncode == 0, ran.stderr
