#!/usr/bin/env python3
"""Channel covariance of one run.

    python analyse.py data/run_0412.csv

Reads the run's table, diagonalises the covariance of its channels and writes
results/<run>.json (the folder is made if it is not there). Paths are taken
relative to the directory the program is started in.

The linear algebra is numpy's and is multithreaded: it runs on as many threads
as OMP_NUM_THREADS says, and on every core of the machine if that is not set.
A full-size run takes about 70 minutes on 8 cores and peaks near 12 GB.
"""
import json
import sys
from pathlib import Path

import numpy as np


def main(path):
    table = np.loadtxt(path, delimiter=",", skiprows=1)
    covariance = np.cov(table, rowvar=False)
    values = np.linalg.eigvalsh(covariance)
    results = Path("results")
    results.mkdir(exist_ok=True)
    target = results / (Path(path).stem + ".json")
    target.write_text(json.dumps({"run": Path(path).stem, "rows": int(table.shape[0]),
                                  "eigenvalues": [float(v) for v in values]}, indent=1) + "\n")
    print("wrote", target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
