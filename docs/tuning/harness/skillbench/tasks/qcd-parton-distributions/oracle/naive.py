"""What the task is built to catch: the Hessian uncertainty quoted as it comes out of the formula.

The eigenvector formulae are right, and so are the replica mean and standard
deviation. But CT18's eigenvector members span a 90% confidence interval, as
its .info file says, and the numbers are reported as if they were 68% ones:
too large by 1.645.
"""
import json

import numpy as np

hessian = np.loadtxt("ct18nlo_members.csv", delimiter=",", skiprows=1)[:, 1]
replicas = np.loadtxt("nnpdf31_members.csv", delimiter=",", skiprows=1)[1:, 1]
central, plus, minus = hessian[0], hessian[1::2], hessian[2::2]
zero = np.zeros(len(plus))
json.dump({
    "ct18_sym_pb": 0.5 * np.sqrt(np.sum((plus - minus) ** 2)),
    "ct18_up_pb": np.sqrt(np.sum(np.maximum.reduce([plus - central, minus - central, zero]) ** 2)),
    "ct18_down_pb": np.sqrt(np.sum(np.maximum.reduce([central - plus, central - minus, zero]) ** 2)),
    "nnpdf_central_pb": replicas.mean(),
    "nnpdf_unc_pb": replicas.std(ddof=1),
}, open("result.json", "w"), indent=1)
