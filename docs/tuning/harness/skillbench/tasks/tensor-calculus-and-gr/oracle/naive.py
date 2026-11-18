"""What the task is built to catch: the curvature computed with the usual textbook definition.

R^r_{smn} = d_m Gamma^r_{ns} - d_n Gamma^r_{ms} + Gamma^r_{ml} Gamma^l_{ns} - Gamma^r_{nl} Gamma^l_{ms},
R_{mn} = R^r_{mrn}: the Misner-Thorne-Wheeler convention, which is also what
sympy.diffgeom returns. The note defines the Riemann tensor with the opposite
sign, so every Ricci component and the Ricci scalar come out with the wrong
sign. The Kretschmann scalar is right.
"""
import json

import sympy as sp

t, r, theta, phi = sp.symbols("t r theta phi", positive=True)
M, Q = sp.Integer(1), sp.Rational(4, 5)
x = [t, r, theta, phi]
f = 1 - 2 * M / r
area = r * (r - Q ** 2 / M)
g = sp.diag(-f, 1 / f, area, area * sp.sin(theta) ** 2)
ginv = g.inv()
n = 4
gamma = [[[sum(ginv[a, s] * (sp.diff(g[s, b], x[c]) + sp.diff(g[s, c], x[b]) - sp.diff(g[b, c], x[s])) for s in range(n)) / 2
           for c in range(n)] for b in range(n)] for a in range(n)]


def riemann(a, b, c, e):
    return (sp.diff(gamma[a][e][b], x[c]) - sp.diff(gamma[a][c][b], x[e])
            + sum(gamma[a][c][l] * gamma[l][e][b] - gamma[a][e][l] * gamma[l][c][b] for l in range(n)))


full = [[[[sp.simplify(riemann(a, b, c, e)) for e in range(n)] for c in range(n)] for b in range(n)] for a in range(n)]
ricci = [[sp.simplify(sum(full[a][b][a][e] for a in range(n))) for e in range(n)] for b in range(n)]
scalar = sum(ginv[b, b] * ricci[b][b] for b in range(n))
kretschmann = sum((g[a, a] * full[a][b][c][e]) ** 2 * ginv[a, a] * ginv[b, b] * ginv[c, c] * ginv[e, e]
                  for a in range(n) for b in range(n) for c in range(n) for e in range(n))
at = {r: 3, theta: sp.pi / 3}
value = lambda expression: float(sp.simplify(expression).subs(at))
json.dump({"ricci_tt": value(ricci[0][0]), "ricci_rr": value(ricci[1][1]), "ricci_thth": value(ricci[2][2]),
           "ricci_phph": value(ricci[3][3]), "ricci_scalar": value(scalar), "kretschmann": value(kretschmann)},
          open("result.json", "w"), indent=1)
