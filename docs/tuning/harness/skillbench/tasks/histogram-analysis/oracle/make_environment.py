"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir> [seed]

A peak over a falling background, six mass bins. The data are Poisson draws
from signal + background. The background simulation has a third of the data's
luminosity, and its events carry weights: a generator weight of +1 or -1 (12%
negative, as an NLO generator gives) times a pile-up weight (log-normal) times
scale factors. So a simulated event counts for about three data events, the
simulation's statistical error in a bin is about twice the data's, and it is
sqrt(sum of w^2), which sqrt(expected events) understates by a factor 2.

True numbers per bin (95-155 GeV, 10 GeV bins):

    background  900  760  640  540  460  390
    signal       40  620 1250  560   30    0     total 2500, 4281 before the efficiency of 0.584
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
# The first seed tried. The last bin (no signal) comes out negative after subtraction, as it
# does for half of all seeds, and the corrected yield is 0.13 standard deviations from the truth.
seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20261117
rng = np.random.default_rng(seed)

EDGES = np.arange(95.0, 155.0 + 1, 10.0)
BACKGROUND = np.array([900.0, 760.0, 640.0, 540.0, 460.0, 390.0])
SIGNAL = np.array([40.0, 620.0, 1250.0, 560.0, 30.0, 0.0])
EFFICIENCY, EFFICIENCY_ERR = 0.584, 0.032
XSEC_PB, LUMI_FB, SUMW_GENERATED = 61.5, 36.1, 7.403e5
SCALE = XSEC_PB * LUMI_FB * 1000 / SUMW_GENERATED            # expected events per unit of weight: 3.0
SKIM = (80.0, 200.0)                                         # the skim keeps more than the histogram shows


def weights(n):
    sign = np.where(rng.random(n) < 0.12, -1.0, 1.0)
    return sign * rng.lognormal(-0.08, 0.45, n) * rng.normal(0.985, 0.02, n)


def off_edge(masses):
    """Three decimals in the files: keep any value from landing exactly on a bin edge."""
    masses = np.round(masses, 3)
    on_edge = np.isin(masses, np.round(np.arange(SKIM[0], SKIM[1] + 1, 5.0), 3))
    return np.where(on_edge, masses + 0.001, masses)


mean_weight = weights(400_000).mean()
# Simulated background: in each bin, the number of events whose weights sum to the expected yield.
mc_mass, mc_weight = [], []
below, above = (SKIM[0], EDGES[0], 1500.0), (EDGES[-1], SKIM[1], 1150.0)       # outside the histogram
for low, high, expected in list(zip(EDGES[:-1], EDGES[1:], BACKGROUND)) + [below, above]:
    n = rng.poisson(expected / SCALE / mean_weight)
    mc_mass.append(rng.uniform(low, high, n))
    mc_weight.append(weights(n))
mc_mass, mc_weight = off_edge(np.concatenate(mc_mass)), np.concatenate(mc_weight)
order = rng.permutation(len(mc_mass))
(out / "background_mc.csv").write_text("m_gev,weight\n" + "".join("%.3f,%.5f\n" % (mc_mass[i], mc_weight[i]) for i in order))

data = []
for low, high, expected in list(zip(EDGES[:-1], EDGES[1:], BACKGROUND + SIGNAL)) + [below, above]:
    data.append(rng.uniform(low, high, rng.poisson(expected)))
data = off_edge(np.concatenate(data))
rng.shuffle(data)
(out / "data.csv").write_text("m_gev\n" + "".join("%.3f\n" % m for m in data))

(out / "notes.md").write_text("""# Signal yield in the mass spectrum, 2026 data

- `data.csv`: the data events passing the selection, one mass per line. The
  skim keeps 80-200 GeV.
- `background_mc.csv`: the simulated background passing the same selection.
  `weight` is the event's full weight: generator weight (NLO, so some are
  negative) x pile-up weight x lepton scale factors.
- Histogram for the result: 95 to 155 GeV in six bins of 10 GeV.

## Normalising the simulation

- Cross-section of the background process: 61.5 pb.
- Integrated luminosity of the data: 36.1 fb^-1.
- The sum of the generator weights over all generated events of the sample,
  before any selection, is 7.403e5.

## Efficiency

The fraction of signal events that pass the selection is 0.584 +- 0.032, from
the tag-and-probe study on the 2025 data (so independent of these two files).
The corrected yield is the background-subtracted signal divided by it.
""")

counts = np.histogram(data, EDGES)[0]
sumw = np.histogram(mc_mass, EDGES, weights=mc_weight)[0]
sumw2 = np.histogram(mc_mass, EDGES, weights=mc_weight**2)[0]
signal = counts - SCALE * sumw
error = np.sqrt(counts + SCALE**2 * sumw2)
total, total_err = signal.sum(), np.sqrt(np.sum(error**2))
corrected = total / EFFICIENCY
corrected_err = corrected * np.hypot(total_err / total, EFFICIENCY_ERR / EFFICIENCY)
print("seed %d: scale %.4f; %d simulated events in range, mean weight %.3f" % (seed, SCALE, np.sum((mc_mass >= 95) & (mc_mass < 155)), mean_weight))
print("signal    ", " ".join("%7.1f" % s for s in signal))
print("error     ", " ".join("%7.1f" % s for s in error))
print("sqrt(N+B) ", " ".join("%7.1f" % s for s in np.sqrt(counts + SCALE * sumw)))
print("pull      ", " ".join("%7.2f" % s for s in (signal - SIGNAL) / error))
print("corrected %.0f +- %.0f (truth %.0f, %.2f sigma); without the efficiency's error +- %.0f" % (
    corrected, corrected_err, SIGNAL.sum() / EFFICIENCY, (corrected - SIGNAL.sum() / EFFICIENCY) / corrected_err, total_err / EFFICIENCY))
