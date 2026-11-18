---
skill: hep-data-formats
also: hep-columnar-analysis, hep-event-generators
category: particle
pitfall: luminosity summed over sections outside the good-run list (or delivered, or /ub taken as /pb); events repeated in the two primary datasets counted twice; simulation normalised by the skimmed file's entries or weights instead of the sum of weights in the Runs tree
timeout_sec: 1200
---
I want a quick Z -> mu mu yield check on the low-pile-up runs: the two data ntuples, the golden JSON, the luminosity table and the skimmed DY simulation are here, and notes.md says what each is and gives the Z selection. How many Z candidates do we have in certified data, what integrated luminosity do they correspond to, and how many does the simulation predict for that luminosity? Write result.json with n_data, lumi_pb (in pb^-1) and n_mc_expected.
