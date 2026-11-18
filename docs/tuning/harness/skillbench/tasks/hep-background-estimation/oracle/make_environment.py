"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Multijet yields are generated with a correlation between the two ABCD variables, the same in the
b-tagged set and in the b-veto validation set: the pass-pass region holds KAPPA times what
B x C / D gives. Prompt-lepton events are added at exactly their simulated yields, and the data
are Poisson counts of the sum.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
# The first seed from 20261117 on whose counts give a correct estimate within half a standard deviation of
# the truth (20261117 itself has region B one sigma high): the check is of the method, not of a fluctuation.
rng = np.random.default_rng(20261118)

KAPPA = 0.65
# Expected multijet yields in the fail regions; A follows from KAPPA.
MULTIJET = {"B": 372.0, "C": 2300.0, "D": 9200.0, "VB": 1890.0, "VC": 3625.0, "VD": 14500.0}
MULTIJET["A"] = KAPPA * MULTIJET["B"] * MULTIJET["C"] / MULTIJET["D"]            # 60.45: what the task asks for
MULTIJET["VA"] = KAPPA * MULTIJET["VB"] * MULTIJET["VC"] / MULTIJET["VD"]
# Simulated prompt-lepton yields and their total uncertainties.
PROMPT = {"A": (512.0, 49.0), "B": (200.0, 24.0), "C": (575.0, 60.0), "D": (240.0, 28.0),
          "VA": (30.0, 5.0), "VB": (20.0, 4.0), "VC": (90.0, 12.0), "VD": (60.0, 9.0)}
WHERE = {"A": ("isolated", "high", ">=1"), "B": ("anti-isolated", "high", ">=1"), "C": ("isolated", "low", ">=1"),
         "D": ("anti-isolated", "low", ">=1"), "VA": ("isolated", "high", "0"), "VB": ("anti-isolated", "high", "0"),
         "VC": ("isolated", "low", "0"), "VD": ("anti-isolated", "low", "0")}

rows = ["region,isolation,met,b_tags,data,prompt_mc,prompt_mc_unc\n"]
for region in ("A", "B", "C", "D", "VA", "VB", "VC", "VD"):
    count = rng.poisson(MULTIJET[region] + PROMPT[region][0])
    rows.append("%s,%s,%s,%s,%s,%.1f,%.1f\n" % ((region,) + WHERE[region] + ("" if region == "A" else str(count),) + PROMPT[region]))
(out / "regions.csv").write_text("".join(rows))
(out / "notes.md").write_text("""# Multijet background in the single-muon search

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
""")
print("true multijet in A: %.2f; uncorrected B*C/D: %.2f" % (MULTIJET["A"], MULTIJET["A"] / KAPPA))
