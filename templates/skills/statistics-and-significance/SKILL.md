---
name: statistics-and-significance
description: "Statistical inference for physics results - p-values and significance, confidence intervals and upper limits, efficiencies, the look-elsewhere effect."
---

# Statistics and significance

## Say what the number is

A p-value is the probability, under the null hypothesis, of data at least as
extreme as observed - not the probability that the null is true. A 68% CL
interval is a statement about the procedure's coverage. State the null, the
test statistic, and whether the result is one- or two-sided.

Significance Z and p are related by Z = Φ⁻¹(1 − p) (one-sided):
`scipy.stats.norm.isf(p)` and `norm.sf(Z)`. Conventions in particle physics:
3σ (p ≈ 1.35 × 10⁻³) "evidence", 5σ (p ≈ 2.87 × 10⁻⁷) "discovery".

## Counting experiments

- Expected discovery significance for s signal over b known exactly
  (Asimov, Cowan et al. 2011): Z = √(2[(s + b) ln(1 + s/b) − s]). It reduces
  to s/√b only when s ≪ b - do not use s/√b otherwise.
- A background counted in a sideband or control region is not known
  exactly, and the formula above and `poisson.sf(n − 1, b)` both overstate Z.
  With n in the window and m in sidebands τ times as wide (τ = sideband
  width ÷ window width, so the background estimate is m/τ: print it, and if
  it is not the number you expected, τ is upside down):
  `p = scipy.stats.binom.sf(n - 1, n + m, 1 / (1 + τ))`, then
  `Z = scipy.stats.norm.isf(p)`. n = 7, m = 4, τ = 2 gives 1.8σ, not 2.6.
  For a background with a Gaussian uncertainty σ_b, profile it; never quote
  a significance that silently neglects it.
- Small counts: use the Poisson distribution directly
  (`scipy.stats.poisson.sf(n − 1, b)` for P(N ≥ n)), not a Gaussian
  approximation.

## Intervals and limits

- Gaussian measurement far from a boundary: x ± σ is a 68.3% interval.
- Near a physical boundary (a mass, a rate ≥ 0) or with few events: use
  Feldman-Cousins (unified) intervals or a likelihood-ratio construction; state
  which. The CLs method is the convention for exclusion limits at the LHC.
- Upper limit with zero observed events and no background: 2.30 events at 90%
  CL and 3.00 at 95% CL (classical Poisson). Say which confidence level.
- Bayesian intervals depend on the prior; state the prior.

## Efficiencies and ratios k/n

Binomial, not √k: use Clopper-Pearson (exact, conservative) or Wilson
intervals - `statsmodels.stats.proportion.proportion_confint(k, n, method="beta")`
or the beta-distribution quantiles directly. √k/n gives zero error at
efficiencies of 0 or 1, which is wrong.

## Comparing results

Two independent measurements agree at |a − b| / √(σ_a² + σ_b²) standard
deviations; account for correlation if they share systematics. Do not call a
2σ difference a discrepancy or a 1σ agreement a confirmation.

**Before calling two numbers contradictory, check they are the same quantity.**
Two reports of one dataset often state one fact in two conventions: standard
deviation and variance (σ, σ²), standard deviation and standard error (σ,
σ/√n), n or n − 1 in the denominator, σ and FWHM (× 2.355), frequency and
angular frequency (× 2π), radius and diameter, a rate and a period, a unit
prefix (× 1000), a fraction and a percentage. Compute each candidate from the
data - square it, take the root, divide by √n, multiply by 2π - and see whether
one turns A into B. If one does, neither is wrong: say which convention each
uses. 4.13 and 17.1 given as the "spread" of one batch were its standard
deviation and its variance, and six sessions of six called the second wrong,
having tried only the standard deviation and the range (2026-11-17).

## Look-elsewhere effect

A local significance found by scanning (a mass, an energy, many bins) must be
converted to a global one - the trials factor. Report both, and say how the
global one was estimated.
