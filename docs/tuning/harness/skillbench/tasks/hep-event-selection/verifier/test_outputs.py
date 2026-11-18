"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Nothing is statistical: the yields are sums over the rows of the two files, and the numbers below
are from oracle/make_environment.py, which counts each generated event once. Data counts are
compared exactly; the simulated yields to 0.5%, which only allows for rounding in what was written
out. Of the 1900 data events 166 fired both triggers and are in the file twice: counted as they
come, the flow is 1726, 1698, 1419, 491, 264, 148. Removing rows by event number alone takes out
22 distinct events that share a number across runs: 1569, 1541, 1286, 448, 243, 138.

The first data row is accepted from 1560 to 1588: 1588 unique events are in good blocks, and
someone who takes muon events from SingleMuon and electron events from EGamma has already applied
the trigger there and has 1560.

sqrt(sum of squared weights) of the final tt-bar yield is 8.91; sqrt(yield) is 10.89 and
yield / sqrt(raw events) is 4.93, against a 3% tolerance. Normalising to the 6400 processed events
instead of their sum of generator weights gives 60% of every simulated yield.
"""
import json
import math
from pathlib import Path

DATA_FLOW = [1588, 1560, 1301, 455, 247, 142]
MC_FLOW = [520.059, 444.935, 385.164, 235.672, 200.236, 118.503]
MC_FINAL_UNC = 8.913


def result():
    return json.loads(Path("result.json").read_text())


def test_two_lists_of_six_and_an_uncertainty():
    data = result()
    for key in ("data", "ttbar"):
        assert isinstance(data[key], list) and len(data[key]) == 6, key
        for value in data[key]:
            assert isinstance(value, (int, float)) and math.isfinite(value), key
    assert isinstance(data["ttbar_final_unc"], (int, float)) and math.isfinite(data["ttbar_final_unc"])


def test_data_counts_each_event_once_from_the_trigger_cut_on():
    got = result()["data"][1:]
    assert all(abs(a - b) < 0.5 for a, b in zip(got, DATA_FLOW[1:])), got


def test_data_after_the_good_run_list():
    assert DATA_FLOW[1] - 0.5 < result()["data"][0] < DATA_FLOW[0] + 0.5


def test_simulated_yields_are_weighted_and_normalised():
    got = result()["ttbar"]
    assert all(abs(a / b - 1) < 0.005 for a, b in zip(got, MC_FLOW)), got


def test_simulated_yield_error_is_from_the_squared_weights():
    assert abs(result()["ttbar_final_unc"] / MC_FINAL_UNC - 1) < 0.03
