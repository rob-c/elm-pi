# Cross-section of the 1779 keV line: runs 1 and 2

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
