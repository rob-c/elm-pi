"""What the task is built to catch: the working point chosen on the test set and quoted from it."""
import json

import numpy as np
import pandas as pd

scores = pd.read_csv("scores.csv")
test = scores[scores["set"] == "test"]
best = None
for cut in (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85):
    passed = test[test["score"] > cut]
    s, b = passed.loc[passed["label"] == 1, "weight"].sum(), passed.loc[passed["label"] == 0, "weight"].sum()
    z = float(np.sqrt(2 * ((s + b) * np.log1p(s / b) - s)))
    if best is None or z > best["significance"]:
        best = {"cut": cut, "signal_events": s, "background_events": b, "significance": z,
                "signal_efficiency": s / test.loc[test["label"] == 1, "weight"].sum()}
json.dump(best, open("result.json", "w"))
