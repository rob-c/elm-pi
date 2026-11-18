"""What the task is built to catch: B x C / D on the raw data counts with the Poisson error of the three
counts - no prompt subtraction, and the validation set never looked at."""
import json

import pandas as pd

data = pd.read_csv("regions.csv").set_index("region")["data"]
estimate = data["B"] * data["C"] / data["D"]
error = estimate * (1 / data["B"] + 1 / data["C"] + 1 / data["D"]) ** 0.5
json.dump({"multijet_a": estimate, "multijet_a_unc": error}, open("result.json", "w"), indent=1)
print(estimate, error)
