---
skill: hep-columnar-analysis
also: hep-kinematics, hep-event-selection, scientific-python
category: particle
pitfall: the first two muons taken as the pair, or an object cut applied as an event cut, so candidates in events with a third or fourth muon are lost; sqrt(yield) quoted for a sum of weights
timeout_sec: 900
---
events.root (tree Events) is our dimuon skim of the Drell-Yan and diboson simulation: jagged arrays Muon_pt, Muon_eta, Muon_phi and Muon_charge per event, and an event weight; notes.md lists the branches. I need the weighted number of opposite-charge muon pairs with 81 < m(mumu) < 101 GeV in which both muons have pT > 20 GeV and |eta| < 2.4, every such pair counted once with its event's weight, and the weighted number of events that have at least one such pair, with its statistical uncertainty. Write result.json with pair_yield, event_yield and event_yield_unc.
