---
name: statistics-and-significance
description: "Statistical inference for physics results: hypothesis tests and p-values, discovery significance, confidence intervals and upper limits, efficiencies, look-elsewhere effect, and what each claim means. Use when stating a significance, a limit, an interval, an efficiency, or whether two results agree."
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

- Expected discovery significance for s signal over b known background
  (Asimov, Cowan et al. 2011): Z = √(2[(s + b) ln(1 + s/b) − s]). It reduces
  to s/√b only when s ≪ b - do not use s/√b otherwise.
- With a background uncertainty σ_b, s/√b overstates the significance; use the
  profile-likelihood version or say the uncertainty was neglected.
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

## Look-elsewhere effect

A local significance found by scanning (a mass, an energy, many bins) must be
converted to a global one - the trials factor. Report both, and say how the
global one was estimated.
