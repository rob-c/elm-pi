"""What the task is built to catch.

The event plane from all the tracks of the event, each track then correlated with that
plane - its own Q-vector still in it - and no resolution correction; the error is that
of the mean. And sqrt(s_NN) with the kinetic energy taken as the beam energy.
"""
import json
import math

import numpy as np

values = []
for line in open("events.txt"):
    phi = np.array(line.split(), dtype=float)
    psi = 0.5 * math.atan2(np.sin(2 * phi).sum(), np.cos(2 * phi).sum())
    values.extend(np.cos(2 * (phi - psi)))
values = np.array(values)
json.dump({"v2": values.mean(), "v2_stat": values.std() / math.sqrt(len(values)),
           "sqrt_snn_gev": math.sqrt(2 * 0.9389**2 + 2 * 0.9389 * 30.0)}, open("result.json", "w"))
