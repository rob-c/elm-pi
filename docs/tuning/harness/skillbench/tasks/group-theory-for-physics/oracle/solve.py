"""The reference solution: run in the project folder, writes result.json.

An SU(N) irrep with Dynkin labels (a_1 .. a_{N-1}) is the partition
l_i = a_i + ... + a_{N-1} (l_N = 0). Then, with T(fundamental) = 1/2:

    dimension  prod_{i<j} (l_i - l_j + j - i) / (j - i)                      (Weyl)
    C2         [sum l_i^2 - n^2/N + sum l_i (N + 1 - 2i)] / 2,  n = sum l_i
    T(R)       C2(R) dim(R) / (N^2 - 1)

Tensor products by the Racah-Speiser algorithm: add every weight of the smaller
factor to the highest weight of the other plus rho, reflect into the dominant
chamber with the sign of the reflection, subtract rho.

Checked here by other routes: C2 again from the inverse Cartan matrix, and for
SU(3) from (p^2 + q^2 + pq + 3p + 3q)/3; each product by its dimensions, by the
index sum rule T(R1) dim(R2) + dim(R1) T(R2) = sum T(R_i), and by the characters
(Schur functions as ratios of determinants) at fixed group elements.
"""
import cmath
import json
import re
from collections import Counter
from fractions import Fraction as F
from itertools import product

import numpy as np


def partition(labels):
    return [sum(labels[i:]) for i in range(len(labels) + 1)]


def dimension(labels):
    lam = partition(labels)
    value = F(1)
    for i in range(len(lam)):
        for j in range(i + 1, len(lam)):
            value *= F(lam[i] - lam[j] + j - i, j - i)
    assert value.denominator == 1
    return int(value)


def casimir(labels):
    lam = partition(labels)
    n, boxes = len(lam), sum(lam)
    return F(1, 2) * (sum(l * l for l in lam) - F(boxes * boxes, n) + sum(l * (n - 1 - 2 * i) for i, l in enumerate(lam)))


def casimir_from_cartan_matrix(labels):
    """(L, L + 2 rho)/2 with the inverse Cartan matrix of A_{N-1}, min(i,j) (N - max(i,j)) / N: roots of length^2 2,
    and the factor 1/2 is what makes T(fundamental) = 1/2."""
    rank = len(labels)
    n = rank + 1
    inverse = [[F(min(i, j) * (n - max(i, j)), n) for j in range(1, n)] for i in range(1, n)]
    return F(1, 2) * sum(labels[i] * inverse[i][j] * (labels[j] + 2) for i in range(rank) for j in range(rank))


def index(labels):
    n = len(labels) + 1
    return casimir(labels) * dimension(labels) / (n * n - 1)


def weights(labels):
    """Weights with multiplicities, as the contents of the Gelfand-Tsetlin patterns of the partition."""
    found = Counter()

    def descend(row, content):
        if len(row) == 1:
            found[tuple([row[0]] + content)] += 1
            return
        for below in product(*[range(row[i + 1], row[i] + 1) for i in range(len(row) - 1)]):
            descend(list(below), [sum(row) - sum(below)] + content)

    descend(partition(labels), [])
    return found


def tensor_product(first, second):
    if dimension(first) > dimension(second):
        first, second = second, first
    n = len(first) + 1
    rho = [n - 1 - i for i in range(n)]
    base = [l + r for l, r in zip(partition(second), rho)]
    found = Counter()
    for weight, multiplicity in weights(first).items():
        shifted = [b + w for b, w in zip(base, weight)]
        if len(set(shifted)) < n:
            continue                                   # on a wall of a Weyl chamber: contributes nothing
        order = sorted(range(n), key=lambda i: -shifted[i])
        sign = 1
        for i in range(n):                             # parity of the sorting permutation
            for j in range(i + 1, n):
                if order[i] > order[j]:
                    sign = -sign
        lam = [s - r for s, r in zip(sorted(shifted, reverse=True), rho)]
        found[tuple(lam[i] - lam[i + 1] for i in range(n - 1))] += sign * multiplicity
    assert all(m >= 0 for m in found.values())
    return sorted(labels for labels, m in found.items() for _ in range(m))


def character(labels, angles):
    """Schur function of the partition at diag(exp(i angle)), as a ratio of determinants."""
    lam = partition(labels)
    n = len(lam)
    x = [cmath.exp(1j * a) for a in angles]
    top = np.array([[x[i] ** (lam[j] + n - 1 - j) for j in range(n)] for i in range(n)])
    bottom = np.array([[x[i] ** (n - 1 - j) for j in range(n)] for i in range(n)])
    return np.linalg.det(top) / np.linalg.det(bottom)


def parse(text):
    return tuple(int(v) for v in re.findall(r"-?\d+", text))


result = {}
for line in open("reps.md", encoding="utf-8"):
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(cells) != 3 or not re.fullmatch(r"SU\(\d\)", cells[1]):
        continue
    name, group, what = cells
    n = int(group[3])
    if " x " not in what:
        labels = parse(what)
        assert len(labels) == n - 1
        assert casimir(labels) == casimir_from_cartan_matrix(labels)
        if n == 3:
            p, q = labels
            assert casimir(labels) == F(p * p + q * q + p * q + 3 * p + 3 * q, 3)
            assert dimension(labels) == (p + 1) * (q + 1) * (p + q + 2) // 2
        result[name + "_dim"] = dimension(labels)
        result[name + "_c2"] = float(casimir(labels))
        result[name + "_index"] = float(index(labels))
        print("%s %s %s: dimension %d, C2 = %s, T = %s" % (name, group, labels, dimension(labels), casimir(labels), index(labels)))
    else:
        first, second = (parse(side) for side in what.split(" x "))
        parts = tensor_product(first, second)
        assert sum(dimension(p) for p in parts) == dimension(first) * dimension(second)
        assert sum(index(p) for p in parts) == index(first) * dimension(second) + dimension(first) * index(second)
        for k in range(1, 4):                          # three generic elements of the maximal torus, trace zero
            angles = [0.37 * k * (i + 1) ** 1.5 for i in range(n)]
            angles = [a - sum(angles) / n for a in angles]
            assert abs(character(first, angles) * character(second, angles) - sum(character(p, angles) for p in parts)) < 1e-7
        result[name] = [list(p) for p in parts]
        print("%s %s %s x %s = %s" % (name, group, first, second, " + ".join("%s[%d]" % (p, dimension(p)) for p in parts)))

json.dump(result, open("result.json", "w"), indent=1)
