# Lepton+jets selection, first 2026 collisions

`data.csv` is the lepton+jets skim of the first stable-beam runs, from the
SingleMuon and EGamma primary datasets (column `dataset`). The skim keeps
events with exactly one electron or muon candidate of pT > 25 GeV and at least
two jets. `ttbar.csv` is the same skim of the tt-bar simulation.

## Columns

| column | meaning |
|---|---|
| run, lumi, event | run number, luminosity block, event number (data) |
| event | event number (simulation) |
| hlt_mu, hlt_el | 1 if the single-muon / single-electron trigger fired |
| lep_flavour | 13 for a muon, 11 for an electron |
| lep_pt, lep_eta | the lepton's pT [GeV] and pseudorapidity |
| n_jets | jets with pT > 30 GeV and abs(eta) < 2.4, after removing jets within deltaR < 0.4 of the lepton |
| n_btag | how many of those jets are b-tagged (medium working point) |
| met | missing transverse momentum [GeV] |
| gen_weight, pu_weight, sf_lepton, sf_btag | simulation only: generator weight, pile-up weight, lepton and b-tagging scale factors |

## Selection, in this order

1. Data quality (data only): the luminosity block is in `good_runs.json`,
   which lists for each good run its ranges of good blocks, first and last
   included. Simulated events all pass.
2. Trigger: muon events (lep_flavour 13) need hlt_mu, electron events need hlt_el.
3. Lepton: pT > 30 GeV and abs(eta) < 2.4.
4. Jets: n_jets >= 4.
5. b-tag: n_btag >= 1.
6. Missing momentum: met > 40 GeV.

## Normalisation of the simulation

The good blocks correspond to an integrated luminosity of 4.7 pb-1. The
tt-bar sample (lepton+jets, NLO generator with weights of +1 and -1) has a
cross-section times branching fraction of 314.0 pb. 6400 events were
processed before the skim, with a sum of generator weights of 3814. An event's
weight is the product of its four weight columns, normalised to the data's
luminosity.
