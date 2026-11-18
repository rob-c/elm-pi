---
name: hep-jets
description: "Jets - anti-kT and sequential recombination, IRC safety, FastJet, pile-up mitigation, energy scale and resolution, b-tagging working points and scale factors, substructure, truth matching, overlaps."
disable-model-invocation: true
---

# Jets

What goes wrong: jets compared across different algorithms, radii or inputs;
cuts applied before calibration; tagging scale factors for another working
point, or none; and "matching" to partons treated as unambiguous.

## A jet is a definition

State all five: the inputs (particle-flow objects, calorimeter clusters,
tracks, or stable generated particles - with or without neutrinos and muons),
the algorithm, the radius R, the recombination scheme (four-vector sum unless
said), and the minimum p_T.

Sequential recombination: d(ij) = min(pTi^(2p), pTj^(2p)) ΔR(ij)²/R²,
d(iB) = pTi^(2p); p = 1 is kT, p = 0 Cambridge/Aachen, p = -1 anti-kT.
Here ΔR² = (yᵢ - yⱼ)² + (φᵢ - φⱼ)² with rapidity y = ½ ln((E + p_z)/(E - p_z)),
not pseudorapidity η (they differ for massive hadrons and for every merged
object), and Δφ wrapped into (-π, π]. A jet's p_T, y and mass come from its
summed four-momentum (E-scheme).
Anti-kT gives regular, cone-like jets and is the LHC default (R = 0.4; 0.8
or 1.0 for boosted objects); Cambridge/Aachen reclusters for substructure.

Infrared and collinear (IRC) safety: an observable must not change when a
soft particle is added or a particle splits collinearly, or a fixed-order
prediction for it means nothing. The algorithms above are safe; constituent
counts and many tagger inputs are not - label them.

## FastJet

C++: `JetDefinition jd(antikt_algorithm, 0.4); ClusterSequence cs(particles, jd);`
then `sorted_by_pt(cs.inclusive_jets(20.0))`; the `ClusterSequence` must
outlive its jets. Python: the scikit-hep `fastjet` package. Without either,
the algorithm above is thirty lines: write it; a cone is not it.

## Pile-up

Extra collisions add about ρ × area to a jet. Remedies: area-median
subtraction (p_T - ρA), charged-hadron subtraction, PUPPI, and a
track-vertex cut against pile-up jets inside the tracker.

## Calibration and its uncertainties

- Use the experiment's calibration for exactly this jet collection, software
  release and data period; data and simulation get different steps. Cut after
  it, not before.
- Energy scale (JES): many components (in-situ balance, flavour, pile-up,
  η intercalibration). Shift the four-momenta, then redo
  the selection and recompute missing momentum from the shifted jets.
- Energy resolution (JER): data are worse than simulation, so simulated jets
  are smeared. With a matched generated jet: p_T → p_T(gen) + s (p_T -
  p_T(gen)). Without: multiply by 1 + N(0, σ) √(max(s² - 1, 0)); s is the
  data-to-simulation resolution ratio, σ the relative resolution. Seed the
  random numbers per event so reruns agree.

## Flavour tagging

- A working point is a cut on the tagger score, defined by b efficiency or
  light-jet mistag rate on a reference sample. Record tagger, version and
  working point: scale factors belong to exactly that combination.
- Scale factors depend on p_T, η and true flavour (b, c, light, labelled from
  hadrons). Event weight: Π over tagged jets of SF × Π over untagged of
  (1 - SF ε)/(1 - ε), ε being the simulation efficiency measured in your own
  sample and selection.

## Substructure

- Soft drop: recluster with Cambridge/Aachen, undo the last merge, drop the
  softer branch unless min(p_T1, p_T2)/(p_T1 + p_T2) > z_cut (ΔR12/R)^β, and
  repeat on the harder one. β = 0, z_cut = 0.1 is the common choice.
- N-subjettiness (angular exponent 1): τN = Σ p_Tk min(ΔR(1,k), ..., ΔR(N,k))
  / (R Σ p_Tk). Ratios τ21 and τ32 pick out two- and three-prong jets.

## Matching and overlaps

- Reconstructed to particle-level jet: nearest in ΔR inside a fixed cone,
  one to one; give the matched fraction. Response = p_T(reco)/p_T(particle).
- Flavour comes from hadrons associated with the jet. Parton matching is
  ambiguous beyond leading order.
- An electron is also reconstructed as a jet: remove jets and leptons that
  overlap in the analysis's documented order (`hep-event-selection`).

## Check before reporting

- The five-item definition and the calibration version; cuts after it.
- Scale and resolution variations carried through missing momentum and cuts.
- Tagger, working point, scale-factor set, source of ε; yields before and
  after the weights.
- For theory comparisons: an IRC-safe observable, the same algorithm and R,
  and a stated particle level (`hep-unfolding`).

## Related

- Skills here: `hep-kinematics`, `hep-event-selection`, `hep-systematics`,
  `hep-efficiency-measurement`, `hep-ml-classifiers`,
  `hep-detector-performance`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `torch-geometric`, `matplotlib`.
