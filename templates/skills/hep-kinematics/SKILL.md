---
name: hep-kinematics
description: "Relativistic kinematics for collider and fixed-target work - units, four-vectors, invariant and transverse mass, rapidity and pseudorapidity, boosts, centre-of-mass energy, thresholds, two-body decays, PDG codes."
disable-model-invocation: true
---

# Relativistic kinematics

What goes wrong: MeV mixed with GeV; pseudorapidity used for a massive object
where rapidity was meant; Δφ not wrapped; a four-vector built from
(pt, eta, phi, E) handed to code expecting (pt, eta, phi, m); and fixed-target
√s computed as for a collider.

## Units and conventions

- Natural units, ħ = c = 1: energy, momentum and mass in GeV - or MeV;
  experiments differ, so check a known peak before trusting a file.
  ħc = 197.327 MeV fm; (ħc)² = 0.389379 GeV² mb; ħ = 6.582 × 10⁻²⁵ GeV s.
- Metric (+,-,-,-): p² = E² - |p|² = m². Say so if you use the other sign.
- Collider axes: z along the beam, φ the azimuth around it, θ the polar
  angle; p_T = |p| sin θ.

## Formulae

- Invariant mass of a system: m² = (ΣE)² - |Σp|². For two massless
  particles: m² = 2 p_T1 p_T2 (cosh Δη - cos Δφ).
- Rapidity y = ½ ln((E + p_z)/(E - p_z)); pseudorapidity η = -ln tan(θ/2).
  They coincide only for m = 0. Differences in y are invariant under boosts
  along z; Δη only for massless objects. Say which is used for jets.
- ΔR = √(Δη² + Δφ²), with Δφ wrapped into (-π, π].
- Transverse mass, W → ℓν: mT² = 2 p_T(ℓ) p_T(miss) (1 - cos Δφ); its upper
  edge is at m_W.
- Missing transverse momentum: minus the vector sum of all reconstructed
  transverse momenta. A two-vector: at a hadron collider the longitudinal
  balance is unknown.
- Boost: β = |p|/E, γ = E/m. Along the boost, E' = γ(E - β p∥) and
  p∥' = γ(p∥ - β E). To a system's rest frame, boost by -Σp/ΣE.
- Decay length L = βγ cτ = (p/m) cτ; proper time t = L m / p.
- Two-body decay M → 1 + 2, rest frame:
  |p*| = √((M² - (m1 + m2)²)(M² - (m1 - m2)²)) / (2M),
  E1* = (M² + m1² - m2²) / (2M).
- Centre-of-mass energy. Head-on beams E1, E2, masses negligible:
  √s = 2√(E1 E2). Beam of total energy E on a target at rest:
  s = m_b² + m_t² + 2 E m_t. Threshold for a final state of total mass M_f:
  E = (M_f² - m_b² - m_t²) / (2 m_t); for p p → p p p p̄ that is E = 7 m_p.
- Mandelstam, 1 + 2 → 3 + 4: s = (p1 + p2)², t = (p1 - p3)², u = (p1 - p4)²;
  s + t + u = Σm².
- Partons at a hadron collider, for a system of mass M and rapidity y:
  x1,2 = (M/√s) e^(±y), and ŝ = x1 x2 s.

## Pitfalls

- Name the components when building a four-vector:
  `vector.obj(pt=..., eta=..., phi=..., mass=...)`. Constructors take
  (pt, eta, phi, m), (pt, eta, phi, E) or (px, py, pz, E), and nothing warns
  when the last slot holds the wrong one.
- A mass given to a track is a hypothesis (π, K, p, μ); at low momentum the
  invariant mass depends on it.
- Add four-vectors, then take the mass. Scalar sums (HT = Σ|p_T| of jets) are
  other quantities: define them.
- Wrap Δφ: ((Δφ + π) mod 2π) - π, or the library's `deltaphi`.
- E² - p² for a light, energetic particle cancels in single precision and
  gives negative m². Use double precision or the (pt, eta, phi, m) form, and
  count the cases.
- E is not ET (E sin θ); p is not p_T; |η| < 2.5 is not |y| < 2.5.

## Particle codes (PDG Monte Carlo numbering)

d, u, s, c, b, t are 1-6; e⁻ 11, νe 12, μ⁻ 13, νμ 14, τ⁻ 15, ντ 16; gluon 21,
γ 22, Z 23, W⁺ 24, H 25; π⁺ 211, π⁰ 111, K⁺ 321, K0S 310, K0L 130, p 2212,
n 2112. Antiparticles are negative: e⁺ is -11. Anything else, and every mass:
the `particle` package (`Particle.from_pdgid(13).mass`, in MeV) or
`physical-constants`, not memory.

## Tools

`vector` (NumPy and awkward backends: `.mass`, `.deltaR()`,
`.boostCM_of_p4()`), `particle`, `hepunits` (MeV is 1, GeV is 1000). In ROOT:
`ROOT::Math::PtEtaPhiMVector` and `PxPyPzEVector`; `TLorentzVector` is legacy.

## Check before reporting

- Units on every number and axis; the frame named (laboratory, centre of
  mass, rest frame of X).
- A known resonance or threshold comes out right (Z → μμ near 91.2 GeV).
- Invariants are invariant: the mass is the same before and after a boost.
- Components were named and masses sourced when vectors were built.
- Edge cases counted: wrapped Δφ, negative m².

## Related

- Skills here: `physical-constants`, `derivation-checks`,
  `hep-columnar-analysis`, `hep-root`, `hep-jets`, `qft-phase-space`,
  `nuclear-reaction-kinematics`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `uncertainty-and-units`.
