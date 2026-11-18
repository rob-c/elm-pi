# Y(1S) -> mu+ mu- cross-section at 13 TeV, dimuon stream

## What is measured

- Fiducial region, at particle level: both muons (dressed) with pT > 4.5 GeV
  and abs(eta) < 2.4, from a Y(1S) with abs(y) < 2.4.
- Fiducial cross-section: sigma(pp -> Y(1S) X) x B(Y(1S) -> mu+ mu-) with the
  muons in the fiducial region.
- Total cross-section: sigma(pp -> Y(1S) X) for abs(y) < 2.4, all decays.

## Data

- Trigger: HLT_Dimuon0_Upsilon. It ran with a prescale of 60 for the whole period.
- Luminosity recorded for the good-run list: 0.800 fb^-1, relative uncertainty 2.3%.
- Events in the Y(1S) mass window after the full selection: 27113.
- Background in the window, from the sideband fit: 7250 +- 290. The
  uncertainty is the spread over the background shapes tried.

## Signal simulation

mc_counts.csv has sums of event weights in the Y(1S) -> mu mu sample
(unpolarised) at four stages:

| stage | |
|---|---|
| generated | Y(1S) -> mu mu with abs(y) < 2.4 |
| fiducial | of those, the events in the fiducial region at particle level |
| selected | events reconstructed and passing the full selection, with the trigger decision as simulated (no prescale) |
| selected_and_fiducial | of the selected events, those in the fiducial region at particle level |

The simulation's statistical uncertainty is negligible. The muon
reconstruction, identification and trigger scale factors are applied; their
uncertainty on the selected yield is 2.4%.

## Extrapolation to the total

- Acceptance: 6.5% relative uncertainty (polarisation and the pT spectrum).
- B(Y(1S) -> mu+ mu-) = (2.48 +- 0.05)% (PDG).
