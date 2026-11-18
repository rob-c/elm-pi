"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

An hour of leakage-current readings from an autoranging picoammeter, one every
5 s. The logger writes each reading with the unit of the range it was taken on:
below 1000 nA in nA, from 1000 nA up in uA. The quiet current is 940 +- 24 nA,
so nearly every row is in nA; the micro-discharge spikes (6.5% of the readings,
a few hundred nA on top) are the rows in uA. Read without the unit column, a
spike of 1.38 uA is 1.38 "nA": the mean comes out 9% low and the median four
of its standard errors low, both looking like currents.

The data are noise by construction; what the task checks is arithmetic on the
file, so the verifier holds the numbers computed from it (see there), not the
940 nA used here.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261117)

READINGS, STEP_S = 720, 5.0
QUIET_NA, NOISE_NA = 940.0, 24.0
SPIKE_FRACTION, SPIKE_NA = 0.065, 350.0

current = rng.normal(QUIET_NA, NOISE_NA, READINGS)
spikes = rng.random(READINGS) < SPIKE_FRACTION
current[spikes] += rng.exponential(SPIKE_NA, spikes.sum())
bias = rng.normal(120.0, 0.004, READINGS)
temperature = 21.3 + 0.2 * np.sin(np.arange(READINGS) / 230.0) + rng.normal(0, 0.02, READINGS)

lines = ["time_s,bias_v,current,unit,temp_c"]
for i in range(READINGS):
    value, unit = (current[i], "nA") if current[i] < 1000.0 else (current[i] / 1000.0, "uA")
    lines.append("%.0f,%.3f,%.6g,%s,%.2f" % (i * STEP_S, bias[i], value, unit, temperature[i]))
(out / "scan.csv").write_text("\n".join(lines) + "\n")
print("%d readings, %d of them in uA (first at row %d)" % (READINGS, (current >= 1000).sum(), int(np.argmax(current >= 1000)) + 1))
