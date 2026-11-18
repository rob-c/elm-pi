---
skill: lattice-qcd-analysis
also: data-fitting, uncertainty-propagation, statistics-and-significance
category: particle-theory
pitfall: errors that ignore the autocorrelation of the configurations (three times too small); a fit window with excited states in it, or a plain exponential on a periodic lattice; the scale uncertainty left out of the MeV value
timeout_sec: 1200
---
corr.h5 has the strange-strange pseudoscalar two-point function on our S16 ensemble, and notes.md the ensemble details. I need the ground-state mass in lattice units and in MeV, each with its uncertainty, and the fit range you settle on. Put them in result.json as am, am_err, mass_mev, mass_mev_err, tmin and tmax (the fit range in t/a).
