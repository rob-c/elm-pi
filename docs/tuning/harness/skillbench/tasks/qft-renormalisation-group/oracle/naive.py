"""What the task is built to catch: the five-flavour running used at every scale.

The one-loop formulae are right, but alpha_s(m_Z) is run with n_f = 5 down to
m_tau and m_c and up to 1 TeV, and Lambda for four and three flavours is taken
from alpha_s(m_Z) with only beta_0 changed, instead of from the coupling of the
four- and three-flavour theories below the b and c masses.
"""
import json
import math

ALPHA_MZ, MZ = 0.1180, 91.1876
MC, MB, MTAU = 1.27, 4.18, 1.77686


def beta0(nf):
    return 11 - 2 * nf / 3


def alpha(mu):
    return 1 / (1 / ALPHA_MZ + beta0(5) / (2 * math.pi) * math.log(mu / MZ))


json.dump({
    "alphas_mtau": alpha(MTAU),
    "alphas_1tev": alpha(1000.0),
    "lambda5_mev": 1000 * MZ * math.exp(-2 * math.pi / (beta0(5) * ALPHA_MZ)),
    "lambda4_mev": 1000 * MZ * math.exp(-2 * math.pi / (beta0(4) * ALPHA_MZ)),
    "lambda3_mev": 1000 * MZ * math.exp(-2 * math.pi / (beta0(3) * ALPHA_MZ)),
    "mb_mz_gev": MB * (ALPHA_MZ / alpha(MB)) ** (4 / beta0(5)),
    "mc_mz_gev": MC * (ALPHA_MZ / alpha(MC)) ** (4 / beta0(5)),
}, open("result.json", "w"), indent=1)
