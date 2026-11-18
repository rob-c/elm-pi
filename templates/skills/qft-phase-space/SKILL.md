---
name: qft-phase-space
description: "From a squared matrix element to a decay rate or cross section - Lorentz-invariant phase space, two- and three-body formulae, flux and symmetry factors, Monte Carlo integration, GeV to barn conversion."
disable-model-invocation: true
---

# Phase space, decay rates and cross sections

The amplitude is usually right and the rate wrong: a missing 2π, a flux factor
taken in the wrong frame, identical particles counted twice, an average left
out, or GeV⁻² never converted to barns. Every formula below assumes spinors
and states normalised to 2E particles per unit volume (ū u = 2m), and ⟨|M|²⟩
summed over final and averaged over initial spins and colours
(`qft-amplitudes`).

## Definitions

- dΦn = (2π)⁴ δ⁴(P - Σ p_i) Π d³p_i / ((2π)³ 2E_i); its mass dimension is
  2n - 4.
- Decay, parent at rest: dΓ = ⟨|M|²⟩ dΦn / (2M).
- Scattering: dσ = ⟨|M|²⟩ dΦn / F with F = 4 √((p1·p2)² - m1² m2²)
  = 2 λ^{1/2}(s, m1², m2²), which is 2s for massless beams.
- Källén function: λ(a, b, c) = a² + b² + c² - 2ab - 2bc - 2ca.
- Divide by n! for each set of n identical final-state particles when the
  integral runs over the whole phase space.

## Two bodies

- |p*| = λ^{1/2}(s, m1², m2²) / (2√s) in the centre-of-mass frame, and
  dΦ2 = |p*| dΩ / (16π² √s). Integrated: |p*| / (4π√s), or 1/(8π) massless.
- Decay 1 → 2: Γ = S |p*| ⟨|M|²⟩ / (8π M²) when ⟨|M|²⟩ has no angular
  dependence. S = 1/2 when the two final particles are identical (γγ, ZZ, two
  of one real scalar), 1 otherwise; the same S multiplies a 2 → 2 cross
  section integrated over the whole solid angle.
- 2 → 2: dσ/dΩ = ⟨|M|²⟩ |p_f| / (64π² s |p_i|) in the centre-of-mass frame,
  and dσ/dt = ⟨|M|²⟩ / (16π λ(s, m1², m2²)); λ = s² for massless beams.
- Worked check: the massless e⁺e⁻ → μ⁺μ⁻ square 2e⁴(t² + u²)/s² integrates to
  σ = 4πα²/(3s) = 86.8 nb / (s in GeV²).

## Three bodies and more

- 1 → 3: dΓ = ⟨|M|²⟩ dm12² dm23² / ((2π)³ 32 M³). Uniform phase space is a
  flat Dalitz plot.
- Massless n-body volume, for testing an integrator:
  Φn = (2π)^{4-3n} (π/2)^{n-1} s^{n-2} / ((n-1)! (n-2)!).
- Narrow-width approximation: σ(ab → X → f) ≈ σ(ab → X) × BR(X → f), from
  ∫ ds / ((s - M²)² + M²Γ²) = π/(MΓ). Errors are of order Γ/M; it fails near
  thresholds and where signal and background interfere, and it drops spin
  correlations unless the decay keeps the full matrix element.

## Monte Carlo integration

1. Generate points with weights w: flat n-body by RAMBO or by a chain of
   two-body splittings, or adaptively with VEGAS (the `vegas` package).
2. Estimate: the integral is the mean weight, its error
   √((⟨w²⟩ - ⟨w⟩²)/N). Quote both and N.
3. VEGAS adapts along its axes only: choose variables in which the peaks lie
   along an axis (a Breit-Wigner mapped by s = M² + MΓ tan y, a 1/t pole by
   ln t). Discard the warm-up iterations and check that the rest agree
   (χ² per degree of freedom across iterations near 1).
4. A weighted generator's events must be histogrammed with their weights;
   unweighting keeps an event with probability w/w_max and costs efficiency.
5. Massless t-channel and soft or collinear regions diverge at tree level:
   the cuts that make the number finite are part of the result.
6. Hadron colliders add the convolution with parton distributions
   (`qcd-parton-distributions`); events and showers: `hep-event-generators`.

## Units

(ħc)² = 0.3894 GeV² mb, so 1 GeV⁻² = 0.3894 mb = 3.894 × 10⁸ pb.
ħ = 6.582 × 10⁻²⁵ GeV s turns a width into a lifetime, τ = ħ/Γ. Values to
more digits: `physical-constants`.

## Check before reporting

- Dimensions: σ in GeV⁻² before conversion, Γ in GeV.
- Spin and colour averages, identical-particle factors, the flux factor.
- A known rate reproduced by the same code (the e⁺e⁻ → μ⁺μ⁻ value above, or
  the massless n-body volume).
- Monte Carlo: integral ± error, number of points, a second seed, and
  stability when the cuts or mappings change.
- Which approximations were made: massless limits, narrow width, cuts.

## Related

- Skills here: `qft-amplitudes`, `numerical-methods`, `derivation-checks`,
  `physical-constants`, `qcd-parton-distributions`, `hep-event-generators`,
  `hep-kinematics`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `matplotlib`.
