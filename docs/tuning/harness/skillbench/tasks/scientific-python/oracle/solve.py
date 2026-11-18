"""The reference solution: run in the project folder, writes result.json and leaves itself as analysis.py.

    python3 analysis.py [log.csv]

Leakage-current summary of one log. The picoammeter autoranges and the logger
writes each reading in the unit of its range (the `unit` column: nA or uA), so
every reading is converted to nA before anything is computed. The bootstrap is
seeded, so a rerun on the same log gives the same numbers.
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent if Path(__file__).name == "analysis.py" else Path.cwd()
SEED, RESAMPLES = 20261117, 20_000
TO_NA = {"pA": 1e-3, "nA": 1.0, "uA": 1e3, "mA": 1e6}

log = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "scan.csv"
table = pd.read_csv(log)
print("%d rows, columns %s; units %s" % (len(table), list(table.columns), table["unit"].value_counts().to_dict()))
unknown = set(table["unit"]) - set(TO_NA)
assert not unknown, "unit not handled: %s" % unknown
current = (table["current"] * table["unit"].map(TO_NA)).to_numpy()          # nA
assert np.isfinite(current).all()

rng = np.random.default_rng(SEED)
medians = np.median(rng.choice(current, size=(RESAMPLES, len(current)), replace=True), axis=1)
low, high = np.percentile(medians, [15.865, 84.135])
result = {
    "mean_na": float(current.mean()),
    "sem_na": float(current.std(ddof=1) / np.sqrt(len(current))),
    "median_na": float(np.median(current)),
    "median_lo_na": float(low),
    "median_hi_na": float(high),
}
(HERE / "result.json").write_text(json.dumps(result, indent=1) + "\n")
print("numpy %s, pandas %s, seed %d, %d resamples" % (np.__version__, pd.__version__, SEED, RESAMPLES))
print(result)

if Path(__file__).name != "analysis.py":            # run as the oracle: leave the script the task asks for
    shutil.copy(__file__, HERE / "analysis.py")
