---
skill: hep-efficiency-measurement
also: statistics-and-significance
category: particle
pitfall: the normal-approximation error sqrt(e(1-e)/n) quoted as the interval, which has no width in the bins where no probe or every probe passes
timeout_sec: 900
---
probes.csv has one row per offline muon from the MET-triggered reference sample: its pT and whether HLT_Mu50 fired; notes.md describes it and lists the pT bins. I need the trigger efficiency in each of those bins with its 68.3% confidence interval. Write result.json with three lists, one entry per bin in order: efficiency, lower and upper, the last two being the ends of the interval as efficiencies between 0 and 1.
