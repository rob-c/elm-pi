# Z -> mu mu check on the low-pile-up runs

## Data

`SingleMuon.root` and `DoubleMuon.root`: our ntuples from the two primary
datasets, NanoAOD layout, one `Events` tree each with `run`, `luminosityBlock`,
`event` and the muons (`nMuon`, `Muon_pt`, `Muon_eta`, `Muon_phi`,
`Muon_charge`), highest pT first. The ntuple job kept events with two muons of
pT > 20 GeV inside abs(eta) < 2.4, from all of runs 279760, 279766, 279794, 279823, 279841.
For this selection every event fires at least one of the two triggers.

`golden.json`: the certification for these runs, in the usual format - run to
a list of [first, last] luminosity-section ranges, both ends included.

`lumi_by_ls.csv`: brilcalc output by luminosity section for the same runs,
delivered and recorded luminosity in /ub.

## Simulation

`DYJetsToLL_skim.root`: DYJetsToLL (aMC@NLO, all three lepton flavours,
m(ll) > 50 GeV), same layout, with `genWeight` in `Events` and the usual `Runs`
tree. It is a skim - only events with two reconstructed muons as above were
kept - merged from three files. Cross section 6077.22 pb (NNLO, for the
sample as generated). No efficiency scale factors are applied to it yet.

## Z selection

The two highest-pT muons, of opposite charge, both with pT > 25 GeV and
abs(eta) < 2.4, and 80 < m(mu mu) < 100 GeV. Muon mass 0.105658 GeV.
