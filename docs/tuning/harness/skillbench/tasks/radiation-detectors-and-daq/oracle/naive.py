"""What the task is built to catch: m = n exp(-n tau) solved by iterating n = m exp(n tau) from
the measured rate, which finds the low-rate root of a channel that is in fact saturated; and
accidentals as tau R1 R2 with tau the width of one logic pulse."""
import json
import math

rate_a, tau_a = 843_000 / 10.0, 2.50e-6
rate_b, tau_b = 2_479_480 / 10.0, 1.20e-6
true_a = rate_a / (1 - rate_a * tau_a)
true_b = rate_b
for _ in range(200):
    true_b = rate_b * math.exp(true_b * tau_b)

singles_a, singles_b, coincidences = 3_126_000 / 600.0, 2_322_000 / 600.0, 8772 / 600.0
accidentals = 40.0e-9 * singles_a * singles_b
json.dump({"true_rate_a_per_s": true_a, "true_rate_b_per_s": true_b,
           "accidental_rate_per_s": accidentals, "true_coincidence_rate_per_s": coincidences - accidentals},
          open("result.json", "w"), indent=1)
