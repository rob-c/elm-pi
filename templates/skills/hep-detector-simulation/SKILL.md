---
name: hep-detector-simulation
description: "Detector simulation - Geant4 geometry, materials, physics lists, production cuts and scoring, digitisation, validation against data, and fast simulation with Delphes and where it stops being valid."
disable-model-invocation: true
---

# Detector simulation

A simulation fails silently in three places: overlapping volumes that lose or
double-count energy, a physics list used outside the energies it was validated
for, and a production cut that hides the secondaries which set the resolution.
Fast simulation fails differently: it answers every question, including those
its parametrisation never covered.

## Full simulation with Geant4

1. **Geometry.** One source of truth (C++ classes, GDML, or a DD4hep compact
   description) and an overlap check before any physics run: `CheckOverlaps()`
   on each placement, or the geometry test in the macro. Materials from the NIST
   database where they exist, with the density you actually have; isotopic
   composition where neutrons matter.
2. **Physics list.** Name it and the Geant4 version: results move between
   releases. FTFP_BERT is the reference list for collider calorimetry;
   QGSP_BIC_HP or QGSP_BERT_HP add high-precision neutron transport below
   20 MeV; electromagnetic option 4 (the EMZ suffix) is the precise choice at
   low energy and for thin layers. A list is validated for a range: say why
   yours fits the energies and particles of the problem.
3. **Production cuts.** A range cut (of order 1 mm by default) becomes an
   energy threshold in each material; below it no secondary is made and the
   energy is deposited locally. It must be smaller than the thinnest sensitive
   feature (silicon, sampling gaps). Add a step limit in thin volumes and in
   strong fields. Show the result is stable when the cut is halved.
4. **Scoring.** A sensitive detector or scoring mesh; sum deposits per event,
   not per step. Apply Birks' quenching for scintillators. Keep the truth
   (primary, process, parent) beside the hits.
5. **Digitisation.** Deposits become signals: photostatistics, electronic
   noise, thresholds, shaping and time windows, dead channels. In a real
   detector these, not Geant4, usually set the resolution - a simulation
   without them is an upper bound on performance.
6. **Seeds.** A distinct, recorded seed per job, with the engine named. Jobs
   sharing a seed produce the same events, and the statistical error is then
   understated.
7. **Validation.** Before use, compare with test-beam or in-situ data:
   response linearity, resolution, shower shapes, the minimum-ionising peak.

## How many events

- An efficiency ε from N generated events has binomial error √(ε(1-ε)/N); see
  `hep-efficiency-measurement` near 0 and 1.
- Weighted events: the effective number is (Σw)² / Σw².
- Aim for a simulation statistical error well below the data's (a third or
  less), and quote it.

## Fast simulation with Delphes

- A card parametrises the detector: tracking efficiency and smearing,
  calorimeter towers and resolution, particle flow, jets through FastJet,
  b-tagging efficiency and mistag rates as formulas, isolation, missing
  transverse momentum. Use the card written for the experiment, and name it
  and the Delphes version.
- Not valid for: displaced vertices and long-lived particles, shower shapes,
  leptons and photons faked by jets, pile-up detail, timing, and any object
  outside the momentum and pseudorapidity range the card's formulas cover.
- Trust it for a new selection only after it reproduces a published efficiency
  or cut flow for the same objects (`hep-reinterpretation`).

## Check before reporting

- Geant4 version, physics list, range cuts, geometry source, overlap check.
- The result with the cut (and step limit) halved.
- Seeds distinct and recorded; number of events and the statistical error.
- A validation plot against data or a reference.
- For Delphes: card, version, and why the observable is inside its validity.

## Related

- Skills here: `hep-event-generators`, `hep-detector-performance`,
  `radiation-transport-monte-carlo`, `stopping-power-and-range`,
  `hep-reinterpretation`, `scientific-cpp`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `get-available-resources`, `matplotlib`.
