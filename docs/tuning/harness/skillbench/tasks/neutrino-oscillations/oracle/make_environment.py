"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

The unoscillated muon-neutrino event spectrum at a far detector 295 km away, in
10 MeV bins, and six much wider analysis bins. Below 800 MeV the survival
probability swings from 1 to 0 and back inside one analysis bin, so it has to
be averaged over the spectrum in the bin; at a bin's centre it is 0.996 where
the bin's average is 0.56.
"""
import sys
from pathlib import Path

import numpy as np
from scipy import integrate, stats

out = Path(sys.argv[1])

BASELINE_KM = 295.0
SIN2_THETA23 = 0.545
DM2_32 = 2.47e-3                 # eV^2
N_UNOSCILLATED = 1480.0          # events in 200 to 3000 MeV for this exposure
FINE = np.arange(200, 3000 + 1, 10)                          # MeV
ANALYSIS = [200, 400, 600, 800, 1200, 2000, 3000]            # MeV


def shape_cdf(e_mev):
    """Unoscillated spectrum: an off-axis peak near 600 MeV and a high-energy tail."""
    return stats.gamma.cdf(e_mev, 4.2, scale=170.0) + 0.14 * stats.gamma.cdf(e_mev, 2.6, scale=620.0)


def shape_pdf(e_mev):
    return stats.gamma.pdf(e_mev, 4.2, scale=170.0) + 0.14 * stats.gamma.pdf(e_mev, 2.6, scale=620.0)


scale = N_UNOSCILLATED / (shape_cdf(3000.0) - shape_cdf(200.0))


def survival(e_mev):
    sin2_2theta = 4 * SIN2_THETA23 * (1 - SIN2_THETA23)
    return 1 - sin2_2theta * np.sin(1.267 * DM2_32 * BASELINE_KM / (e_mev / 1000.0)) ** 2


events = scale * np.diff(shape_cdf(FINE))
(out / "unoscillated.csv").write_text("e_low_mev,e_high_mev,events\n" + "".join(
    "%d,%d,%.4f\n" % row for row in zip(FINE[:-1], FINE[1:], events)))

(out / "notes.md").write_text("""# Far-detector muon-neutrino sample: truth-level cross-check of the fit inputs

- Beam: muon neutrinos, off-axis; far detector at a baseline of %(baseline).0f km.
- unoscillated.csv: expected numu charged-current events in the far detector
  for the current exposure if there were no oscillations, in %(step)d MeV bins of
  true neutrino energy from %(low)d to %(high)d MeV (flux x cross-section x
  efficiency, from the beam and detector simulation).
- For this cross-check: numu disappearance in the two-flavour approximation
  with theta23 and dm2_32, in vacuum. No theta13 correction, no matter effect,
  no energy smearing.
- Oscillation parameters, the best fit of our last analysis:
  sin^2(theta23) = %(s23).3f, dm2_32 = %(dm2).2e eV^2.
- Analysis bins (true energy, MeV): %(bins)s.
""" % dict(baseline=BASELINE_KM, step=FINE[1] - FINE[0], low=FINE[0], high=FINE[-1], s23=SIN2_THETA23, dm2=DM2_32,
           bins=", ".join("%d-%d" % pair for pair in zip(ANALYSIS[:-1], ANALYSIS[1:]))))

# The truth: the continuous spectrum times the survival probability, integrated over each analysis bin.
print("bin [MeV]      unoscillated  oscillated  ratio   P at centre   from the 10 MeV table")
total = 0.0
for low, high in zip(ANALYSIS[:-1], ANALYSIS[1:]):
    grid = np.linspace(low, high, 200_001)
    oscillated = scale * integrate.simpson(shape_pdf(grid) * survival(grid), x=grid)
    plain = scale * (shape_cdf(high) - shape_cdf(low))
    inside = (FINE[:-1] >= low) & (FINE[1:] <= high)
    table = np.sum(events[inside] * survival(0.5 * (FINE[:-1] + FINE[1:])[inside]))
    total += oscillated
    print("%4d-%4d  %12.3f  %10.3f  %.4f  %.4f        %.3f" % (low, high, plain, oscillated, oscillated / plain,
                                                             survival(0.5 * (low + high)), table))
print("total oscillated %.3f of %.1f" % (total, N_UNOSCILLATED))
