"""Writes environment/ for this task. The reference limits are in the verifier, nowhere a session can read them.

    python make_environment.py <environment dir>

Nothing is random: one bin, 41 events observed on a background of 50 +- 10, and a signal of
35.0 +- 3.5 events per fb. The count is 0.7 sigma below the background, so CLs and CLs+b are far
apart, and the background uncertainty is larger than sqrt(b), so a limit without it is far too strong.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

OBSERVED = 41
BACKGROUND, BACKGROUND_UNC = 50.0, 10.0
SIGNAL_PER_FB, SIGNAL_UNC = 35.0, 3.5

(out / "yields.csv").write_text(
    "quantity,value,uncertainty\n"
    "observed,%d,\n"
    "background,%.1f,%.1f\n"
    "signal_per_fb,%.1f,%.1f\n" % (OBSERVED, BACKGROUND, BACKGROUND_UNC, SIGNAL_PER_FB, SIGNAL_UNC))
(out / "notes.md").write_text("""# Heavy-resonance search, high-mass signal region: numbers after unblinding

One signal region, one bin: events with m(jj) above 2.1 TeV. `yields.csv` has
the three inputs.

- `observed`: events in data, 140 fb-1.
- `background`: the expected background in the bin, from the fit of the dijet
  function to the sideband, extrapolated under the signal region. Its
  uncertainty is the total one - the fit's statistical error and the spread
  between fit functions - and is taken as Gaussian.
- `signal_per_fb`: the signal events expected in the bin for a production
  cross-section times branching fraction of 1 fb, that is acceptance x
  efficiency x luminosity. Its uncertainty covers the luminosity, the jet
  energy scale and resolution, and the acceptance; also Gaussian.

The two uncertainties are independent of each other.

## How results are quoted

As in the collaboration's statistics recommendations: upper limits on the
cross-section times branching fraction at 95% confidence level with the CLs
criterion. An observed limit is always shown next to the limit expected for
background only: its median and the +-1 sigma band.
""")
print("written")
