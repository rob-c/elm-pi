---
skill: hep-background-estimation
also: hep-event-selection, uncertainty-propagation
category: particle
pitfall: B x C / D on raw counts with a Poisson error - prompt-lepton simulation not subtracted from the control regions, and the 35% non-closure seen in the validation set neither corrected for nor in the uncertainty
timeout_sec: 900
---
regions.csv has the data and the simulated prompt-lepton yields in the four regions of our multijet estimate and in the b-veto validation set; notes.md defines the regions. I need the multijet background in signal region A with its total uncertainty. Write result.json with multijet_a and multijet_a_unc, both in events.
