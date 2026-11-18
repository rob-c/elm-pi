# X -> l+ l- search, full 2026 dataset: unblinding

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
