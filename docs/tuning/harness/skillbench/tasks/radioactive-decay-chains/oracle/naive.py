"""What the task is built to catch: the parent-daughter formula with every Mo-99 decay
feeding Tc-99m (the 87.6% branch left out), and the Tc-99 counted as what has left Tc-99m."""
import json
import math

RATE, T_IRR, T_COOL = 2.60e11, 144.0, 30.0
l1, l2 = math.log(2) / 65.924, math.log(2) / 6.0067            # per hour

a_eob = RATE * (1 - math.exp(-l1 * T_IRR))
a_load = a_eob * math.exp(-l1 * T_COOL)
n1 = a_load * 3600 / l1
t_max = math.log(l2 / l1) / (l2 - l1)
n2 = n1 * l1 / (l2 - l1) * (math.exp(-l1 * t_max) - math.exp(-l2 * t_max))
n3 = n1 * (1 - math.exp(-l1 * t_max)) - n2
json.dump({"a_mo99_eob_bq": a_eob, "a_mo99_load_bq": a_load, "t_max_h": t_max,
           "a_tc99m_max_bq": n2 * l2 / 3600, "n_tc99_atoms": n3}, open("result.json", "w"), indent=1)
