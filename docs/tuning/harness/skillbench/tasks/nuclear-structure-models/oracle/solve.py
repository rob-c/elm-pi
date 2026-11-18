"""The reference solution: run in the project folder, writes result.json.

Half-life to mean life, the gamma-ray share of the decay rate through
(1 + alpha), B(E2; 2+ -> 0+) from the rate, times (2 x 2 + 1)/(2 x 0 + 1) = 5 for
the excitation value, e2 fm4 to e2 b2, and the rest from the level energies.
"""
import json
import math
import re

notes = open("notes.md").read()


def number(pattern):
    return float(re.search(pattern, notes).group(1))


protons, nucleons = number(r"Z = (\d+)"), number(r"A = (\d+)")
e_2 = number(r"\| 2\+ \| ([\d.]+)") / 1000          # MeV
e_4 = number(r"\| 4\+ \| ([\d.]+)") / 1000
half_life = number(r"T1/2 = ([\d.]+)\(\d+\) ns") * 1e-9
alpha = number(r"alpha = (\d+\.\d+)")
rate_constant = number(r"= ([\d.e]+) x \(E_gamma")
weisskopf = number(r"Weisskopf unit for E2: ([\d.]+)") * nucleons ** (4 / 3)       # e2 fm4
r0 = number(r"R0 = ([\d.]+) A") * nucleons ** (1 / 3)                              # fm

mean_life = half_life / math.log(2)
gamma_rate = 1 / mean_life / (1 + alpha)
be2_down = gamma_rate / (rate_constant * e_2**5)                                   # e2 fm4, 2+ -> 0+
be2_up = be2_down * (2 * 2 + 1) / (2 * 0 + 1)                                      # e2 fm4, 0+ -> 2+
beta2 = 4 * math.pi / (3 * protons * r0**2) * math.sqrt(be2_up)

result = {
    "be2_up_e2b2": be2_up / 1e4,
    "be2_down_wu": be2_down / weisskopf,
    "beta2": beta2,
    "r42": e_4 / e_2,
    "moment_of_inertia_hbar2_per_mev": 2 * 3 / (2 * e_2),         # E(2+) = 6 hbar^2 / (2 I)
}
json.dump(result, open("result.json", "w"), indent=1)
print("mean life %.3f ns; B(E2; 2+ -> 0+) = %.0f e2 fm4; Weisskopf unit %.2f e2 fm4" % (mean_life * 1e9, be2_down, weisskopf))
for key, value in result.items():
    print("%-34s %.4f" % (key, value))
