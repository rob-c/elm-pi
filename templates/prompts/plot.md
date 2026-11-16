---
description: Plot data properly, then look at the figure you made
argument-hint: "[what to plot, and against what]"
---
Plot ${1:-the data in this project}. Write a script that produces the figure,
keep the script, and look at the figure before you report it.

- Axes labelled with the quantity **and its units**; a legend where there is
  more than one series; tick labels readable when printed in a single column.
- Error bars wherever the data have uncertainties, from those uncertainties -
  never invented ones. A fit drawn as a line over the data's own range, with
  the fit parameters and their uncertainties in the legend or the reply.
- Residuals underneath when there is a fit, on the same x range.
- Data as points, models as lines; no smoothing that hides the scatter; no
  truncated axis that exaggerates a difference.
- Log axes where the quantity spans decades, and say so.

Then `view` the file you wrote - a PNG or a PDF page - and report what you see:
the range covered, whether the error bars are visible, any label overlapping or
cut off, and what the figure shows that the numbers do not. A figure you have
not looked at is not finished.
