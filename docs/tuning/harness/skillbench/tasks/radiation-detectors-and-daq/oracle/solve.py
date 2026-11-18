"""The reference solution: run in the project folder, writes result.json.

Channel A: non-extending dead time, n = m / (1 - m tau). Channel B: extending,
m = n exp(-n tau), which has two roots; the reading at 14 cm, predicted from
each root by the inverse square law, says which one is real. Accidentals for
two logic pulses of width tau in an overlap coincidence: 2 tau R1 R2.
"""
import json
import math
import re

from scipy.optimize import brentq
from scipy.special import lambertw

notes = open("notes.md").read()


def number(pattern, group=1):
    return float(re.search(pattern, notes).group(group).replace(" ", ""))


tau_a = number(r"blocks the channel for ([\d.]+) us") * 1e-6
rate_a = number(r"run position: ([\d ]+) counts in ([\d.]+) s") / number(r"run position: ([\d ]+) counts in ([\d.]+) s", 2)
tau_b = number(r"Output width ([\d.]+) us") * 1e-6
near, far = number(r"Strong source at ([\d.]+) cm"), number(r"pulled back to ([\d.]+) cm")
rate_b = number(r"source at [\d.]+ cm: ([\d ]+) counts in ([\d.]+) s") / number(r"source at [\d.]+ cm: ([\d ]+) counts in ([\d.]+) s", 2)
rate_b_far = number(r"pulled back to [\d.]+ cm: ([\d ]+) counts in ([\d.]+) s") \
    / number(r"pulled back to [\d.]+ cm: ([\d ]+) counts in ([\d.]+) s", 2)
width = number(r"logic pulse ([\d.]+) ns wide") * 1e-9
run = number(r"Run time ([\d.]+) s")
singles_a = number(r"inputs: A ([\d ]+) counts") / run
singles_b = number(r"B ([\d ]+) counts\. Coincidences") / run
coincidences = number(r"Coincidences: ([\d ]+) counts") / run

true_a = rate_a / (1 - rate_a * tau_a)

# m tau = x exp(-x): x below 1 on the principal branch of Lambert's W, above 1 on the other.
assert rate_b * tau_b < math.exp(-1), "above the largest rate an extending dead time can show"
roots = [float(-lambertw(-rate_b * tau_b, k).real) / tau_b for k in (0, -1)]
bracketed = [brentq(lambda n: n * math.exp(-n * tau_b) - rate_b, lo, hi, xtol=1e-6)
             for lo, hi in ((rate_b, 1 / tau_b), (1 / tau_b, 50 / tau_b))]
assert all(abs(a / b - 1) < 1e-9 for a, b in zip(roots, bracketed)), (roots, bracketed)


def reading_far(true_near):
    there = true_near * (near / far) ** 2
    return there * math.exp(-there * tau_b)


true_b = min(roots, key=lambda n: abs(reading_far(n) / rate_b_far - 1))
assert abs(reading_far(true_b) / rate_b_far - 1) < 0.01, "neither root explains the reading at the far position"

accidentals = 2 * width * singles_a * singles_b
true_coincidences = coincidences - accidentals

json.dump({"true_rate_a_per_s": true_a, "true_rate_b_per_s": true_b,
           "accidental_rate_per_s": accidentals, "true_coincidence_rate_per_s": true_coincidences},
          open("result.json", "w"), indent=1)
print("A: %.0f /s measured, %.0f /s true" % (rate_a, true_a))
print("B: %.0f /s measured; roots %.0f and %.0f /s; at %.0f cm they would read %.0f and %.0f /s, measured %.0f: true %.0f /s"
      % (rate_b, roots[0], roots[1], far, reading_far(roots[0]), reading_far(roots[1]), rate_b_far, true_b))
print("coincidences %.3f /s, accidentals %.3f /s, true %.3f /s" % (coincidences, accidentals, true_coincidences))
