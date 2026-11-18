"""What the task is built to catch: the Casimir and index in the mathematician's normalisation.

C2 = (L, L + 2 rho) with roots of length^2 2, and the index that goes with it,
are what the general weight-space formula gives when it is used as it stands:
the fundamental then has index 1, as in the tables that list an integer
"Dynkin index", so every C2 and every index is twice the value in the
normalisation the note asks for, T(fundamental) = 1/2. The dimensions and the
two decompositions are right.
"""
import json
from fractions import Fraction as F

REPRESENTATIONS = {"su3_a": (2, 1), "su3_b": (4, 0), "su3_c": (2, 2),
                   "su5_a": (0, 1, 0, 0), "su5_b": (1, 0, 0, 1), "su5_c": (0, 1, 0, 1)}


def dimension(labels):
    n = len(labels) + 1
    lam = [sum(labels[i:]) for i in range(n)]
    value = F(1)
    for i in range(n):
        for j in range(i + 1, n):
            value *= F(lam[i] - lam[j] + j - i, j - i)
    return int(value)


def casimir(labels):
    """(L, L + 2 rho) with the inverse Cartan matrix: no factor 1/2."""
    rank = len(labels)
    n = rank + 1
    inverse = [[F(min(i, j) * (n - max(i, j)), n) for j in range(1, n)] for i in range(1, n)]
    return sum(labels[i] * inverse[i][j] * (labels[j] + 2) for i in range(rank) for j in range(rank))


result = {}
for name, labels in REPRESENTATIONS.items():
    n = len(labels) + 1
    result[name + "_dim"] = dimension(labels)
    result[name + "_c2"] = float(casimir(labels))
    result[name + "_index"] = float(casimir(labels) * dimension(labels) / (n * n - 1))
result["product_su3"] = [[1, 0], [0, 2], [2, 1], [2, 1], [4, 0], [1, 3], [3, 2]]
result["product_su5"] = [[0, 1, 0, 0], [2, 0, 0, 0], [0, 0, 1, 1], [1, 1, 0, 1]]
json.dump(result, open("result.json", "w"), indent=1)
