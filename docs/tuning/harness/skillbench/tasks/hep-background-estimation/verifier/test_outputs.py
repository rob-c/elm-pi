"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The multijet yields were generated with region A holding 0.65 of B x C / D, in the b-tagged set and
in the validation set alike (oracle/make_environment.py): 60.45 events expected in A.

Both honest uses of the validation set are accepted. Applied as a correction, the estimate is
59.8 +- 7.3: data statistics 7.0%, prompt subtraction 7.1%, the correction 6.8%. Left uncorrected
with the non-closure as a systematic uncertainty it is 90.8 +- 32, one of its sigma from the truth.
What is refused:
- no prompt subtraction: 172 uncorrected, 113 or more with any correction (the window ends at 100);
- no use of the validation set: 90.8 +- 9.1, or +- 10.3 with the prompt errors fully correlated,
  which is 3.4 or 2.9 of its own sigma from the truth (2 allowed);
- counting statistics alone: 7.0% or less; with either of the other two sources it is 9.7% or
  more (8.5% required), and with both 12%.
"""
import json
import math
from pathlib import Path

TRUE_MULTIJET_A = 60.45


def result():
    data = json.loads(Path("result.json").read_text())
    return data["multijet_a"], data["multijet_a_unc"]


def test_result_file_has_both_numbers():
    for value in result():
        assert isinstance(value, (int, float)) and math.isfinite(value)
    assert result()[1] > 0


def test_prompt_events_were_subtracted():
    estimate, _ = result()
    assert 45.0 < estimate < 100.0, "with the prompt simulation left in, B x C / D is 172"


def test_estimate_agrees_with_the_truth_within_its_own_uncertainty():
    estimate, error = result()
    assert abs(estimate - TRUE_MULTIJET_A) <= 2.0 * error, "%.1f +- %.1f against %.2f" % (estimate, error, TRUE_MULTIJET_A)


def test_uncertainty_is_more_than_counting_statistics():
    estimate, error = result()
    assert error / estimate > 0.085, "data statistics alone are 7.0%"


def test_uncertainty_is_not_inflated_to_cover_anything():
    estimate, error = result()
    assert error / estimate < 0.45
