"""What the task is built to catch: the table used as it loads, and a bootstrap nobody can repeat.

    python3 analysis.py

The `current` column is taken to be in nA throughout - the first rows are - so
the readings the meter took on its uA range count as one or two nA. The
bootstrap draws from numpy's global generator without a seed, so every run of
the script gives another interval.
"""
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

current = pd.read_csv("scan.csv")["current"].to_numpy()
medians = [np.median(np.random.choice(current, len(current))) for _ in range(2000)]
json.dump({
    "mean_na": float(np.mean(current)),
    "sem_na": float(np.std(current) / np.sqrt(len(current))),
    "median_na": float(np.median(current)),
    "median_lo_na": float(np.percentile(medians, 16)),
    "median_hi_na": float(np.percentile(medians, 84)),
}, open("result.json", "w"), indent=1)

if Path(__file__).name != "analysis.py":
    shutil.copy(__file__, "analysis.py")
