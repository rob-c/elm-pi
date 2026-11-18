"""What the task is built to catch: the textbook equation with the note's Planck mass put straight in.

dY/dx = -(lambda / x^2) (Y^2 - Y_eq^2) with lambda = 0.264 (g_*s / sqrt(g_*)) M_Pl m <sigma v>
and Y_eq = 0.145 (g / g_*s) x^(3/2) exp(-x) is the usual textbook form, written for
M_Pl = G^(-1/2) = 1.22e19 GeV. The note gives the reduced Planck mass,
2.4353e18 GeV: used here as it stands, lambda is sqrt(8 pi) = 5 times too
small. Everything else - the unit conversion, <sigma v> = a + 6 b / x, a stiff
solver, the integration to large x - is done properly.
"""
import json
import math

from scipy.integrate import solve_ivp
from scipy.optimize import brentq

m, g, g_star = 150.0, 2.0, 86.25
planck_mass = 2.4353e18                                    # GeV, from the note
gev2 = (1.973270e-14) ** 2 * 2.997925e10                   # 1 GeV^-2 in cm^3/s
a, b = 0.8e-26 / gev2, 9.0e-26 / gev2
strength = 0.264 * g_star / math.sqrt(g_star) * planck_mass * m
y_eq = lambda x: 0.145 * (g / g_star) * x ** 1.5 * math.exp(-x)
coefficient = lambda x: strength * (a + 6 * b / x) / x ** 2

X_END = 1e5
solution = solve_ivp(lambda x, w: [-coefficient(x) * (math.exp(w[0]) - y_eq(x) ** 2 * math.exp(-w[0]))], (5.0, X_END),
                     [math.log(y_eq(5.0))], method="Radau", rtol=1e-9, atol=1e-12, dense_output=True)
yield_of = lambda x: math.exp(solution.sol(x)[0])
x_f = brentq(lambda x: yield_of(x) / y_eq(x) - 2.5, 6.0, 80.0)
y_today = yield_of(X_END)
json.dump({"x_f": x_f, "y_today": y_today, "omega_h2": m * y_today * 2891.2 / 1.0537e-5}, open("result.json", "w"), indent=1)
