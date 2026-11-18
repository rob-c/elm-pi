# Checking our gluino model against the jets + missing-momentum search

## The search

Zero leptons, jets and missing transverse momentum, 139 fb^-1 at 13 TeV.
What it published, and what we have here:

- signal_regions.csv: for its two signal regions the observed events, the
  fitted background with its uncertainty, and the model-independent 95% CL
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
  0.70. The rest goes through heavier charginos and neutralinos into final
  states with leptons, for which the search gives no efficiencies; we do not
  count those events.
- Points to check (gluino mass, LSP mass, GeV): p1 (1900, 400); p2 (1800, 1000); p3 (1600, 1400).
