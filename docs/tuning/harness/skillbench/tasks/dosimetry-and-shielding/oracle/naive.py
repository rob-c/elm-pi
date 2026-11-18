"""What the task is built to catch: narrow-beam attenuation for a broad-beam shield.

The unshielded dose rate is done properly. The wall is then exp(-mu x) with no build-up
factor, and the thickness for the target is ln(ratio)/mu.
"""
import json
import math

activity = 2.00 * 3.7e10 * 0.5 ** (10.0 / 30.05)
fluence_rate = activity * 0.851 / (4 * math.pi * 250.0**2)
unshielded = fluence_rate * 0.6617 * 0.0323 * 1.602177e-10 * 3600 * 1e6
mu = 0.0775 * 2.30
json.dump({"unshielded_ugy_per_h": unshielded,
           "shielded_ugy_per_h": unshielded * math.exp(-mu * 30.0),
           "thickness_cm": math.log(unshielded / 2.0) / mu}, open("result.json", "w"))
