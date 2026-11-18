"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

750 events of about 60 tracks, azimuths drawn from 1 + 2 v2 cos 2(phi - Psi) about a
reaction plane that is random event by event and not written out. Nothing else is in
the sample: no other harmonics, no non-flow, no fluctuation of v2, uniform acceptance.
With 60 tracks the full event plane has a resolution near 0.6 and a half-event plane
near 0.45, so an uncorrected v2 is 40 to 60% low, and a track left in its own plane
gives 0.145.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

V2 = 0.10                        # the truth
EVENTS, MEAN_TRACKS = 750, 60

lines = []
for _ in range(EVENTS):
    tracks = max(30, rng.poisson(MEAN_TRACKS))
    plane = rng.uniform(0, 2 * np.pi)
    phis = []
    while len(phis) < tracks:
        trial = rng.uniform(0, 2 * np.pi, 2 * tracks)
        keep = rng.uniform(0, 1 + 2 * V2, 2 * tracks) < 1 + 2 * V2 * np.cos(2 * (trial - plane))
        phis.extend(trial[keep].tolist())
    lines.append(" ".join("%.3f" % phi for phi in phis[:tracks]))
(out / "events.txt").write_text("\n".join(lines) + "\n")
(out / "notes.md").write_text("""# Flow sample, fixed-target Au+Au run

- Beam: 197Au, kinetic energy 30.0 GeV per nucleon, on a thin gold foil at
  rest in the laboratory.
- Nucleon mass to use: 0.9389 GeV.
- Events: 20-30% most central, by the multiplicity in the forward counters.
- Tracks: charged hadrons in the pT and rapidity window of the analysis note,
  after the quality cuts.
- events.txt: one event per line, the azimuthal angles of its selected tracks
  in radians, 0 to 2 pi, in no particular order.
- Acceptance and efficiency are uniform in azimuth after the standard
  corrections: nothing is left to flatten.
- Correlations from jets and resonance decays were checked with the event
  generator and are below the statistical error for this selection.
""")
print("%d events, %d tracks" % (EVENTS, sum(len(line.split()) for line in lines)))
