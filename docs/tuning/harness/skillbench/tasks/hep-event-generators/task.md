---
skill: hep-event-generators
also: hep-data-formats, uncertainty-propagation
category: particle
pitfall: normalised by the number of events or by the skimmed file's weights instead of the sum of weights of everything written; filter efficiency or forced-decay branching ratio left out of the cross-section; sqrt(N) for a sample with negative weights
timeout_sec: 900
---
events.csv is our skimmed ttZ sample from MadGraph5_aMC@NLO; the sample card and the signal-region cuts are in notes.md. How many events do we expect in the signal region for the luminosity given there, and what is the Monte Carlo statistical uncertainty on that number? Write result.json with expected_events and mc_stat_uncertainty, both in events.
