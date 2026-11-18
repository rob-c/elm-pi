"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The answer is the solution of the eight equations in model.md. Radau, BDF,
LSODA and DOP853 at rtol 1e-12, with the peak found as the root of dP/dt on the
dense output, agree to ten figures (2026-11-17):

    peak power 362.6496734 MW at 104.8193726 ms; 16.69159858 MJ by 10 s

Five significant figures were asked for. Rounded to five these are 362.65,
104.82 and 16.692, which are 8e-7, 6e-6 and 2.4e-5 from the exact values. Each
tolerance below is about one unit in the fifth figure, so a correctly rounded
answer passes with room to spare, and so does a peak time from an optimiser
stopped at 0.01 ms.

Relative errors of what less care gives:

                                              peak     time     energy
    RK45, defaults, max over its own steps    8e-3     1e-2     4e-4
    LSODA, defaults, max over its own steps   5e-3     1e-2     4e-5
    Radau, defaults, 100 001 output points    1.5e-4   1.9e-4   8e-7
    any method, rtol 1e-8, 10 001 points      1.8e-4   1.7e-3   <1e-8
    any method, rtol 1e-8, 100 001 points     2e-6     1.9e-4   <1e-8
    any method, rtol 1e-8, 1 000 001 points   <1e-8    6e-6     <1e-8
    any method, rtol 1e-8, root of dP/dt      <1e-8    <1e-8    <1e-8
"""
import json
import math
from pathlib import Path

PEAK_MW, PEAK_MS, ENERGY_MJ = 362.6496734, 104.8193726, 16.69159858


def result():
    return json.loads(Path("result.json").read_text())


def off(key, exact):
    return abs(result()[key] / exact - 1)


def test_result_file_has_the_three_numbers():
    data = result()
    for key in ("peak_power_mw", "peak_time_ms", "energy_10s_mj"):
        assert isinstance(data[key], (int, float)) and not isinstance(data[key], bool) and math.isfinite(data[key]), key


def test_the_model_is_the_one_in_the_file():
    # Units and equations before precision: within 2%, which every integration above is.
    assert off("peak_power_mw", PEAK_MW) < 0.02 and off("peak_time_ms", PEAK_MS) < 0.02 and off("energy_10s_mj", ENERGY_MJ) < 0.02


def test_peak_power_to_five_figures():
    assert off("peak_power_mw", PEAK_MW) < 5e-5


def test_peak_time_to_five_figures():
    # 104.82 ms within 0.01 ms. An output grid of 0.1 ms, or of 0.05 ms, gives 104.80.
    assert off("peak_time_ms", PEAK_MS) < 1e-4


def test_energy_to_five_figures():
    assert off("energy_10s_mj", ENERGY_MJ) < 5e-5
