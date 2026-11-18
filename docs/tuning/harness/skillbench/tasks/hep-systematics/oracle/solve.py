"""The reference solution: run in the project folder, writes result.json.

Per source, the shift of the quantity itself - the SR yield, or the ratio SR/CR recomputed from the
varied yields of both regions, so that what is common cancels and what is opposite adds. Two-sided
sources by half the up-down difference, single variations by the full difference; sources in
quadrature; the simulation statistics of the two regions independent.
"""
import csv
import json
import math

STAT = {"sr": 9.1, "cr": 27.4}          # notes.md

rows = {row["variation"]: (float(row["sr_yield"]), float(row["cr_yield"])) for row in csv.DictReader(open("yields.csv"))}
nominal = rows.pop("nominal")
quantities = {"sr": lambda pair: pair[0], "tf": lambda pair: pair[0] / pair[1]}

sources = {}
for name in rows:
    base = name[: -len("_up")] if name.endswith("_up") else name[: -len("_down")] if name.endswith("_down") else name
    sources.setdefault(base, {})["up" if name.endswith("_up") else "down" if name.endswith("_down") else "only"] = rows[name]

total = {}
for key, quantity in quantities.items():
    central = quantity(nominal)
    variance = 0.0
    for base, found in sorted(sources.items()):
        if "only" in found:
            shift = quantity(found["only"]) - central
        else:
            shift = (quantity(found["up"]) - quantity(found["down"])) / 2
        variance += (shift / central) ** 2
        print("%-3s %-14s %+6.2f%%" % (key, base, 100 * shift / central))
    total[key] = variance
total["sr"] += (STAT["sr"] / nominal[0]) ** 2
total["tf"] += (STAT["sr"] / nominal[0]) ** 2 + (STAT["cr"] / nominal[1]) ** 2

answer = {"transfer_factor": nominal[0] / nominal[1], "tf_syst_percent": 100 * math.sqrt(total["tf"]),
          "sr_syst_percent": 100 * math.sqrt(total["sr"])}
json.dump(answer, open("result.json", "w"), indent=1)
print(answer)
