---
name: particle-cosmology
description: "Early-universe particle physics - natural-unit conversions, expansion rate and entropy, g*, freeze-out and the Boltzmann equation, relic abundance, N_eff and BBN, baryogenesis conditions, and the standard tools."
disable-model-invocation: true
---

# Particle cosmology

The physics is rarely the problem. The slips are unit conversions between
GeV, kelvin, seconds and centimetres; the Planck mass confused with the
reduced one; g* held constant or confused with the entropy g*s; a freeze-out
formula used outside its assumptions; and cosmological parameters quoted from
memory.

## Units (ħ = c = k_B = 1)

- 1 GeV⁻¹ = 1.973 × 10⁻¹⁴ cm = 6.582 × 10⁻²⁵ s; 1 GeV = 1.160 × 10¹³ K
  = 1.783 × 10⁻²⁴ g.
- 1 GeV⁻² = 3.894 × 10⁻²⁸ cm² = 1.167 × 10⁻¹⁷ cm³/s as σv. Handy:
  1 pb × c = 3.0 × 10⁻²⁶ cm³/s.
- Planck mass M_Pl = G^{-1/2} = 1.221 × 10¹⁹ GeV; the reduced one is
  M_Pl/√(8π) = 2.435 × 10¹⁸ GeV. Say which a formula uses.

## Expansion and entropy

- H² = 8πGρ/3. Radiation: ρ = (π²/30) g* T⁴, so H = 1.66 √g* T²/M_Pl and
  t = 1/(2H), about 2.4 s /√g* × (MeV/T)².
- Entropy density s = (2π²/45) g*s T³, conserved per comoving volume.
- g* counts bosons fully and fermions with 7/8: 106.75 for the whole
  Standard Model, 10.75 between about 1 and 100 MeV, and after e⁺e⁻
  annihilation g* = 3.36 but g*s = 3.91 because neutrinos are colder,
  T_ν = (4/11)^{1/3} T_γ. Around the QCD transition it changes fast: use a
  tabulated g*(T), not a step.
- Today: s0 = 2891 cm⁻³ and ρ_c = 1.054 × 10⁻⁵ h² GeV cm⁻³, hence
  Ω h² = 2.74 × 10⁸ (m/GeV) Y0 for a relic of yield Y0 = n/s.

## Freeze-out

1. Boltzmann equation: dn/dt + 3Hn = -⟨σv⟩ (n² - n_eq²). In Y = n/s and
   x = m/T, with g* constant,
   dY/dx = -(λ/x²)(Y² - Y_eq²), λ = 0.264 (g*s/√g*) M_Pl m ⟨σv⟩,
   and Y_eq = 0.145 (g/g*s) x^{3/2} exp(-x) when non-relativistic.
2. It is stiff while Y tracks Y_eq: use an implicit solver or integrate
   ln Y, starting at x of a few with Y = Y_eq (`numerical-methods`).
3. Rule of thumb, s-wave: Ω h² ≈ 1.07 × 10⁹ GeV⁻¹ x_f / (√g* M_Pl ⟨σv⟩) with
   x_f around 20 to 25, so Ω h² near 0.1 needs ⟨σv⟩ near 3 × 10⁻²⁶ cm³/s.
4. For σv = a + b v² the thermal average is a + 6b/x. The expansion fails
   near resonances and thresholds, and coannihilation changes the answer:
   then use a code's full thermal average.
5. A particle distinct from its antiparticle carries a factor of 2 relative
   to a self-conjugate one for the same ⟨σv⟩. State which case.

The measured abundance and other cosmological parameters come from the
source (`hep-literature-and-data`, PDG reviews), with edition - not memory.

## Radiation, nucleosynthesis, asymmetry

- ρ_rad = ρ_γ [1 + (7/8)(4/11)^{4/3} N_eff], N_eff about 3.044 in the
  Standard Model. A light species that decoupled at T_d adds
  ΔN_eff = (4/7) g (43 / (4 g*s(T_d)))^{4/3} for bosons, times 7/8 for
  fermions: 0.027 for one scalar decoupling above the electroweak scale.
- Nucleosynthesis: neutron-proton freeze-out near T = 0.8 MeV (t about 1 s),
  deuterium forms near 0.07 MeV (about 3 minutes). New physics that changes
  H or injects energy later than about 0.1 s is constrained; codes:
  PArthENoPE, AlterBBN, PRIMAT.
- Baryogenesis needs the three Sakharov conditions: baryon-number violation,
  C and CP violation, and departure from thermal equilibrium.

## Tools

micrOMEGAs and MadDM (relic density and detection rates from a model file:
`bsm-model-tools`), DarkSUSY, CLASS and CAMB for perturbations,
`astropy.cosmology` for distances, ages and H(z). Check a hand-written
solver against one of them on a simple model.

## Check before reporting

- Every conversion written out; which Planck mass; the source of g*(T).
- Solver converged: tolerance halved, starting x varied, result stable.
- Assumptions named: kinetic equilibrium, s-wave or not, no coannihilation,
  self-conjugate or not.
- The rule of thumb and the numerical solution agree to tens of per cent.
- Measured values cited from a source read in this session.

## Related

- Skills here: `numerical-methods`, `physical-constants`,
  `derivation-checks`, `bsm-model-tools`, `qft-phase-space`,
  `tensor-calculus-and-gr`, `rare-event-searches`, `hep-literature-and-data`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `astropy`, `sympy`, `matplotlib`, `uncertainty-and-units`.
