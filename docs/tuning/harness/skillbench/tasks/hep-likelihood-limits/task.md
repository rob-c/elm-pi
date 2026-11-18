---
skill: hep-likelihood-limits
also: statistics-and-significance, hep-systematics
category: particle
pitfall: the limit computed without the nuisance parameters - background fixed at its central value, its 20% uncertainty left out of the model - or with CLs+b, which excludes far too much when the count fluctuates low
timeout_sec: 1200
---
notes.md and yields.csv have the unblinded numbers of our single-bin search: the observed count, the background estimate and the signal yield per fb, with their uncertainties. I need the observed and expected upper limits on the signal cross-section, as we quote them. Write result.json with obs_limit_fb, exp_limit_fb for the median expected limit, and exp_minus1_fb and exp_plus1_fb for the ends of its +-1 sigma band.
