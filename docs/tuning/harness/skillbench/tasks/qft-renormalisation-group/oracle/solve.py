"""The reference solution: run in the project folder, writes result.json.

One-loop running in the conventions of notes.md, with n_f changed at each
quark mass and the coupling continuous there:

    1/alpha_s(mu) = 1/alpha_s(mu0) + (beta_0/2 pi) ln(mu/mu0),   beta_0 = 11 - 2 n_f/3
    m(mu) = m(mu0) [alpha_s(mu)/alpha_s(mu0)]^(4/beta_0)
    Lambda(n_f) = mu exp(-2 pi / (beta_0 alpha_s(mu))),  mu anywhere in the n_f-flavour interval

Checked against a numerical integration of the two differential equations
across the thresholds, and by running back up to m_Z.
"""
import json
import math

from scipy.integrate import solve_ivp

ALPHA_MZ, MZ = 0.1180, 91.1876              # notes.md
MC, MB, MT, MTAU = 1.27, 4.18, 162.5, 1.77686
THRESHOLDS = [MC, MB, MT]                   # n_f = 3 below the first, 6 above the last


def flavours(mu):
    return 3 + sum(mu > mass for mass in THRESHOLDS)


def beta0(nf):
    return 11 - 2 * nf / 3


def stages(start, end):
    """The path from start to end cut at the thresholds between them: [(from, to, n_f), ...]."""
    low, high = min(start, end), max(start, end)
    cuts = [low] + [mass for mass in THRESHOLDS if low < mass < high] + [high]
    pieces = [(a, b, flavours(0.5 * (a + b))) for a, b in zip(cuts[:-1], cuts[1:])]
    return pieces if start < end else [(b, a, nf) for a, b, nf in reversed(pieces)]


def run(alpha, mass, start, end):
    """(alpha_s, quark mass) taken from scale start to scale end."""
    for a, b, nf in stages(start, end):
        new = 1 / (1 / alpha + beta0(nf) / (2 * math.pi) * math.log(b / a))
        mass *= (new / alpha) ** (4 / beta0(nf))
        alpha = new
    return alpha, mass


def run_numerically(alpha, mass, start, end):
    for a, b, nf in stages(start, end):
        solution = solve_ivp(lambda t, y: [-beta0(nf) / (2 * math.pi) * y[0] ** 2, -2 * y[0] / math.pi * y[1]],
                             (math.log(a), math.log(b)), [alpha, mass], rtol=1e-12, atol=1e-14)
        alpha, mass = solution.y[0, -1], solution.y[1, -1]
    return alpha, mass


def lam(alpha, mu, nf):
    return mu * math.exp(-2 * math.pi / (beta0(nf) * alpha))


alpha_mb, _ = run(ALPHA_MZ, 1.0, MZ, MB)
alpha_mc, _ = run(ALPHA_MZ, 1.0, MZ, MC)
result = {
    "alphas_mtau": run(ALPHA_MZ, 1.0, MZ, MTAU)[0],
    "alphas_1tev": run(ALPHA_MZ, 1.0, MZ, 1000.0)[0],
    "lambda5_mev": 1000 * lam(ALPHA_MZ, MZ, 5),
    "lambda4_mev": 1000 * lam(alpha_mb, MB, 4),
    "lambda3_mev": 1000 * lam(alpha_mc, MC, 3),
    "mb_mz_gev": run(alpha_mb, MB, MB, MZ)[1],
    "mc_mz_gev": run(alpha_mc, MC, MC, MZ)[1],
}

for end in (MTAU, 1000.0, 1.0):
    assert abs(run(ALPHA_MZ, 1.0, MZ, end)[0] / run_numerically(ALPHA_MZ, 1.0, MZ, end)[0] - 1) < 1e-9
assert abs(run(alpha_mc, MC, MC, MZ)[1] / run_numerically(alpha_mc, MC, MC, MZ)[1] - 1) < 1e-9
assert abs(run(alpha_mb, MB, MB, MZ)[1] / run_numerically(alpha_mb, MB, MB, MZ)[1] - 1) < 1e-9
assert abs(run(alpha_mc, 1.0, MC, MZ)[0] / ALPHA_MZ - 1) < 1e-12, "running back up does not return alpha_s(m_Z)"
# Lambda is one number per n_f: the same from either end of an interval.
assert abs(lam(run(ALPHA_MZ, 1.0, MZ, MTAU)[0], MTAU, 4) / lam(alpha_mb, MB, 4) - 1) < 1e-12
assert abs(lam(alpha_mb, MB, 5) / lam(ALPHA_MZ, MZ, 5) - 1) < 1e-12

json.dump(result, open("result.json", "w"), indent=1)
for key, value in result.items():
    print("%-12s %.9g" % (key, value))
