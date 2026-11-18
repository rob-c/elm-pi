"""The reference solution: run in the project folder, writes result.json.

Route 1: Christoffel symbols, Riemann, Ricci, the scalar and the Kretschmann
scalar from the definitions exactly as notes.md writes them (Weinberg's),
symbolically, then evaluated at the point.

Route 2: sympy.diffgeom's own Ricci and Riemann components. Its sign
convention is found by running both routes on the unit sphere first: the
note's definition gives R = -2 there, sympy's gives +2, so sympy's Ricci
tensor is multiplied by that ratio before the two routes are compared.

Physics checks: the Ricci scalar of this solution is fixed by the dilaton,
e^{-2 phi} = 1 - Q^2/(M r), as R = -2 g^{rr} (phi')^2 in the note's convention;
the Ricci tensor has no off-diagonal components; and for Q = 0 the Ricci tensor
vanishes and K = 48 M^2 / r^6 (Schwarzschild).
"""
import json
import re

import sympy as sp
from sympy.diffgeom import CoordSystem, Manifold, Patch, TensorProduct, metric_to_Ricci_components, metric_to_Riemann_components


def curvature(metric, coordinates):
    """Ricci tensor, Ricci scalar and Kretschmann scalar with the definitions of notes.md."""
    n = len(coordinates)
    inverse = metric.inv()
    d = lambda expression, index: sp.diff(expression, coordinates[index])
    gamma = [[[sp.simplify(sum(inverse[l, s] * (d(metric[s, k], m) + d(metric[s, m], k) - d(metric[m, k], s)) for s in range(n)) / 2)
               for k in range(n)] for m in range(n)] for l in range(n)]                       # gamma[l][m][k] = Gamma^l_{mk}
    riemann = [[[[sp.simplify(d(gamma[l][m][nu], k) - d(gamma[l][m][k], nu)
                              + sum(gamma[e][m][nu] * gamma[l][k][e] - gamma[e][m][k] * gamma[l][nu][e] for e in range(n)))
                  for k in range(n)] for nu in range(n)] for m in range(n)] for l in range(n)]   # riemann[l][m][nu][k] = R^l_{m nu k}
    ricci = sp.Matrix(n, n, lambda m, k: sp.simplify(sum(riemann[l][m][l][k] for l in range(n))))
    scalar = sp.simplify(sum(inverse[m, k] * ricci[m, k] for m in range(n) for k in range(n)))
    lowered = [[[[sum(metric[l, s] * riemann[s][m][nu][k] for s in range(n)) for k in range(n)] for nu in range(n)]
                for m in range(n)] for l in range(n)]
    indices = range(n)
    kretschmann = sp.simplify(sum(                    # the metric is diagonal: each index is raised by one factor
        lowered[l][m][nu][k] ** 2 * inverse[l, l] * inverse[m, m] * inverse[nu, nu] * inverse[k, k]
        for l in indices for m in indices for nu in indices for k in indices))
    return ricci, scalar, kretschmann


def diffgeom_curvature(diagonal, symbols):
    """The same three from sympy.diffgeom, in sympy's own sign convention; `diagonal` is the list of g_ii."""
    system = CoordSystem("chart", Patch("patch", Manifold("manifold", len(symbols))), symbols)
    scalars, forms = system.base_scalars(), system.base_oneforms()
    to_fields = dict(zip(symbols, scalars))
    back = dict(zip(scalars, symbols))
    # xreplace, not subs: a coordinate field contains its chart's symbols, and subs would go on to replace those.
    components = [sp.sympify(g).xreplace(to_fields) for g in diagonal]
    metric = sum((g * TensorProduct(form, form) for g, form in zip(components, forms)), sp.Integer(0))
    ricci = sp.Matrix(metric_to_Ricci_components(metric)).xreplace(back)
    riemann = metric_to_Riemann_components(metric)        # R^a_{bcd}
    n = len(symbols)
    values = [sp.sympify(g) for g in diagonal]
    scalar = sp.simplify(sum(ricci[i, i] / values[i] for i in range(n)))
    kretschmann = sp.simplify(sum((values[a] * riemann[a, b, c, e].xreplace(back)) ** 2 / (values[a] * values[b] * values[c] * values[e])
                                  for a in range(n) for b in range(n) for c in range(n) for e in range(n)))
    return ricci.applyfunc(sp.simplify), scalar, kretschmann


# The sign convention of each route, from the unit sphere.
theta, phi = sp.symbols("theta phi", positive=True)
sphere = [sp.Integer(1), sp.sin(theta) ** 2]
_, sphere_note, _ = curvature(sp.diag(*sphere), [theta, phi])
_, sphere_sympy, _ = diffgeom_curvature(sphere, [theta, phi])
assert sphere_note == -2 and sphere_sympy == 2, (sphere_note, sphere_sympy)
sign = sphere_note / sphere_sympy

# The black hole.
t, r, M, Q = sp.symbols("t r M Q", positive=True)
f = 1 - 2 * M / r
area = r * (r - Q ** 2 / M)
diagonal = [-f, 1 / f, area, area * sp.sin(theta) ** 2]
coordinates = [t, r, theta, phi]
ricci, scalar, kretschmann = curvature(sp.diag(*diagonal), coordinates)
ricci_sympy, scalar_sympy, kretschmann_sympy = diffgeom_curvature(diagonal, coordinates)
assert (ricci - sign * ricci_sympy).applyfunc(sp.simplify) == sp.zeros(4, 4), "the two routes disagree on the Ricci tensor"
assert sp.simplify(scalar - sign * scalar_sympy) == 0
assert sp.simplify(kretschmann - kretschmann_sympy) == 0
assert all(ricci[i, j] == 0 for i in range(4) for j in range(4) if i != j)
dilaton = -sp.log(1 - Q ** 2 / (M * r)) / 2
assert sp.simplify(scalar + 2 * f * sp.diff(dilaton, r) ** 2) == 0, "R is not what the dilaton equation gives"
assert sp.simplify(kretschmann.subs(Q, 0) - 48 * M ** 2 / r ** 6) == 0
assert all(sp.simplify(ricci[i, i].subs(Q, 0)) == 0 for i in range(4))

note = open("notes.md", encoding="utf-8").read()
where = re.search(r"M = (\S+), Q = (\S+), at the point r = (\S+), theta = ([^\s(]+)", note)
point = dict(zip((M, Q, r, theta), (sp.nsimplify(text.rstrip(",")) for text in where.groups())))
value = lambda expression: float(expression.subs(point))
result = {"ricci_tt": value(ricci[0, 0]), "ricci_rr": value(ricci[1, 1]), "ricci_thth": value(ricci[2, 2]),
          "ricci_phph": value(ricci[3, 3]), "ricci_scalar": value(scalar), "kretschmann": value(kretschmann)}
json.dump(result, open("result.json", "w"), indent=1)
print("R_tt =", sp.factor(ricci[0, 0]), "\nR_rr =", sp.factor(ricci[1, 1]), "\nR_thth =", sp.factor(ricci[2, 2]),
      "\nR_phph =", sp.factor(ricci[3, 3]), "\nR =", sp.factor(scalar), "\nK =", sp.factor(kretschmann))
print(point, result)
