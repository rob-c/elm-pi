---
skill: scientific-python
also: statistics-and-significance
category: analysis
pitfall: the table used as it loads - the unit column (nA on most rows, uA on the 44 spikes) never looked at, so the mean is 9% low; a bootstrap without a seed, so the script kept for rerunning never gives the same interval twice
timeout_sec: 900
---
scan.csv is last night's leakage-current log of sensor W07 at 120 V. Give me the mean current with its standard error and, because of the micro-discharge spikes, the median with a 68% bootstrap interval, all in nA. Write them to result.json as mean_na, sem_na, median_na, median_lo_na and median_hi_na, and keep the script as analysis.py: I will rerun it on tonight's log.
