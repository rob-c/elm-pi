# Multijet background in the single-muon search

The multijet background (a muon from a heavy-flavour decay or a misidentified
hadron) is not taken from simulation. It is estimated from data in regions
defined by two requirements on events that pass the rest of the selection:

- muon isolation: `isolated` is I_rel < 0.06; `anti-isolated` is 0.15 < I_rel < 0.50.
- missing transverse momentum: `high` is MET > 60 GeV; `low` is MET < 20 GeV.

| region | isolation | MET | role |
|---|---|---|---|
| A | isolated | high | signal region |
| B | anti-isolated | high | |
| C | isolated | low | |
| D | anti-isolated | low | |

Regions A to D require at least one b-tagged jet. VA to VD are the same four
regions with the b-tag requirement inverted (no b-tagged jet): the validation
set. No signal is expected there, the kinematics are otherwise the same, and
it was set up to test the multijet estimate before it is used.

## regions.csv

- `data`: events observed in 138 fb-1. Region A is blinded, so its count is
  not given.
- `prompt_mc`: simulated events with a prompt muon (W+jets, top pairs and
  single top, Z+jets, dibosons), normalised to 138 fb-1.
- `prompt_mc_unc`: the total uncertainty of that simulated yield, statistical
  and systematic together.

A benchmark signal (stop pair, m = 600 GeV) would add less than 0.5% to the
data in any of B, C and D.
