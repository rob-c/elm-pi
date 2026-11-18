"""The reference solution: run in the project folder, writes result.json.

Mo-99 at the end of irradiation from the saturation formula, decayed to the
loading time; then the chain on the column by the matrix exponential of its
decay matrix, with the 87.6% branch to Tc-99m and both routes to Tc-99. The
two-member formula and atom conservation check it.
"""
import json
import math
import re

import numpy as np
from scipy.linalg import expm
from scipy.optimize import minimize_scalar

notes = open("notes.md").read()
rate = float(re.search(r"monitor: ([\d.e+]+) atoms", notes).group(1))                 # atoms/s
t_irr = float(re.search(r"\(([\d.]+) h\)", notes).group(1))                            # h
t_cool = float(re.search(r"([\d.]+) h after the end of irradiation", notes).group(1))  # h
half_mo = float(re.search(r"Mo-99 \| ([\d.]+) h", notes).group(1))
half_tcm = float(re.search(r"Tc-99m \| ([\d.]+) h", notes).group(1))
half_tc = float(re.search(r"Tc-99 \| ([\d.e+]+) y", notes).group(1)) * 365.25 * 24
branch = float(re.search(r"([\d.]+)% of decays feed Tc-99m", notes).group(1)) / 100

l_mo, l_tcm, l_tc = (math.log(2) / h for h in (half_mo, half_tcm, half_tc))           # per hour
PER_S = 1 / 3600.0

a_eob = rate * (1 - math.exp(-l_mo * t_irr))                # Bq: saturation, not rate x time
a_load = a_eob * math.exp(-l_mo * t_cool)
n_mo_load = a_load / (l_mo * PER_S)

# Columns: what Mo-99, Tc-99m, Tc-99 feed; the last row collects the Ru-99.
decay = np.array([
    [-l_mo, 0.0, 0.0, 0.0],
    [branch * l_mo, -l_tcm, 0.0, 0.0],
    [(1 - branch) * l_mo, l_tcm, -l_tc, 0.0],
    [0.0, 0.0, l_tc, 0.0],
])
start = np.array([n_mo_load, 0.0, 0.0, 0.0])


def atoms(t):
    return expm(decay * t) @ start


peak = minimize_scalar(lambda t: -atoms(t)[1], bounds=(1.0, 100.0), method="bounded", options={"xatol": 1e-9})
t_max = float(peak.x)
at_peak = atoms(t_max)
a_tcm_max = at_peak[1] * l_tcm * PER_S
n_tc = at_peak[2]

# Independent route: the closed forms for a pure parent.
t_formula = math.log(l_tcm / l_mo) / (l_tcm - l_mo)
n_tcm_formula = n_mo_load * branch * l_mo / (l_tcm - l_mo) * (math.exp(-l_mo * t_formula) - math.exp(-l_tcm * t_formula))
n_tc_formula = n_mo_load * (1 - math.exp(-l_mo * t_formula)) - n_tcm_formula
assert abs(t_max / t_formula - 1) < 1e-6, (t_max, t_formula)
assert abs(at_peak[1] / n_tcm_formula - 1) < 1e-9 and abs(n_tc / n_tc_formula - 1) < 1e-6
assert abs(at_peak.sum() / n_mo_load - 1) < 1e-12 and (at_peak >= 0).all()

result = {"a_mo99_eob_bq": a_eob, "a_mo99_load_bq": a_load, "t_max_h": t_max,
          "a_tc99m_max_bq": a_tcm_max, "n_tc99_atoms": n_tc}
json.dump(result, open("result.json", "w"), indent=1)
for key, value in result.items():
    print("%-16s %.5g" % (key, value))
