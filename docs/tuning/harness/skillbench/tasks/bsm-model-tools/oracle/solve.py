"""The reference solution: run in the project folder, writes result.json.

Every field of model.md is turned into left-handed Weyl multiplets (a
right-handed field enters as its conjugate: conjugate representation, -Y, -X),
and the six traces are taken in exact fractions with the multiplicities of
colour, weak isospin and generations. They are taken a second time state by
state, with explicit diagonal generators, and the two must agree. For
assignment B the traces are polynomials in z: their common root is the answer,
and the Higgs charge follows from each Yukawa term being a U(1)_X singlet.
"""
import json
import re
from fractions import Fraction

import sympy as sp

z = sp.Symbol("z")


def charge(text):
    return z if text == "z" else sp.Rational(str(Fraction(text)))


def read_fields(path="model.md"):
    """Rows of the field table: name, SU(3) dimension, SU(2) dimension, Y, copies, X_A, X_B."""
    fields = []
    for line in open(path, encoding="utf-8"):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 7 and re.fullmatch(r"\w+_[LR]", cells[0]):
            fields.append((cells[0], int(cells[1]), int(cells[2]), charge(cells[3]), int(cells[4]),
                           charge(cells[5]), charge(cells[6])))
    return fields


def traces(fields, which):
    """The six coefficients from multiplet dimensions and Dynkin indices, T(fundamental) = 1/2."""
    half = sp.Rational(1, 2)
    total = dict.fromkeys(("a_ccx", "a_wwx", "a_yyx", "a_yxx", "a_xxx", "a_ggx"), sp.Integer(0))
    for name, d3, d2, y, copies, x_a, x_b in fields:
        sign = 1 if name.endswith("_L") else -1          # a right-handed field counts as its left-handed conjugate
        y, x = sign * y, sign * (x_a if which == "A" else x_b)
        states = copies * d3 * d2
        total["a_ccx"] += copies * d2 * (half if d3 == 3 else 0) * x
        total["a_wwx"] += copies * d3 * (half if d2 == 2 else 0) * x
        total["a_yyx"] += states * y ** 2 * x
        total["a_yxx"] += states * y * x ** 2
        total["a_xxx"] += states * x ** 3
        total["a_ggx"] += states * x
    return {key: sp.expand(value) for key, value in total.items()}


def traces_by_state(fields, which):
    """The same six, summed state by state with one diagonal generator of each group:
    T^3 = diag(1/2, -1/2, 0) on a colour triplet and diag(1/2, -1/2) on a doublet, so Tr[T^3 T^3 X] = a."""
    half = sp.Rational(1, 2)
    total = dict.fromkeys(("a_ccx", "a_wwx", "a_yyx", "a_yxx", "a_xxx", "a_ggx"), sp.Integer(0))
    for name, d3, d2, y, copies, x_a, x_b in fields:
        sign = 1 if name.endswith("_L") else -1
        y, x = sign * y, sign * (x_a if which == "A" else x_b)
        colour = [sign * half, -sign * half, 0] if d3 == 3 else [0]      # the conjugate triplet has -T^3
        weak = [sign * half, -sign * half] if d2 == 2 else [0]
        for _ in range(copies):
            for t3_colour in colour:
                for t3_weak in weak:
                    total["a_ccx"] += t3_colour ** 2 * x
                    total["a_wwx"] += t3_weak ** 2 * x
                    total["a_yyx"] += y ** 2 * x
                    total["a_yxx"] += y * x ** 2
                    total["a_xxx"] += x ** 3
                    total["a_ggx"] += x
    return {key: sp.expand(value) for key, value in total.items()}


fields = read_fields()
a = traces(fields, "A")
assert a == traces_by_state(fields, "A"), "the two ways of taking the traces disagree"
b = traces(fields, "B")
assert b == traces_by_state(fields, "B")

# Assignment B: the value of z at which all six vanish together.
roots = None
for value in b.values():
    if value != 0:
        found = set(sp.solve(value, z))
        roots = found if roots is None else roots & found
assert roots is not None and len(roots) == 1, roots
z_b = roots.pop()
assert all(value.subs(z, z_b) == 0 for value in b.values())

# Higgs charge: each Yukawa term must carry no U(1)_X charge. Qbar H~ u: -x_Q - x_H + x_u = 0, and so on.
x = {name: (x_b.subs(z, z_b) if x_b.has(z) else x_b) for name, _, _, _, _, _, x_b in fields}
from_each_term = {x["u_R"] - x["Q_L"], x["Q_L"] - x["d_R"], x["L_L"] - x["e_R"], x["N_R"] - x["L_L"]}
assert len(from_each_term) == 1, from_each_term
x_higgs = from_each_term.pop()

result = {key: float(value) for key, value in a.items()}
result["anomaly_free_a"] = all(value == 0 for value in a.values())
result["z_b"] = float(z_b)
result["x_higgs_b"] = float(x_higgs)
json.dump(result, open("result.json", "w"), indent=1)
print("assignment A:", {key: str(value) for key, value in a.items()}, "anomaly-free:", result["anomaly_free_a"])
print("assignment B:", {key: str(sp.factor(value)) for key, value in b.items()}, "z =", z_b, "x_H =", x_higgs)
