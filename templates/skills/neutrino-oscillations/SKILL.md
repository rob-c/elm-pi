---
name: neutrino-oscillations
description: "Neutrino oscillation calculations and analyses - two- and three-flavour probabilities, PMNS, mass ordering, matter effects, event rates, near/far ratios, systematics, sensitivities."
disable-model-invocation: true
---

# Neutrino oscillations

The recurring errors: the factor 1.267 used with the wrong units; the
two-flavour formula used where three-flavour interference or matter effects
matter; and oscillation parameters quoted from memory instead of from a
named global fit.

## Vacuum probabilities

- **Two flavours.** P(α → β) = sin²2θ sin²(1.267 Δm² L / E) with Δm² in eV²,
  L in km, E in GeV (equally L in m, E in MeV); survival is one minus that.
  First maximum at L/E = 1.24/Δm²; oscillation length 2.48 E/Δm².
- **Three flavours.** With Δ(ij) = 1.267 Δm²(ij) L/E and Δm²(ij) = mᵢ² - mⱼ²,
  P(α → β) = δ(αβ) - 4 Σ Re[U(αi) U*(βi) U*(αj) U(βj)] sin²Δ(ij)
  + 2 Σ Im[U(αi) U*(βi) U*(αj) U(βj)] sin 2Δ(ij), sums over i > j.
  Antineutrinos: U → U*, which flips the sign of the Im term. Evaluate it
  numerically from the matrix; do not expand it by hand.
- **PMNS.** Three angles θ12, θ13, θ23 and one phase δ in the standard
  parametrisation (Majorana phases do not affect oscillations). Two
  independent splittings: Δm²21, and Δm²31 or Δm²32, whose sign is the mass
  ordering (normal: m3 heaviest). Say which of the two you use - experiments
  also quote effective ones.
- **Parameter values** come from a named global fit (NuFIT, or the PDG
  review) with its version, looked up (`hep-literature-and-data`).

## Matter effects

- Electron neutrinos gain a potential √2 GF Nₑ in matter, of opposite sign
  for antineutrinos. In two flavours at constant density, with
  a = 2√2 GF Nₑ E / Δm²:
  sin²2θ(m) = sin²2θ / [(cos 2θ - a)² + sin²2θ], and Δm² is multiplied by
  the square root of that bracket. Resonance at a = cos 2θ.
- Numerically 2√2 GF Nₑ E = 1.52 × 10⁻⁴ eV² × Yₑ ρ[g/cm³] E[GeV], with Yₑ
  the electron fraction (about 0.5 in rock).
- The effect enhances neutrinos for normal ordering and antineutrinos for
  inverted: that is how the ordering is measured, and it mimics CP
  violation, so it must be in any long-baseline calculation. For varying
  density integrate numerically with an Earth model (nuSQuIDS, Prob3++,
  GLoBES).

## From probability to events

- N(reconstructed E) = targets × exposure × ∫ flux × cross section ×
  P × efficiency × energy response dE. Keep the units of each factor in
  view (flux per proton on target per cm², exposure in kt yr).
- Average P over the energy resolution and the size of source and detector:
  fast oscillations average to ½ sin²2θ, and a dip narrower than the
  resolution disappears.
- A near/far ratio cancels flux and cross section only to first order: the
  two detectors see different fluxes (line source against point source) and
  have different acceptance. Extrapolate with simulation, and say what
  cancels.
- Energy reconstruction from lepton kinematics assumes quasi-elastic
  scattering on a nucleon at rest and is biased by nuclear effects;
  calorimetric sums miss neutrons. Interaction-model systematics come from
  comparing generators (GENIE, NEUT, NuWro); flux systematics from
  hadron-production data.

## Sensitivities

Build an Asimov dataset at the assumed true parameters; Δχ² between each
tested point and the best fit, minimised over nuisance parameters and the
other oscillation parameters (octant and ordering included). √Δχ² is a
number of σ only where Wilks' theorem holds - not for the mass ordering, at
physical boundaries, or for the cyclic phase: use pseudo-experiments there
(`rare-event-searches`, `statistics-and-significance`).

## Check before reporting

- Units of L, E and Δm²; neutrino or antineutrino; which Δm² and ordering.
- The parameter set with its source and version.
- Probabilities lie in [0, 1] and sum to 1 over final flavours.
- The matter result returns to vacuum as the density goes to zero.
- Density profile, energy resolution and binning stated.

## Related

- Skills here: `numerical-methods`, `hep-likelihood-limits`,
  `statistics-and-significance`, `hep-systematics`, `hep-event-generators`,
  `hep-literature-and-data`, `rare-event-searches`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `uncertainty-and-units`, `matplotlib`.
