"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The files were drawn (oracle/make_environment.py) from a signal of
40, 620, 1250, 560, 30, 0 events in the six bins - 4281 before the efficiency
of 0.584 - over a background of 900 ... 390, simulated with a third of the
data's luminosity and weighted events. What the files themselves give, with the
simulation normalised by cross-section x luminosity / sum of generated weights
(2.999 events per unit weight) and its error taken as sqrt(sum of w^2):

    signal      37.6  579.5  1229.0  604.4   64.0  -41.6
    error       72.6   71.8    67.1   64.0   53.1   50.2     (pulls from the truth: all under 0.9)
    sqrt(N+B)   43.2   46.9    49.9   41.6   31.2   27.9     the error if the simulation were a count
    corrected yield 4234 +- 354   (0.13 sigma from the truth; +- 288 with sqrt(N+B); +- 267
                                   without the efficiency's 5.5%)

The values are arithmetic on the files, so they are held tightly; the errors
to 8-10%, which no correct propagation is outside and every shortcut is.
"""
import json
import math
from pathlib import Path

SIGNAL = [37.57, 579.46, 1228.95, 604.38, 64.00, -41.61]
ERROR = [72.61, 71.78, 67.13, 63.97, 53.07, 50.22]
CORRECTED, CORRECTED_ERR = 4234.2, 353.9


def result():
    return json.loads(Path("result.json").read_text())


def numbers(value, n):
    assert isinstance(value, list) and len(value) == n, "a list of %d numbers" % n
    for x in value:
        assert isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
    return value


def test_result_file_has_the_lists_and_the_numbers():
    data = result()
    numbers(data["signal"], 6)
    numbers(data["signal_unc"], 6)
    numbers([data["corrected_yield"], data["corrected_yield_unc"]], 2)


def test_signal_per_bin_is_data_minus_normalised_background():
    # Two events: the normalisation rounded to 3.0 moves a bin by 0.3; forgetting the weights,
    # or fb for pb in the luminosity, moves every bin by hundreds.
    for got, want in zip(numbers(result()["signal"], 6), SIGNAL):
        assert abs(got - want) < 2.0


def test_negative_bin_is_not_clipped():
    assert numbers(result()["signal"], 6)[5] < -30


def test_error_per_bin_uses_the_sum_of_squared_weights():
    # sqrt(N + scale^2 sum w^2), within 8%. sqrt(N + B) is 26 to 45% lower in every bin, and
    # the data's sqrt(N) alone lower still.
    for got, want in zip(numbers(result()["signal_unc"], 6), ERROR):
        assert abs(got / want - 1) < 0.08


def test_corrected_yield():
    # Sum of the six bins over 0.584, within half a per cent.
    assert abs(result()["corrected_yield"] / CORRECTED - 1) < 0.005


def test_corrected_yield_error_has_the_simulation_and_the_efficiency_in_it():
    # 354 within 10%: 6.3% from the subtraction and 5.5% from the efficiency. 288 with
    # sqrt(N + B) errors, 267 without the efficiency's uncertainty, 268 without the simulation's.
    assert abs(result()["corrected_yield_unc"] / CORRECTED_ERR - 1) < 0.10
