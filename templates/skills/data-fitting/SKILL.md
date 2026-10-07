---
name: data-fitting
description: "Fitting a model to measured data and reporting it properly: choosing least squares vs likelihood, weights and Poisson counts, curve_fit/iminuit usage, chi2/ndf and p-values, residuals and pulls, parameter covariance, and derived quantities with uncertainties. Use for any fit, regression, calibration, decay curve, peak or spectrum."
---

# Fitting data

## Choose the estimator from the errors, not from habit

- **Known Gaussian errors per point**: weighted least squares, χ² = Σ ((y − f)/σ)².
  Use the measurement errors as weights; never fit unweighted when errors are known.
- **Counts (histograms, decays, spectra)**: the errors are Poisson. For counts
  below about 10-20 per bin, a χ² fit with σ = √N is biased (Neyman's χ²
  pulls the fit low, and empty bins break it). Use a Poisson likelihood
  (minimise −2 ln L, the Cash statistic) instead. Above that, σ = √N is fine.
- **Never linearise and fit unweighted.** Fitting ln(N) against t with equal
  weights gives the tail points (smallest N, largest relative error) the same
  weight as the head. If you linearise, propagate the weights: σ_lnN = σ_N / N.
  Better: fit the exponential directly.
- **Errors on x as well as y**: orthogonal distance regression
  (`scipy.odr`) or an effective variance σ_eff² = σ_y² + (f′ σ_x)².

## Tools

```python
from scipy.optimize import curve_fit
popt, pcov = curve_fit(f, x, y, p0=p0, sigma=sigma, absolute_sigma=True)
perr = np.sqrt(np.diag(pcov))
```

`absolute_sigma=True` when `sigma` holds real measurement errors. The default
(`False`) rescales the covariance by χ²/ndf, which silently hides a bad error
model. For likelihood fits, MINOS errors or correlated parameters, use
`iminuit` (`Minuit(cost, ...)`, `.migrad()`, `.hesse()`, `.minos()`) with
`iminuit.cost.LeastSquares`, `UnbinnedNLL` or `ExtendedBinnedNLL`. Always give
starting values from the data, not 1.0, and check the fit converged
(`m.valid`, `m.fmin.is_valid`).

## Judge the fit

- **χ²/ndf** with ndf = points − free parameters. Expect 1 within about
  √(2/ndf). Far above: the model or the errors are wrong. Far below: errors
  overestimated or correlated. Neither is a "good fit". Give the p-value
  (`scipy.stats.chi2.sf(chi2, ndf)`).
- **Residuals or pulls** (y − f)/σ: plot them. They should scatter as N(0, 1)
  with no trend; structure means a missing term.
- **Correlations**: report the correlation matrix when parameters are
  correlated (|ρ| > 0.5 is common for slope/intercept, amplitude/width).
- **Stability**: refit from different starting values and, if it matters, with
  one point removed. A result that moves is not a result.

## Derived quantities

Propagate with the full covariance, not just the diagonal: for g(p),
σ_g² = J C Jᵀ with J = ∂g/∂p (see `uncertainty-propagation`). Example: a half
life from a decay constant, t½ = ln 2 / λ, σ_t½ = t½ σ_λ / λ.

## Report

Result with uncertainty and units, method (estimator, weights, model),
χ²/ndf and p-value, number of points, and the script (kept in the working
directory) with the command that produced the numbers. Plot data with error
bars, the fit, and a residual panel underneath.
