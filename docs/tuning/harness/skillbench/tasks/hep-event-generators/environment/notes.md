# ttZ (Z -> ll) sample for the dilepton + jets channel

## Sample card

Copied from the production request and the generator log.

| | |
|---|---|
| Generator | MadGraph5_aMC@NLO 3.5.3 at NLO QCD, showered with Pythia 8.310 (MC@NLO matching) |
| Process | p p -> t t~ Z at 13 TeV, with the Z undecayed in the matrix element |
| Cross-section printed by the generator | 0.7603 pb |
| Decays | Z -> l+ l- (l = e, mu, tau) forced with MadSpin. BR(Z -> ll) = 0.10099 is not in the number above |
| Generator filter | two leptons with pT > 15 GeV and abs(eta) < 2.8. Efficiency 0.584; events failing it were not written |
| k-factor | 1.12 (to NLO+NNLL QCD with NLO electroweak corrections, same phase space) |
| Events written | 40000 |
| Sum of the generator weights of the written events | 13920 |

Every event has generator weight +1 or -1.

## events.csv

A skim of the written events for this channel: only events with
ptll > 100 GeV were kept, to save space. One row per event.

| column | |
|---|---|
| event | event number in the written sample |
| ptll | transverse momentum of the dilepton system, GeV |
| njet | number of selected jets |
| weight | generator weight |

ptll and njet are the quantities the selection cuts on.

## Signal region

ptll > 150 GeV and njet >= 4.

## Data

Full Run 2: 140 fb^-1.
