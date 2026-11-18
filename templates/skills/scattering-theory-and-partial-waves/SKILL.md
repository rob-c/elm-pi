---
name: scattering-theory-and-partial-waves
description: "Quantum scattering calculations - partial waves and phase shifts, cross sections, optical theorem, effective range and scattering length conventions, Breit-Wigner resonances, solving the radial equation, R-matrix."
disable-model-invocation: true
---

# Scattering theory and partial waves

The mistakes: the sign convention of the scattering length assumed; k built
from the wrong mass or energy (nucleon instead of reduced mass, lab instead
of centre-of-mass); the partial-wave sum cut off too early; a numerical
wavefunction matched inside the potential's range; and a resonance claimed
from a bump with no look at the phase.

## Formulae (spinless, central potential, centre-of-mass frame)

- k = √(2μE)/ħ, μ the reduced mass, E the centre-of-mass energy.
  ħ²/(2 m_N) = 20.74 MeV fm², so for two nucleons (μ = m_N/2)
  ħ²/(2μ) = 41.47 MeV fm² and E = E_lab/2. ħc = 197.327 MeV fm.
- f(θ) = Σ (2l+1) f_l P_l(cos θ), f_l = (S_l - 1)/(2ik) = exp(iδ_l) sin δ_l / k,
  S_l = exp(2iδ_l); dσ/dΩ = |f(θ)|².
- Elastic: σ = (4π/k²) Σ (2l+1) sin² δ_l. With absorption, |S_l| < 1:
  σ_el = (π/k²) Σ (2l+1) |1 - S_l|², σ_reac = (π/k²) Σ (2l+1) (1 - |S_l|²).
- Optical theorem: σ_tot = (4π/k) Im f(0). Unitarity limits each partial
  wave to 4π(2l+1)/k² elastic.
- Waves needed: up to l about kR for range R, plus a few. Show the sum has
  converged. 1 fm² = 10 mb.

## Low energy

- Effective-range expansion, s wave: k cot δ0 = -1/a + ½ r k² + ...
  With this sign (usual in nuclear physics) a shallow bound state gives a
  large positive a and a nearly-bound (virtual) state a large negative one;
  a hard sphere has a = R. Much of the particle-physics and lattice
  literature uses the opposite sign. State the convention with every a.
- σ → 4πa² as k → 0 in either convention; δ_l goes as k^(2l+1).
- A shallow bound state has binding energy about ħ²/(2μa²).
- Identical particles: use f(θ) ± f(π - θ). Two unpolarised identical
  spin-½ fermions: dσ/dΩ = ¼ |f(θ) + f(π-θ)|² + ¾ |f(θ) - f(π-θ)|².

## Resonances

- Isolated level: σ(a → b) = (π/k²) g Γa Γb / ((E - Er)² + Γ²/4), with
  g = (2J+1) / ((2s1+1)(2s2+1)). Lifetime ħ/Γ, ħ = 6.582e-22 MeV s.
- A resonance is a phase rising rapidly through π/2 (an anticlockwise
  circle on the Argand plot), on top of any background phase - not just a
  peak, and never a falling phase.
- Near a threshold, or when broad, the widths depend on energy through the
  penetrability; overlapping levels interfere. Then fit with an R-matrix
  (AZURE2 for charged-particle reactions) and check the answer does not
  hang on the channel radius.

## Born approximation

f(θ) = -(2μ/ħ²) (1/q) ∫ r V(r) sin(qr) dr, q = 2k sin(θ/2). For weak
potentials or high energy only; it does not respect unitarity.

## Solving the radial equation

1. u'' + [k² - l(l+1)/r² - (2μ/ħ²) V(r)] u = 0, u(0) = 0, starting as
   r^(l+1).
2. Integrate outwards with Numerov, at least 20 steps per local wavelength
   and finer near a core, to beyond the range of the short-range potential.
3. Match at two radii to cos δ j_l(kr) - sin δ n_l(kr) times kr, using
   `scipy.special.spherical_jn` and `scipy.special.spherical_yn`. With a
   Coulomb potential match to the regular and irregular Coulomb functions,
   mpmath.coulombf() and mpmath.coulombg(): δ is then the nuclear phase on
   top of the Coulomb phase, and the cross section is quoted as a ratio to
   Rutherford, since the Coulomb total diverges.
4. Show δ does not change with step size or matching radius.
5. Reproduce an analytic case first: hard sphere δ0 = -kR; square well
   tan(δ0 + kR) = (k/K) tan(KR), K² = k² + 2μV0/ħ².
6. Non-local potentials: solve the Lippmann-Schwinger equation in momentum
   space on a Gauss-Legendre mesh, subtracting the pole. Coupled waves
   (tensor force): say whether phases are in the Stapp or the
   Blatt-Biedenharn convention.

## Check before reporting

- Frame, μ, and the value of ħ²/(2μ) used; units of k and σ.
- Scattering-length sign convention stated.
- |S_l| = 1 for a real potential, at most 1 with absorption.
- Converged in l, step and matching radius; analytic case reproduced.
- σ → 4πa² at low energy and the optical theorem hold numerically.
- Symmetrisation and spin factors for identical particles.
- A resonance shown by its phase motion.

## Related

- Skills here: `numerical-methods`, `derivation-checks`, `data-fitting`,
  `nuclear-reaction-codes`, `nuclear-reaction-kinematics`,
  `nuclear-astrophysics`, `qft-phase-space`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `matplotlib`, `uncertainty-and-units`.
