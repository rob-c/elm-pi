---
skill: hep-unfolding
also: hep-systematics, uncertainty-propagation
category: particle
pitfall: the response matrix inverted as it stands, which with a resolution of one bin width swings by tens of per cent from bin to bin; or bin-by-bin factors, pulled to a simulated shape the data do not have
timeout_sec: 1200
---
spectra.csv and response.csv are the inputs for the jet-mass measurement: the measured spectrum, and from the simulation the response matrix with the generated, reconstructed and fake counts; notes.md says what each column is. Unfold the data to particle level in the same 15 bins: I need the number of events in each bin with its uncertainty. Write result.json with two lists of 15 numbers, unfolded and uncertainty.
