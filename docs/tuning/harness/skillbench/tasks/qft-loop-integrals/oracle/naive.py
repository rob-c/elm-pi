"""What the task is built to catch: the logarithm of a negative argument taken on the default branch.

The same Feynman-parameter integral as solve.py, with the right MS-bar
subtraction, but ln(D) for D < 0 is whatever the complex logarithm of the
language returns: ln|D| + i pi. The i0 of the propagators says -i pi, so the
imaginary part above threshold comes out with the wrong sign.
"""
import csv
import json

import numpy as np
from scipy.integrate import quad

result = {}
for row in csv.DictReader(open("points.csv")):
    p2, m1, m2, mu = (float(row[key]) for key in ("p2_gev2", "m1_gev", "m2_gev", "mu_gev"))
    a, b, c = p2, m1**2 - m2**2 - p2, m2**2
    zeros = [x.real for x in np.roots([a, b, c]) if abs(x.imag) < 1e-12 and 0 < x.real < 1]

    def integrand(x):
        return -np.log(complex(a * x * x + b * x + c) / mu**2)

    result["re_" + row["point"]] = quad(lambda x: integrand(x).real, 0, 1, points=zeros or None, limit=200)[0]
    result["im_" + row["point"]] = quad(lambda x: integrand(x).imag, 0, 1, points=zeros or None, limit=200)[0]
json.dump(result, open("result.json", "w"), indent=1)
