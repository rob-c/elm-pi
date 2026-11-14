---
name: data-fitting
description: "Fitting a model to measured data and reporting it properly - least squares or likelihood, weights and Poisson counts, chi2/ndf, residuals, parameter uncertainties."
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

A Poisson likelihood fit, the whole of it:

```python
from iminuit import Minuit
def cash(N0, lam, B):                      # -2 ln L for counts n at times t, up to a constant
    mu = N0 * np.exp(-lam * t) + B
    return 2 * np.sum(mu - n * np.log(mu))
m = Minuit(cash, N0=n[0], lam=np.log(2) / 130, B=n[-10:].mean())   # starts from the data
m.errordef = 1                             # 1 for -2 ln L or chi-square; 0.5 for -ln L
m.limits["N0"] = m.limits["lam"] = m.limits["B"] = (0, None)
m.migrad(); m.hesse()
assert m.valid, m.fmin                     # then m.values["lam"], m.errors["lam"], m.covariance
```

**Not `scipy.optimize.minimize` for a likelihood fit unless you check it.**
Its "converged" is not proof: with parameters of very different sizes (N₀ ≈ 800
beside λ ≈ 0.005) L-BFGS-B stopped almost where it started and said success -
a decay fit reported 145.1 ± 1.3 s where the minimum was at 151.5 ± 2.7 s
(2026-11-14). Use iminuit, which scales its steps and reports validity. With
`minimize`, restart it from its own result with another method (Nelder-Mead)
and keep the lower minimum; a parameter that hardly left its starting value,
or a p-value below 0.05, is a fit to look into, not one to report.

## Judge the fit

- **χ²/ndf** with ndf = points − free parameters. Expect 1 within about
  √(2/ndf). Far above: the model or the errors are wrong. Far below: errors
  overestimated or correlated. Neither is a "good fit". Give the p-value
  (`scipy.stats.chi2.sf(chi2, ndf)`).
- **Fix the model, not the errors.** χ²/ndf far above 1 with structured
  residuals means a term is missing: add it. Adding an "intrinsic scatter" in
  quadrature until χ²/ndf ≈ 1 makes any model fit and hides the missing term - a
  straight line through 50 years of CO₂, which grows faster than linearly, was
  given 3 ppm of "scatter" that way (2026-11-13). A scatter term is only for a
  known physical spread, stated with its cause.
- **Residuals or pulls** (y − f)/σ: plot them. They should scatter as N(0, 1)
  with no trend; structure means a missing term. A periodic term of period T is
  cos(2πt/T) and sin(2πt/T): a yearly cycle's harmonics have T = 1, 1/2, 1/3 yr.
- **Correlations**: report the correlation matrix when parameters are
  correlated (|ρ| > 0.5 is common for slope/intercept, amplitude/width).
- **Stability**: refit from different starting values and, if it matters, with
  one point removed. A result that moves is not a result.
- **Several σ from a known value**: suspect the fit before the apparatus. Check
  it reached its minimum (another minimiser, another start) before naming dead
  time or an offset - the 145.1 s above was explained that way, and was the fit.

## Derived quantities

Propagate with the full covariance, not just the diagonal: for g(p),
σ_g² = J C Jᵀ with J = ∂g/∂p (see `uncertainty-propagation`). Example: a half
life from a decay constant, t½ = ln 2 / λ, σ_t½ = t½ σ_λ / λ.

## Report

Result with uncertainty and units, method (estimator, weights, model),
χ²/ndf and p-value, number of points, and the script (kept in the working
directory) with the command that produced the numbers. Plot data with error
bars, the fit, and a residual panel underneath.
