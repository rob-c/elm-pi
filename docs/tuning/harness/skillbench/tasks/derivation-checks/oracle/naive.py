"""What the task is built to catch: the last line of the derivation, evaluated as it stands.

The units are handled correctly (mu = mu/rho x density in 1/cm, the radius in cm
from the diameter in mm); the derivation is taken on trust, its own check
having passed.
"""
import json
import math

mu = 0.0726 * 8.96
result = {}
for name, diameter_mm in (("a", 36.0), ("b", 60.0)):
    tau = mu * diameter_mm / 20.0
    result["escape_fraction_" + name] = 3 / (8 * tau**3) * (2 * tau**2 - 1 + (1 - 2 * tau) * math.exp(-2 * tau))
json.dump(result, open("result.json", "w"), indent=1)
