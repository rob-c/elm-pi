# Leading-jet mass: inputs for the particle-level spectrum

Groomed mass of the leading large-radius jet, 30 to 180 GeV in 15 bins of
10 GeV; the same binning at detector level and at particle level. The mass
resolution is about 10 GeV.

Particle level (the fiducial region): the leading particle-level jet has
pT > 400 GeV, |y| < 2.0, and a groomed mass between 30 and 180 GeV.

## spectra.csv, one row per bin

- `data`: events observed with the reconstructed mass in the bin.
- `mc_reco`: simulated events reconstructed in the bin.
- `mc_reco_fake`: those of `mc_reco` whose particle-level jet is outside the
  fiducial region (in practice its mass is below 30 or above 180 GeV).
- `mc_truth`: simulated events generated in the bin at particle level, inside
  the fiducial region, reconstructed or not.

## response.csv

Simulated events that are inside the fiducial region at particle level and
reconstructed between 30 and 180 GeV: row = bin of the reconstructed mass,
column = bin of the particle-level mass.

## Remarks

- The simulated counts are raw numbers of events, not normalised to the data.
  The simulated sample is about three times the size of the data.
- The simulation is the multijet sample only. It is known not to describe the
  shape of the data around 100 GeV, and it has not been reweighted.
- Other backgrounds are negligible in this selection.
