---
skill: hep-ml-classifiers
also: hep-event-selection, statistics-and-significance
category: particle
pitfall: the working point chosen on the test set, on the training set or on all rows together, or chosen on validation and quoted from validation, instead of chosen on validation and quoted from test
timeout_sec: 900
---
scores.csv has the output of our BDT for the simulated signal and background events of the three sets from its training; notes.md describes the columns, the working points we can use and the figure of merit. Which working point gives the best expected significance for 140 fb^-1, and what do we expect there? Write result.json with cut, signal_events, background_events, significance and signal_efficiency (a fraction).
