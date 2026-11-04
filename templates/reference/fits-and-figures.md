# Checking fits and figures

## Fits

Judge a fit by its statistics, not its appearance. Compute chi2 from the
measurement uncertainties (for counts with no stated errors, sqrt(N)), not from
the scatter of the residuals. chi2/ndf should be near 1 (within about
sqrt(2/ndf)): far below 1 means the uncertainties are overestimated or
correlated, far above means a wrong model or underestimated errors. Say which,
and do not call either a good fit. Look at the residuals.

## Figures and documents

Look at every figure and document you produce before you report it. Image and
PDF files a command writes are attached to its result; examine each one:

- what it shows, and whether that is what was asked for
- axis labels and units, ranges and scales
- legibility, overlapping text, empty or clipped panels
- whether a fit follows the data

Fix and regenerate what is wrong, and say in the report what each figure
shows. For one you are given or want to see again, call `view` (PDF pages with
their text, images; SVG and EPS are converted first). Save figures as PNG or
PDF.
