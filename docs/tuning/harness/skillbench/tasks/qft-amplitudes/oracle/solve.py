"""The reference solution: run in the project folder, writes result.json.

g g -> t tbar at tree level from the Feynman rules, with explicit Dirac
matrices, spinors, Gell-Mann matrices and the two transverse polarisation
vectors of each gluon, so only physical polarisations are summed. Averaged
over 2 x 2 polarisations and 8 x 8 colours. Checked at every point against the
closed form of the literature (Combridge; Ellis, Stirling and Webber's chapter
on heavy quarks), which it reproduces to rounding, and for gauge invariance.

`squared(points, polarisations)` takes the polarisation sum as an argument so
that naive.py can run the same amplitudes with the sum this task is about.
"""
import csv
import itertools
import json
import math

import numpy as np

ALPHA_S, M_TOP = 0.118, 173.0          # notes.md
G2 = 4 * math.pi * ALPHA_S             # g_s^2

METRIC = np.diag([1.0, -1.0, -1.0, -1.0])
PAULI = [np.array([[0, 1], [1, 0]], complex), np.array([[0, -1j], [1j, 0]]), np.array([[1, 0], [0, -1]], complex)]
ZERO, ONE = np.zeros((2, 2)), np.eye(2)
GAMMA = [np.block([[ONE, ZERO], [ZERO, -ONE]]).astype(complex)] + [np.block([[ZERO, s], [-s, ZERO]]) for s in PAULI]

GELL_MANN = np.zeros((8, 3, 3), complex)
for index, (i, j) in zip((0, 3, 5), ((0, 1), (0, 2), (1, 2))):
    GELL_MANN[index][i, j] = GELL_MANN[index][j, i] = 1
    GELL_MANN[index + 1][i, j], GELL_MANN[index + 1][j, i] = -1j, 1j
GELL_MANN[2] = np.diag([1, -1, 0])
GELL_MANN[7] = np.diag([1, 1, -2]) / math.sqrt(3)
T = GELL_MANN / 2
F = np.zeros((8, 8, 8))
for a, b, c in itertools.product(range(8), repeat=3):
    F[a, b, c] = (-2j * np.trace((T[a] @ T[b] - T[b] @ T[a]) @ T[c])).real

# The amplitude is (T^a T^b) A_t + (T^b T^a) A_u + (i f^{abc} T^c) A_s; COLOUR[x, y] is the
# sum over a, b and the quark colours of structure x times the conjugate of structure y.
STRUCTURES = [np.einsum("aij,bjk->abik", T, T), np.einsum("bij,ajk->abik", T, T), 1j * np.einsum("abc,cik->abik", F, T)]
COLOUR = np.array([[np.einsum("abik,abik->", x, y.conj()) for y in STRUCTURES] for x in STRUCTURES])


def dot(a, b):
    return a @ METRIC @ b


def slash(p):
    return sum(METRIC[mu, mu] * p[mu] * GAMMA[mu] for mu in range(4))


def spinors(p, mass):
    """([u(p, 1), u(p, 2)], [v(p, 1), v(p, 2)]) with ubar u = 2 m."""
    sigma_p = sum(p[i + 1] * PAULI[i] for i in range(3))
    norm = math.sqrt(p[0] + mass)
    us, vs = [], []
    for chi in np.eye(2, dtype=complex):
        us.append(np.concatenate([norm * chi, sigma_p @ chi / norm]))
        vs.append(np.concatenate([sigma_p @ chi / norm, norm * chi]))
    return us, vs


def pieces(k1, k2, p3, e1, e2, u, v):
    """(A_t, A_u, A_s) for g_s = 1. Rules: quark vertex i g gamma^mu T^a, three-gluon vertex
    g f^{abc} [g^{mu nu}(k - p)^rho + g^{nu rho}(p - q)^mu + g^{rho mu}(q - k)^nu], all momenta in."""
    ubar = u.conj() @ GAMMA[0]
    mass = M_TOP * np.eye(4)
    a_t = -(ubar @ slash(e1) @ (slash(p3 - k1) + mass) @ slash(e2) @ v) / (dot(p3 - k1, p3 - k1) - M_TOP**2)
    a_u = -(ubar @ slash(e2) @ (slash(p3 - k2) + mass) @ slash(e1) @ v) / (dot(p3 - k2, p3 - k2) - M_TOP**2)
    q = -(k1 + k2)
    vertex = dot(e1, e2) * (k1 - k2) + dot(e1, k2 - q) * e2 + dot(e2, q - k1) * e1
    a_s = -(ubar @ slash(vertex) @ v) / dot(q, q)
    return np.array([a_t, a_u, a_s])


def transverse(k):
    """The two physical polarisation vectors of a massless vector with momentum k, each with weight 1."""
    n = k[1:] / np.linalg.norm(k[1:])
    first = np.cross(n, [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0])
    first /= np.linalg.norm(first)
    return [(np.concatenate([[0.0], e]), 1.0) for e in (first, np.cross(n, first))]


def squared(point, polarisations):
    """|M|^2 averaged over initial and summed over final colours and spins; polarisations(k)
    gives the (vector, weight) pairs the sum over one gluon's polarisations runs over."""
    k1, k2, p3, p4 = point
    us, vs = spinors(p3, M_TOP)[0], spinors(p4, M_TOP)[1]
    total = 0.0
    for (e1, w1), (e2, w2), u, v in itertools.product(polarisations(k1), polarisations(k2), us, vs):
        amplitude = pieces(k1, k2, p3, e1, e2, u, v)
        total += w1 * w2 * (amplitude @ COLOUR @ amplitude.conj()).real
    return G2**2 * total / (2 * 2 * 8 * 8)


def closed_form(point):
    k1, k2, p3, _ = point
    s = dot(k1 + k2, k1 + k2)
    tau1, tau2, rho = 2 * dot(k1, p3) / s, 2 * dot(k2, p3) / s, 4 * M_TOP**2 / s
    return G2**2 * (1 / (6 * tau1 * tau2) - 3 / 8) * (tau1**2 + tau2**2 + rho - rho**2 / (4 * tau1 * tau2))


def read_points():
    points = {}
    for row in csv.DictReader(open("points.csv")):
        points.setdefault(int(row["point"]), {})[row["particle"]] = np.array([float(row[x]) for x in ("E", "px", "py", "pz")])
    return {number: (p["g1"], p["g2"], p["t"], p["tbar"]) for number, p in sorted(points.items())}


if __name__ == "__main__":
    result = {}
    for number, point in read_points().items():
        value = squared(point, transverse)
        assert abs(value / closed_form(point) - 1) < 1e-9, "the Feynman-rule result and the closed form disagree"
        # Gauge check: gluon 1's polarisation replaced by its momentum, gluon 2 physical. With
        # i f T = [T^a, T^b] the amplitude is T^a T^b (A_t + A_s) + T^b T^a (A_u - A_s).
        a_t, a_u, a_s = pieces(point[0], point[1], point[2], point[0], transverse(point[1])[0][0],
                               spinors(point[2], M_TOP)[0][0], spinors(point[3], M_TOP)[1][1])
        assert abs(a_t + a_s) < 1e-9 * point[0][0] and abs(a_u - a_s) < 1e-9 * point[0][0], "not gauge invariant"
        result["msq_%d" % number] = value
        print("point %d: %.10f" % (number, value))
    json.dump(result, open("result.json", "w"), indent=1)
