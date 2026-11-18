"""The reference solution: run in the project folder, writes result.json.

Reads the excerpt in ENSDF's notation: an uncertainty counts in the last digits
of its value ("249.83 D 4" is 249.83 +- 0.04 d, "1.28 +5-3" is 1.28 +0.05 -0.03).
The isomer is the excited level that lives long; its decay data set is the one
headed with that half-life; photons per decay are RI x NR x BR / 100.
"""
import json
import math
import re

SECONDS = {"NS": 1e-9, "S": 1.0, "D": 86400.0}
text = open("ag110_ensdf.txt").read()


def ensdf(field):
    """(value, plus, minus) from 'value', 'value unc' or 'value +a-b'."""
    parts = field.split()
    value = float(parts[0])
    digit = 10.0 ** -len(parts[0].partition(".")[2])          # one unit in the last place
    if len(parts) == 1:
        return value, 0.0, 0.0
    asymmetric = re.fullmatch(r"\+(\d+)-(\d+)", parts[1])
    if asymmetric:
        return value, int(asymmetric.group(1)) * digit, int(asymmetric.group(2)) * digit
    return value, int(parts[1]) * digit, int(parts[1]) * digit


# Adopted levels: the isomer is the excited level with the longest half-life.
levels = []
for match in re.finditer(r"^  ([\d.]+(?: \d+)?) +\S+ +([\d.]+) (NS|S|D) (\d+) +%", text, re.M):
    energy = ensdf(match.group(1))[0]
    value, plus, _ = ensdf(match.group(2) + " " + match.group(4))
    levels.append({"energy": energy, "printed": "%s %s" % (match.group(2), match.group(3)),
                   "half_life": value * SECONDS[match.group(3)], "unc": plus * SECONDS[match.group(3)]})
isomer = max((level for level in levels if level["energy"] > 0), key=lambda level: level["half_life"])

# Its decay data set, up to the next blank-line-separated legend.
start = text.index("B- DECAY (%s)" % isomer["printed"])
block = text[start:text.index("Columns and records", start)]
nr = ensdf(re.search(r"NR=([\d.]+ \d+)", block).group(1))
br = ensdf(re.search(r"BR=([\d.]+ \d+)", block).group(1))
factor = nr[0] * br[0] / 100                                   # photons per decay of the isomer, per unit RI
factor_rel = math.hypot(nr[1] / nr[0], br[1] / br[0])

lines = {}
for match in re.finditer(r"^  (\d+\.\d+ \d+) +(\d[\d.]*(?: (?:\d+|\+\d+-\d+))?)", block, re.M):
    energy = ensdf(match.group(1))[0]
    lines[energy] = ensdf(match.group(2))


def photons(wanted):
    energy = min(lines, key=lambda e: abs(e - wanted))
    assert abs(energy - wanted) < 0.05, wanted
    ri, plus, minus = lines[energy]
    value = ri * factor
    return value, value * math.hypot(plus / ri, factor_rel), value * math.hypot(minus / ri, factor_rel)


p_885 = photons(884.68)
p_1562 = photons(1562.29)
energy_per_decay = sum(energy * ri[0] * factor for energy, ri in lines.items())

result = {
    "half_life_s": isomer["half_life"], "half_life_unc_s": isomer["unc"],
    "p_885": p_885[0], "p_885_unc": p_885[1],
    "p_1562": p_1562[0], "p_1562_unc_plus": p_1562[1], "p_1562_unc_minus": p_1562[2],
    "gamma_energy_per_decay_kev": energy_per_decay,
}
json.dump(result, open("result.json", "w"), indent=1)
print("isomer at %.2f keV, T1/2 = %s; NR x BR = %.4f x %.4f; %d lines" % (isomer["energy"], isomer["printed"], nr[0], br[0], len(lines)))
for key, value in result.items():
    print("%-28s %.6g" % (key, value))
