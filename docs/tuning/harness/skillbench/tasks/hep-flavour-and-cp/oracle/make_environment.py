"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Flavour-tagged B0 -> D+ D- candidates in bins of decay time, in three tagging
categories with mistag fractions of 8, 24 and 40%. Each category shows the
asymmetry S sin(dm t) - C cos(dm t) shrunk by its own dilution 1 - 2w, so the
raw asymmetry of the sample is about 0.37 of the true one.
"""
import sys
from pathlib import Path

import numpy as np
from scipy import integrate

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

S_TRUE, C_TRUE = -0.58, 0.14     # what the task asks for
DM, TAU = 0.5065, 1.517          # ps^-1, ps
SIGMA_T = 0.055                  # ps: decay-time resolution; it shrinks the oscillation by 0.04%
N_SIGNAL = 80_000                # signal candidates, tagged or not
CATEGORIES = {"A": (0.045, 0.08), "B": (0.110, 0.24), "C": (0.215, 0.40)}     # tagging efficiency, mistag fraction
EDGES = np.round(np.arange(0.3, 6.3 + 1e-9, 0.5), 1)   # ps: to 6.3, where the smallest category still has 20 events a bin


def rate(t):
    """Decay-time distribution after the displacement trigger's acceptance (not normalised)."""
    return (1 - np.exp(-t / 0.45)) * np.exp(-t / TAU)


def asymmetry(t):
    return np.exp(-0.5 * (DM * SIGMA_T) ** 2) * (S_TRUE * np.sin(DM * t) - C_TRUE * np.cos(DM * t))


norm = integrate.quad(rate, EDGES[0], EDGES[-1])[0]
rows, tagged = [], {}
for name, (efficiency, mistag) in CATEGORIES.items():
    tagged[name] = 0
    for low, high in zip(EDGES[:-1], EDGES[1:]):
        share = integrate.quad(rate, low, high)[0]
        mean_asymmetry = integrate.quad(lambda t: rate(t) * asymmetry(t), low, high)[0] / share
        n = rng.poisson(N_SIGNAL * efficiency * share / norm)
        n_bbar = rng.binomial(n, 0.5 * (1 + (1 - 2 * mistag) * mean_asymmetry))
        rows.append("%s,%.1f,%.1f,%d,%d\n" % (name, low, high, n - n_bbar, n_bbar))
        tagged[name] += n
(out / "counts.csv").write_text("category,t_low_ps,t_high_ps,n_b0_tag,n_b0bar_tag\n" + "".join(rows))

# The table's efficiencies are this sample's own, so the table and the counts agree.
table = "".join("| %s | %.4f | %.2f |\n" % (name, tagged[name] / N_SIGNAL, CATEGORIES[name][1]) for name in CATEGORIES)
(out / "notes.md").write_text("""# B0 -> D+ D-: flavour-tagged decay-time sample

## counts.csv

Signal candidates that have a flavour tag, background subtracted, in bins of
reconstructed decay time and in the three tagging categories.

| column | |
|---|---|
| category | tagging category |
| t_low_ps, t_high_ps | edges of the decay-time bin, ps |
| n_b0_tag | candidates tagged as B0 at production |
| n_b0bar_tag | candidates tagged as anti-B0 at production |

## Flavour tagging

Of the %(n)d signal candidates in this decay-time range, tagged or not:

| category | tagging efficiency | mistag fraction |
|---|---|---|
%(table)s
The mistag fractions were calibrated on the flavour-specific B0 -> Ds+ D-
sample and are the same for B0 and anti-B0. Production and detection
asymmetries are below 1%% and are neglected here.

## Decay time

- Mixing frequency: dm_d = %(dm).4f ps^-1 (PDG), to be kept fixed. B0 lifetime %(tau).3f ps.
- Decay-time resolution: %(res).0f fs.
- The trigger's acceptance falls at short decay times; it is the same for both
  tags.

## Convention

    A(t) = [Gamma(anti-B0(t) -> D+ D-) - Gamma(B0(t) -> D+ D-)] / [sum] = S sin(dm_d t) - C cos(dm_d t)

where B0(t) is a meson that was a B0 at production.
""" % dict(n=N_SIGNAL, table=table, dm=DM, tau=TAU, res=1000 * SIGMA_T))

power = sum(tagged[name] / N_SIGNAL * (1 - 2 * mistag) ** 2 for name, (_, mistag) in CATEGORIES.items())
total = sum(tagged.values()) / N_SIGNAL
average = sum(tagged[name] * mistag for name, (_, mistag) in CATEGORIES.items()) / sum(tagged.values())
print("tagged: %s; efficiency %.4f" % (tagged, total))
print("tagging power %.5f; from the average mistag %.3f it would be %.5f" % (power, average, total * (1 - 2 * average) ** 2))
