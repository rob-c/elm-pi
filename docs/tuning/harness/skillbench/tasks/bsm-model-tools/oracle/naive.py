"""What the task is built to catch: the anomaly sums done one table row at a time.

The right-handed fields are conjugated and the U(1) traces are counted properly,
but the two non-abelian coefficients take one term per row: the quark doublet
is counted as one colour triplet (not two) and as one weak doublet (not three),
so 2 x_Q - x_u - x_d becomes x_Q - x_u - x_d and 3 x_Q + x_L becomes x_Q + x_L.
z is then read off the SU(2) condition alone.
"""
import json
from fractions import Fraction as F

# field: SU(3), SU(2), Y, copies, X in assignment A, X in assignment B (None: the open charge z)
FIELDS = {
    "Q_L": (3, 2, F(1, 3), 3, F(1, 3), F(2)),
    "u_R": (3, 1, F(4, 3), 3, F(1), F(5)),
    "d_R": (3, 1, F(-2, 3), 3, F(-2, 3), F(-1)),
    "L_L": (1, 2, F(-1), 3, F(-2), None),
    "e_R": (1, 1, F(-2), 3, F(-3), F(-9)),
    "N_R": (1, 1, F(0), 3, F(-1), F(-3)),
    "T_L": (3, 1, F(4, 3), 1, F(1), F(5)),
    "T_R": (3, 1, F(4, 3), 1, F(1), F(5)),
}

a = dict.fromkeys(("a_ccx", "a_wwx", "a_yyx", "a_yxx", "a_xxx", "a_ggx"), F(0))
for name, (d3, d2, y, copies, x, _) in FIELDS.items():
    sign = 1 if name.endswith("_L") else -1
    y, x = sign * y, sign * x
    if d3 == 3:
        a["a_ccx"] += copies * F(1, 2) * x           # one triplet per row
    if d2 == 2:
        a["a_wwx"] += copies * F(1, 2) * x           # one doublet per row
    a["a_yyx"] += copies * d3 * d2 * y * y * x
    a["a_yxx"] += copies * d3 * d2 * y * x * x
    a["a_xxx"] += copies * d3 * d2 * x ** 3
    a["a_ggx"] += copies * d3 * d2 * x

x_b = {name: row[5] for name, row in FIELDS.items()}
z_b = -x_b["Q_L"]                                    # from x_Q + x_L = 0
result = {key: float(value) for key, value in a.items()}
result["anomaly_free_a"] = all(value == 0 for value in a.values())
result["z_b"] = float(z_b)
result["x_higgs_b"] = float(x_b["Q_L"] - x_b["d_R"])
json.dump(result, open("result.json", "w"), indent=1)
