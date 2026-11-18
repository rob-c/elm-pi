"""Hidden check, run in the project folder after the session. All must pass for reward 1.

runs.csv was generated (oracle/make_environment.py, fixed seed) around the true
tally exp(-mu x)/(4 pi r^2) = 5.3697e-8 /cm2 per source photon. What is asked
for is a function of the table as written, so the expected values are the
oracle's, from the five independent runs (run 6 has run 5's seed, histories
and tally: it is run 5 again):

    combined tally   history-weighted      5.3647e-8 /cm2   (0.1% from the truth)
    its relative error                     0.01385
    flux             x 1.85e9 Bq x 0.851   84.46 /cm2/s
    narrow beam      1.5744e9 x 5.3697e-8  84.54 /cm2/s
    runs over 0.10   1 (0.248) and 2 (0.146)

Other sound ways of combining the five - weights 1/sigma^2 or 1/R^2, with or
without the two unreliable runs (1.3% of the histories) - give a tally within
0.17% and an error within 0.7% of those; the tally has 1% and the error -12%
to +30% (the upper side leaves room for a chi-square scale factor, 1.16 here).
What that shuts out: a plain average of the lines (3 to 7% low, error 1.4 to 4
times too large); run 6 counted as independent (error 0.0104, 25% too small);
both seed-1009 runs thrown away (3.9% low, error doubled); the tally times the
activity with no emission probability (17.5% high).
"""
import json
import math
from pathlib import Path

COMBINED = 5.3647e-8
REL_ERR = 0.01385
FLUX = 84.46
ANALYTIC = 84.538


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_every_entry():
    data = result()
    for key in ("combined_tally_per_cm2", "combined_rel_err", "flux_per_cm2_s", "flux_unc_per_cm2_s", "analytic_flux_per_cm2_s"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key
    assert isinstance(data["unreliable_runs"], list)


def test_unreliable_runs_are_the_two_short_ones():
    # Run 6 (or 5) may be listed as well by someone who set the repeated seed aside here.
    listed = {int(run) for run in result()["unreliable_runs"]}
    assert {1, 2} <= listed and not listed & {3, 4}, listed


def test_combined_tally_weights_the_runs_by_what_they_ran():
    assert abs(result()["combined_tally_per_cm2"] / COMBINED - 1) < 0.01


def test_combined_error_counts_the_repeated_seed_once():
    assert 0.88 < result()["combined_rel_err"] / REL_ERR < 1.30, "five independent runs, 5.27e8 histories: 1.39%"


def test_flux_has_the_activity_and_the_emission_probability():
    assert abs(result()["flux_per_cm2_s"] / FLUX - 1) < 0.01, "1.85e9 decays/s x 0.851 photons per decay"


def test_flux_uncertainty_is_the_combined_error():
    data = result()
    assert 0.88 < data["flux_unc_per_cm2_s"] / data["flux_per_cm2_s"] / REL_ERR < 1.30


def test_analytic_narrow_beam_flux():
    assert abs(result()["analytic_flux_per_cm2_s"] / ANALYTIC - 1) < 0.005, "mu = 0.1101 x 11.35 = 1.2496 /cm, 4.00 cm, 100 cm"
