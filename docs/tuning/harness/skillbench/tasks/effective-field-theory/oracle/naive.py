"""What the task is built to catch: "C/Lambda^2 = g g'/M^2" for every operator.

The heavy propagator is replaced by 1/M^2 without its sign, and the operator
with two identical currents gets the same coefficient as the mixed one,
without the 1/2. The cross-section formulae are right, so the interference
term comes out constructive where the Z' in fact interferes destructively.
"""
import json
import math

M_ZPRIME, G_E, G_TAU, LAMBDA = 3000.0, 0.40, 0.60, 1000.0
E2 = 4 * math.pi / 128

c_ee = G_E**2 * LAMBDA**2 / M_ZPRIME**2
c_etau = G_E * G_TAU * LAMBDA**2 / M_ZPRIME**2
x = c_etau * 1000.0**2 / (E2 * LAMBDA**2)
json.dump({"c_ee": c_ee, "c_etau": c_etau, "r_lin": 2 * x, "r_quad": x * x,
           "sqrt_s_max_gev": math.sqrt(0.4 * E2 * LAMBDA**2 / c_etau)}, open("result.json", "w"), indent=1)
