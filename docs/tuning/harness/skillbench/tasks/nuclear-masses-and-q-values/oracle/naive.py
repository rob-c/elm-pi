"""What the task is built to catch: the beta-plus endpoint taken as the bare mass difference
(no 2 m_e c^2), and the textbook non-relativistic threshold -Q (m_a + m_A)/m_A."""
import csv
import json

excess, number = {}, {}
for row in csv.DictReader(open("mass_excess.csv")):
    excess[row["nuclide"]] = float(row["mass_excess_keV"])
    number[row["nuclide"]] = int(row["A"])

q_ec = excess["Cu-64"] - excess["Ni-64"]
q_alpha = excess["Gd-148"] - excess["Sm-144"] - excess["He-4"]
q_reaction = excess["H-1"] + excess["He-4"] - excess["H-2"] - excess["He-3"]
mass = lambda name: number[name] * 931494.10 + excess[name]
json.dump({
    "q_beta_minus_kev": excess["Cu-64"] - excess["Zn-64"],
    "beta_plus_endpoint_kev": q_ec,
    "k_capture_neutrino_kev": q_ec - 8.333,
    "q_alpha_kev": q_alpha,
    "alpha_energy_kev": q_alpha * 144 / 148,
    "threshold_kev": -q_reaction * (mass("H-1") + mass("He-4")) / mass("He-4"),
}, open("result.json", "w"), indent=1)
