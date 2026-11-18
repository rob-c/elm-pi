"""Writes environment/ for this task. The truth is printed here and copied to the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A jet-mass spectrum, 15 bins of 10 GeV with a resolution of 10 GeV, so that about 37% of the
reconstructed events of a bin were generated in it. The simulation falls exponentially; the "data"
are the same spectrum times 1 + 3 exp(-(m - 105)^2 / (2 x 18^2)), a broad enhancement the simulation
does not have, well inside the range so that the simulated fake fractions at its two ends hold for
the data. Both go through the same detector: an efficiency rising from 0.66 to 0.86, a shift of
-0.5 GeV and the Gaussian resolution. 4 million data events, 12 million simulated.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

LOW, HIGH, BINS = 30.0, 180.0, 15
EDGES = np.linspace(LOW, HIGH, BINS + 1)
N_DATA, N_MC = 4_000_000, 12_000_000
RESOLUTION, SHIFT, SLOPE = 10.0, -0.5, 60.0
AMPLITUDE, CENTRE, WIDTH = 3.0, 105.0, 18.0


def generate(n, enhanced):
    """Particle-level masses from 5 GeV up; with the enhancement, by accept-reject."""
    kept = []
    while sum(len(k) for k in kept) < n:
        mass = 5.0 + rng.exponential(SLOPE, size=n)
        mass = mass[mass < 400.0]
        if enhanced:
            ratio = 1 + AMPLITUDE * np.exp(-0.5 * ((mass - CENTRE) / WIDTH) ** 2)
            mass = mass[rng.random(len(mass)) < ratio / (1 + AMPLITUDE)]
        kept.append(mass)
    return np.concatenate(kept)[:n]


def reconstruct(mass):
    """Reconstructed mass, NaN where the jet is not reconstructed or fails the selection."""
    efficiency = 0.62 + 0.24 * (1 - np.exp(-(mass - 5.0) / 50.0))
    found = rng.random(len(mass)) < efficiency
    return np.where(found, mass + rng.normal(SHIFT, RESOLUTION, len(mass)), np.nan)


def inside(values):
    return (values >= LOW) & (values < HIGH)


truth_mc = generate(N_MC, False)
reco_mc = reconstruct(truth_mc)
truth_data = generate(N_DATA, True)
reco_data = reconstruct(truth_data)

both = inside(truth_mc) & inside(reco_mc)
response = np.histogram2d(reco_mc[both], truth_mc[both], bins=[EDGES, EDGES])[0].astype(int)       # [reco, truth]
mc_truth = np.histogram(truth_mc[inside(truth_mc)], EDGES)[0]
mc_reco = np.histogram(reco_mc[inside(reco_mc)], EDGES)[0]
mc_fake = np.histogram(reco_mc[inside(reco_mc) & ~inside(truth_mc)], EDGES)[0]
data = np.histogram(reco_data[inside(reco_data)], EDGES)[0]
true_spectrum = np.histogram(truth_data[inside(truth_data)], EDGES)[0]

lines = ["bin,m_low,m_high,data,mc_reco,mc_reco_fake,mc_truth\n"]
for i in range(BINS):
    lines.append("%d,%.0f,%.0f,%d,%d,%d,%d\n" % (i + 1, EDGES[i], EDGES[i + 1], data[i], mc_reco[i], mc_fake[i], mc_truth[i]))
(out / "spectra.csv").write_text("".join(lines))
header = "reco_bin," + ",".join("truth_%d" % (j + 1) for j in range(BINS)) + "\n"
(out / "response.csv").write_text(header + "".join("%d," % (i + 1) + ",".join(str(v) for v in response[i]) + "\n" for i in range(BINS)))
(out / "notes.md").write_text("""# Leading-jet mass: inputs for the particle-level spectrum

Groomed mass of the leading large-radius jet, 30 to 180 GeV in 15 bins of
10 GeV; the same binning at detector level and at particle level. The mass
resolution is about 10 GeV.

Particle level (the fiducial region): the leading particle-level jet has
pT > 400 GeV, |y| < 2.0, and a groomed mass between 30 and 180 GeV.

## spectra.csv, one row per bin

- `data`: events observed with the reconstructed mass in the bin.
- `mc_reco`: simulated events reconstructed in the bin.
- `mc_reco_fake`: those of `mc_reco` whose particle-level jet is outside the
  fiducial region (in practice its mass is below 30 or above 180 GeV).
- `mc_truth`: simulated events generated in the bin at particle level, inside
  the fiducial region, reconstructed or not.

## response.csv

Simulated events that are inside the fiducial region at particle level and
reconstructed between 30 and 180 GeV: row = bin of the reconstructed mass,
column = bin of the particle-level mass.

## Remarks

- The simulated counts are raw numbers of events, not normalised to the data.
  The simulated sample is about three times the size of the data.
- The simulation is the multijet sample only. It is known not to describe the
  shape of the data around 100 GeV, and it has not been reweighted.
- Other backgrounds are negligible in this selection.
""")
print("TRUTH =", true_spectrum.tolist())
print("total %d; data %d events in range; purity of the central bins %.2f" % (true_spectrum.sum(), data.sum(), response[7, 7] / response[7].sum()))
