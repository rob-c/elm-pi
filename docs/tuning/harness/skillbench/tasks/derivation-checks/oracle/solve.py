"""The reference solution: run in the project folder, writes result.json.

The derivation is checked against its own starting point: the double integral
of step 2, done numerically for each sphere, is the answer whatever the algebra
says. Then each step is redone in sympy to find where the algebra leaves it
(step 5, the sign of the boundary term), and the corrected closed form is
checked against the integral and in the limit tau -> 0, where f must go to 1.
"""
import json
import re

import numpy as np
import sympy as sp
from scipy import integrate

text = open("derivation.md").read()
mu_rho = float(re.search(r"mu/rho = ([\d.]+) cm\^2/g", text).group(1))
density = float(re.search(r"density ([\d.]+) g/cm\^3", text).group(1))
diameter_mm = {name: float(d) for name, d in re.findall(r"\| ([AB]) \| ([\d.]+) mm \|", text)}
mu = mu_rho * density                                  # 1/cm


def from_the_definition(radius):
    """Step 2 as it stands: the survival probability averaged over the sphere."""
    volume = 4 / 3 * np.pi * radius**3
    inner = lambda rho: integrate.quad(lambda z, h: np.exp(-mu * (h - z)), -np.sqrt(radius**2 - rho**2), np.sqrt(radius**2 - rho**2),
                                       args=(np.sqrt(radius**2 - rho**2),), epsabs=1e-13, epsrel=1e-13)[0]
    return integrate.quad(lambda rho: 2 * np.pi * rho * inner(rho), 0, radius, epsabs=1e-12, epsrel=1e-12)[0] / volume


# The algebra, step by step.
R, m, h, t = sp.symbols("R mu h tau", positive=True)
I_right = sp.integrate(h * sp.exp(-2 * m * h), (h, 0, R))
I_written = R * sp.exp(-2 * m * R) / (2 * m) + (1 - sp.exp(-2 * m * R)) / (4 * m**2)
print("step 5 as written minus the integral:", sp.simplify(I_written - I_right))
closed = sp.simplify((2 * sp.pi / (m * sp.Rational(4, 3) * sp.pi * R**3) * (R**2 / 2 - I_right)).subs(m, t / R))
written = 3 / (8 * t**3) * (2 * t**2 - 1 + (1 - 2 * t) * sp.exp(-2 * t))
corrected = 3 / (8 * t**3) * (2 * t**2 - 1 + (1 + 2 * t) * sp.exp(-2 * t))
assert sp.simplify(closed - corrected) == 0
print("tau -> 0: corrected", sp.series(corrected, t, 0, 2), "| as written", sp.limit(written, t, 0))

result = {}
for name, diameter in diameter_mm.items():
    radius = diameter / 20.0                           # mm diameter -> cm radius
    tau = mu * radius
    numeric = from_the_definition(radius)
    formula = float(corrected.subs(t, tau))
    assert abs(numeric / formula - 1) < 1e-9, (numeric, formula)
    print("sphere %s: tau = %.4f, f = %.6f (integral), %.6f (corrected formula), %.6f (as written)" % (
        name, tau, numeric, formula, float(written.subs(t, tau))))
    result["escape_fraction_" + name.lower()] = numeric
json.dump(result, open("result.json", "w"), indent=1)
