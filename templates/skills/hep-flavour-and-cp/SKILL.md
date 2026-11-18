---
name: hep-flavour-and-cp
description: "Flavour physics and CP-violation measurements - CKM, neutral-meson mixing, time-dependent asymmetries, flavour tagging, decay-time resolution and acceptance, Dalitz and angular analyses, normalisation channels."
disable-model-invocation: true
---

# Flavour physics and CP violation

Results here go wrong through conventions (C against A = -C, the sign of S,
which angle is called what), through dilution left out (mistag and decay-time
resolution shrink the measured asymmetry), and through efficiencies assumed
to cancel in a ratio of channels that are not alike.

## CKM

- Unitarity of the first and third columns gives the triangle
  V_ud V_ub* + V_cd V_cb* + V_td V_tb* = 0, with
  β = arg(-V_cd V_cb* / V_td V_tb*), γ = arg(-V_ud V_ub* / V_cd V_cb*),
  α = arg(-V_td V_tb* / V_ud V_ub*); Belle calls them φ1, φ3, φ2.
- Element magnitudes, angles, lifetimes, mixing frequencies and averages
  come from the PDG and HFLAV, looked up with their edition
  (`hep-literature-and-data`), never from memory.

## Mixing and time-dependent CP violation

- Mass eigenstates differ by Δm and ΔΓ; x = Δm/Γ, y = ΔΓ/(2Γ). The sign
  convention of ΔΓ varies: state it.
- For a CP eigenstate f and negligible ΔΓ (the B⁰):
  A(t) = [Γ(B̄⁰ → f) - Γ(B⁰ → f)] / [sum] = S sin(Δm t) - C cos(Δm t),
  with λ = (q/p)(Ā/A), S = 2 Im λ / (1 + |λ|²), C = (1 - |λ|²)/(1 + |λ|²).
  BaBar and LHCb quote C; Belle quotes A = -C. For B⁰ → J/ψ K0S, a CP-odd
  final state, S = sin 2β and C is close to zero.
- With sizeable ΔΓ (the B_s) the denominator gains cosh and sinh terms in
  ΔΓ t/2: use the full expression.
- Three kinds: in decay (|Ā/A| ≠ 1), in mixing (|q/p| ≠ 1), and in the
  interference between them.

## What dilutes a measured asymmetry

- **Tagging.** Efficiency ε, mistag fraction ω, dilution D = 1 - 2ω: the
  measured amplitude is D times the true one, and the statistical power is
  the effective tagging efficiency ε D² (summed over categories). Calibrate
  ω on flavour-specific control channels.
- **Decay-time resolution** σ(t) multiplies the oscillation amplitude by
  exp(-Δm² σ(t)² / 2): decisive for the fast B_s oscillation.
- **Decay-time acceptance.** Displacement triggers and cuts remove short
  decay times; model it from a control channel or validated simulation.
- **Production and detection asymmetries** add to a raw charge asymmetry:
  to first order A(raw) = A(CP) + A(prod) + A(det). Remove them with control
  channels, or measure a difference of asymmetries in which they cancel.

## Multibody decays

- **Dalitz plots.** Three-body phase space is flat in (m²₁₂, m²₂₃); structure
  is dynamics. An isobar model (Breit-Wigners with barrier and angular
  factors) is not unitary for broad overlapping S-waves: use a K-matrix or a
  dedicated S-wave model there. Fit fractions need not sum to 100%. Take
  the efficiency over the plot from simulation, background from sidebands,
  scan many starting points for other minima, and quote a model systematic
  from alternative models.
- **Angular analyses.** Define the helicity angles explicitly - conventions
  differ between experiments and between particle and antiparticle - and
  correct for angular acceptance.

## Branching fractions

B(signal) = B(norm) × (N(sig)/N(norm)) × (ε(norm)/ε(sig)), times a ratio of
production fractions when the parent hadrons differ. Choose a normalisation
channel with the same topology and trigger, so that systematics cancel;
quote the uncertainty from B(norm) separately. Keep the signal region, or
the CP parameter (a hidden offset), blind until selection and systematics
are frozen.

## Check before reporting

- Conventions: S and C (or A), angle names, sign of ΔΓ, helicity angles.
- Dilution, resolution and acceptance are in the fit; tagging calibration
  named.
- External inputs with source and edition.
- Fit validated on pseudo-experiments (pulls) and on a control channel with
  a known answer.
- Other likelihood minima searched for.

## Related

- Skills here: `data-fitting`, `hep-roofit-models`,
  `hep-particle-identification`, `hep-efficiency-measurement`,
  `hep-systematics`, `hep-literature-and-data`, `physical-constants`,
  `effective-field-theory`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `uncertainty-and-units`, `matplotlib`.
