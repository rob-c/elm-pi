# Event 48213, particle level

`event.csv` has the stable particles (c tau > 10 mm) of one simulated
proton-proton event at 13.6 TeV with |y| < 4.5: one row per particle, its PDG
code and its four-momentum px, py, pz, e in GeV. The z axis is along the beam.

## Particle-level jets, as defined in the analysis

- Inputs: all stable particles except neutrinos (PDG codes 12, 14, 16 and
  their antiparticles). Muons are kept.
- Algorithm: anti-kT with R = 0.4.
- Recombination: E-scheme (four-momenta are added).
- Jets are counted if pT > 25 GeV; there is no rapidity cut in this check.

The leading jet is the one with the highest pT.
