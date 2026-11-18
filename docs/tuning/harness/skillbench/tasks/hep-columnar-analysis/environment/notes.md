# events.root

A skim of the Drell-Yan plus diboson simulation for the dimuon study, written
with uproot. One tree, `Events`, 4800 entries.

| branch | type | meaning |
|---|---|---|
| event | int32 | event number |
| weight | float32 | event weight: generator weight (NLO, so some are negative) x pile-up weight x normalisation to 138 fb-1 |
| nMuon | int32 | number of muons in the event |
| Muon_pt | float32[nMuon] | transverse momentum [GeV] |
| Muon_eta | float32[nMuon] | pseudorapidity |
| Muon_phi | float32[nMuon] | azimuth [rad] |
| Muon_charge | int32[nMuon] | +1 or -1 |

All reconstructed muons passing the loose identification are kept, with no
kinematic cut, in the order of the reconstruction's own list. The muon mass is
0.10566 GeV.
