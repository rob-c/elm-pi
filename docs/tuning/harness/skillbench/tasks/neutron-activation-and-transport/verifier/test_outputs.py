"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Expected values are arithmetic on notes.md (oracle/solve.py), confirmed by integrating
sigma(v) n(v) v over the Maxwellian and the activity over the count numerically:

  atoms 3.704e20; rate per atom (sqrt(pi)/2) x 13.36 b x 6.0e7 = 7.10e-16 /s
  saturation 2.631e5 Bq; x (1 - exp(-lambda 200 min)) = 0.5918 -> 1.557e5 Bq
  x exp(-lambda 47 min) = 0.8101, x (1 - exp(-lambda 5400 s))/lambda = 4444 s,
  x 0.9885 x 8.62e-4 -> 4.777e5 counts
  flight time 437.1 - 118.4 + 20.00/c = 385.41 ns, beta 0.17309 -> 14.40 MeV

Nothing here is statistical; the tolerances leave room for rounding and for the activity
at mid-count in place of the integral (0.8% low). The 2200 m/s cross section with this
flux is 12.8% high; no decay during the count another 21%; the classical energy is 2.2%
low, and the flight time without the gamma flash's own L/c gives 21 MeV.
"""
import json
import math
from pathlib import Path

ACTIVITY_EOI_BQ = 1.5572e5
PEAK_COUNTS = 4.777e5
COUNTS_PER_BQ = 3.068        # counts per Bq at the end of irradiation: the wait, the count, emission, efficiency
TOF_ENERGY_MEV = 14.400


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_three_numbers():
    data = result()
    for key in ("activity_eoi_bq", "expected_peak_counts", "tof_energy_mev"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_activity_is_not_the_saturation_activity():
    assert result()["activity_eoi_bq"] < 0.8 * 2.631e5, "3 h 20 min is 1.3 half-lives: 59% of saturation"


def test_activity_at_end_of_irradiation():
    assert abs(result()["activity_eoi_bq"] / ACTIVITY_EOI_BQ - 1) < 0.03


def test_counts_follow_from_the_activity_with_decay_in_the_wait_and_the_count():
    data = result()
    assert abs(data["expected_peak_counts"] / data["activity_eoi_bq"] / COUNTS_PER_BQ - 1) < 0.02


def test_expected_counts():
    assert abs(result()["expected_peak_counts"] / PEAK_COUNTS - 1) < 0.03


def test_flight_time_starts_when_the_neutrons_left_the_target():
    assert result()["tof_energy_mev"] < 16.0, "peak minus gamma flash is 66.7 ns short of the flight time"


def test_neutron_energy_from_time_of_flight():
    assert abs(result()["tof_energy_mev"] / TOF_ENERGY_MEV - 1) < 0.005
