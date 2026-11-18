"""The reference solution: run in the project folder, writes result.json.

Each run: N = A sigma sqrt(2 pi) / w from the fitted height and width, with
the statistical error from the full covariance matrix, J C J^T (A and sigma are
anticorrelated, so it is smaller than the two relative errors in quadrature).
Checked by sampling the fit parameters from their covariance.

The two runs: the target thickness and the efficiency are common to both, so
they are a scale factor on any combination and their uncertainty stays whole:
the runs are averaged with their statistical weights, and the common 4.0% and
2.5% are applied to the average. In the comparison of the two runs the common
factor cancels, so only the statistical errors count.
"""
import json
import re

import numpy as np

notes = open("notes.md").read()
bin_width = float(re.search(r"bins are ([\d.]+) keV wide", notes).group(1))
beam = [float(x) for x in re.search(r"\| beam particles[^|]*\|\s*([\d.e+]+)\s*\|\s*([\d.e+]+)\s*\|", notes).groups()]
target, target_rel = re.search(r"Target: ([\d.e+]+) atoms/cm2, known to ([\d.]+)%", notes).groups()
efficiency, efficiency_rel = re.search(r"at the detector position: ([\d.]+), known to\s+([\d.]+)%", notes).groups()
target, efficiency = float(target), float(efficiency)
common = np.hypot(float(target_rel), float(efficiency_rel)) / 100       # relative, the same factor in both runs
MB = 1e-27                                                                # cm2

value, stat = [], []
for run in (1, 2):
    fit = json.load(open("fit_run%d.json" % run))
    names = fit["parameters"]
    p, C = np.array(fit["values"]), np.array(fit["covariance"])
    iA, iS = names.index("A"), names.index("sigma")

    def xsec(parameters):
        events = parameters[..., iA] * parameters[..., iS] * np.sqrt(2 * np.pi) / bin_width
        return events / (beam[run - 1] * target * efficiency) / MB

    x = xsec(p)
    J = np.zeros(len(p))
    J[iA], J[iS] = x / p[iA], x / p[iS]
    error = float(np.sqrt(J @ C @ J))
    sampled = xsec(np.random.default_rng(1).multivariate_normal(p, C, size=200_000))
    quadrature = x * np.hypot(np.sqrt(C[iA, iA]) / p[iA], np.sqrt(C[iS, iS]) / p[iS])
    print("run %d: %.2f +- %.2f mb (stat); sampled %.2f; without the covariance term %.2f" % (run, x, error, sampled.std(), quadrature))
    assert abs(sampled.std() / error - 1) < 0.02
    value.append(float(x))
    stat.append(error)

weights = 1 / np.square(stat)
mean = float(np.sum(weights * value) / weights.sum())
mean_stat = float(weights.sum() ** -0.5)
mean_syst = common * mean
differ = abs(value[0] - value[1]) / np.hypot(*stat)
print("combined: %.2f +- %.2f (stat) +- %.2f (syst) mb; the runs differ by %.2f sigma" % (mean, mean_stat, mean_syst, differ))
json.dump({"xsec_mb": mean, "stat_mb": mean_stat, "syst_mb": mean_syst, "runs_differ_sigma": float(differ)}, open("result.json", "w"), indent=1)
