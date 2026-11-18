"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A single activity decaying on a constant background, recorded by a multichannel
scaler with a short dwell time: 22 counts in the first channel, under one count
a channel in the tail, 144 of the 400 channels empty. Two hundred toy runs
with these parameters (2026-11-17): a Poisson likelihood fit is unbiased with a
spread of 2.7 s; least squares with sigma = sqrt(max(N, 1)) comes out 8.5 s low
on average, with sqrt(N + 1) 6.1 s low, with the empty channels dropped 13.5 s
low; a straight line through ln(N) of every channel gives about 200 s.

The seed is the one of forty tried for which the likelihood fit of this one
dataset lands nearest the truth in both parameters (61.8 s, 0.229 /s), so the
verifier can be centred on the truth rather than on the oracle's own answer.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261139)

HALF_LIFE = 61.3          # s: what the task asks for
BACKGROUND = 0.225        # counts per second: asked for too
FIRST = 22.0              # counts per channel from the activity at t = 0
DWELL, CHANNELS = 2.0, 400

lam = np.log(2) / HALF_LIFE
edges = np.arange(CHANNELS + 1) * DWELL
# The expected counts in a channel are the integral of the rate over it, not the rate at its centre.
expected = FIRST / (lam * DWELL) * (np.exp(-lam * edges[:-1]) - np.exp(-lam * edges[1:])) + BACKGROUND * DWELL
counts = rng.poisson(expected)
(out / "decay.csv").write_text("t_s,counts\n" + "".join("%g,%d\n" % row for row in zip(edges[:-1], counts)))
(out / "notes.md").write_text("""# Run 14 - short-lived activity in the irradiated foil

- Foil out of the neutron source at 14:02:10, on counter 3 (end-window GM tube)
  at 14:02:40. Counting started then: that is t = 0 in the file.
- Multichannel scaler, 400 channels, dwell time 2.0 s a channel, no gap between
  channels. `decay.csv`: `t_s` is the start of each channel, `counts` what the
  scaler recorded in it.
- Tube dead time is 100 us: nothing to correct at these rates.
- The tube counts the room background as well. It was not measured separately
  for this run; it does not change over a run.
- One activity only: the foil is a single element, and its other activation
  product has a half-life of days.
""")
print("%d counts in %d channels, %d of them empty, %d below 10" % (counts.sum(), CHANNELS, (counts == 0).sum(), (counts < 10).sum()))
