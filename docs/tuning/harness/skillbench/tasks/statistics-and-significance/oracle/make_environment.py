"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A dilepton search after unblinding, two channels. The counts are chosen, the
masses drawn flat inside each region (no candidate within 5 MeV of an edge, so
counting them is not the test):

    ee      9 in the window, 3 in sidebands 1.5 times as wide: background 2.0 +- 1.2
    mumu    1 in the window, 2 in sidebands 4 times as wide:   background 0.5 +- 0.35

What follows from them is in verifier/test_outputs.py.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

REGIONS = {
    # channel: (signal window, the two sidebands, events in the window, events in the sidebands)
    "ee": ((9.60, 10.00), ((9.30, 9.60), (10.00, 10.30)), 9, (2, 1)),
    "mumu": ((9.70, 9.90), ((9.30, 9.70), (9.90, 10.30)), 1, (1, 1)),
}
EDGE = 0.005

rows = []
for channel, (window, sidebands, n_window, n_side) in REGIONS.items():
    for (low, high), n in [(window, n_window)] + list(zip(sidebands, n_side)):
        rows += [(channel, m) for m in rng.uniform(low + EDGE, high - EDGE, n)]
# In run order, as the selection job writes them.
runs = np.sort(rng.integers(41200, 43900, len(rows)))
lines = ["run,event,channel,mass_gev"]
for run, index in zip(runs, rng.permutation(len(rows))):
    channel, mass = rows[index]
    lines.append("%d,%d,%s,%.4f" % (run, rng.integers(1, 9_000_000), channel, mass))
(out / "candidates.csv").write_text("\n".join(lines) + "\n")
(out / "notes.md").write_text("""# X -> l+ l- search, full 2026 dataset: unblinding

Regions were frozen in the note of 2026-09-30, before the signal windows were
opened. The fit range is 9.30-10.30 GeV in both channels; `candidates.csv` has
every candidate in it that passes the final selection.

| channel | signal window [GeV] | sidebands [GeV] |
|---|---|---|
| ee | 9.60 - 10.00 | 9.30 - 9.60 and 10.00 - 10.30 |
| mumu | 9.70 - 9.90 | 9.30 - 9.70 and 9.90 - 10.30 |

- The mumu window is narrower because the mass resolution is better there; each
  window holds essentially all of the signal in its channel.
- Background: combinatorial, flat in mass over the fit range in both channels
  (same-sign sample, 2026-10-08). The simulation predicts no peaking background.
  So the background in a window is estimated from that channel's sidebands,
  which hold no signal.
- The two channels are treated separately; no combination yet.
""")
for channel, (window, sidebands, n_window, n_side) in REGIONS.items():
    tau = sum(b - a for a, b in sidebands) / (window[1] - window[0])
    print("%s: %d in the window, %d in the sidebands, sidebands %.2f times as wide" % (channel, n_window, sum(n_side), tau))
