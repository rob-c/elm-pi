---
name: hep-cross-section-measurement
description: "Measuring a cross section - yield, background, efficiency, acceptance and luminosity; fiducial versus total, differential bins, pile-up reweighting, units, and comparison with theory."
disable-model-invocation: true
---

# Measuring a cross section

The usual errors: efficiency and acceptance defined against different
denominators, so events are counted twice or not at all; a total cross
section quoted where only a fiducial one was measured; and a factor of 1000
between pb and fb, or a luminosity that is not the dataset's.

## The formula, and what each factor means

σ = (N - B) / (L · ε · A · BR)

- **N** observed events, **B** the estimated background
  (`hep-background-estimation`).
- **L** the integrated luminosity of exactly the runs and trigger used: for
  a trigger with prescale p, the recorded luminosity divided by p.
- **A** acceptance: the fraction of signal events generated inside the
  fiducial phase space. Particle level, and theory-dependent.
- **ε** efficiency: the fraction of events inside the fiducial phase space
  that are triggered, reconstructed and selected, corrected by
  data-to-simulation scale factors (`hep-efficiency-measurement`).
- **BR** the branching fraction, with its source, when a production cross
  section is quoted from one decay channel.

Fiducial first: σ(fid) = (N - B) / (L · C), with C = all selected
reconstructed events / particle-level events in the fiducial region. The
numerator is every selected event, also those outside the fiducial region
at particle level (the data contain them too), not "selected and fiducial". It is the measurement. The total,
σ(fid) / (A · BR), adds the theory uncertainty of the extrapolation (PDF,
scales, parton shower) - quote it separately. Define the fiducial region with
stable particles (cτ above 10 mm), leptons dressed with nearby photons, and
particle-level jets, and write the definition down.

## Units

- 1 b = 10⁻²⁴ cm², 1 pb = 10⁻³⁶ cm², 1 fb = 10⁻³⁹ cm²; 1 fb⁻¹ = 1000 pb⁻¹.
- N = σ L: 1 pb × 1 fb⁻¹ = 1000 events.
- Natural units: (ħc)² = 0.3894 mb GeV², so 1 GeV⁻² = 0.3894 mb.
- An instantaneous luminosity of 10³⁴ cm⁻² s⁻¹ is 10 nb⁻¹ per second.

## Differential cross sections

dσ/dx in bin i is the unfolded yield over L and the bin width Δx. Divide by
the width; correct migrations by unfolding (`hep-unfolding`), bin-by-bin
factors only where purity is high; publish the covariance matrix. A
normalised shape (1/σ)(dσ/dx) cancels the luminosity and much else, but the
bins are then correlated by the sum constraint.

## Luminosity and pile-up

- Take L and its uncertainty from the experiment's luminosity calibration
  for that data-taking period (per cent level at the LHC); it is fully
  correlated between channels using the same data.
- A prescaled trigger sees the prescaled luminosity, not the delivered one.
- Pile-up reweighting matches the simulation's distribution of interactions
  per crossing to the data's: μ = per-bunch luminosity × inelastic cross
  section / revolution frequency. Vary the inelastic cross section as a
  systematic, and check the weights keep the sample's normalisation.

## Uncertainties

Quote them apart: σ = value ± (stat) ± (syst) ± (lumi), plus the
extrapolation's for a total (A and BR; not also inside its syst). The
relative statistical one is √N/(N - B), not 1/√(N - B). Propagate with correlations
(`uncertainty-propagation`), or fit a signal strength μ = σ/σ(theory) with
nuisance parameters (`hep-likelihood-limits`) and convert.

## Comparing with theory

State the order (LO, NLO, NNLO, resummation, electroweak corrections), PDF
set, αs, scales and how they were varied, masses, and that the prediction
uses the same fiducial definition (`qcd-parton-distributions`). Ratios (W/Z,
two energies, e/μ) cancel luminosity and many systematics: say which
uncertainties were taken as correlated.

## Check before reporting

- ε and A share one fiducial definition, stated at particle level.
- Units of σ and L; N = σ L ε A reproduces the yield.
- Luminosity matches the good-run list and trigger (prescales).
- Background and its uncertainty; scale factors applied.
- Result with separate stat, syst and lumi; theory comparison's settings.

## Related

- Skills here: `hep-event-selection`, `hep-background-estimation`,
  `hep-efficiency-measurement`, `hep-unfolding`, `hep-systematics`,
  `hep-likelihood-limits`, `qcd-parton-distributions`,
  `uncertainty-propagation`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `uncertainty-and-units`, `matplotlib`.
