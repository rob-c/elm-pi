"""Hidden check, run in the project folder after the session. All must pass for reward 1.

The expected values are exact group theory in the normalisation reps.md states,
T(fundamental) = 1/2 and T^a T^a = C2(R): dimension from Weyl's formula,
C2 = (L, L + 2 rho)/2 (for SU(3): (p^2 + q^2 + pq + 3p + 3q)/3), and
T(R) = C2(R) dim(R) / dim(G). oracle/solve.py computes them in fractions, C2 by
two routes, and the products by Racah-Speiser checked against the dimension
sum, the index sum rule and the characters.

    (2,1)      15   16/3   10          (0,1,0,0)  10   18/5   3/2
    (4,0)      15   28/3   35/2        (1,0,0,1)  24   5      5
    (2,2)      27   8      27          (0,1,0,1)  45   32/5   12

    (2,1) x (1,1)         = (1,0) + (0,2) + 2 (2,1) + (4,0) + (1,3) + (3,2)       3 + 6 + 15 + 15 + 15 + 24 + 42 = 120
    (0,1,0,0) x (1,0,0,1) = (0,1,0,0) + (2,0,0,0) + (0,0,1,1) + (1,1,0,1)         10 + 15 + 40 + 175 = 240

The tolerance (0.5%) only allows for three significant figures in the file.
The other common normalisation, with index 1 for the fundamental, gives twice
every C2 and every index; a conjugate dropped in a product changes the labels
but not the dimensions, which is why the labels are compared.
"""
import json
import math
import re
from fractions import Fraction
from pathlib import Path

EXPECTED = {
    "su3_a": (15, Fraction(16, 3), Fraction(10)),
    "su3_b": (15, Fraction(28, 3), Fraction(35, 2)),
    "su3_c": (27, Fraction(8), Fraction(27)),
    "su5_a": (10, Fraction(18, 5), Fraction(3, 2)),
    "su5_b": (24, Fraction(5), Fraction(5)),
    "su5_c": (45, Fraction(32, 5), Fraction(12)),
}
PRODUCTS = {
    "product_su3": (120, [(1, 0), (0, 2), (2, 1), (2, 1), (4, 0), (1, 3), (3, 2)]),
    "product_su5": (240, [(0, 1, 0, 0), (2, 0, 0, 0), (0, 0, 1, 1), (1, 1, 0, 1)]),
}


def result():
    return json.loads(Path("result.json").read_text())


def number(value):
    """A JSON number, or a fraction written as a string ("16/3") or as [16, 3]: the third run with
    the skill had every Casimir right and was failed for writing them as pairs."""
    assert not isinstance(value, bool)
    if isinstance(value, str):
        value = float(Fraction(value.strip()))
    elif isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in value) and value[1]:
        value = value[0] / value[1]
    assert isinstance(value, (int, float)) and math.isfinite(value), value
    return float(value)


def close(got, want):
    return abs(number(got) - float(want)) <= 5e-3 * abs(float(want))


def irreps(entries):
    """The decomposition as a sorted list of Dynkin-label tuples; an entry may be a list or a string like "(2,1)"."""
    assert isinstance(entries, list) and entries
    found = []
    for entry in entries:
        labels = re.findall(r"-?\d+", entry) if isinstance(entry, str) else entry
        found.append(tuple(int(v) for v in labels))
    return sorted(found)


def dimension(labels):
    lam = [sum(labels[i:]) for i in range(len(labels) + 1)]
    value = Fraction(1)
    for i in range(len(lam)):
        for j in range(i + 1, len(lam)):
            value *= Fraction(lam[i] - lam[j] + j - i, j - i)
    return value


def test_result_file_has_every_key():
    data = result()
    for name in EXPECTED:
        for suffix in ("_dim", "_c2", "_index"):
            number(data[name + suffix])
    for name in PRODUCTS:
        irreps(data[name])


def test_dimensions():
    data = result()
    for name, (dim, _, _) in EXPECTED.items():
        assert number(data[name + "_dim"]) == dim, name


def test_casimirs_in_the_stated_normalisation():
    data = result()
    for name, (_, c2, _) in EXPECTED.items():
        assert close(data[name + "_c2"], c2), "%s: C2 = %s with T(fundamental) = 1/2" % (name, c2)


def test_indices_in_the_stated_normalisation():
    data = result()
    for name, (_, _, index) in EXPECTED.items():
        assert close(data[name + "_index"], index), "%s: T = %s with T(fundamental) = 1/2" % (name, index)


def test_dimensions_of_each_product_add_up():
    data = result()
    for name, (total, parts) in PRODUCTS.items():
        found = irreps(data[name])
        assert all(len(labels) == len(parts[0]) and min(labels) >= 0 for labels in found), name
        assert sum(dimension(labels) for labels in found) == total, name


def test_su3_product():
    assert irreps(result()["product_su3"]) == sorted(PRODUCTS["product_su3"][1])


def test_su5_product():
    assert irreps(result()["product_su5"]) == sorted(PRODUCTS["product_su5"][1])
