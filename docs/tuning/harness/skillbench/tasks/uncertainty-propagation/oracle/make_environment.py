"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir> [seed]

Two runs measure one cross-section. Each run's spectrum is simulated (a
Gaussian peak on a flat background), fitted here with a Poisson likelihood, and
only the fit result is kept: values and covariance matrix, as a fit log has
them. The peak's height and width come out anticorrelated (rho about -0.6), so
the number of events in the peak, N = A sigma sqrt(2 pi) / w, is known better
than adding the two relative errors in quadrature says. The target thickness
and the detection efficiency are the same objects in both runs, so their
uncertainties do not average down between the runs and cancel in a comparison
of the two.
"""
import json
import sys
from pathlib import Path

import numpy as np
from iminuit import Minuit

out = Path(sys.argv[1])
# One of twenty seeds tried: the runs differ by 0.9 of a statistical standard deviation and their
# mean is 0.35 from the truth. Not one where they differ by more than one: chi2/ndf of the two
# would then be above 1, and whether to scale the error by its root (the PDG's convention) is a
# question with two defensible answers, which a check cannot hold anyone to.
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20261132
rng = np.random.default_rng(seed)

XSEC_MB = 37.5                       # the cross-section both runs measure
TARGET = 2.40e19                     # atoms / cm2
EFFICIENCY = 0.0183
BEAM = {1: 1.10e11, 2: 1.70e11}      # particles on target
WIDTH = 2.0                          # keV per bin
edges = np.arange(1700.0, 1860.0 + WIDTH / 2, WIDTH)
centres = (edges[:-1] + edges[1:]) / 2
MEAN, SIGMA, FLAT = 1778.9, 6.1, {1: 14.0, 2: 22.0}


def shape(x, height, mean, sigma, flat):
    return height * np.exp(-0.5 * ((x - mean) / sigma) ** 2) + flat


summary = {}
for run, beam in BEAM.items():
    events = XSEC_MB * 1e-27 * beam * TARGET * EFFICIENCY
    height = events * WIDTH / (SIGMA * np.sqrt(2 * np.pi))
    counts = rng.poisson(shape(centres, height, MEAN, SIGMA, FLAT[run]))

    def nll(A, mu, sigma, c):
        expected = shape(centres, A, mu, sigma, c)
        return 2 * np.sum(expected - counts * np.log(expected))

    fit = Minuit(nll, A=float(counts.max()), mu=1780.0, sigma=5.0, c=float(np.median(counts)))
    fit.errordef = 1.0
    fit.limits["A"] = fit.limits["c"] = (1e-6, None)
    fit.limits["sigma"] = (1.0, 20.0)
    fit.migrad()
    fit.hesse()
    assert fit.valid, fit.fmin
    names = list(fit.parameters)
    covariance = np.array(fit.covariance)
    record = {
        "run": run,
        "spectrum": "run%d.spe, 1700-1860 keV, %d bins of %.1f keV" % (run, len(centres), WIDTH),
        "function": "A*exp(-0.5*((E-mu)/sigma)**2) + c",
        "method": "binned Poisson likelihood, MIGRAD then HESSE",
        "valid": True,
        "parameters": names,
        "values": [float("%.6g" % fit.values[n]) for n in names],
        "errors": [float("%.4g" % fit.errors[n]) for n in names],
        "covariance": [[float("%.5g" % v) for v in row] for row in covariance],
    }
    (out / ("fit_run%d.json" % run)).write_text(json.dumps(record, indent=1) + "\n")
    A, sigma = fit.values["A"], fit.values["sigma"]
    n_peak = A * sigma * np.sqrt(2 * np.pi) / WIDTH
    relative = np.sqrt(covariance[0, 0] / A**2 + covariance[2, 2] / sigma**2 + 2 * covariance[0, 2] / (A * sigma))
    summary[run] = (n_peak / (beam * TARGET * EFFICIENCY) / 1e-27, relative, covariance[0, 2] / np.sqrt(covariance[0, 0] * covariance[2, 2]),
                    np.sqrt(covariance[0, 0] / A**2 + covariance[2, 2] / sigma**2), events, n_peak)

(out / "notes.md").write_text("""# Cross-section of the 1779 keV line: runs 1 and 2

Same target, same detector, same beam energy in both runs; only the beam time
differs.

## Peak fits

`fit_run1.json` and `fit_run2.json` are the fit results as the fit program
wrote them: the values, their errors and the covariance matrix, rows and
columns in the order of `parameters`. The fitted function is the counts per bin,

    A * exp(-0.5 * ((E - mu) / sigma)**2) + c

with A the height of the peak in counts per bin, mu and sigma in keV, and c the
flat background in counts per bin. The bins are 2.0 keV wide, so the number of
events in the peak is N = A * sigma * sqrt(2 pi) / (2.0 keV).

## From events to cross-section

    cross-section = N / (beam particles * target atoms per cm2 * efficiency)

| | run 1 | run 2 |
|---|---|---|
| beam particles on target (current integrator, good to 0.1%) | 1.10e11 | 1.70e11 |

- Target: 2.40e19 atoms/cm2, known to 4.0% (weighing and area, done once: it is
  the same foil in both runs).
- Detection efficiency for the line at the detector position: 0.0183, known to
  2.5% (the source calibration of 2026-10-02, used for both runs).
- 1 mb = 1e-27 cm2.
""")
for run, (xsec, relative, rho, quadrature, events, n_peak) in summary.items():
    print("run %d: expected %.0f events, fitted %.0f; cross-section %.2f mb +- %.2f%% (rho(A, sigma) = %.2f; in quadrature %.2f%%)" % (
        run, events, n_peak, xsec, 100 * relative, rho, 100 * quadrature))
x1, r1 = summary[1][:2]
x2, r2 = summary[2][:2]
s1, s2 = x1 * r1, x2 * r2
w1, w2 = 1 / s1**2, 1 / s2**2
mean = (w1 * x1 + w2 * x2) / (w1 + w2)
print("seed %d: stat-weighted mean %.2f +- %.2f (stat); runs differ by %.2f sigma; mean is %.2f sigma from the truth" % (
    seed, mean, (w1 + w2) ** -0.5, abs(x1 - x2) / np.hypot(s1, s2), (mean - XSEC_MB) * (w1 + w2) ** 0.5))
