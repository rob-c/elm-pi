"""The reference solution: run in the project folder, writes result.json.

With the definition in notes.md,

    B0 = 1/eps - gamma_E + ln 4 pi - Int_0^1 dx ln[(D(x) - i0)/mu^2] + O(eps),
    D(x) = x m1^2 + (1 - x) m2^2 - x (1 - x) p^2,

and MS-bar removes 1/eps - gamma_E + ln 4 pi. Where D < 0 the prescription gives
ln(D - i0) = ln|D| - i pi, so the imaginary part of B0 is +pi times the length of
that interval. The Feynman-parameter integral is done numerically, split at the
zeros of D, and checked at every point against the closed form in the
variable r of Denner's review of one-loop techniques and, above threshold,
against the optical theorem: Im B0 = pi sqrt(lambda(p^2, m1^2, m2^2)) / p^2.
"""
import cmath
import csv
import json
import math

from scipy.integrate import quad


def b0_feynman(p2, m1, m2, mu):
    a, b, c = p2, m1**2 - m2**2 - p2, m2**2            # D(x) = a x^2 + b x + c

    def delta(x):
        return a * x * x + b * x + c

    edges = [0.0, 1.0]
    disc = b * b - 4 * a * c
    if disc > 0:
        edges += [x for x in ((-b - math.sqrt(disc)) / (2 * a), (-b + math.sqrt(disc)) / (2 * a)) if 0 < x < 1]
    edges.sort()
    real = imag = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        # The logarithmic singularities sit at the ends of each piece, where quad copes with them.
        real -= quad(lambda x: math.log(abs(delta(x)) / mu**2), low, high, epsabs=1e-13, epsrel=1e-13, limit=200)[0]
        if delta(0.5 * (low + high)) < 0:
            imag += math.pi * (high - low)
    return real, imag


def b0_closed(p2, m1, m2, mu):
    """2 - ln(m1 m2/mu^2) + (m1^2 - m2^2)/p^2 ln(m2/m1) - m1 m2/p^2 (1/r - r) ln r,
    with r + 1/r = (m1^2 + m2^2 - p^2 - i0)/(m1 m2)."""
    s = (m1**2 + m2**2 - p2) / (m1 * m2) - 1e-13j
    r = (s + cmath.sqrt(s * s - 4)) / 2
    value = 2 - math.log(m1 * m2 / mu**2) + (m1**2 - m2**2) / p2 * math.log(m2 / m1) - m1 * m2 / p2 * (1 / r - r) * cmath.log(r)
    return value.real, value.imag


result = {}
for row in csv.DictReader(open("points.csv")):
    point = [float(row[key]) for key in ("p2_gev2", "m1_gev", "m2_gev", "mu_gev")]
    real, imag = b0_feynman(*point)
    closed = b0_closed(*point)
    assert abs(real - closed[0]) < 1e-8 and abs(imag - closed[1]) < 1e-8, "integral and closed form disagree"
    p2, m1, m2, _ = point
    if p2 > (m1 + m2) ** 2:
        kallen = (p2 - m1**2 - m2**2) ** 2 - 4 * m1**2 * m2**2
        assert abs(imag - math.pi * math.sqrt(kallen) / p2) < 1e-10, "imaginary part is not the optical theorem's"
    result["re_" + row["point"]], result["im_" + row["point"]] = real, imag
    print("point %s: %.9f %+.9f i" % (row["point"], real, imag))
json.dump(result, open("result.json", "w"), indent=1)
