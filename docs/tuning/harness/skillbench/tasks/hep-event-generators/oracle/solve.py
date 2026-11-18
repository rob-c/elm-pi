"""The reference solution: run in the project folder, writes result.json.

Each event counts sigma x L x w / (sum of w over everything written), with
sigma the generator's cross-section times the forced decay's branching ratio,
the filter efficiency and the k-factor. The card is read from notes.md.
"""
import json
import re

import numpy as np

notes = open("notes.md").read()


def card(label):
    """The first number in the card row (or line) that starts with this label."""
    return float(re.search(re.escape(label) + r"[^0-9]*([0-9][0-9.]*)", notes).group(1))


sigma_pb = card("Cross-section printed by the generator")
branching = card("BR(Z -> ll) =")
filter_eff = card("Efficiency")
k_factor = card("| k-factor |")
sum_w_written = card("Sum of the generator weights of the written events")
lumi_fb = card("Full Run 2:")
region = re.search(r"## Signal region\s+ptll > ([0-9.]+) GeV and njet >= (\d+)", notes)
sr_pt, sr_njet = float(region.group(1)), int(region.group(2))

events = np.genfromtxt("events.csv", delimiter=",", names=True)
weights = events["weight"][(events["ptll"] > sr_pt) & (events["njet"] >= sr_njet)]

# pb x fb^-1 = 1000 events. The denominator is the card's sum, not this skim's.
per_weight = sigma_pb * branching * filter_eff * k_factor * lumi_fb * 1000.0 / sum_w_written
expected = per_weight * weights.sum()
uncertainty = per_weight * np.sqrt(np.sum(weights**2))
json.dump({"expected_events": expected, "mc_stat_uncertainty": uncertainty}, open("result.json", "w"), indent=1)
print("sigma x BR x filter x k = %.5f pb; %d events, sum of weights %.0f, effective %.0f"
      % (sigma_pb * branching * filter_eff * k_factor, len(weights), weights.sum(), weights.sum() ** 2 / np.sum(weights**2)))
print("expected %.1f +- %.1f events" % (expected, uncertainty))
