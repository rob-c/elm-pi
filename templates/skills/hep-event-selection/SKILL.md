---
name: hep-event-selection
description: "Selecting collision events - data quality, trigger and its plateau, object definitions, overlap removal, cut flows, signal, control and validation regions, blinding, unbiased optimisation."
disable-model-invocation: true
---

# Event selection, regions and blinding

What goes wrong: cuts tuned on the data of the region where the signal is
sought; a cut flow nobody can reproduce because weights, duplicates or the
trigger were left out; and regions that share events.

**Data first, before any cut or count:**
`n = len(df); df = df.drop_duplicates(['run', 'lumi', 'event']); print(n - len(df), 'duplicate rows dropped')`.
Two primary datasets or trigger streams (a `dataset` column, two files) hold
every event that fired both triggers twice. The selection list you are handed
never names this step; every row of the cut flow, the first included, counts
unique events.

## The order of a selection

1. Data quality (data only): the good-run list or luminosity mask, detector
   flags, event cleaning - after the duplicates above are gone.
2. Trigger: require it, and put the offline threshold on its plateau or apply
   the measured efficiency (`hep-efficiency-measurement`). Match the offline
   object to the trigger object. A prescaled trigger's events carry the
   prescale as a weight.
3. Objects: for each, kinematic acceptance, identification, isolation, and the
   working point. Baseline (loose: for vetoes and overlap removal) and signal
   (tight) definitions are separate lists.
4. Overlap removal between collections in one documented order; the order
   changes the result.
5. Event cuts: multiplicities, vetoes, masses, missing transverse momentum,
   angles, discriminants - calibrations applied first.
6. Weights (simulation): generator weight, pile-up, each scale factor, and
   the normalisation to luminosity. Data have weight 1.

## Cut flow

Per sample, after every cut: raw events, weighted yield with its √Σw² error,
efficiency against the previous cut and against the start. The first row is
all processed events - the denominator of the normalisation. Raw counts are
for debugging and for synchronising with someone else's code (compare lists
of run and event numbers); weighted yields are the physics.

N-1 plots: each cut variable with every other cut applied, signal and
backgrounds overlaid, the cut marked. They show whether a cut sits somewhere
sensible.

## Regions

- Signal region: where the signal is sought. Control region: rich in one
  background, poor in signal, used to normalise or model it. Validation
  region: between the two, not in the fit, tests the extrapolation.
- Regions used together are mutually exclusive: define them by inverted cuts
  and verify that no event is in two.
- Quantify the signal contamination of each control region with a benchmark
  signal.

## Blinding

Fix the selection, the background estimate and the systematic uncertainties
before looking at data in the signal region; develop on simulation and on
control and validation data. Record when the region was unblinded; a change
made afterwards is reported as such. If a cut was tuned on signal-region
data, say so: the p-value is then biased.

## Optimisation

- Optimise on simulation or sidebands. With few simulated events, tune on
  one part and take the expected yields from another: cuts tuned on a sample's
  fluctuations flatter it.
- Figures of merit, for expected signal s and background b: s/√b only for
  b much larger than s; Z = √(2((s + b) ln(1 + s/b) - s)) otherwise; with a
  background uncertainty use a formula that includes it or the full fit
  (`hep-likelihood-limits`). For a search with no assumed cross-section the
  Punzi form ε/(a/2 + √b), with ε the signal efficiency and a the number of
  sigmas sought.
- Keep enough simulated events in the signal region: effective number
  (Σw)²/Σw², not the weighted yield.
- Before cutting on a variable, check that data and simulation agree in it in
  a control region.

## Check before reporting

- Cut-flow table, raw and weighted, for data and each simulated sample.
- Trigger and plateau stated; object definitions and overlap order listed.
- Regions verified disjoint; duplicates removed and counted.
- Blinding status; what was optimised, and on which sample.
- Luminosity, its mask, and the list of simulation weights.
- A rerun gives the same yields.

## Related

- Skills here: `histogram-analysis`, `statistics-and-significance`,
  `hep-columnar-analysis`, `hep-background-estimation`,
  `hep-efficiency-measurement`, `hep-kinematics`, `hep-jets`,
  `hep-ml-classifiers`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `matplotlib`, `scientific-visualization`.
