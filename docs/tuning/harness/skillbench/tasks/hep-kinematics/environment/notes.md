# Run 4127, event 880213: exclusive p p -> p p pi+ pi- pi0 candidate

Fixed-target run: proton beam of 3.500 GeV kinetic energy on the liquid-hydrogen
target (protons at rest). The z axis is along the beam.

The event passed the exclusive selection: four charged tracks from the primary
vertex and two photon clusters, nothing else. The kinematic fit identifies the
tracks as below; the two clusters are the photons of the pi0.

## tracks.csv (spectrometer)

One row per track at the primary vertex. Momentum components px, py, pz are in
MeV/c, the tracking software's unit. `pdg_id` is the particle hypothesis from
the kinematic fit and time of flight (2212 proton, 211 pi+, -211 pi-).

## clusters.csv (electromagnetic calorimeter)

One row per photon cluster: `energy` in GeV after calibration, and the direction
from the primary vertex as polar angle `theta` (from the beam axis) and azimuth
`phi`, both in radians.

## Masses (PDG, MeV)

| particle | mass |
|---|---|
| proton | 938.272 |
| pi+- | 139.570 |
| pi0 | 134.977 |
