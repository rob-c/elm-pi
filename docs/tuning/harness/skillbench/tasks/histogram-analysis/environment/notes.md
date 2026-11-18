# Signal yield in the mass spectrum, 2026 data

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
