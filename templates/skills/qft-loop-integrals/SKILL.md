---
name: qft-loop-integrals
description: "Loop integrals in dimensional regularisation - conventions and MS-bar, Feynman parameters, Passarino-Veltman and IBP reduction, UV versus infrared poles, thresholds, numerical libraries, and the checks."
disable-model-invocation: true
---

# Loop integrals

Loop results go wrong through normalisation (factors of i, π and 4π between
conventions, which move finite terms), through UV and infrared poles treated
as one thing, and through the wrong sign of an imaginary part above threshold.
Fix the conventions, then let a library check the algebra.

## Conventions to state

- d = 4 - 2ε, measure ∫ d^dk/(2π)^d, and a factor μ^{2ε} per loop so that the
  coupling stays dimensionless.
- MS-bar: subtract the pole together with -γE + ln 4π; equivalently rescale
  μ² → μ² e^{γE}/(4π) and subtract 1/ε alone.
- Libraries normalise differently (prefactors iπ², (2π)^d, Γ(1+ε)). At order
  ε⁰ a mismatch appears as stray ln 4π, γE or π²/6 terms. Read the manual's
  definition of A0 and B0 before using a number from it.

## Standard steps, metric (+,-,-,-), propagators 1/(k² - m² + iε)

1. Combine denominators: 1/(AB) = ∫₀¹ dx 1/[xA + (1-x)B]²; for n factors,
   (n-1)! ∫ dx1...dxn δ(1 - Σx) / [Σ x_i A_i]^n.
2. Shift the loop momentum to complete the square; drop odd powers of k and
   replace k^μ k^ν by k² g^{μν}/d.
3. Wick-rotate (k⁰ = i k⁰ Euclidean) and integrate:
   ∫ d^dk/(2π)^d 1/(k² - Δ)^n = (-1)^n i/(4π)^{d/2} Γ(n - d/2)/Γ(n) Δ^{d/2-n};
   with k² in the numerator,
   (-1)^{n-1} i/(4π)^{d/2} (d/2) Γ(n - d/2 - 1)/Γ(n) Δ^{d/2-n+1}.
4. Expand, Γ(ε) = 1/ε - γE + O(ε), keeping the O(ε) part of whatever
   multiplies a pole: d-dimensional Dirac algebra produces such terms.

## Reduction and evaluation

- One loop: Passarino-Veltman reduction to the scalar integrals A0, B0, C0,
  D0. Of these only A0 and B0 are UV divergent. The reduction divides by Gram
  determinants: where one nearly vanishes the result is numerically unstable,
  and the cure is a library built for it (Collier), not more digits.
- One-loop libraries: LoopTools, Collier, QCDLoop, OneLOop. Compare two at one
  point when the finite part matters.
- Beyond one loop: integration-by-parts reduction to master integrals (FIRE,
  Kira, LiteRed, Reduze), then the masters from differential equations, or
  numerically with pySecDec or FIESTA (sector decomposition) or AMFlow.
  A numerical master has an integration error: report it.
- Polylogarithms: `mpmath.polylog`; GiNaC for multiple polylogarithms.
- Reductions can need tens of GB and hours: check the machine first.

## Poles and imaginary parts

- UV poles go into renormalisation. Soft and collinear poles (up to 1/ε² per
  loop) cancel against real emission or are absorbed into parton
  distributions. Keep them labelled, ε_UV and ε_IR, until that is done.
- A scaleless integral vanishes in dimensional regularisation because its UV
  and infrared poles cancel: ∫ d^dk/(2π)^d 1/k⁴ = i/(16π²) (1/ε_UV - 1/ε_IR).
  Setting it to zero silently moves a pole from one kind to the other.
- Above a threshold the imaginary part is fixed by the iε:
  ln(-s - iε) = ln s - iπ for s > 0. Check its sign against the optical
  theorem or a library value.
- With i/(16π²) B0 = μ^{2ε} ∫ d^dk/(2π)^d 1/[(k² - m1²)((k+p)² - m2²)]:
  B0 = 1/ε - γE + ln 4π - ∫₀¹ dx ln[(x m1² + (1-x) m2² - x(1-x) p² - iε)/μ²].
  So MS-bar B0(0; m, m) = -ln(m²/μ²), with no +1; B0 rises as ln μ²; and
  Im B0 = +π λ^{1/2}(p², m1², m2²)/p² above threshold. Split the x integral
  at the zeros of the argument: quadrature across them misses narrow pieces.

## Check before reporting

- Conventions written: d, measure, μ, scheme, the library's normalisation.
- UV poles cancel after renormalisation, or equal the known counterterm;
  infrared poles have the universal form, or cancel against the real part.
- The μ dependence of the renormalised result is compensated by the running
  coupling at the order worked (`qft-renormalisation-group`).
- Numbers: agreement with a library at a Euclidean point (all invariants
  negative, no thresholds), then at a physical point with its imaginary part.
- Limits: a mass to zero, a mass to infinity (decoupling), symmetry under
  exchange of masses, independence of the gauge parameter.
- Output of FORM, FeynCalc or a reduction code is reported only from a run
  that happened (`qft-computer-algebra`).

## Related

- Skills here: `qft-computer-algebra`, `qft-amplitudes`,
  `qft-renormalisation-group`, `derivation-checks`, `numerical-methods`,
  `hep-literature-and-data`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `get-available-resources`.
