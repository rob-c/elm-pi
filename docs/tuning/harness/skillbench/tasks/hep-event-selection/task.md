---
skill: hep-event-selection
also: hep-columnar-analysis, histogram-analysis
category: particle
pitfall: events that fired both triggers are in both primary datasets and are counted twice; sqrt(N) quoted for a yield of weighted events
timeout_sec: 900
---
data.csv and ttbar.csv are the lepton+jets skims of the first 2026 runs and of the ttbar simulation; notes.md has the event selection and the normalisation. I need the cut flow of both, that is the yield after each of the six cuts in order, with the simulation normalised to the data's luminosity, and the statistical uncertainty of the final ttbar yield. Write result.json with data and ttbar, each a list of six numbers, and ttbar_final_unc.
