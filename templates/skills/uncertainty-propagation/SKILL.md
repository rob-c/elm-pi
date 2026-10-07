---
name: uncertainty-propagation
description: "Propagating and quoting uncertainties: linear propagation with covariance, correlated inputs, Monte Carlo propagation when linearisation fails, combining statistical and systematic errors, weighted averages, and rounding results to the PDG convention. Use whenever a reported number needs an error bar."
---

# Uncertainty propagation

## Linear propagation

For y = g(x₁ … xₙ) with covariance matrix C of the inputs:

σ_y² = J C Jᵀ,  J_i = ∂g/∂x_i at the central values.

With independent inputs this reduces to σ_y² = Σ (∂g/∂x_i)² σ_i². Use the full
C whenever inputs share a source (same calibration, same fit, same sample):
ignoring a positive correlation under-states the error of a sum and over-states
the error of a difference. Compute derivatives analytically (sympy) or
numerically with a step much smaller than σ.

Rules worth having in hand: for products and quotients, relative errors add in
quadrature (independent inputs); for y = xⁿ, σ_y/y = |n| σ_x/x.

## When linear propagation fails

If σ is not small compared with the curvature of g (e.g. 1/x with x near zero,
ln x with large relative error, ratios of small numbers), propagate by Monte
Carlo: sample the inputs from their joint distribution
(`rng.multivariate_normal(mean, C, size=10**5)`), evaluate g, and quote the
median with the 16th-84th percentile interval. Report asymmetric errors when
the interval is asymmetric. Seed the generator and say how many samples.

## Statistical and systematic

Keep them separate in the report: x = 1.234 ± 0.012 (stat) ± 0.020 (syst).
Combine in quadrature only when asked or for a total, and only if the
systematics are independent of each other. Evaluate a systematic by varying
the assumption (calibration ± 1σ, alternative model, fit range) and taking the
shift; do not count the same effect twice.

## Weighted average

x̄ = Σ wᵢxᵢ / Σ wᵢ, wᵢ = 1/σᵢ², σ_x̄ = (Σ wᵢ)^(-1/2), for independent
measurements. Check consistency with χ² = Σ wᵢ(xᵢ − x̄)² against ndf = n − 1;
if χ²/ndf > 1, the PDG convention scales σ_x̄ by √(χ²/ndf) - say so.

## Rounding (PDG convention)

Take the three highest-order digits of the uncertainty:
- 100-354: round the uncertainty to two significant digits;
- 355-949: round to one significant digit;
- 950-999: round up to 1000 and keep two significant digits.

Then quote the value to the same decimal place as the uncertainty:
1.2345 ± 0.0123 → 1.234 ± 0.012; 1.2345 ± 0.0456 → 1.23 ± 0.05. Never quote
more digits than the uncertainty supports, and keep full precision in
intermediate steps.
