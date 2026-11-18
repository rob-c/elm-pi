"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# From oracle/make_environment.py: the continuous spectrum times the two-flavour survival
# probability (sin^2 theta23 = 0.545, dm2 = 2.47e-3 eV^2, 295 km), integrated over each analysis
# bin. The 10 MeV table reproduces these to 0.1% whether the probability is taken at each fine
# bin's centre, averaged over its edges or integrated across it; with 1.27 for 1.267 the two
# bins around the dip move by 1.8%. Hence 3% a bin and 1% on the total.
TRUTH = [158.415, 44.072, 23.412, 124.734, 115.241, 34.842]
TOTAL = 500.715
UNOSCILLATED = 1480.0


def result():
    return json.loads(Path("result.json").read_text())


def close(key, expected, tolerance):
    value = result()[key]
    assert abs(value / expected - 1) < tolerance, "%s = %s, expected %.2f" % (key, value, expected)


def test_result_file_has_the_seven_numbers():
    data = result()
    for key in ["n_osc_%d" % i for i in range(1, 7)] + ["n_osc_total"]:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_bin_with_the_fast_oscillation_is_averaged():
    # 200-400 MeV: the probability at the bin's centre is 0.996 and gives 217.9; the average is 0.724.
    close("n_osc_1", TRUTH[0], 0.03)


def test_bins_around_the_dip():
    # 400-600 and 600-800 MeV. At the bin centres: 28.2 and 22.4.
    close("n_osc_2", TRUTH[1], 0.03)
    close("n_osc_3", TRUTH[2], 0.03)


def test_bins_above_the_dip():
    # At the bin centres: 138.0 (+10.6%), 126.0 (+9.4%), 35.5 (+1.8%).
    close("n_osc_4", TRUTH[3], 0.03)
    close("n_osc_5", TRUTH[4], 0.03)
    close("n_osc_6", TRUTH[5], 0.03)


def test_total():
    # Bin centres give 568 (+13%); sin^2(theta) in place of sin^2(2 theta), 942; MeV put in
    # where 1.267 wants GeV, 1480 (no oscillation at all); the baseline in metres, 772.
    close("n_osc_total", TOTAL, 0.01)


def test_neutrinos_do_disappear():
    assert 0.2 * UNOSCILLATED < result()["n_osc_total"] < 0.5 * UNOSCILLATED


def test_total_is_the_sum_of_the_bins():
    data = result()
    assert abs(sum(data["n_osc_%d" % i] for i in range(1, 7)) / data["n_osc_total"] - 1) < 0.005
