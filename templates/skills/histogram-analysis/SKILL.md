---
name: histogram-analysis
description: "Building and analysing histograms and event selections correctly: binning, per-bin Poisson errors, normalisation and densities, weighted events, background subtraction, efficiency-corrected yields, and ROOT/uproot/hist usage. Use for any binned data, spectra, event selections or particle-physics style analysis."
---

# Histograms and event selections

## Binning and errors

- Choose bins from the resolution: bin width comparable to (not much smaller
  than) the detector resolution, enough entries per bin for the fit you plan.
  State the range and width; keep under/overflow counts.
- Unweighted counts: σ = √N per bin for display. For N = 0 the error is not
  zero - show nothing or use Poisson (Garwood) intervals; for fits use a
  Poisson likelihood (see `data-fitting`).
- Weighted events: the per-bin error is √(Σ wᵢ²), not √(Σ wᵢ). Keep the sum of
  squared weights (`hist` with `storage=hist.storage.Weight()`, ROOT `Sumw2`).

## Normalisation

Say which: raw counts, counts per bin width (density: divide by the width, and
the integral then has units of events), unit area (shape comparisons only),
or normalised to luminosity (σ × L × ε). Compare data with simulation at the
same normalisation, and state the luminosity and cross sections used.

## Selections

- Report a cut flow: events remaining after each cut, and efficiency with
  binomial errors (see `statistics-and-significance`).
- Decide cuts before looking at the signal region when the result is a search
  (blinding); if you optimised on the data, say so.
- Background subtraction: propagate the background's statistical and
  systematic error; a subtracted bin can be negative - do not clip it to zero
  before fitting.
- Efficiency-corrected yield N/ε: propagate the efficiency's error; correlated
  if ε comes from the same sample.

## Tools

- `uproot` to read/write ROOT files, `awkward` for jagged arrays, `hist` (and
  `mplhep` for HEP-style plots) for histograms in Python.
- ROOT in C++ or PyROOT when the analysis already uses it: `TH1D`, call
  `Sumw2()` before filling weighted events, `TH1::Fit` with option `"L"` for a
  Poisson likelihood fit on counts.
- Plot: data as points with error bars, simulation as filled stacked
  histograms, ratio or pull panel underneath, axis label "Events / (X MeV)".
