---
skill: hep-cross-section-measurement
also: uncertainty-propagation, hep-efficiency-measurement
category: particle
pitfall: the recorded luminosity used for a prescaled trigger; fb^-1 not turned into pb^-1; the correction factor taken without the events that migrate into the selection; sqrt(N - B) for the statistical error; luminosity or extrapolation uncertainty folded into the systematic one
timeout_sec: 900
---
notes.md and mc_counts.csv have the inputs for our Y(1S) -> mu mu cross-section measurement from the dimuon stream. Give me the fiducial cross-section (times branching fraction) and the total production cross-section, in pb, each with its statistical, systematic and luminosity uncertainties kept apart, and for the total also the extrapolation uncertainty (acceptance and branching fraction). Write result.json with fid_pb, fid_stat_pb, fid_syst_pb, fid_lumi_pb, tot_pb, tot_stat_pb, tot_syst_pb, tot_lumi_pb and tot_extrap_pb.
