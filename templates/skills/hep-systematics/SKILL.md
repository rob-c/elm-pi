---
name: hep-systematics
description: "Systematic uncertainties in a collider analysis - the inventory, plus and minus one sigma templates, shape against normalisation, correlations, one-sided and two-point variations, smoothing, pruning, the breakdown."
disable-model-invocation: true
---

# Systematic uncertainties in a HEP analysis

What goes wrong: a source counted twice, or a correlation left out;
statistical noise in a variation booked as a systematic effect; a one-sided or
two-point variation symmetrised without saying so; and a cross-check that
disagreed turned into one more number in the table.

## Inventory

For each source write down: what is varied, by how much and on whose
authority, which samples and regions it touches, whether it moves shape,
normalisation or both, and what it is correlated with.

- Experimental: luminosity; pile-up reweighting; trigger, reconstruction,
  identification and isolation efficiencies; energy and momentum scale and
  resolution of leptons, photons and jets; flavour tagging;
  misidentified-object backgrounds.
- Theory and modelling: renormalisation and factorisation scales (each by 2
  and ½, without the two opposite combinations: the seven-point envelope); PDF by the set's own prescription and αs
  (`qcd-parton-distributions`); parton shower and hadronisation; matching and
  merging; initial- and final-state radiation; cross-section normalisations.
- Of the method: limited simulation statistics; control-region statistics;
  non-closure of a data-driven estimate; unfolding bias.

## Building a variation

1. Vary the source by ±1σ where it enters (the calibration, the weight) and
   redo the whole selection: events migrate across thresholds. Do not rescale
   the final histogram by a guessed factor.
2. Separate normalisation (ratio of integrals) from shape (the variation
   rescaled to the nominal integral) when the fit treats them separately. A
   background whose normalisation floats keeps only its shape and its
   region-to-region extrapolation.
3. Prefer variations made by reweighting the same events.
4. Two-point comparisons (generator A against B) have no ±1σ. By convention
   the full difference is taken as one sigma and symmetrised: say so.
5. One-sided variations (extra resolution smearing): say how they were
   symmetrised. Up and down moving the same way in a bin is noise or a real
   non-linearity: find out which.
6. Noise: smooth (wider bins, a fitted ratio) or prune (drop a normalisation
   effect below a stated threshold, and a shape with no significant bin), by
   one rule applied to every source and written down.
7. Limited simulation statistics: per-bin Σw², as Barlow-Beeston terms (one
   per bin for the summed background). Merge bins with a large error.

## Correlations

- One source is one nuisance parameter in every sample, region and channel it
  touches. Different data-taking periods are usually partly correlated: follow
  the calibration's own split into correlated and uncorrelated parts.
- Do not count twice: a scale-factor uncertainty that already contains the
  generator comparison; scale variations entered both as a cross-section
  uncertainty and as a normalisation-changing template.

## The table

- No fit: per source the shift of the result up and down; independent sources
  in quadrature, correlated ones with their covariance
  (`uncertainty-propagation`). For a ratio or transfer factor, recompute the
  ratio in each variation (common shifts cancel). Simulation statistics
  (√Σw²) is a systematic source, not the "stat" of x ± stat ± syst - that is
  the data's. It goes inside every systematic total, the transfer factor's
  as much as a yield's: for SR/CR both regions' relative errors, in
  quadrature with the rest. Luminosity and theory apart where the
  field does.
- Profile-likelihood fit: fix a group of parameters at their fitted values
  and take σ(group) = √(σ(total)² - σ(group fixed)²). The groups do not add up
  to the total, because of correlations: say so. See `hep-likelihood-limits`
  for pulls, constraints and impacts.

## Check before reporting

- A table: source, size, shape or normalisation, correlated with what, origin
  of the ±1σ.
- Every up/down-over-nominal ratio was looked at; none is mostly noise.
- Dominant sources named; data statistics apart from the systematic total,
  which contains simulation statistics.
- Symmetrisation, smoothing and pruning rules are stated.
- Cross-checks are reported as cross-checks. One that fails is a problem to
  understand, not an uncertainty to add.

## Related

- Skills here: `uncertainty-propagation`, `statistics-and-significance`,
  `hep-likelihood-limits`, `hep-event-generators`, `hep-jets`,
  `hep-efficiency-measurement`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `uncertainty-and-units`, `statistical-analysis`, `matplotlib`.
