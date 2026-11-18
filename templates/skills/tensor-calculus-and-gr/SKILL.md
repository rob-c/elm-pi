---
name: tensor-calculus-and-gr
description: "Tensor calculus and general relativity - sign conventions, Christoffel symbols, curvature, geodesics, Einstein's equations, standard metrics, gauge choices in perturbation theory, symbolic tools and their checks."
disable-model-invocation: true
---

# Tensor calculus and general relativity

Three sign conventions (metric signature, Riemann tensor, Einstein equation)
vary between textbooks and programs, and a result that mixes two of them is
wrong by a sign that survives every later step. The other regular faults are
an index summed that should be free, a gauge-dependent quantity compared
across gauges, and units with G = c = 1 never restored.

## Conventions used here - state yours

Signature (-,+,+,+), and
- Γ^ρ_μν = ½ g^{ρσ} (∂_μ g_σν + ∂_ν g_σμ - ∂_σ g_μν);
- R^ρ_σμν = ∂_μ Γ^ρ_νσ - ∂_ν Γ^ρ_μσ + Γ^ρ_μλ Γ^λ_νσ - Γ^ρ_νλ Γ^λ_μσ;
- R_μν = R^ρ_μρν, R = g^{μν} R_μν, G_μν = R_μν - ½ g_μν R;
- G_μν + Λ g_μν = (8πG/c⁴) T_μν.

With these a unit sphere has R = +2. That is the one-line test of what a book
or a program uses: with the opposite Riemann or Ricci definition the sphere
gives -2 and the field equations carry -8πG. Flipping the signature alone
leaves Γ and R_μν unchanged and flips the sign of R.

## Working with components

1. Coordinates, then the metric as a symmetric matrix; invert it.
2. Christoffel symbols, Riemann, Ricci, the scalar, the Einstein tensor -
   simplifying at each stage with the assumptions declared (r > 0, the range
   of θ), or the expressions grow unmanageably.
3. Geodesics: d²x^μ/dτ² + Γ^μ_νρ (dx^ν/dτ)(dx^ρ/dτ) = 0, with
   g_μν u^μ u^ν = -1 (massive) or 0 (null, affine parameter). It is usually
   easier to use the Lagrangian ½ g_μν ẋ^μ ẋ^ν and the conserved ξ_μ u^μ of
   each Killing vector (∇_μ ξ_ν + ∇_ν ξ_μ = 0).
4. Integrating geodesics or field equations numerically: `numerical-methods`.

## Reference results

- Schwarzschild: ds² = -(1 - r_s/r) c² dt² + dr²/(1 - r_s/r) + r² dΩ², with
  r_s = 2GM/c² (2.95 km for a solar mass). Photon sphere at 1.5 r_s, innermost
  stable circular orbit at 3 r_s. Kretschmann scalar 12 r_s²/r⁶.
- FLRW: ds² = -c² dt² + a(t)² [dr²/(1 - k r²) + r² dΩ²];
  H² = 8πGρ/3 - kc²/a² + Λc²/3 and ä/a = -(4πG/3)(ρ + 3p/c²) + Λc²/3.
- Newtonian limit: the time-time metric component is -(1 + 2Φ/c²), with
  ∇²Φ = 4πGρ.
- Counting: Riemann has n²(n² - 1)/12 independent components: 20 in four
  dimensions, 6 in three, 1 in two. The Weyl tensor vanishes in three
  dimensions and the Einstein tensor identically in two.
- Geometric units: mass M corresponds to a length GM/c² (1.48 km for a solar
  mass) and a time GM/c³ (4.93 μs).

## Perturbation theory

- g = background + h, with gauge freedom h_μν → h_μν + ∇_μ ξ_ν + ∇_ν ξ_μ
  (the sign of ξ is itself a convention).
- Harmonic (de Donder) gauge: ∇^μ of the trace-reversed h vanishes;
  transverse-traceless gauge exists only in vacuum.
- Cosmology: the names and signs of the two potentials in Newtonian gauge
  differ between standard references, and synchronous gauge has residual
  freedom. Compare results in one gauge or through gauge-invariant variables,
  and say which reference's convention is used.

## Tools

- SymPy: `sympy.diffgeom` (Christoffel, Riemann and Ricci components from a
  metric) or explicit loops over a `sympy.Matrix`; `sympy.tensor` for
  abstract indices, with limited simplification.
- EinsteinPy's symbolic module and SageManifolds (in SageMath) for component
  work; SageManifolds is the most complete free option.
- xAct (Mathematica: xTensor, xCoba, xPert) and Cadabra2 for abstract tensor
  algebra and perturbation theory.
- Before trusting any of them, compute the unit sphere to learn its sign
  convention. Report tool output only from a run that happened.

## Check before reporting

- Signature and curvature conventions stated; sphere test done for the tool.
- A known solution through the same code: Schwarzschild has R_μν = 0 and the
  Kretschmann scalar above; flat space in curvilinear coordinates has zero
  Riemann tensor.
- Contracted Bianchi identity ∇^μ G_μν = 0, and symmetry of every tensor that
  should be symmetric.
- Free indices match on both sides of every equation.
- Newtonian or weak-field limit recovered; G and c restored and the
  dimensions checked (`derivation-checks`).

## Related

- Skills here: `derivation-checks`, `numerical-methods`,
  `particle-cosmology`, `physical-constants`, `physics-documents`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `astropy`, `matplotlib`.
