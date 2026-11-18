# Kaon identification cut DLL(K - pi) > 5: calibration and analysis samples

## calibration.csv

Tracks from D*+ -> D0 (-> K- pi+) pi+ and the charge conjugate in the 2025
data, selected on kinematics alone. The charge of the slow pion says which D0
daughter is the kaon and which the pion, so no identification requirement was
put on them. The D0 mass window is tight: the background under the peak is
below 0.5% and is ignored.

| column | |
|---|---|
| species | K or pi, from the slow pion's charge |
| p_gev | track momentum, GeV |
| passed | 1 if the track has DLL(K - pi) > 5, else 0 |

## analysis_tracks.csv

The kaons and pions of our B -> h h' signal simulation after the full
selection except the identification cut: true species and momentum. The
simulation's own DLL is not trusted, which is why the cut's performance is
taken from data.

Both samples are restricted to 3 < p < 100 GeV, where the RICH radiators cover
kaons and pions, and to the same pseudorapidity range and data-taking period.
