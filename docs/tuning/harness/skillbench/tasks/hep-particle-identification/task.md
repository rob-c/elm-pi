---
skill: hep-particle-identification
also: hep-efficiency-measurement, histogram-analysis
category: particle
pitfall: efficiency and misidentification integrated over the calibration sample quoted for an analysis sample with a harder momentum spectrum, instead of calibration binned in momentum and weighted to the analysis sample
timeout_sec: 900
---
calibration.csv is the D*-tagged calibration sample for our kaon identification cut and analysis_tracks.csv has the kaons and pions of the B -> h h' signal simulation; notes.md describes both. What kaon efficiency and what pion misidentification rate does the cut have for the analysis sample? Write result.json with kaon_efficiency and pion_misid_rate, both as fractions.
