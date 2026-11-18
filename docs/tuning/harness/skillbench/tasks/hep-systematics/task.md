---
skill: hep-systematics
also: uncertainty-propagation, hep-background-estimation
category: particle
pitfall: the ratio's uncertainty taken as the two regions' totals in quadrature instead of source by source on the ratio; a one-sided and a two-point variation halved by (up - down)/2
timeout_sec: 900
---
yields.csv has the simulated W+jets yields in our signal and control regions, nominal and for each of the systematic variations; notes.md says how the variations were made and what our conventions are. I need the transfer factor SR/CR with its total relative systematic uncertainty, and the total relative systematic uncertainty of the SR yield on its own. Write result.json with transfer_factor, tf_syst_percent and sr_syst_percent, the last two in per cent.
