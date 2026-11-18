---
skill: radiation-transport-monte-carlo
also: uncertainty-propagation, statistics-and-significance
category: nuclear
pitfall: runs of 2e6 to 4e8 histories averaged with equal weight; a job that reused another's seed counted as an independent run, so the error comes out 25% too small; the per-source-photon tally multiplied by the activity without the emission probability
timeout_sec: 900
---
runs.csv lists the tallies from last night's Monte Carlo jobs for the Cs-137 lead-slab validation described in notes.md. Combine them into one tally with its relative error, turn that into the photon flux at the detector for our source with its uncertainty, and give the analytic narrow-beam flux to compare it with; also tell me which runs fail the reliability rule in the notes. Write result.json with combined_tally_per_cm2, combined_rel_err, flux_per_cm2_s, flux_unc_per_cm2_s, analytic_flux_per_cm2_s and unreliable_runs (a list of run numbers).
