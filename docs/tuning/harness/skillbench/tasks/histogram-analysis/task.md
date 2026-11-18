---
skill: histogram-analysis
also: uncertainty-propagation
category: analysis
pitfall: the simulated background's error per bin taken as sqrt(expected events) instead of sqrt(sum of squared weights), half the real one; a negative bin clipped to zero; the efficiency's uncertainty left out of the corrected yield
timeout_sec: 900
---
data.csv has the selected data events and background_mc.csv the simulated background passing the same selection; notes.md has the binning, the normalisation and the signal efficiency. Subtract the background from the data in each mass bin, and give me the efficiency-corrected signal yield summed over the bins. Put in result.json: signal and signal_unc as lists with one number per bin, lowest mass first, and corrected_yield and corrected_yield_unc, each one number for the sum over the bins.
