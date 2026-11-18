"""The reference solution: run in the project folder, writes result.json.

With g_* constant, dY/dx = -(s <sigma v> / (H x)) (Y^2 - Y_eq^2), and from the
note's H and s (reduced Planck mass)

    s / (H x) = (2 pi sqrt(90) / 45) (g_*s / sqrt(g_*)) Mbar_Pl m / x^2,
    Y_eq      = (45 / (2 pi^2)) (g / g_*s) (2 pi)^(-3/2) x^(3/2) exp(-x),
    <sigma v> = a + 6 b / x          (<v_rel^2> = 6 T / m),

a and b converted from cm^3/s with 1 GeV^-2 = (hbar c)^2 c.

The equation is stiff while Y tracks Y_eq: it is integrated in ln Y with an
implicit method (Radau) from x = 5, where Y = Y_eq, to x = 10^5, and the rest
of the way to x = infinity analytically (Y_eq is zero there, so 1/Y grows by
the integral of the coefficient).

Second route: Y itself with BDF from a different starting point and to a
different end point. Convergence: tolerances tightened, start and end moved.
And the freeze-out estimate Omega h^2 = 1.07e9 GeV^-1 x_f / (sqrt(g_*) M_Pl
(a + 3 b / x_f)), with the unreduced Planck mass, must agree to 25%.
"""
import json
import math
import re

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

note = open("relic.md", encoding="utf-8").read()


def read(pattern):
    return float(re.search(pattern + r"\s*=\s*([-+0-9.eE]+)", note).group(1))


m, g = read(r"mass m"), read(r"\bg")
a_cgs, b_cgs = read(r"\ba"), read(r"\bb")
g_star = read(r"g_\* = g_\*s")
g_star_s = g_star
mpl_reduced = read(r"\(8 pi G\)\^\(-1/2\)")
hbar_c, c_light = read(r"hbar c"), read(r"- c")
s_today, rho_crit = read(r"s_0"), read(r"rho_c / h\^2")

gev2_in_cm3_per_s = hbar_c ** 2 * c_light                 # 1 GeV^-2 as sigma v: 1.1673e-17 cm^3/s
a, b = a_cgs / gev2_in_cm3_per_s, b_cgs / gev2_in_cm3_per_s
strength = 2 * math.pi * math.sqrt(90.0) / 45.0 * g_star_s / math.sqrt(g_star) * mpl_reduced * m


def coefficient(x):
    """lambda(x) / x^2 in dY/dx = -(lambda / x^2) (Y^2 - Y_eq^2)."""
    return strength * (a + 6.0 * b / x) / x ** 2


def y_eq(x):
    return 45.0 / (2 * math.pi ** 2) * (g / g_star_s) * (2 * math.pi) ** -1.5 * x ** 1.5 * np.exp(-x)


def tail(x):
    """Integral of the coefficient from x to infinity."""
    return strength * (a / x + 3.0 * b / x ** 2)


def in_log(x_start=5.0, x_end=1e5, rtol=1e-9):
    solution = solve_ivp(lambda x, w: [-coefficient(x) * (math.exp(w[0]) - y_eq(x) ** 2 * math.exp(-w[0]))],
                         (x_start, x_end), [math.log(y_eq(x_start))], method="Radau", rtol=rtol, atol=1e-12, dense_output=True)
    assert solution.success, solution.message
    yield_of = lambda x: math.exp(solution.sol(x)[0])
    x_f = brentq(lambda x: yield_of(x) / y_eq(x) - 2.5, x_start + 1.0, 80.0)
    return x_f, 1.0 / (1.0 / yield_of(x_end) + tail(x_end))


def in_y(x_start=8.0, x_end=3e4, rtol=1e-9):
    solution = solve_ivp(lambda x, y: [-coefficient(x) * (y[0] ** 2 - y_eq(x) ** 2)], (x_start, x_end), [y_eq(x_start)],
                         method="BDF", jac=lambda x, y: [[-2.0 * coefficient(x) * y[0]]], rtol=rtol, atol=1e-22, dense_output=True)
    assert solution.success, solution.message
    yield_of = lambda x: solution.sol(x)[0]
    x_f = brentq(lambda x: yield_of(x) / y_eq(x) - 2.5, x_start + 1.0, 80.0)
    return x_f, 1.0 / (1.0 / yield_of(x_end) + tail(x_end))


x_f, y_today = in_log()
for label, (other_x_f, other_y) in {"Y with BDF": in_y(), "tighter tolerance": in_log(rtol=1e-11),
                                    "start at x = 3": in_log(x_start=3.0), "end at x = 1e6": in_log(x_end=1e6)}.items():
    print("%-18s x_f = %.4f, Y = %.5e" % (label, other_x_f, other_y))
    assert abs(other_x_f - x_f) < 2e-3 and abs(other_y / y_today - 1) < 1e-3, label
omega = m * y_today * s_today / rho_crit

mpl = math.sqrt(8 * math.pi) * mpl_reduced
estimate = 1.07e9 * x_f / (math.sqrt(g_star) * mpl * (a + 3.0 * b / x_f))
assert abs(estimate / omega - 1) < 0.25, (estimate, omega)

json.dump({"x_f": x_f, "y_today": y_today, "omega_h2": omega}, open("result.json", "w"), indent=1)
print("1 GeV^-2 = %.4e cm^3/s; a = %.4e, b = %.4e GeV^-2; M_Pl = %.4e GeV" % (gev2_in_cm3_per_s, a, b, mpl))
print("x_f = %.3f, Y today = %.4e, Omega h^2 = %.4f (freeze-out estimate %.3f)" % (x_f, y_today, omega, estimate))
