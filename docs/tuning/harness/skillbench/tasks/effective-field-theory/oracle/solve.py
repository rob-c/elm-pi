"""The reference solution: run in the project folder, writes result.json.

Matching. At tree level and leading order in 1/M^2 the Z' equation of motion
from L = 1/2 M^2 Z'^2 + Z'.J is Z' = -J/M^2, so L_eff = -J.J/(2 M^2) with
J = g_e (ebar gamma e) + g_tau (taubar gamma tau):

    C_etau / Lambda^2 = - g_e g_tau / M^2        C_ee / Lambda^2 = - g_e^2 / (2 M^2)

(done with sympy below). The same from the Feynman rules, a vertex being i times
the Lagrangian term and the Z' propagator -i g_{mu nu}/(q^2 - M^2): Z' exchange
gives (i g_e)(i g_tau)(-i)/(s - M^2) = i g_e g_tau/(s - M^2) -> -i g_e g_tau/M^2
times the current-current structure, where the photon gives +i e^2/s.

Cross section. Photon and contact term multiply the same structure, so
sigma / sigma_SM = (1 + x)^2 with x = C_etau s / (e^2 Lambda^2):
r_lin = 2 x, r_quad = x^2, and |r_quad| = 0.2 |r_lin| at |x| = 0.4.
Checked against the full theory, (1 + g_e g_tau s / (e^2 (s - M^2)))^2, which
the EFT must approach as s/M^2 -> 0.
"""
import json
import math

import sympy

M_ZPRIME, G_E, G_TAU = 3000.0, 0.40, 0.60      # notes.md; GeV
LAMBDA = 1000.0
E2 = 4 * math.pi / 128                         # e^2
CHARGE = -1.0                                  # of the electron and of the tau
ROOT_S = 1000.0                                # the request
QUAD_OVER_LIN = 0.20                           # the validity criterion

# --- matching, from the equation of motion ---------------------------------------------
z, je, jtau, ge, gtau, mass = sympy.symbols("Z j_e j_tau g_e g_tau M")
lagrangian = mass**2 * z**2 / 2 + z * (ge * je + gtau * jtau)
effective = sympy.expand(lagrangian.subs(z, sympy.solve(sympy.diff(lagrangian, z), z)[0]))
numbers = {ge: G_E, gtau: G_TAU, mass: M_ZPRIME}
c_ee = float(effective.coeff(je, 2).subs(numbers)) * LAMBDA**2
c_etau = float(effective.coeff(je, 1).coeff(jtau, 1).subs(numbers)) * LAMBDA**2
c_tautau = float(effective.coeff(jtau, 2).subs(numbers)) * LAMBDA**2


# --- matching, from the Feynman rules ------------------------------------------------------
# Each function is i M with the common structure (vbar gamma^mu u)(ubar gamma_mu v) taken out.
def photon(s):
    vertex = -1j * math.sqrt(E2) * CHARGE
    return vertex * vertex * (-1j / s)


def zprime(q2, coupling1, coupling2):
    return (1j * coupling1) * (1j * coupling2) * (-1j / (q2 - M_ZPRIME**2))


def contact(coefficient, attachments=1):
    """attachments: 2! for an operator made of two identical currents."""
    return 1j * attachments * coefficient / LAMBDA**2


LOW = 1.0                                      # GeV^2, where s/M^2 = 1e-7
assert abs(contact(c_etau) / zprime(LOW, G_E, G_TAU) - 1) < 1e-6           # e- e+ -> tau- tau+, s channel
assert abs(contact(c_ee, 2) / zprime(-LOW, G_E, G_E) - 1) < 1e-6           # e- e- -> e- e-, t channel
assert abs(contact(c_tautau, 2) / zprime(-LOW, G_TAU, G_TAU) - 1) < 1e-6


# --- the cross section ---------------------------------------------------------------------
def x(root_s):
    """Contact amplitude over photon amplitude: real, and the same for every helicity."""
    ratio = contact(c_etau) / photon(root_s**2)
    assert abs(ratio.imag) < 1e-15
    return ratio.real


def full_theory_ratio(root_s):
    s = root_s**2
    return abs(1 + zprime(s, G_E, G_TAU) / photon(s)) ** 2


r_lin, r_quad = 2 * x(ROOT_S), x(ROOT_S) ** 2
root_s_max = math.sqrt(2 * QUAD_OVER_LIN * E2 * LAMBDA**2 / abs(c_etau))
assert abs(x(root_s_max) ** 2 / abs(2 * x(root_s_max)) - QUAD_OVER_LIN) < 1e-12
# EFT against the full theory: the difference is the dimension-eight term, relative size s/M^2.
for root_s in (30.0, 100.0, 300.0):
    eft = 2 * x(root_s) + x(root_s) ** 2
    full = full_theory_ratio(root_s) - 1
    assert abs(eft / full - 1) < 1.5 * root_s**2 / M_ZPRIME**2, "EFT does not approach the full theory"

result = {"c_ee": c_ee, "c_etau": c_etau, "r_lin": r_lin, "r_quad": r_quad, "sqrt_s_max_gev": root_s_max}
json.dump(result, open("result.json", "w"), indent=1)
for key, value in result.items():
    print("%-15s %.9g" % (key, value))
print("at %.0f GeV: EFT %.4f (linear only %.4f), full theory %.4f" % (ROOT_S, 1 + r_lin + r_quad, 1 + r_lin, full_theory_ratio(ROOT_S)))
