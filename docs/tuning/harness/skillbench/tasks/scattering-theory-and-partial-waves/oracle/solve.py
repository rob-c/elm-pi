"""The reference solution: run in the project folder, writes result.json.

Analytic square well: inside, the regular solution is j_l(K r) with
K^2 = k^2 + 2 mu V0 / hbar^2; its logarithmic derivative at R is matched to
cos(delta) j_l(k r) - sin(delta) n_l(k r). k is from the reduced mass and the
centre-of-mass energy, E_lab x M / (m + M). The cross section is summed until the next
wave adds nothing. Scattering length and effective range from the closed forms, turned
into the notes' convention k cot(delta_0) = 1/a + r k^2 / 2 (the opposite sign of a to
the usual nuclear one).

Confirmed numerically: the radial equation integrated outwards and matched at two radii
beyond the well, and a fit to k cot(delta_0) at low energy.
"""
import json
import math

import numpy as np
from scipy.integrate import solve_ivp
from scipy.special import spherical_jn, spherical_yn

M_N, M_HE, HBARC = 939.565, 3727.379, 197.327          # notes.md
V0, RADIUS, E_LAB = 24.0, 2.60, 25.0

mu = M_N * M_HE / (M_N + M_HE)
h2m = HBARC**2 / (2 * mu)                              # hbar^2 / 2 mu, MeV fm^2
e_cm = E_LAB * M_HE / (M_N + M_HE)


def delta(l, energy):
    """Phase shift of partial wave l at centre-of-mass energy `energy`, radians."""
    k, big_k = math.sqrt(energy / h2m), math.sqrt((energy + V0) / h2m)
    x, y = k * RADIUS, big_k * RADIUS
    inside, d_inside = spherical_jn(l, y), big_k * spherical_jn(l, y, True)
    top = k * spherical_jn(l, x, True) * inside - spherical_jn(l, x) * d_inside
    bottom = k * spherical_yn(l, x, True) * inside - spherical_yn(l, x) * d_inside
    return math.atan2(top, bottom)


def delta_numerical(l, energy, match):
    """The same from u'' = [l(l+1)/r^2 - (E - V)/h2m] u, integrated to `match` > RADIUS."""
    k = math.sqrt(energy / h2m)

    def rhs(r, y, depth):
        return [y[1], (l * (l + 1) / r**2 - (energy + depth) / h2m) * y[0]]

    start = 1e-4
    y = [start ** (l + 1), (l + 1) * start**l]
    for a, b, depth in ((start, RADIUS, V0), (RADIUS, match, 0.0)):       # stop at the edge: V jumps there
        y = solve_ivp(rhs, (a, b), y, args=(depth,), rtol=1e-11, atol=1e-14).y[:, -1]
    log_derivative, x = y[1] / y[0], k * match
    f, df = x * spherical_jn(l, x), k * (spherical_jn(l, x) + x * spherical_jn(l, x, True))
    g, dg = -x * spherical_yn(l, x), -k * (spherical_yn(l, x) + x * spherical_yn(l, x, True))
    return math.atan2(df - log_derivative * f, log_derivative * g - dg)


k = math.sqrt(e_cm / h2m)
phases, total, l = [], 0.0, 0
while True:
    phases.append(delta(l, e_cm))
    term = (2 * l + 1) * math.sin(phases[-1]) ** 2
    total += term
    if l > k * RADIUS and term < 1e-10 * total:
        break
    l += 1
sigma_b = 4 * math.pi / k**2 * total * 0.01            # 1 fm^2 = 0.01 b

k0 = math.sqrt(V0 / h2m)
a_nuclear = RADIUS * (1 - math.tan(k0 * RADIUS) / (k0 * RADIUS))           # k cot(delta) = -1/a + ...
effective_range = RADIUS * (1 - RADIUS**2 / (3 * a_nuclear**2) - 1 / (k0**2 * a_nuclear * RADIUS))
scattering_length = -a_nuclear                                             # k cot(delta) = +1/a + ...


def degrees(angle):
    return math.degrees(angle) % 180.0


json.dump({"delta0_deg": degrees(phases[0]), "delta1_deg": degrees(phases[1]), "sigma_b": sigma_b,
           "scattering_length_fm": scattering_length, "effective_range_fm": effective_range},
          open("result.json", "w"), indent=1)

print("mu %.3f MeV, hbar^2/2mu %.4f MeV fm^2, E_cm %.4f MeV, k %.5f /fm, kR %.2f" % (mu, h2m, e_cm, k, k * RADIUS))
for wave, phase in enumerate(phases[:5]):
    numerical = [degrees(delta_numerical(wave, e_cm, match)) for match in (3.0, 6.0)]
    print("l=%d: delta %.4f deg; numerical, matched at 3 and 6 fm: %.4f %.4f; (2l+1) sin^2 = %.5f"
          % (wave, degrees(phase), numerical[0], numerical[1], (2 * wave + 1) * math.sin(phase) ** 2))
print("sigma %.5f b from %d waves" % (sigma_b, len(phases)))
energies = np.linspace(0.005, 0.2, 40)
k2 = energies / h2m
k_cot = np.array([math.sqrt(q) / math.tan(delta(0, e)) for q, e in zip(k2, energies)])
c2, c1, c0 = np.polyfit(k2, k_cot, 2)
print("a %.4f fm, r %.4f fm (k cot delta = 1/a + r k^2/2); fitted below 0.2 MeV: %.4f, %.4f; 4 pi a^2 = %.4f b, sigma(1 keV) = %.4f b"
      % (scattering_length, effective_range, 1 / c0, 2 * c1, 4 * math.pi * a_nuclear**2 * 0.01,
         4 * math.pi / (1e-3 / h2m) * math.sin(delta(0, 1e-3)) ** 2 * 0.01))
