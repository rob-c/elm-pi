"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The counts are exact (oracle/make_environment.py), so the efficiencies are checked to rounding.
The request names no interval, so each end is accepted anywhere between the most and the least
conservative of the standard 68.3% binomial intervals - Clopper-Pearson (the widest), Wilson,
and the Bayesian ones with a uniform or a Jeffreys prior, central or one-sided at the edge -
with a margin of 0.002 plus a quarter of the Clopper-Pearson half-width. That margin lets the
normal approximation through wherever it is merely a little narrow; what is refused is an
interval of no width where no probe or every probe passes. There the bound must be at least a
fifth of the Clopper-Pearson distance away from the estimate: the narrowest standard interval
(Jeffreys, one-sided) is at 0.27 of it or more in these bins, the normal approximation at 0.
"""
import json
import math
from pathlib import Path

from scipy.stats import beta

PASSED = [0, 2, 11, 29, 47, 76, 99, 124, 86, 41, 17, 5]
PROBES = [180, 150, 96, 71, 64, 83, 102, 127, 88, 41, 17, 5]
LEVEL = 0.683


def result():
    return json.loads(Path("result.json").read_text())


def clopper_pearson(k, n):
    tail = (1 - LEVEL) / 2
    return (0.0 if k == 0 else float(beta.ppf(tail, k, n - k + 1)), 1.0 if k == n else float(beta.ppf(1 - tail, k + 1, n - k)))


def references(k, n):
    """(lower, upper) of each standard interval for k of n at 68.3%."""
    tail = (1 - LEVEL) / 2
    estimate = k / n
    found = [clopper_pearson(k, n)]
    # Wilson score, z = 1.
    centre, half = (k + 0.5) / (n + 1), math.sqrt(estimate * (1 - estimate) * n + 0.25) / (n + 1)
    found.append((max(centre - half, 0.0), min(centre + half, 1.0)))
    # Bayesian: uniform and Jeffreys priors; central, and one-sided where the posterior peaks at 0 or 1.
    for prior in (1.0, 0.5):
        a, b = k + prior, n - k + prior
        found.append((float(beta.ppf(tail, a, b)), float(beta.ppf(1 - tail, a, b))))
        if k == 0:
            found.append((0.0, float(beta.ppf(LEVEL, a, b))))
        if k == n:
            found.append((float(beta.ppf(1 - LEVEL, a, b)), 1.0))
    return found


def window(k, n, end):
    values = [pair[end] for pair in references(k, n)]
    exact = clopper_pearson(k, n)
    margin = 0.002 + 0.25 * (exact[1] - exact[0]) / 2
    return min(values) - margin, max(values) + margin


def test_three_lists_of_twelve_numbers():
    data = result()
    for key in ("efficiency", "lower", "upper"):
        assert isinstance(data[key], list) and len(data[key]) == 12, key
        for value in data[key]:
            assert isinstance(value, (int, float)) and math.isfinite(value), key


def test_efficiency_is_passing_over_all_probes_in_each_bin():
    for got, k, n in zip(result()["efficiency"], PASSED, PROBES):
        assert abs(got - k / n) < 0.002, (got, k, n)


def test_bounds_are_efficiencies_and_ordered():
    data = result()
    for low, high in zip(data["lower"], data["upper"]):
        assert -1e-9 <= low < high <= 1 + 1e-9, (low, high)


def test_lower_bounds_are_those_of_a_binomial_interval():
    for got, k, n in zip(result()["lower"], PASSED, PROBES):
        low, high = window(k, n, 0)
        assert low <= got <= high, "%d of %d: lower %.4f, accepted %.4f to %.4f" % (k, n, got, low, high)


def test_upper_bounds_are_those_of_a_binomial_interval():
    for got, k, n in zip(result()["upper"], PASSED, PROBES):
        low, high = window(k, n, 1)
        assert low <= got <= high, "%d of %d: upper %.4f, accepted %.4f to %.4f" % (k, n, got, low, high)


def test_every_probe_passing_still_has_a_lower_bound_below_one():
    lower = result()["lower"]
    for i in (9, 10, 11):          # 41 of 41, 17 of 17, 5 of 5
        exact = clopper_pearson(PASSED[i], PROBES[i])[0]
        assert lower[i] < 1 - 0.2 * (1 - exact), "%d of %d: lower bound %.4f" % (PASSED[i], PROBES[i], lower[i])


def test_no_probe_passing_still_has_an_upper_bound_above_zero():
    upper = result()["upper"]
    exact = clopper_pearson(PASSED[0], PROBES[0])[1]
    assert upper[0] > 0.2 * exact, "0 of %d: upper bound %.5f" % (PROBES[0], upper[0])
