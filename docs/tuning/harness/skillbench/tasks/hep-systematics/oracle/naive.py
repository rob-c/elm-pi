"""What the task is built to catch: every source by (up - down)/2 with a missing side filled in with the
nominal yield, which halves the single variations; and the ratio's uncertainty as the two regions'
totals in quadrature, as if nothing were common to them."""
import json

import numpy as np
import pandas as pd

table = pd.read_csv("yields.csv").set_index("variation")
nominal = table.loc["nominal"]
relative = {}
for region, stat in (("sr_yield", 9.1), ("cr_yield", 27.4)):
    squares = (stat / nominal[region]) ** 2
    for source in ("lumi", "pileup", "jes", "jer", "btag", "muon", "generator"):
        rows = [name for name in table.index if name.startswith(source)]
        up = table.loc[rows[0], region]
        down = table.loc[rows[1], region] if len(rows) > 1 else nominal[region]
        squares += ((up - down) / 2 / nominal[region]) ** 2
    relative[region] = np.sqrt(squares)
json.dump({"transfer_factor": nominal["sr_yield"] / nominal["cr_yield"],
           "tf_syst_percent": 100 * np.hypot(relative["sr_yield"], relative["cr_yield"]),
           "sr_syst_percent": 100 * relative["sr_yield"]}, open("result.json", "w"), indent=1)
print(relative)
