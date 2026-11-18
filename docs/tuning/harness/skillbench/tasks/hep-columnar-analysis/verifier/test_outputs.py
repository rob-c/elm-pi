"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Nothing is statistical: the three numbers are sums over the events in the file, counted with plain
loops in oracle/make_environment.py when it wrote them. No muon is within 0.02 GeV of the pT cut or
0.002 of the eta cut, and no pair within 0.05 GeV of a mass cut, so float32 or float64 and massless
or massive muons give the same events; the 0.5% tolerance on the yields is for nothing but rounding.

2640 pairs in 2463 events, 147 of which have more than one. What the wrong routes give:
- the first two muons of each event as the pair: 640.5 for both yields;
- the two leading selected muons: 818.2 for both;
- the muon cuts applied as event cuts (all muons must pass): 700.8 pairs, 648.1 events;
- no charge requirement: 979.2 pairs; unweighted: 2640 and 2463.
The error of the event yield is sqrt(sum of squared weights) = 22.58; sqrt(yield) is 29.69,
mean weight times sqrt(N) 17.76, and the pairs' squared weights give 23.34 (2% allowed).
"""
import json
import math
from pathlib import Path

PAIR_YIELD = 943.2242
EVENT_YIELD = 881.3888
EVENT_YIELD_UNC = 22.5849


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_three_numbers():
    data = result()
    for key in ("pair_yield", "event_yield", "event_yield_unc"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_every_pair_in_every_event_is_counted_with_its_weight():
    assert abs(result()["pair_yield"] / PAIR_YIELD - 1) < 0.005


def test_events_with_a_candidate_are_counted_once_each():
    assert abs(result()["event_yield"] / EVENT_YIELD - 1) < 0.005


def test_events_with_two_candidates_make_the_difference():
    data = result()
    assert abs((data["pair_yield"] - data["event_yield"]) - (PAIR_YIELD - EVENT_YIELD)) < 3.0


def test_error_of_the_weighted_event_yield():
    assert abs(result()["event_yield_unc"] / EVENT_YIELD_UNC - 1) < 0.02
