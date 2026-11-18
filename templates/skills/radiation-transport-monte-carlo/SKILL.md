---
name: radiation-transport-monte-carlo
description: "Monte Carlo radiation transport with Geant4, FLUKA, MCNP, PHITS or OpenMC - geometry, materials, source, physics and data libraries, cuts, tallies and their normalisation, statistics, variance reduction."
disable-model-invocation: true
---

# Monte Carlo radiation transport

The mistakes: a tally per source particle reported as an absolute rate; no
statistical error, or a run in which a handful of histories carry the result;
a wrong density or composition; physics unsuited to the problem (no
data-driven neutron transport below 20 MeV); production cuts coarser than the
layers that matter; and parallel jobs that all used one seed.

## Which code

- **Geant4**: a C++ toolkit for any particle; you choose the physics list.
  TOPAS and GATE wrap it for medical physics.
- **FLUKA**: hadronic and electromagnetic cascades, activation, accelerator
  shielding; fixed, tuned physics.
- **MCNP**: neutrons, photons, electrons; shielding and criticality.
- **PHITS**: heavy ions and a wide energy range.
- **OpenMC** (open source, Python API) and **Serpent**: neutron and photon
  transport, criticality, depletion.

FLUKA, MCNP, PHITS and Serpent are licensed: use what the user already has.

## Building the model

1. **Geometry.** Mind each code's units (Geant4: mm, MeV, ns through its unit
   constants; MCNP and OpenMC: cm, with MeV and eV; FLUKA: cm and GeV). Plot
   it and run the overlap or lost-particle check before any physics.
2. **Materials.** Density, and composition by mass or by atom fraction - say
   which. Isotopics where they matter (B-10, Li-6, enriched targets), and
   thermal-scattering data for hydrogen bound in water or polyethylene.
3. **Source.** Particle, energy spectrum, position, direction. For a
   radionuclide, the emission probabilities come from `nuclear-data-lookup`,
   and the run is normalised per decay or per emitted particle: state which.
4. **Physics.** Geant4: FTFP_BERT for general high-energy work; QGSP_BIC_HP
   or the Shielding list when neutrons below 20 MeV matter (the HP data-driven
   package); the option4, Livermore or Penelope electromagnetic sets for
   low-energy precision. MCNP, OpenMC: name the evaluated library and its
   temperature.
5. **Cuts.** Geant4 production cuts are ranges (0.7 mm by default): make
   them small against the thinnest layer scored, and limit the step there.
6. **Tallies.** Fluence, current, energy deposition, dose (energy over the
   mass of the scoring volume - check that mass), pulse height. Results are
   per source particle: multiply by the source rate for an absolute answer. A
   pulse-height spectrum needs detector resolution folded in before it is
   compared with a measurement.

## Statistics

- Every result with its relative error R. R falls as 1/√N; the figure of
  merit 1/(R² T) should stay constant as the run grows. If it jumps, rare
  heavy histories dominate and the result is not converged. MCNP's guidance:
  R below 0.10 (0.05 for point detectors) and all ten statistical checks.
- Parallel runs need distinct seeds or the code's own parallel streams;
  record them. Combine independent runs to check the quoted error.
- Variance reduction (importance splitting, weight windows, source biasing)
  must leave the mean unchanged: confirm on a cut-down problem against an
  analogue run, and watch for large weight fluctuations.
- Criticality: discard cycles until the fission source has converged.

## Validate first

Run an analytic case in the same set-up before the real one: uncollided
narrow-beam photon transmission exp(-μx) with μ from NIST XCOM; the 1/(4πr²)
fluence of a point source in vacuum; energy deposited plus energy escaping
equal to the source energy; a tabulated range (`stopping-power-and-range`).

## Check before reporting

- Code, version, physics list or data library, cuts.
- Geometry plotted; no overlaps or lost particles.
- Normalisation from per-source-particle to absolute, with the source
  strength and its date.
- Relative errors, histories run, figure of merit stable.
- The analytic validation and its result.
- The key number's sensitivity to the cut and to the physics choice.
- For shielding or dose: an estimate for planning, not a safety assessment -
  the local radiation protection officer and regulations decide.

## Related

- Skills here: `stopping-power-and-range`, `dosimetry-and-shielding`,
  `neutron-activation-and-transport`, `radiation-detectors-and-daq`,
  `hep-detector-simulation`, `nuclear-data-lookup`, `scientific-cpp`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `get-available-resources`, `matplotlib`, `pydicom`.
