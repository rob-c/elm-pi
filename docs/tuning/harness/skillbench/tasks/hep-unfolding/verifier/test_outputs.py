"""Hidden check, run in the project folder after the session. All must pass for reward 1.

TRUTH is the particle-level spectrum of the very events the "data" were made from
(oracle/make_environment.py). The Poisson error of a bin is 0.2% to 0.8%, but no binned unfolding
gets that close: the data's shape inside a bin is not the simulation's, which leaves about 1.3% rms
whatever the method. Relative deviation from TRUTH over the 15 bins, rms and largest:

  iterative Bayesian, 4 to 200 iterations (simulated or flat prior)   1.3% to 2.7%    2.4% to 6.4%
  iterative Bayesian, 3 iterations                                    3.5%            6.0%
  Tikhonov (curvature), strength over three decades                   1.3% to 3.0%    2.2% to 8.0%
  the reference solution (10 iterations, from its stress test)        1.4%            2.7%
  bin-by-bin factors                                                  7.4%            15.1%
  iterative Bayesian, 1 or 2 iterations                               13.7%, 5.9%     26.8%, 11.3%
  plain inversion of the response matrix                              15.5%           24.2%

The limits are 4.5% rms and 9% for any bin: above every regularised answer of sensible strength,
below bin-by-bin factors and far below inversion. The total is within 0.2% for all of these; it is
23% low without the efficiency and 7% high with the fakes left in (1.5% allowed).

The uncertainties are only held to those of a stable answer: the median relative uncertainty is
0.2% to 2.3% for the regularised methods (more if a bias is added), and 10% for the inversion with
its errors propagated (6% allowed).
"""
import json
import math
import statistics
from pathlib import Path

TRUTH = [280957, 239837, 215162, 214544, 252882, 316507, 365137, 344993, 262951, 164732, 93955, 57264, 40847, 32838, 27381]


def result():
    data = json.loads(Path("result.json").read_text())
    return data["unfolded"], data["uncertainty"]


def deviations():
    return [got / true - 1 for got, true in zip(result()[0], TRUTH)]


def test_two_lists_of_fifteen_numbers():
    for values in result():
        assert isinstance(values, list) and len(values) == 15
        for value in values:
            assert isinstance(value, (int, float)) and math.isfinite(value)
    assert all(value > 0 for value in result()[1])


def test_spectrum_follows_the_truth():
    rms = math.sqrt(sum(d * d for d in deviations()) / 15)
    assert rms < 0.045, "rms relative deviation %.1f%%" % (100 * rms)


def test_no_bin_is_far_off():
    worst = max(abs(d) for d in deviations())
    assert worst < 0.09, "largest relative deviation %.1f%%" % (100 * worst)


def test_total_has_the_efficiency_in_and_the_fakes_out():
    assert abs(sum(result()[0]) / sum(TRUTH) - 1) < 0.015


def test_uncertainties_are_those_of_a_stable_answer():
    unfolded, uncertainty = result()
    median = statistics.median(u / abs(v) for u, v in zip(uncertainty, unfolded))
    assert 0.0008 < median < 0.06, "median relative uncertainty %.2f%%" % (100 * median)
