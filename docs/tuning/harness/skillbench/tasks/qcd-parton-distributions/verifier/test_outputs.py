"""Hidden check, run in the project folder after the session. All must pass for reward 1."""
import json
import math
from pathlib import Path

# From oracle/solve.py on the two CSV files. CT18NLO, 29 eigenvector pairs at 90% CL:
#   symmetric (1/2) sqrt(sum (X+ - X-)^2)                = 107.53 pb
#   up        sqrt(sum max(X+ - X0, X- - X0, 0)^2)       = 131.95 pb
#   down      sqrt(sum max(X0 - X+, X0 - X-, 0)^2)       = 103.66 pb
# each divided by 1.6449 for 68% CL. NNPDF3.1: mean and standard deviation of the 100 replicas.
TRUE = {"ct18_sym_pb": 65.3756, "ct18_up_pb": 80.2223, "ct18_down_pb": 63.0193,
        "nnpdf_central_pb": 4541.87, "nnpdf_unc_pb": 38.3473}
# 0.4% takes 1.64, 1.645 or 1.6449 for the 90% quantile. Not scaling at all is 64% out; a
# standard deviation over the eigenvector members 66% or more; taking odd members as up and
# even ones as down 11 and 19%; counting both members of a pair that moves one way 1.7 and 1.8%.
HESSIAN_TOLERANCE = 4e-3
# Member 0 is 0.01% from the replica mean, so either is the central value. For the
# uncertainty the standard deviation with N or N - 1 and the central 68% interval, however its
# end points are interpolated, are all within 2.5% of each other.
CENTRAL_TOLERANCE = 5e-4
REPLICA_TOLERANCE = 0.04
CL90_OVER_CL68 = 1.6449


def result():
    return json.loads(Path("result.json").read_text())


def off(key):
    return abs(abs(result()[key]) / TRUE[key] - 1)


def test_result_file_has_the_five_numbers():
    data = result()
    for key in TRUE:
        assert isinstance(data[key], (int, float)) and math.isfinite(data[key]), key


def test_hessian_symmetric_uncertainty_at_68_per_cent():
    assert off("ct18_sym_pb") < HESSIAN_TOLERANCE


def test_hessian_upward_uncertainty_at_68_per_cent():
    assert off("ct18_up_pb") < HESSIAN_TOLERANCE


def test_hessian_downward_uncertainty_at_68_per_cent():
    assert off("ct18_down_pb") < HESSIAN_TOLERANCE


def test_hessian_uncertainty_is_not_left_at_90_per_cent():
    for key in ("ct18_sym_pb", "ct18_up_pb", "ct18_down_pb"):
        assert abs(abs(result()[key]) / (TRUE[key] * CL90_OVER_CL68) - 1) > 0.01, "%s is the 90%% CL value" % key


def test_replica_central_value():
    assert off("nnpdf_central_pb") < CENTRAL_TOLERANCE


def test_replica_uncertainty():
    assert off("nnpdf_unc_pb") < REPLICA_TOLERANCE
