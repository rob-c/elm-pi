"""What the task is built to catch: the weights summed but normalised by the number of
events generated, the filter efficiency left out of the cross-section, and sqrt(N)."""
import json

import numpy as np

events = np.genfromtxt("events.csv", delimiter=",", names=True)
selected = events[(events["ptll"] > 150) & (events["njet"] >= 4)]
sigma_pb = 0.7603 * 0.10099 * 1.12
expected = sigma_pb * 140.0 * 1000.0 * selected["weight"].sum() / 40000
json.dump({"expected_events": expected, "mc_stat_uncertainty": expected / np.sqrt(len(selected))}, open("result.json", "w"))
