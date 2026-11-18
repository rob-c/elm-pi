"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

ACTIVITY_REF = 41_300.0          # Bq on the reference date: what the task asks for
HALF_LIFE_Y = 5.2711
ELAPSED_Y = 2.000                # reference date to the count
LIVE, REAL = 3000.0, 3600.0      # s: 16.7% dead time
I_GAMMA = {1173.228: 0.9985, 1332.492: 0.999826}
GAIN, OFFSET = 0.5, 0.4          # keV = OFFSET + GAIN * channel
EFF = {600.0: 0.004350, 900.0: 0.003120, 1100.0: 0.002650, 1250.0: 0.002390, 1400.0: 0.002180, 1700.0: 0.001860}


def efficiency(energy):
    """The curve the points in notes.md lie on: ln(eff) quadratic in ln(E)."""
    x, y = np.log(list(EFF)), np.log(list(EFF.values()))
    return float(np.exp(np.polyval(np.polyfit(x, y, 2), np.log(energy))))


activity_now = ACTIVITY_REF * 0.5 ** (ELAPSED_Y / HALF_LIFE_Y)
channels = np.arange(4096)
energy = OFFSET + GAIN * channels
# Continuum: a falling background plus the Compton plateaux below each line.
expected = 40.0 * np.exp(-energy / 900.0) + 6.0
for line, intensity in I_GAMMA.items():
    area = activity_now * intensity * efficiency(line) * LIVE
    sigma = 0.85 / 2.355 * np.sqrt(line / 1332.5) / GAIN * 2.0   # channels; FWHM about 1.7 keV at 1332
    expected += area * np.exp(-0.5 * ((channels - (line - OFFSET) / GAIN) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
    edge = 2 * line**2 / (511.0 + 2 * line)
    expected += np.where(energy < edge, 0.012 * area / 100.0, 0.0)
counts = rng.poisson(expected)
(out / "spectrum.csv").write_text("channel,counts\n" + "".join("%d,%d\n" % row for row in zip(channels, counts)))
(out / "notes.md").write_text("""# Co-60 check source, HPGe detector 2

- Source: Co-60 point source, certificate reference date 2024-11-17 12:00 UTC.
- Counted 2026-11-17, starting 12:00 UTC, on the 10 cm shelf (the geometry the
  efficiency calibration below was made in).
- MCA: 4096 channels. Real time 3600 s, live time 3000 s.
- Energy calibration: E [keV] = 0.4 + 0.5 x channel.

## Decay data (ENSDF, as on the source certificate)

- Half-life of Co-60: 5.2711 y (take 1 y = 365.25 d).
- 1173.228 keV, emission probability 0.9985
- 1332.492 keV, emission probability 0.999826

## Full-energy-peak efficiency, 10 cm shelf, point source

Measured last month with the calibrated multi-nuclide source. Each point has a
relative standard uncertainty of 1.5%, common to the whole curve.

| E [keV] | efficiency |
|---|---|
| 600 | 0.004350 |
| 900 | 0.003120 |
| 1100 | 0.002650 |
| 1250 | 0.002390 |
| 1400 | 0.002180 |
| 1700 | 0.001860 |
""")
print("activity at the count: %.1f Bq; reference: %.1f Bq" % (activity_now, ACTIVITY_REF))
