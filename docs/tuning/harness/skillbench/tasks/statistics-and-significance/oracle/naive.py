"""What the task is built to catch: s / sqrt(b) and a Gaussian limit, at nine events and at one.

The counting and the background estimate are right. The significance treats
the background as known and the counts as Gaussian; the limit is the excess
plus 1.645 sqrt(n).
"""
import csv
import json
import math

rows = list(csv.DictReader(open("candidates.csv")))


def count(channel, low, high):
    return sum(row["channel"] == channel and low <= float(row["mass_gev"]) < high for row in rows)


n_ee = count("ee", 9.60, 10.00)
b_ee = (count("ee", 9.30, 9.60) + count("ee", 10.00, 10.30)) / 1.5
n_mm = count("mumu", 9.70, 9.90)
b_mm = (count("mumu", 9.30, 9.70) + count("mumu", 9.90, 10.30)) / 4.0
json.dump({
    "significance_ee_sigma": (n_ee - b_ee) / math.sqrt(b_ee),
    "upper_limit_mumu_events": (n_mm - b_mm) + 1.645 * math.sqrt(n_mm),
}, open("result.json", "w"), indent=1)
