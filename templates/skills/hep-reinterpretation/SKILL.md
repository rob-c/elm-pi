---
name: hep-reinterpretation
description: "Reinterpreting published collider results for another model - HEPData, full likelihoods, simplified models, Rivet, MadAnalysis 5, CheckMATE, SModelS, Contur; validating against the published limit."
disable-model-invocation: true
---

# Reinterpreting published results

A recast is wrong in three typical ways: it was never validated against the
analysis's own benchmark, so its efficiencies are off by an unknown factor;
signal regions that overlap or share systematics are combined as if
independent; or a simplified-model limit is applied to a model whose
topology or kinematics it does not cover.

## Choose the route by what the experiment published

1. **A full statistical model** on HEPData (a pyhf JSON workspace, or
   Combine datacards): the best case. Replace the signal yields per region
   by yours (a pyhf patch) and rerun the fit: every nuisance parameter and
   correlation is the experiment's own.
2. **A simplified likelihood**: background yields with a covariance matrix
   across signal regions. It allows a proper combination.
3. **Only observed and expected counts per region**: a single-bin limit per
   region. Regions cannot be combined without their correlations.
4. **Upper-limit or efficiency maps for simplified models**: SModelS
   decomposes a model into simplified topologies and compares cross section
   times branching fraction with the maps. Fast and conservative, and valid
   only where topology, mass pattern and prompt decays match the map's
   assumptions; topologies with no map are simply not constrained.
5. **Unfolded fiducial measurements**: Rivet routines give particle-level
   predictions to set against HEPData tables, and Contur turns agreement
   with Standard Model measurements into exclusions. Shapes need the
   published covariance.

**Yield per region: N = 1000 × σ[pb] × L[fb⁻¹] × BRⁿ × (A×ε)** - the 1000
because 1 pb is 1000 fb - with n the number of decays that must match the
map's topology (2 for a pair). A point near the published contour has N
near S95; N of 0.01 is the missing 1000.

**Several signal regions and no correlations (routes 3 and 4): one region
per model point.** In every region compute r(exp) = N(signal) / S95(expected);
take the region with the largest r(exp) and quote r = N(signal) /
S95(observed) in that region; excluded if r > 1. Never the largest observed
r, nor "excluded if any region excludes": a region that fluctuated low then
excludes what it cannot see.

## Recasting a search by simulation

1. Generate the signal (`bsm-model-tools`, `hep-event-generators`) with
   enough events that the efficiency in each signal region has a small
   statistical error, and normalise to a cross section at the order the
   analysis used.
2. Detector response: the validated card or efficiency functions shipped
   with the recast (MadAnalysis 5's public analysis database, CheckMATE,
   Rivet's smearing), or the experiment's published efficiencies
   (`hep-detector-simulation`).
3. Implement the selection from the paper and its auxiliary material:
   object definitions, overlap removal, isolation, trigger, the exact
   variables. Published cut flows and code snippets are there for this.
4. **Validate before anything else**: reproduce the published cut flow for
   a benchmark point and then the published exclusion contour. Record the
   disagreement step by step. No validation, no limit.
5. Statistics from routes 1 to 3 (`hep-likelihood-limits`), CLs at 95%, with
   the signal's scale, PDF and simulation-statistics uncertainties included
   or stated.
6. Signal contamination: if the new signal populates the control regions,
   the published background estimate does not hold for it. Check those
   yields.

## What a recast cannot do

- Long-lived particles, displaced vertices, disappearing tracks and heavy
  stable charged particles: only with efficiency maps the experiment
  published for them, inside the grid they cover.
- Networks that are not public, taggers that are not parametrised, fake or
  non-prompt backgrounds, timing.
- A limit outside the mass, lifetime or coupling range that was validated.

## Check before reporting

- Which route, and what was public for this analysis.
- Validation: benchmark cut flow and limit against the published ones.
- How regions were chosen or combined, and on what correlation information.
- Signal cross section: order, source, uncertainty.
- Analysis, HEPData record and tools cited with versions.
- Control-region contamination checked.
- Uncovered topologies listed.

## Related

- Skills here: `hep-likelihood-limits`, `hep-event-generators`,
  `hep-detector-simulation`, `bsm-model-tools`, `hep-event-selection`,
  `hep-literature-and-data`, `effective-field-theory`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `matplotlib`, `scientific-visualization`, `citation-management`.
