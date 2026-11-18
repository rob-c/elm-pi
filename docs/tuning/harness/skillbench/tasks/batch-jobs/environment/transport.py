#!/usr/bin/env python3
"""Transport coefficient for one configuration.

    python transport.py E0500_L16

The argument is a label, E<energy in MeV>_L<lattice size>, as listed one to a
line in inputs.txt. Builds the collision matrix, solves for the relaxation
spectrum and writes results/<label>.json (the folder is made if it is not
there). Paths are taken relative to the directory the program is started in.

The linear algebra is numpy's and is multithreaded: it runs on as many threads
as OMP_NUM_THREADS says, and on every core of the machine if that is not set.
At production size a configuration takes about two hours on 12 cores and
peaks near 19 GB.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np


def main(label):
    match = re.fullmatch(r"E(\d{4})_L(\d+)", label)
    if not match:
        sys.exit("not a label: %r" % label)
    energy, lattice = int(match.group(1)), int(match.group(2))
    index = np.arange(4 * lattice)
    matrix = np.diag(1.0 + index / lattice) + (energy / 1000.0) * np.exp(-np.abs(index[:, None] - index[None, :]) / 2.0)
    rates = np.linalg.eigvalsh(matrix)
    results = Path("results")
    results.mkdir(exist_ok=True)
    target = results / (label + ".json")
    target.write_text(json.dumps({"label": label, "slowest_rates": [round(float(v), 5) for v in rates[:5]]}, indent=1) + "\n")
    print("wrote", target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
