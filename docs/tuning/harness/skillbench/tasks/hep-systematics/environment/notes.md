# W+jets background: systematic variations of the simulated yields

The W+jets yield in the signal region (SR: one muon, four jets, at least one
b-tagged) is taken from the control region (CR: same, with a b-jet veto) as

    N_SR = N_CR(data, other backgrounds subtracted) x TF,    TF = MC(SR) / MC(CR).

`yields.csv` has the simulated W+jets yields in both regions (events in
138 fb-1): the nominal ones, and one row per systematic variation. Every
variation was made by shifting the source by one standard deviation where it
enters and rerunning the whole selection, on the same simulated events unless
said.

| rows | source | what was shifted |
|---|---|---|
| lumi_up, lumi_down | integrated luminosity | +-1.7% |
| pileup_up, pileup_down | pile-up reweighting | minimum-bias cross-section, +-4.6% |
| jes_up, jes_down | jet energy scale | all jets by the total scale uncertainty |
| jer_smear | jet energy resolution | simulated jets smeared further by the resolution uncertainty; the resolution can only be made worse, so there is no opposite variation |
| btag_up, btag_down | b-tagging scale factors | efficiency and mistag scale factors together |
| muon_up, muon_down | muon scale factors | trigger, identification and isolation together |
| generator_alt | W+jets modelling | the alternative generator sample in place of the nominal one; a comparison of two models, so a single row |

## Conventions (unchanged from the last round)

- Each source in the table is one nuisance parameter: a shift of it acts on SR
  and CR at once. The sources are independent of each other.
- A source with an up and a down row enters a quantity with half the
  difference between that quantity's up and down values. A source with a single
  row enters with the full difference from the nominal value, taken in both
  directions.
- The statistical uncertainty of the simulated sample counts as a systematic
  uncertainty of the estimate. For the nominal yields sqrt(sum of squared
  weights) is 9.1 events in SR and 27.4 in CR; the regions share no events.
- Relative uncertainties are quoted in per cent of the nominal value.
