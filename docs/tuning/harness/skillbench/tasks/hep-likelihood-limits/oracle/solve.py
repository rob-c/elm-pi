"""The reference solution: run in the project folder, writes result.json.

The model: n ~ Pois(mu s (1 + d theta) + b), with a Gaussian constraint on b (the sideband estimate
as an auxiliary measurement) and on theta. Test statistic q-tilde, the profile likelihood ratio for
upper limits; CLs = p(s+b) / (1 - p(b)) from the asymptotic formulae (Cowan, Cranmer, Gross,
Vitells 2011), the width taken from the background-only Asimov data; the limit is where CLs
crosses 0.05, and the expected limits are where the Asimov CLs at N sigma does. With about 50
events in the bin the asymptotic formulae hold: toys and a hybrid calculation with the nuisance
parameters integrated out agree with these numbers within 4% (verifier/test_outputs.py).
"""
import csv
import json

import numpy as np
from scipy import optimize, stats

rows = {row["quantity"]: row for row in csv.DictReader(open("yields.csv"))}
N_OBS = int(rows["observed"]["value"])
B0, SIGMA_B = float(rows["background"]["value"]), float(rows["background"]["uncertainty"])
S1 = float(rows["signal_per_fb"]["value"])
REL_S = float(rows["signal_per_fb"]["uncertainty"]) / S1
ALPHA = 0.05


def nll(nuisance, mu, n, b_measured):
    """-ln L up to constants. mu is the cross-section in fb; nuisance = (b, theta)."""
    b, theta = nuisance
    expected = mu * S1 * (1 + REL_S * theta) + b
    if expected <= 0 or b <= 0:
        return 1e9
    return expected - n * np.log(expected) + 0.5 * ((b - b_measured) / SIGMA_B) ** 2 + 0.5 * theta**2


def profiled(mu, n, b_measured):
    fit = optimize.minimize(nll, [b_measured, 0.0], args=(mu, n, b_measured), method="Nelder-Mead",
                            options={"xatol": 1e-7, "fatol": 1e-11, "maxiter": 5000})
    return fit.fun


def q_tilde(mu, n, b_measured):
    best = optimize.minimize_scalar(lambda m: profiled(m, n, b_measured), bounds=(0.0, 20.0), method="bounded", options={"xatol": 1e-7})
    mu_hat, minimum = best.x, best.fun
    at_zero = profiled(0.0, n, b_measured)
    if at_zero < minimum:
        mu_hat, minimum = 0.0, at_zero
    if mu_hat > mu:
        return 0.0
    return max(2 * (profiled(mu, n, b_measured) - minimum), 0.0)


def cls_observed(mu):
    q, q_asimov = q_tilde(mu, N_OBS, B0), q_tilde(mu, B0, B0)        # Asimov: n = b, background only
    root, root_asimov = np.sqrt(q), np.sqrt(q_asimov)
    if q <= q_asimov:
        p_sb, one_minus_p_b = stats.norm.sf(root), stats.norm.sf(root - root_asimov)
    else:
        p_sb = stats.norm.sf((q + q_asimov) / (2 * root_asimov))
        one_minus_p_b = stats.norm.sf((q - q_asimov) / (2 * root_asimov))
    return p_sb / one_minus_p_b


def cls_expected(mu, n_sigma):
    root_asimov = np.sqrt(q_tilde(mu, B0, B0))
    return stats.norm.sf(root_asimov - n_sigma) / stats.norm.cdf(n_sigma)


def limit(cls):
    return optimize.brentq(lambda mu: cls(mu) - ALPHA, 0.01, 10.0, xtol=1e-5)


answer = {
    "obs_limit_fb": limit(cls_observed),
    "exp_limit_fb": limit(lambda mu: cls_expected(mu, 0)),
    "exp_minus1_fb": limit(lambda mu: cls_expected(mu, -1)),
    "exp_plus1_fb": limit(lambda mu: cls_expected(mu, +1)),
}
json.dump(answer, open("result.json", "w"), indent=1)
print("95%% CL (CLs, q-tilde, asymptotic): observed %.3f fb; expected %.3f fb, band %.3f to %.3f fb"
      % (answer["obs_limit_fb"], answer["exp_limit_fb"], answer["exp_minus1_fb"], answer["exp_plus1_fb"]))
