"""What the task is built to catch.

The beam energy used as the energy in k (the reduced mass is right); the cross section
from the two waves that were asked for, s and p, though k R is above 2; and the
scattering length in the usual nuclear convention, k cot(delta) = -1/a, not the one the
notes ask for.
"""
import json
import math

from scipy.special import spherical_jn, spherical_yn

mu = 939.565 * 3727.379 / (939.565 + 3727.379)
h2m = 197.327**2 / (2 * mu)
v0, radius, energy = 24.0, 2.60, 25.0

k, big_k = math.sqrt(energy / h2m), math.sqrt((energy + v0) / h2m)
phases = []
for l in (0, 1):
    inside, d_inside = spherical_jn(l, big_k * radius), big_k * spherical_jn(l, big_k * radius, True)
    top = k * spherical_jn(l, k * radius, True) * inside - spherical_jn(l, k * radius) * d_inside
    bottom = k * spherical_yn(l, k * radius, True) * inside - spherical_yn(l, k * radius) * d_inside
    phases.append(math.atan2(top, bottom))
sigma = 4 * math.pi / k**2 * sum((2 * l + 1) * math.sin(p) ** 2 for l, p in enumerate(phases)) * 0.01

k0 = math.sqrt(v0 / h2m)
a = radius * (1 - math.tan(k0 * radius) / (k0 * radius))
r = radius * (1 - radius**2 / (3 * a**2) - 1 / (k0**2 * a * radius))
json.dump({"delta0_deg": math.degrees(phases[0]) % 180, "delta1_deg": math.degrees(phases[1]) % 180, "sigma_b": sigma,
           "scattering_length_fm": a, "effective_range_fm": r}, open("result.json", "w"))
