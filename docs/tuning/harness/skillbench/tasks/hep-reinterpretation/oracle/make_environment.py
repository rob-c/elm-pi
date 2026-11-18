"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A published search with two signal regions and only counts and model-
independent limits for each: SR-2j saw fewer events than expected (observed
limit 34, expected 56), SR-4j more (observed 13.6, expected 8.2). For the
second model point the region with the best expected limit is SR-4j, which
does not exclude it, while SR-2j's lucky observed limit would. Nothing is
random here: the map is a smooth function and the numbers are chosen.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])

LUMI_FB = 139.0
BRANCHING = 0.70                 # gluino -> q qbar LSP in our model; the map is for 100%
REGIONS = {                      # n observed, background, its uncertainty, S95 observed, S95 expected
    "SR-2j": (262, 301.0, 24.0, 34.0, 56.0),
    "SR-4j": (14, 8.3, 1.6, 13.6, 8.2),
}
XSEC_PB = {1400: 0.0284, 1500: 0.0157, 1600: 0.00887, 1700: 0.00507, 1800: 0.00293, 1900: 0.00171,
           2000: 0.00101, 2100: 0.000598, 2200: 0.000356, 2300: 0.000213, 2400: 0.000128}
POINTS = {"p1": (1900, 400), "p2": (1800, 1000), "p3": (1600, 1400)}


def acceptance_x_efficiency(m_gluino, m_lsp):
    """(SR-2j, SR-4j): SR-2j peaks at a mass splitting of 650 GeV, SR-4j turns on above 1100."""
    split = m_gluino - m_lsp
    heavier = (m_gluino - 1400) / 1000.0
    sr2j = 0.24 * np.exp(-0.5 * ((split - 650) / 260.0) ** 2) * (0.9 + 0.1 * heavier) + 0.03
    sr4j = 0.42 / (1 + np.exp(-(split - 1100) / 170.0)) * (0.75 + 0.25 * heavier)
    return round(float(sr2j), 4), round(float(sr4j), 4)


grid = {(m_gluino, m_lsp): acceptance_x_efficiency(m_gluino, m_lsp)
        for m_gluino in range(1400, 2401, 200) for m_lsp in range(0, m_gluino - 199, 200)}
(out / "efficiency_map.csv").write_text("m_gluino_gev,m_lsp_gev,acc_x_eff_sr2j,acc_x_eff_sr4j\n" + "".join(
    "%d,%d,%.4f,%.4f\n" % (*masses, *values) for masses, values in grid.items()))
(out / "signal_regions.csv").write_text("region,n_observed,n_background,background_uncertainty,s95_observed,s95_expected\n" + "".join(
    "%s,%d,%.1f,%.1f,%.1f,%.1f\n" % (name, *row) for name, row in REGIONS.items()))
(out / "cross_sections.csv").write_text("m_gluino_gev,xsec_pb\n" + "".join("%d,%.3e\n" % item for item in XSEC_PB.items()))

(out / "notes.md").write_text("""# Checking our gluino model against the jets + missing-momentum search

## The search

Zero leptons, jets and missing transverse momentum, %(lumi).0f fb^-1 at 13 TeV.
What it published, and what we have here:

- signal_regions.csv: for its two signal regions the observed events, the
  fitted background with its uncertainty, and the model-independent 95%% CL
  upper limits on the number of signal events, observed (s95_observed) and
  expected for background only (s95_expected). No likelihood and no
  correlations between the regions were published.
- efficiency_map.csv: acceptance x efficiency of each signal region for the
  simplified model the search used - gluino pair production with both gluinos
  decaying promptly to q qbar + neutralino (the LSP) - on a grid of gluino and
  LSP mass in steps of 200 GeV. We have reproduced the search's cut flow and its
  exclusion contour for this simplified model with these numbers.

## Our model

- Gluino pair production; cross_sections.csv has the cross-section
  (NNLO+NNLL) against gluino mass, in pb.
- Each gluino decays promptly to q qbar + LSP with a branching fraction of
  %(br).2f. The rest goes through heavier charginos and neutralinos into final
  states with leptons, for which the search gives no efficiencies; we do not
  count those events.
- Points to check (gluino mass, LSP mass, GeV): %(points)s.
""" % dict(lumi=LUMI_FB, br=BRANCHING,
           points="; ".join("%s (%d, %d)" % (name, *masses) for name, masses in POINTS.items())))


def from_map(m_gluino, m_lsp):
    """The map's value, interpolated linearly in gluino mass between the two nearest columns."""
    if (m_gluino, m_lsp) in grid:
        return grid[(m_gluino, m_lsp)]
    low = 200 * (m_gluino // 200)
    weight = (m_gluino - low) / 200.0
    return tuple((1 - weight) * a + weight * b for a, b in zip(grid[(low, m_lsp)], grid[(low + 200, m_lsp)]))


for name, (m_gluino, m_lsp) in POINTS.items():
    produced = XSEC_PB[m_gluino] * 1000.0 * LUMI_FB * BRANCHING**2
    yields = [produced * value for value in from_map(m_gluino, m_lsp)]
    r_expected = [n / REGIONS[region][4] for n, region in zip(yields, REGIONS)]
    r_observed = [n / REGIONS[region][3] for n, region in zip(yields, REGIONS)]
    best = int(np.argmax(r_expected))
    print("%s (%d, %d): map %s (the function itself: %s)" % (name, m_gluino, m_lsp, np.round(from_map(m_gluino, m_lsp), 4),
                                                             acceptance_x_efficiency(m_gluino, m_lsp)))
    print("   yields SR-2j %.2f, SR-4j %.2f; r expected %.3f, %.3f; r observed %.3f, %.3f"
          % (*yields, *r_expected, *r_observed))
    print("   best expected: %s, r = %.3f, %s;   best observed would say r = %.3f"
          % (list(REGIONS)[best], r_observed[best], "excluded" if r_observed[best] > 1 else "not excluded", max(r_observed)))
