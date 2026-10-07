---
name: numerical-methods
description: "Getting numerically trustworthy results: floating-point pitfalls, ODE/PDE integration and stiffness, quadrature, root finding, linear algebra conditioning, convergence studies, Monte Carlo error, and reproducible random numbers. Use when writing or checking any numerical computation or simulation."
---

# Numerical methods

## Prove convergence

A single run proves nothing. Repeat with the resolution changed - step size
halved, grid doubled, tolerance tightened tenfold, Monte Carlo sample ×4 - and
show the result changes by less than the quoted precision. For an order-p
method the error falls by about 2ᵖ when the step halves; Richardson
extrapolation uses that. Report the convergence table, not just the final
number.

## Floating point

- Double precision has ~16 significant digits (machine ε ≈ 2.2 × 10⁻¹⁶).
- **Cancellation**: subtracting nearly equal numbers loses digits. Rewrite:
  `np.expm1(x)` for eˣ − 1, `np.log1p(x)` for ln(1 + x), `np.hypot`, and
  (a² − b²) = (a − b)(a + b); use the stable quadratic formula.
- Sum many terms of mixed magnitude with `math.fsum` or pairwise summation;
  never compare floats with `==` - use a relative tolerance.
- Work in logs for products of many small probabilities (`scipy.special.logsumexp`).
- Overflow/underflow: rescale to natural units of the problem first.

## ODEs

`scipy.integrate.solve_ivp`: `RK45`/`DOP853` for non-stiff problems; if the step
size collapses or it runs very slowly, the system is stiff - use `Radau`,
`BDF` or `LSODA` and supply the Jacobian. Set `rtol`/`atol` deliberately (the
defaults, 1e-3/1e-6, are loose for physics). Check conserved quantities
(energy, norm, charge) along the solution; for long Hamiltonian integrations
use a symplectic integrator (leapfrog/Verlet) rather than RK.

## Integrals and roots

`scipy.integrate.quad` returns an error estimate - report it, and split the
range at singularities or oscillations; transform infinite ranges or use the
`weight` options for oscillatory integrands. For roots, bracket first
(`brentq`) rather than Newton from a guess; check the residual at the answer.

## Linear algebra

Never invert a matrix to solve a system - use `np.linalg.solve` or
`scipy.linalg.lstsq`. Check the condition number (`np.linalg.cond`): with
κ ≈ 10ᵏ, expect to lose about k digits. Use `eigh` for symmetric/Hermitian
matrices.

## Monte Carlo

Statistical error ∝ 1/√N: quote it (standard error of the mean, or batch means
for correlated samples such as Markov chains - check the autocorrelation
time). Use `rng = np.random.default_rng(seed)`, pass `rng` explicitly, and
record the seed so the run can be reproduced.

## Report

Method and its parameters (step, tolerance, grid, N, seed), the convergence
evidence, and the estimated numerical error alongside any physical uncertainty.
