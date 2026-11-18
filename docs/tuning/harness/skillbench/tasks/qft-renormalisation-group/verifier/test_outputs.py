"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

import pytest

# One-loop running from alpha_s(m_Z) = 0.1180 with n_f = 6, 5, 4, 3 above m_t, m_b, m_c and
# below, coupling and masses continuous at each quark mass (notes.md). From oracle/solve.py:
# the closed forms, equal to 1e-9 to a numerical integration of the two equations across the
# thresholds. Lambda(4) and Lambda(3) come from alpha_s(m_b) = 0.212169 and alpha_s(m_c) = 0.319161,
# and satisfy the continuity relations Lambda4 = Lambda5 (m_b/Lambda5)^(2/25),
# Lambda3 = Lambda4 (m_c/Lambda4)^(2/27).
TRUE = {
    "alphas_mtau": 0.279437168,
    "alphas_1tev": 0.0892544057,
    "lambda5_mev": 87.8270801,
    "lambda4_mev": 119.627843,
    "lambda3_mev": 142.505018,
    "mb_mz_gev": 3.07777450,
    "mc_mz_gev": 0.768682606,
}
# The same with n_f = 5 at every scale (oracle/naive.py).
FIVE_FLAVOURS = {"alphas_mtau": 0.272524898, "alphas_1tev": 0.0877444932, "lambda4_mev": 153.085139,
                 "lambda3_mev": 245.747321, "mc_mz_gev": 0.771448668}
# Closed forms of given numbers, asked for to six digits: 1e-4 passes a value rounded to five
# digits or six decimals, and a numerical integration at loose settings, and nothing else.
# Fixed n_f is 2.5% out at m_tau, 1.7% at 1 TeV, 28% and 72% in Lambda, 0.36% in m_c(m_Z).
TOLERANCE = 1e-4


def result():
    return json.loads(Path("result.json").read_text())


def close(key):
    return abs(result()[key] / TRUE[key] - 1) < TOLERANCE


def test_result_file_has_the_seven_numbers():
    data = result()
    for key in TRUE:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_alphas_at_mtau_is_run_through_the_b_threshold():
    assert close("alphas_mtau")


def test_alphas_at_1tev_is_run_through_the_top_threshold():
    assert close("alphas_1tev")


@pytest.mark.parametrize("key", ["lambda5_mev", "lambda4_mev", "lambda3_mev"])
def test_lambda_belongs_to_its_number_of_flavours(key):
    assert close(key)


@pytest.mark.parametrize("key", ["mb_mz_gev", "mc_mz_gev"])
def test_running_mass_at_mz(key):
    assert close(key)


def test_number_of_flavours_is_not_fixed_at_five():
    data = result()
    for key, value in FIVE_FLAVOURS.items():
        assert abs(data[key] / value - 1) > 1e-3, "%s is the five-flavour value" % key
