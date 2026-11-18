"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Nothing is random: the yields are the nominal ones times the shifts chosen below.
"""
import math
import sys
from pathlib import Path

out = Path(sys.argv[1])

NOMINAL = {"sr": 412.6, "cr": 2954.1}
STAT = {"sr": 9.1, "cr": 27.4}                     # sqrt(sum w^2) of the nominal sample
# Relative shifts in per cent, (SR, CR), for each row of yields.csv.
SHIFTS = {
    "lumi_up": (+1.7, +1.7), "lumi_down": (-1.7, -1.7),             # cancels in the ratio
    "pileup_up": (+0.9, +1.4), "pileup_down": (-1.2, -1.5),
    "jes_up": (+6.3, +3.9), "jes_down": (-5.6, -3.6),               # partly cancels
    "jer_smear": (-3.4, -1.2),                                      # one-sided
    "btag_up": (+3.1, -1.4), "btag_down": (-3.0, +1.4),             # tag in SR, veto in CR: opposite signs
    "muon_up": (+1.3, +1.3), "muon_down": (-1.3, -1.3),             # cancels
    "generator_alt": (-8.2, -5.9),                                  # two-point
}

rows = ["variation,sr_yield,cr_yield\n", "nominal,%.1f,%.1f\n" % (NOMINAL["sr"], NOMINAL["cr"])]
for name, (sr, cr) in SHIFTS.items():
    rows.append("%s,%.1f,%.1f\n" % (name, NOMINAL["sr"] * (1 + sr / 100), NOMINAL["cr"] * (1 + cr / 100)))
(out / "yields.csv").write_text("".join(rows))
(out / "notes.md").write_text("""# W+jets background: systematic variations of the simulated yields

The W+jets yield in the signal region (SR: one muon, four jets, at least one
b-tagged) is taken from the control region (CR: same, with a b-jet veto) as

    N_SR = N_CR(data, other backgrounds subtracted) x TF,    TF = MC(SR) / MC(CR).

`yields.csv` has the simulated W+jets yields in both regions (events in
138 fb-1): the nominal ones, and one row per systematic variation. Every
variation was made by shifting the source by one standard deviation where it
enters and rerunning the whole selection, on the same simulated events unless
said.

| rows | source | what was shifted |
|---|---|---|
| lumi_up, lumi_down | integrated luminosity | +-1.7% |
| pileup_up, pileup_down | pile-up reweighting | minimum-bias cross-section, +-4.6% |
| jes_up, jes_down | jet energy scale | all jets by the total scale uncertainty |
| jer_smear | jet energy resolution | simulated jets smeared further by the resolution uncertainty; the resolution can only be made worse, so there is no opposite variation |
| btag_up, btag_down | b-tagging scale factors | efficiency and mistag scale factors together |
| muon_up, muon_down | muon scale factors | trigger, identification and isolation together |
| generator_alt | W+jets modelling | the alternative generator sample in place of the nominal one; a comparison of two models, so a single row |

## Conventions (unchanged from the last round)

- Each source in the table is one nuisance parameter: a shift of it acts on SR
  and CR at once. The sources are independent of each other.
- A source with an up and a down row enters a quantity with half the
  difference between that quantity's up and down values. A source with a single
  row enters with the full difference from the nominal value, taken in both
  directions.
- The statistical uncertainty of the simulated sample counts as a systematic
  uncertainty of the estimate. For the nominal yields sqrt(sum of squared
  weights) is SR_STAT events in SR and CR_STAT in CR; the regions share no events.
- Relative uncertainties are quoted in per cent of the nominal value.
""".replace("SR_STAT", "%.1f" % STAT["sr"]).replace("CR_STAT", "%.1f" % STAT["cr"]))

# The answers, from the shifts as designed (not from the rounded file).
tf_var, sr_var = 0.0, 0.0
sources = {}
for name, pair in SHIFTS.items():
    sources.setdefault(name.rsplit("_", 1)[0] if name.endswith(("_up", "_down")) else name, []).append(pair)
for name, pairs in sources.items():
    ratio = [100 * ((1 + sr / 100) / (1 + cr / 100) - 1) for sr, cr in pairs]
    sr_shift = (pairs[0][0] - pairs[1][0]) / 2 if len(pairs) == 2 else pairs[0][0]
    tf_shift = (ratio[0] - ratio[1]) / 2 if len(pairs) == 2 else ratio[0]
    sr_var += sr_shift**2
    tf_var += tf_shift**2
    print("%-14s SR %+6.2f%%   TF %+6.2f%%" % (name, sr_shift, tf_shift))
stat = {key: 100 * STAT[key] / NOMINAL[key] for key in STAT}
sr_var += stat["sr"] ** 2
tf_var += stat["sr"] ** 2 + stat["cr"] ** 2
print("TF %.5f; SR total %.3f%%; TF total %.3f%%" % (NOMINAL["sr"] / NOMINAL["cr"], math.sqrt(sr_var), math.sqrt(tf_var)))
