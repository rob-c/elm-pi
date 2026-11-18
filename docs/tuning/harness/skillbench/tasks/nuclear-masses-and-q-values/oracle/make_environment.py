"""Writes environment/ for this task: a mass-excess table and the constants. Nothing is random.

    python make_environment.py <environment dir>

The mass excesses are close to AME2020's but are the task's own: the answer is
whatever follows from this table, which is why a session must read it.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

# nuclide, Z, A, atomic mass excess [keV], its uncertainty [keV]
TABLE = [
    ("n", 0, 1, 8071.318, 0.001),
    ("H-1", 1, 1, 7288.971, 0.001),
    ("H-2", 1, 2, 13135.722, 0.001),
    ("H-3", 1, 3, 14949.810, 0.001),
    ("He-3", 2, 3, 14931.218, 0.001),
    ("He-4", 2, 4, 2424.916, 0.001),
    ("C-12", 6, 12, 0.000, 0.000),
    ("Ni-64", 28, 64, -67098.99, 0.46),
    ("Cu-64", 29, 64, -65424.37, 0.46),
    ("Zn-64", 30, 64, -66003.97, 0.64),
    ("Ga-64", 31, 64, -58832.8, 1.4),
    ("Nd-144", 60, 144, -83753.5, 1.3),
    ("Sm-144", 62, 144, -81965.41, 1.50),
    ("Sm-148", 62, 148, -79336.2, 1.2),
    ("Gd-148", 64, 148, -76269.28, 1.50),
]

lines = ["nuclide,Z,A,mass_excess_keV,uncertainty_keV"]
for name, z, a, excess, sigma in TABLE:
    lines.append("%s,%d,%d,%s,%s" % (name, z, a, repr(excess), repr(sigma)))
(out / "mass_excess.csv").write_text("\n".join(lines) + "\n")

(out / "notes.md").write_text("""# Constants for the Q-value sheet

mass_excess.csv: atomic mass excesses (neutral atoms, ground states) in keV,
copied from the mass evaluation; "n" is the free neutron.

- Atomic mass unit: 1 u = 931494.10 keV/c^2
- Electron mass: 510.999 keV/c^2
- K-shell electron binding energy in nickel (Z = 28): 8.333 keV

Cu-64 decays to Ni-64 (electron capture and beta-plus) and to Zn-64
(beta-minus). Gd-148 decays by alpha emission to the Sm-144 ground state only.
""")
print("wrote mass_excess.csv (%d nuclides) and notes.md" % len(TABLE))
