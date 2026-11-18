---
skill: uncertainty-propagation
also: statistics-and-significance
category: analysis
pitfall: the height-width covariance left out of the peak yield (error 1.5 times too large); the target and efficiency uncertainties, common to both runs, averaged down in the combination and counted in the comparison of the runs
timeout_sec: 900
---
fit_run1.json and fit_run2.json are the peak fits from the two runs, and notes.md says how to get from them to a cross-section. Combine the two runs: give me the cross-section with its statistical and its systematic uncertainty, and tell me by how many standard deviations the two runs disagree with each other. Put them in result.json as xsec_mb, stat_mb, syst_mb and runs_differ_sigma.
