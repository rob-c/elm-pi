"""The reference solution: run in the project folder, writes result.json.

Each set by the formula for its kind:

- Hessian pairs (X+, X-) around X0: symmetric (1/2) sqrt(sum (X+ - X-)^2);
  up sqrt(sum max(X+ - X0, X- - X0, 0)^2), down the same with X0 - X. The set's
  confidence level is read from notes.md and the result scaled to 68.27% by the
  ratio of the Gaussian quantiles (1.645 for 90%).
- Replicas: mean and standard deviation over members 1 to N.

The Hessian sums are done twice, vectorised and as LHAPDF's own loop over
eigenvectors, and the two must agree.
"""
import csv
import json
import math
import re

import numpy as np
from scipy.stats import norm


def members(name):
    rows = sorted((int(row["member"]), float(row["sigma_pb"])) for row in csv.DictReader(open(name)))
    assert [number for number, _ in rows] == list(range(len(rows)))
    return np.array([value for _, value in rows])


notes = open("notes.md").read()
info = dict((name, body) for name, body in re.findall(r"^(\w+)\.info\n(.*?)(?=^\w+\.info|\Z)", notes, re.M | re.S))
assert "ErrorType: hessian" in info["CT18NLO"] and "ErrorType: replicas" in info["NNPDF31_nlo_as_0118"]
level = float(re.search(r"ErrorConfLevel:\s*([\d.]+)", info["CT18NLO"]).group(1)) / 100
to_68 = norm.ppf(0.5 + 0.5 * math.erf(1 / math.sqrt(2))) / norm.ppf(0.5 + 0.5 * level)      # 1/1.645

hessian = members("ct18nlo_members.csv")
central, plus, minus = hessian[0], hessian[1::2], hessian[2::2]
assert len(plus) == len(minus) == 29
symmetric = 0.5 * math.sqrt(np.sum((plus - minus) ** 2))
up = math.sqrt(np.sum(np.maximum.reduce([plus - central, minus - central, np.zeros(len(plus))]) ** 2))
down = math.sqrt(np.sum(np.maximum.reduce([central - plus, central - minus, np.zeros(len(plus))]) ** 2))

loop = [0.0, 0.0, 0.0]
for k in range(1, (len(hessian) - 1) // 2 + 1):
    loop[0] += (hessian[2 * k - 1] - hessian[2 * k]) ** 2
    loop[1] += max(hessian[2 * k - 1] - hessian[0], hessian[2 * k] - hessian[0], 0.0) ** 2
    loop[2] += max(hessian[0] - hessian[2 * k - 1], hessian[0] - hessian[2 * k], 0.0) ** 2
assert np.allclose([symmetric, up, down], [0.5 * math.sqrt(loop[0]), math.sqrt(loop[1]), math.sqrt(loop[2])], rtol=1e-12)

replicas = members("nnpdf31_members.csv")[1:]
assert len(replicas) == 100

result = {
    "ct18_sym_pb": symmetric * to_68,
    "ct18_up_pb": up * to_68,
    "ct18_down_pb": down * to_68,
    "nnpdf_central_pb": float(np.mean(replicas)),
    "nnpdf_unc_pb": float(np.std(replicas, ddof=1)),
}
json.dump(result, open("result.json", "w"), indent=1)
print("CT18NLO at %.0f%% CL: +%.2f -%.2f (symmetric %.2f); scaled by %.5f" % (100 * level, up, down, symmetric, to_68))
low, high = np.percentile(replicas, [15.865, 84.135])
print("replicas: 68%% interval half-width %.2f, standard deviation %.2f" % ((high - low) / 2, result["nnpdf_unc_pb"]))
for key, value in result.items():
    print("%-17s %.4f" % (key, value))
