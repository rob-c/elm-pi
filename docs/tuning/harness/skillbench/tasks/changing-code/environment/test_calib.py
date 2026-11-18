"""Run with: python3 -m unittest"""
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
