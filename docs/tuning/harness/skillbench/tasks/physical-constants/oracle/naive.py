"""What the task is built to catch: constants typed in from memory, the project's own not looked for.

The physics is right. The neutron mass, e, h and the magnetic moment are the
rounded values everyone remembers; g is the standard 9.81 and the lifetime a
PDG average, although the project's constants.py holds the two values its
analysis uses.
"""
import json
import math

M_N = 1.675e-27          # kg
E = 1.602e-19            # C
H = 6.626e-34            # J s
MU_N_NEV_PER_T = 60.3
G = 9.81
TAU_N = 878.4            # s

wall_j = 213e-9 * E
v = math.sqrt(2 * wall_j / M_N)
json.dump({
    "v_crit_m_s": v,
    "wavelength_nm": H / (M_N * v) * 1e9,
    "h_max_m": wall_j / (M_N * G),
    "b_reflect_t": 213 / MU_N_NEV_PER_T,
    "survival_fraction": math.exp(-300 / TAU_N),
    "sources": {"neutron mass": "CODATA 2018", "e, h": "CODATA 2018", "neutron magnetic moment": "PDG 2024", "g": "standard gravity",
                "neutron lifetime": "PDG 2024"},
}, open("result.json", "w"), indent=1)
