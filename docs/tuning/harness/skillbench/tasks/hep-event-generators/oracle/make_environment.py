"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

An MC@NLO sample: weights +1 and -1, the negative fraction falling with ptll, so
the signal region has fewer negative weights than the sample as a whole and
counting events is not the same as summing weights. events.csv is a skim, so
its own sum of weights is not the denominator either: that is in the card.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

N_WRITTEN = 40_000               # events passing the generator filter, all of them written
SIGMA_GEN_PB = 0.7603            # the generator's cross-section, Z undecayed
BR_Z_LL = 0.10099                # forced decay, three lepton flavours
FILTER_EFF = 0.584
K_FACTOR = 1.12
LUMI_FB = 140.0
TAU, LAM = 70.0, 100.0           # GeV: ptll falls as exp(-pt/TAU); negative fraction 0.18 + 0.25 exp(-pt/LAM)
P_NJET = {2: 0.10, 3: 0.45, 4: 0.27, 5: 0.12, 6: 0.045, 7: 0.015}
SKIM_PT, SR_PT, SR_NJET = 100.0, 150.0, 4

ptll = np.round(rng.exponential(TAU, N_WRITTEN), 2)
njet = rng.choice(list(P_NJET), size=N_WRITTEN, p=list(P_NJET.values()))
negative = rng.random(N_WRITTEN) < 0.18 + 0.25 * np.exp(-ptll / LAM)
weight = np.where(negative, -1, 1)
event = np.arange(1, N_WRITTEN + 1)
ptll[np.isin(ptll, (SKIM_PT, SR_PT))] += 0.01     # no event exactly on a cut: > and >= then agree

kept = ptll > SKIM_PT
rows = zip(event[kept], ptll[kept], njet[kept], weight[kept])
(out / "events.csv").write_text("event,ptll,njet,weight\n" + "".join("%d,%.2f,%d,%d\n" % row for row in rows))

sum_w = int(weight.sum())
(out / "notes.md").write_text("""# ttZ (Z -> ll) sample for the dilepton + jets channel

## Sample card

Copied from the production request and the generator log.

| | |
|---|---|
| Generator | MadGraph5_aMC@NLO 3.5.3 at NLO QCD, showered with Pythia 8.310 (MC@NLO matching) |
| Process | p p -> t t~ Z at 13 TeV, with the Z undecayed in the matrix element |
| Cross-section printed by the generator | %(sigma).4f pb |
| Decays | Z -> l+ l- (l = e, mu, tau) forced with MadSpin. BR(Z -> ll) = %(br).5f is not in the number above |
| Generator filter | two leptons with pT > 15 GeV and abs(eta) < 2.8. Efficiency %(filt).3f; events failing it were not written |
| k-factor | %(k).2f (to NLO+NNLL QCD with NLO electroweak corrections, same phase space) |
| Events written | %(n)d |
| Sum of the generator weights of the written events | %(sumw)d |

Every event has generator weight +1 or -1.

## events.csv

A skim of the written events for this channel: only events with
ptll > %(skim).0f GeV were kept, to save space. One row per event.

| column | |
|---|---|
| event | event number in the written sample |
| ptll | transverse momentum of the dilepton system, GeV |
| njet | number of selected jets |
| weight | generator weight |

ptll and njet are the quantities the selection cuts on.

## Signal region

ptll > %(srpt).0f GeV and njet >= %(srnj)d.

## Data

Full Run 2: %(lumi).0f fb^-1.
""" % dict(sigma=SIGMA_GEN_PB, br=BR_Z_LL, filt=FILTER_EFF, k=K_FACTOR, n=N_WRITTEN, sumw=sum_w,
           skim=SKIM_PT, srpt=SR_PT, srnj=SR_NJET, lumi=LUMI_FB))

# What the verifier holds: the estimate every correct method gets from these files...
in_sr = (ptll > SR_PT) & (njet >= SR_NJET)
per_weight = SIGMA_GEN_PB * BR_Z_LL * FILTER_EFF * K_FACTOR * LUMI_FB * 1000.0 / sum_w
estimate = per_weight * weight[in_sr].sum()
error = per_weight * np.sqrt(np.sum(weight[in_sr] ** 2.0))


# ...and what the model it was drawn from gives, to show the estimate is a fair draw.
def signed_fraction_above(cut):
    """Integral over ptll > cut of the ptll density times (1 - 2 x negative fraction)."""
    rate = 1 / TAU + 1 / LAM
    return 0.64 * np.exp(-cut / TAU) - 0.5 / (TAU * rate) * np.exp(-cut * rate)


p_njet = sum(p for n, p in P_NJET.items() if n >= SR_NJET)
truth = (SIGMA_GEN_PB * BR_Z_LL * FILTER_EFF * K_FACTOR * LUMI_FB * 1000.0
         * p_njet * signed_fraction_above(SR_PT) / signed_fraction_above(0.0))
print("rows kept %d; sum of weights written %d, in the file %d" % (kept.sum(), sum_w, weight[kept].sum()))
print("signal region: %d events, sum of weights %d" % (in_sr.sum(), weight[in_sr].sum()))
print("estimate %.2f +- %.2f events; the model gives %.2f (%.1f sigma away)"
      % (estimate, error, truth, (estimate - truth) / error))
