"""The reference solution: run in the project folder, writes result.json.

The working point is chosen on the validation set and what is quoted for it
comes from the test set, which took no part in the training or in the choice.
"""
import json
import re

import numpy as np
import pandas as pd

notes = open("notes.md").read()
points = [float(x) for x in re.findall(r"\d\.\d\d", re.search(r"x = ([0-9., ]+) only", notes).group(1))]
scores = pd.read_csv("scores.csv")


def expected(name, cut):
    """Signal, background, significance and signal efficiency of score > cut in one set."""
    part = scores[scores["set"] == name]
    signal, passed = part["label"] == 1, part["score"] > cut
    s, b = part.loc[signal & passed, "weight"].sum(), part.loc[~signal & passed, "weight"].sum()
    return s, b, float(np.sqrt(2 * ((s + b) * np.log1p(s / b) - s))), s / part.loc[signal, "weight"].sum()


for name in ("train", "valid", "test"):
    print(name, "  ".join("%.2f: %.3f" % (cut, expected(name, cut)[2]) for cut in points))
cut = max(points, key=lambda x: expected("valid", x)[2])
s, b, z, efficiency = expected("test", cut)
json.dump({"cut": cut, "signal_events": s, "background_events": b, "significance": z, "signal_efficiency": efficiency},
          open("result.json", "w"), indent=1)
print("score > %.2f (from validation); on test s = %.2f, b = %.2f, Z = %.3f, efficiency %.3f" % (cut, s, b, z, efficiency))
