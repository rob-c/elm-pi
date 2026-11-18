"""The reference solution: run in the project folder, writes result.json.

Constants in order of preference: the project's own (constants.py) for the
neutron lifetime and the local gravity; scipy.constants (CODATA) for the
neutron's mass and magnetic moment; e and h are exact in the SI. Nothing is
typed in from memory.
"""
import importlib.util
import json
import math
import re

import scipy
import scipy.constants as sc

spec = importlib.util.spec_from_file_location("project_constants", "constants.py")
project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)

note = open("trap.md").read()
wall_nev = float(re.search(r"([\d.]+) neV", note).group(1))
holding_s = float(re.search(r"Holding time in the standard cycle: ([\d.]+) s", note).group(1))

m_n, m_n_unit, m_n_unc = sc.physical_constants["neutron mass"]
mu_n, mu_n_unit, mu_n_unc = sc.physical_constants["neutron mag. mom."]
wall_j = wall_nev * 1e-9 * sc.e

v_crit = math.sqrt(2 * wall_j / m_n)
codata = "scipy.constants %s (CODATA 2022)" % scipy.__version__
result = {
    "v_crit_m_s": v_crit,
    "wavelength_nm": sc.h / (m_n * v_crit) * 1e9,
    "h_max_m": wall_j / (m_n * project.G_LOCAL),
    "b_reflect_t": wall_j / abs(mu_n),
    "survival_fraction": math.exp(-holding_s / project.TAU_N),
    "sources": {
        "neutron lifetime": "constants.py, TAU_N = %s s (the value adopted for the 2026 analysis)" % project.TAU_N,
        "acceleration of gravity": "constants.py, G_LOCAL = %s m/s^2 (survey of the hall)" % project.G_LOCAL,
        "wall potential": "trap.md, %g neV" % wall_nev,
        "neutron mass": "%s: %r %s" % (codata, m_n, m_n_unit),
        "neutron magnetic moment": "%s: %r %s" % (codata, mu_n, mu_n_unit),
        "elementary charge": "exact in the SI (scipy.constants.e)",
        "Planck constant": "exact in the SI (scipy.constants.h)",
    },
}
json.dump(result, open("result.json", "w"), indent=1)
for key, value in result.items():
    print(key, value if isinstance(value, dict) else "%.9g" % value)
print("relative uncertainty of the neutron mass %.1e, of its magnetic moment %.1e" % (m_n_unc / m_n, mu_n_unc / abs(mu_n)))
