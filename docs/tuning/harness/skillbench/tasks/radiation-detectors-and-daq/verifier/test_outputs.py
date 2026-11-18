"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The readings in environment/notes.md were computed (not drawn at random) from
the values in oracle/make_environment.py, and oracle/solve.py gets these back
from the notes:

    channel A, non-extending 2.50 us:  84 300 /s  ->  m / (1 - m tau)       = 106 810 /s
    channel B, extending 1.20 us:     247 948 /s  ->  n exp(-n tau) = m has the roots 401 354 /s and 1 500 003 /s.
        At 14 cm the two would read 160 160 /s and 305 487 /s; the notes say 305 487: the true rate is 1.500e6 /s.
    accidentals = 2 x 40 ns x 5210 /s x 3870 /s                              = 1.613 /s
    true coincidences = 8772 / 600 s - accidentals                           = 13.007 /s

The readings are given to five or six figures, so the tolerances are
arithmetic ones (the correlated part of the singles changes the accidentals by
0.6%). What they shut out: channel A uncorrected (-21%) or corrected with the
extending model (+4.3%); channel B on the low branch (401 k/s) or with the
non-extending formula (353 k/s); accidentals with one pulse width (0.807 /s),
which leaves the true rate 6% high; no subtraction at all (12% high).
"""
import json
import math
from pathlib import Path

TRUE_A = 106_810.0
TRUE_B = 1.5000e6
ACCIDENTALS = 1.613
TRUE_COINCIDENCES = 13.007


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_four_numbers():
    data = result()
    for key in ("true_rate_a_per_s", "true_rate_b_per_s", "accidental_rate_per_s", "true_coincidence_rate_per_s"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_channel_a_non_extending_correction():
    assert abs(result()["true_rate_a_per_s"] / TRUE_A - 1) < 0.005


def test_channel_b_is_on_the_saturated_branch():
    assert result()["true_rate_b_per_s"] > 1 / 1.20e-6, "the reading rose when the source was moved away: n tau is above 1"


def test_channel_b_true_rate():
    assert abs(result()["true_rate_b_per_s"] / TRUE_B - 1) < 0.01


def test_accidentals_use_both_pulse_widths():
    assert abs(result()["accidental_rate_per_s"] / ACCIDENTALS - 1) < 0.03, "two 40 ns pulses overlap within 80 ns"


def test_true_coincidence_rate():
    assert abs(result()["true_coincidence_rate_per_s"] / TRUE_COINCIDENCES - 1) < 0.01
