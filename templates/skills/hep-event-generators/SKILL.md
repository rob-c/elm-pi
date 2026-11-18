---
name: hep-event-generators
description: "Monte Carlo event generation - matrix element plus parton shower, LHE and HepMC, matching and merging, weights and negative weights, sample normalisation, scale and PDF variations, seeds, Rivet validation."
disable-model-invocation: true
---

# Event generators

What goes wrong: a weighted sample normalised by its number of events, or with
a cross-section missing the filter efficiency or a branching ratio; jets
counted twice between matrix element and shower, or events twice between
overlapping samples; variation weights picked by position; and one seed
reused for "independent" jobs.

## The chain

1. Hard process at fixed order (LO or NLO): MadGraph5_aMC@NLO, POWHEG-BOX,
   Sherpa, with PDFs through LHAPDF.
2. Parton shower, hadronisation, underlying event and decays: Pythia 8,
   Herwig 7 or Sherpa's own; EvtGen, Photos and Tauola for decays and QED
   radiation.
3. Detector simulation: `hep-detector-simulation`.

Formats: LHE (parton level, text; `pylhe`) and HepMC (the full record;
`pyhepmc`). In HepMC, status 1 is a final-state particle, 2 a decayed one,
4 a beam particle; other codes are generator-specific.

## Matching and merging

- NLO with a shower needs matching, or the first emission is counted twice:
  MC@NLO (a fraction of events get negative weights) or POWHEG.
- Several jet multiplicities need merging at a merging scale: MLM or CKKW-L
  at LO, FxFx or MEPS@NLO at NLO. Differential jet rates must be smooth
  across the scale; use the cross-section after merging.
- An inclusive sample overlaps slices of itself (in HT, jet multiplicity, a
  filter): cut the inclusive one at generator level where the slices begin.
- Four- and five-flavour-scheme samples of one process overlap in
  heavy-flavour final states: remove the overlap by a documented rule.

## Normalisation

Weight of an event for luminosity L: w = σ L w(gen) / Σw(gen). With unequal
or negative weights the number of events is the wrong denominator, and the
statistical power is N(eff) = (Σw)²/Σw².

σ and Σw must describe the same set of events. The usual pair: Σw over the
events the generator wrote (after its filter, before any later skim - a
skimmed file's own weights sum to too little), with σ = the generator's
cross-section × the filter efficiency × the branching ratios of forced
decays × a k-factor. If Σw is instead over everything generated before the
filter, leave the filter efficiency out. Never both, never neither.
MadGraph and Sherpa report pb; Pythia 8's
`sigmaGen()` is in mb (1 mb = 10⁹ pb).

- A k-factor (higher-order over generated-order cross-section, in the same
  phase space) corrects the rate only; shapes stay at the generated order.
- Generator cuts sit well below the analysis cuts: shower and detector move
  events across them. Check nothing is sculpted near the cut.

## Variations

- Scales: weights for μR and μF at ½, 1 and 2 times the central value, and
  the seven-point envelope (without the two opposite combinations). Shower
  scales are varied separately.
- PDFs: member weights combined by the set's own rule
  (`qcd-parton-distributions`), with αs varied consistently.
- Find weights by the names in the file header, never by index: the order
  changes between versions.
- Say whether a variation is normalised by its own sum of weights (shape and
  acceptance only) or by the nominal sum (rate change included).
- Shower and hadronisation: a second generator (two-point,
  `hep-systematics`) and tune variations.

## Running

- Every job its own recorded seed. The same seed and settings give the same
  events: reproducible, and duplicates if repeated by accident. Pythia 8:
  `Random:setSeed = on`, `Random:seed = 12345`.
- Keep with the output: generator versions, cards or settings, PDF set, tune,
  masses and widths, flavour scheme, cuts, events generated, and Σw.
- Generate until the effective luminosity N(eff)/σ is well above the data's.
- Forced decays keep spin correlations (MadSpin, or the generator's own).

## Validation

Compare σ with a reference (`hep-literature-and-data`) and basic
distributions with a trusted sample or a Rivet analysis. Check momentum and
charge conservation in a few events, and the weights for outliers.

## Check before reporting

- σ with its order and source, filter efficiency, branching ratios, k-factor,
  which events Σw is over, and the luminosity.
- Matching or merging scheme and scale; overlap removal between samples.
- Variations: which, how normalised, how combined.
- Distinct seeds; versions and cards kept.
- Validation plots or the Rivet comparison.

## Related

- Skills here: `hep-systematics`, `hep-detector-simulation`,
  `hep-cross-section-measurement`, `qcd-parton-distributions`,
  `qft-phase-space`, `hep-data-formats`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `get-available-resources`, `matplotlib`.
