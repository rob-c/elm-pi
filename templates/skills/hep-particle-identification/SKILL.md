---
name: hep-particle-identification
description: "Charged-particle identification - dE/dx, time of flight, Cherenkov angle, transition radiation, E/p and muon systems; combined likelihoods; efficiency and misidentification from data control samples."
disable-model-invocation: true
---

# Particle identification

What goes wrong: performance taken from simulation instead of calibration
samples in data; an efficiency quoted without the misidentification rate at
the same working point, or for kinematics that are not the analysis
sample's; and separation claimed at momenta where the technique has none.

## What separates what, and where

- **dE/dx.** The mean energy loss depends on βγ alone: it falls as 1/β² at
  low βγ, has a minimum near βγ of 3 to 4, then rises logarithmically to a
  plateau. At fixed momentum, different masses have different βγ - until
  their bands cross, where there is no separation. Use a truncated mean
  (discard the highest samples): single measurements have a Landau tail.
  The formula is in `stopping-power-and-range`.
- **Time of flight.** β = L/(ct), so m = p √(c²t²/L² - 1). Two masses at the
  same momentum arrive Δt = (L/c)(m1² - m2²)/(2p²) apart (m and p in the same
  units, both relativistic), falling as 1/p². The mass error grows as
  γ² σ(t)/t.
- **Cherenkov.** Light only for β > 1/n, at cos θ = 1/(nβ); threshold
  momentum p = m/√(n² - 1); photon yield proportional to sin²θ. A ring
  imager measures θ and hence β; a threshold counter answers yes or no. At
  high momentum every species saturates at cos θ = 1/n.
- **Transition radiation** depends on γ (of order 1000 and above): it
  separates electrons from pions between about 1 and 100 GeV.
- **Calorimeters and muon systems.** E/p near 1 and a narrow shower for
  electrons; muons cross the absorber. The fakes are hadron punch-through
  and pions and kaons decaying in flight.

## Combining detectors

- Multiply per-detector likelihoods for each hypothesis and cut on a
  difference of logs, such as ln L(K) - ln L(π).
- A Bayesian probability needs priors, the species abundances, so it is a
  property of the sample: state the priors, and do not carry the
  probability to a sample of different composition.
- A network or BDT trained on simulation inherits its mismodelling:
  calibrate its output on data like any other variable
  (`hep-ml-classifiers`).

## Efficiency and misidentification from data

1. **Calibration samples** selected by kinematics, with no identification
   requirement on the probe: K0S → ππ for pions, Λ → pπ for protons,
   D*⁺ → D⁰(Kπ)π⁺ for kaons and pions (the slow pion's charge tags them),
   φ → KK, J/ψ and Z → ℓℓ by tag and probe for leptons, photon conversions
   for electrons.
2. **Subtract the background** under the peak (sidebands, a fit, or sWeights)
   before counting passes and fails; intervals as in
   `hep-efficiency-measurement`.
3. **Bin** in what the performance depends on: momentum, pseudorapidity or
   angle, and event multiplicity. Then weight the calibration tables to the
   analysis sample's distribution - a single integrated number belongs to
   the calibration sample only.
4. **Quote pairs**: efficiency with the misidentification rate of each other
   species at that working point, or the whole ROC curve.
5. **Systematics**: binning, background subtraction, bins the calibration
   sample does not populate, correlation between two tracks in one event,
   and changes between data-taking periods.

## Check before reporting

- Performance from data control samples, with the samples named.
- Efficiency and misidentification quoted together, per species.
- Tables binned, and reweighted to the analysis kinematics.
- No claim outside the momentum range where the detector separates.
- Period, detector conditions and software version of the calibration.

## Related

- Skills here: `hep-efficiency-measurement`, `stopping-power-and-range`,
  `hep-detector-performance`, `hep-ml-classifiers`, `hep-flavour-and-cp`,
  `hep-kinematics`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `scikit-learn`, `matplotlib`, `uncertainty-and-units`.
