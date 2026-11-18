---
skill: radiation-detectors-and-daq
also: statistics-and-significance
category: nuclear
pitfall: the extending dead time solved on its low-rate branch (or with the non-extending formula) although the channel is saturated and reads low; accidentals taken as tau R1 R2 for two logic pulses of width tau, not 2 tau R1 R2
timeout_sec: 900
---
notes.md has yesterday's rate checks on the two timing channels and the coincidence run. Give me the true, dead-time corrected rate of channel A and of channel B with the source at 10 cm, the accidental coincidence rate in the coincidence run, and the true coincidence rate. Write result.json with true_rate_a_per_s, true_rate_b_per_s, accidental_rate_per_s and true_coincidence_rate_per_s.
