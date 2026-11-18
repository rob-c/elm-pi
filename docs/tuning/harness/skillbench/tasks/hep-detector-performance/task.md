---
skill: hep-detector-performance
also: data-fitting, histogram-analysis
category: particle
pitfall: the r.m.s. of a response with a low-energy tail taken as the resolution; the three terms added linearly, or the noise term left out
timeout_sec: 1200
---
testbeam.csv has the reconstructed energies from the electron energy scan of our ECAL prototype (set-up in notes.md). Fit the energy resolution against beam energy and give me the stochastic, noise and constant terms, and the resolution we should expect at 300 GeV. Write result.json with stochastic_term (in sqrt(GeV)), noise_term_gev, constant_term and resolution_at_300gev, the resolutions as fractions of the energy, not per cent.
