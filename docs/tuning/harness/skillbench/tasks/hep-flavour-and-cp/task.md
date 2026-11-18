---
skill: hep-flavour-and-cp
also: data-fitting, uncertainty-propagation
category: particle
pitfall: the raw asymmetry fitted without the mistag dilution 1 - 2w of each category; tagging power from the summed efficiency and an average mistag instead of the sum over categories; sign convention of S and C
timeout_sec: 900
---
counts.csv has our flavour-tagged B0 -> D+ D- candidates in bins of decay time for the three tagging categories; the tagging calibration and the conventions are in notes.md. What is the effective tagging power of the sample, and what S and C do you get from the time-dependent asymmetry? Write result.json with tagging_power (a fraction), S, S_uncertainty, C and C_uncertainty, the uncertainties statistical.
