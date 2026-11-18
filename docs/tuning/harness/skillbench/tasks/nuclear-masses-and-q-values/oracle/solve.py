"""The reference solution: run in the project folder, writes result.json.

Everything in atomic mass excesses, electrons counted: beta-plus loses 2 m_e,
K capture loses the K binding energy instead, the alpha shares Q with the
recoiling daughter, and the threshold is the exact (invariant-mass) one.
"""
import csv
import json
import math
import re

notes = open("notes.md").read()
U = float(re.search(r"1 u = ([\d.]+) keV", notes).group(1))
M_E = float(re.search(r"Electron mass: ([\d.]+) keV", notes).group(1))
B_K = float(re.search(r"nickel \(Z = 28\): ([\d.]+) keV", notes).group(1))

excess, number, protons = {}, {}, {}
for row in csv.DictReader(open("mass_excess.csv")):
    excess[row["nuclide"]] = float(row["mass_excess_keV"])
    number[row["nuclide"]] = int(row["A"])
    protons[row["nuclide"]] = int(row["Z"])


def atomic(name):
    """Atomic mass in keV."""
    return number[name] * U + excess[name]


def nuclear(name):
    """Nuclear mass in keV; the electrons' binding (eV to a few keV) is left in."""
    return atomic(name) - protons[name] * M_E


q_beta_minus = excess["Cu-64"] - excess["Zn-64"]
q_ec = excess["Cu-64"] - excess["Ni-64"]
beta_plus_endpoint = q_ec - 2 * M_E
neutrino = q_ec - B_K
neutrino -= neutrino**2 / (2 * atomic("Ni-64"))          # the recoiling atom: 0.02 keV

q_alpha = excess["Gd-148"] - excess["Sm-144"] - excess["He-4"]
parent, daughter, alpha = nuclear("Gd-148"), nuclear("Sm-144"), nuclear("He-4")
# Two-body decay at rest, exactly; the non-relativistic Q M_d/(M_d + M_alpha) is 0.04 keV higher.
alpha_energy = (parent**2 + alpha**2 - daughter**2) / (2 * parent) - alpha
assert abs(alpha_energy - q_alpha * daughter / (daughter + alpha)) < 0.1

# 4He(p,d)3He: bare proton on a helium nucleus at rest. T_th = -Q (sum of all four masses) / (2 m_target).
m_p, m_he4, m_d, m_he3 = nuclear("H-1"), nuclear("He-4"), nuclear("H-2"), nuclear("He-3")
q_reaction = excess["H-1"] + excess["He-4"] - excess["H-2"] - excess["He-3"]
threshold = -q_reaction * (m_p + m_he4 + m_d + m_he3) / (2 * m_he4)
# The same from the invariant mass: s at threshold is (m_d + m_he3)^2.
by_invariant = ((m_d + m_he3) ** 2 - (m_p + m_he4) ** 2) / (2 * m_he4)
assert math.isclose(threshold, by_invariant, rel_tol=1e-9), (threshold, by_invariant)

result = {
    "q_beta_minus_kev": q_beta_minus,
    "beta_plus_endpoint_kev": beta_plus_endpoint,
    "k_capture_neutrino_kev": neutrino,
    "q_alpha_kev": q_alpha,
    "alpha_energy_kev": alpha_energy,
    "threshold_kev": threshold,
}
json.dump(result, open("result.json", "w"), indent=1)
for key, value in result.items():
    print("%-26s %.3f" % (key, value))
print("Q(EC) %.2f keV; Q(4He(p,d)3He) %.3f keV; non-relativistic threshold %.1f keV"
      % (q_ec, q_reaction, -q_reaction * (m_p + m_he4) / m_he4))
