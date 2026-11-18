"""Hidden check, run in the project folder after the session. All must pass for reward 1.

Expected values are arithmetic on notes.md (oracle/solve.py):

  activity     2.00 Ci x 3.7e10 x 2^(-10.00/30.05) = 5.876e10 Bq
  fluence rate 5.876e10 x 0.851 / (4 pi 250^2) = 6.366e4 photons/cm2/s
  unshielded   x 0.6617 MeV x 0.0323 cm2/g (soft tissue) x 1.602e-10 Gy g/MeV = 784.8 uGy/h
  wall         mu = 0.0775 x 2.30 = 0.17825 /cm; 30.0 cm = 5.348 mean free paths
  behind it    B exp(-mu x): 42.36 uGy/h with ln B interpolated in the table, 42.60
               linearly, 42.48 with a cubic spline: 42.5, tolerance 4%
  for 2.0      B(mu x) exp(-mu x) = 2.0/784.8 solved for x: 50.99 to 51.08 cm by the
               same three interpolations: 51.03, tolerance 2%

Nothing is statistical. Narrow beam (no build-up) gives 3.74 uGy/h and 33.5 cm; one
pass of build-up on the narrow-beam thickness, 47.9 cm. The certificate activity
undecayed is 26% high, no emission probability 17.5% high, the coefficient of air 9% low.
"""
import json
import math
from pathlib import Path

UNSHIELDED_UGY_H = 784.8
SHIELDED_UGY_H = 42.5
TRANSMISSION = SHIELDED_UGY_H / UNSHIELDED_UGY_H       # 0.0542 = 11.4 x exp(-5.348)
NARROW_BEAM_UGY_H = 3.74
THICKNESS_CM = 51.03


def result():
    return json.loads(Path("result.json").read_text())


def test_result_file_has_the_three_numbers():
    data = result()
    for key in ("unshielded_ugy_per_h", "shielded_ugy_per_h", "thickness_cm"):
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_unshielded_dose_rate_in_tissue():
    assert abs(result()["unshielded_ugy_per_h"] / UNSHIELDED_UGY_H - 1) < 0.03


def test_wall_is_a_broad_beam_shield():
    assert result()["shielded_ugy_per_h"] > 3 * NARROW_BEAM_UGY_H, "exp(-mu x) alone: the build-up factor is 11"


def test_transmission_of_the_wall_with_build_up():
    data = result()
    assert abs(data["shielded_ugy_per_h"] / data["unshielded_ugy_per_h"] / TRANSMISSION - 1) < 0.04


def test_dose_rate_behind_the_wall():
    assert abs(result()["shielded_ugy_per_h"] / SHIELDED_UGY_H - 1) < 0.04


def test_thickness_for_the_target_dose_rate():
    assert abs(result()["thickness_cm"] / THICKNESS_CM - 1) < 0.02
