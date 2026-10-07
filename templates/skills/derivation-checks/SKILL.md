---
name: derivation-checks
description: "Checking an analytic derivation or formula before trusting it: dimensional analysis, natural-unit bookkeeping, limiting and special cases, symmetries, independent symbolic verification with sympy, and numerical spot checks. Use for any derivation, formula manipulation, or result stated in closed form."
---

# Checking a derivation

Run these checks on every derived result before reporting it, and say which
ones passed. A derivation that has not been checked is a draft.

1. **Dimensions.** Every term of a sum and both sides of an equation have the
   same dimensions; arguments of exp, log, sin are dimensionless. In natural
   units, restore ħ and c to check, then drop them again. Track units through
   code too (`pint` or `astropy.units` if installed, otherwise by hand).
2. **Limits.** The result reduces to the known one in the limits it should:
   v ≪ c (non-relativistic), ħ → 0 (classical), m → 0, weak coupling, large N,
   t → 0 and t → ∞, a parameter → 0. Write each limit down and show it.
3. **Special cases.** Plug in a case with a known answer (free particle,
   harmonic oscillator, hydrogen ground state, a single scatterer).
4. **Symmetries and signs.** Lorentz/gauge/rotational invariance where
   expected; correct behaviour under parity, time reversal, exchange of
   identical particles; hermiticity; probabilities in [0, 1] and summing to 1;
   positive energies and cross sections.
5. **Symbolic verification.** Re-derive the key step independently in sympy:
   `sp.simplify(lhs - rhs) == 0`, differentiate a claimed integral, substitute
   a claimed solution back into the equation, series-expand to check limits.
   `simplify` returning something non-zero is not proof of an error - try
   `sp.expand`, `sp.trigsimp`, or numerical evaluation at random points.
6. **Numerical spot check.** Evaluate both sides at a few random parameter
   values (`mpmath` for high precision) and compare; integrate or solve
   numerically where a closed form is claimed.

## Conventions

State them before deriving and keep them fixed: metric signature (+,−,−,−) or
(−,+,+,+), Fourier sign and 2π placement, normalisation of states, units
(SI, Gaussian, natural with ħ = c = 1, Heaviside-Lorentz). A factor of 2π or a
sign is the usual error; it comes from mixing conventions. If the user's
material uses one, use theirs.

## Exact constants for unit conversion

These are exact by definition in the SI since 2019 and safe to use from here:
c = 299 792 458 m s⁻¹; h = 6.626 070 15 × 10⁻³⁴ J s;
e = 1.602 176 634 × 10⁻¹⁹ C; k_B = 1.380 649 × 10⁻²³ J K⁻¹;
N_A = 6.022 140 76 × 10²³ mol⁻¹. Hence ħ = h/2π, ħc = 197.326 980 4… MeV fm,
1 eV = 1.602 176 634 × 10⁻¹⁹ J exactly. Measured constants (G, α, particle
masses, …) are not exact: see `physical-constants`.
