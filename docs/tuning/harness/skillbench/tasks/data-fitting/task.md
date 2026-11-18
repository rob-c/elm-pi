---
skill: data-fitting
also: uncertainty-propagation
category: analysis
pitfall: least squares with sigma = sqrt(N) on channels holding a few counts (a third of them empty), which pulls the half-life 9 s low; chi2/ndf of 0.6 reported as a good fit
timeout_sec: 900
---
decay.csv is the multichannel-scaler record of the activated foil from run 14, and notes.md says how it was taken. Fit it and give me the half-life with its uncertainty and the background rate, with the chi-square and the number of degrees of freedom of the fit. Put them in result.json as half_life_s, half_life_unc_s, background_cps, chi2 and ndf.
