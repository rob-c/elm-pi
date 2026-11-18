#!/usr/bin/env python3
"""Single-particle levels of one nucleus with one interaction.

    python fit_bands.py Sn132_SLy4

The argument is a label, <nucleus>_<interaction>, as listed one to a line in
inputs.txt. Builds the model Hamiltonian in an oscillator basis, diagonalises
it and writes results/<label>.json (the folder is made if it is not there).
Paths are taken relative to the directory the program is started in.

The diagonalisation is numpy's and is multithreaded: it runs on as many
threads as OMP_NUM_THREADS says, and on every core of the machine if that is
not set. At production basis size a nucleus takes about two and a half hours
on 6 cores and peaks near 20 GB.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

STRENGTH = {"SLy4": 1.00, "SkM": 0.93, "UNEDF1": 1.04}


def main(label, size=60):
    match = re.fullmatch(r"([A-Z][a-z]?)(\d+)_(\w+)", label)
    if not match or match.group(3) not in STRENGTH:
        sys.exit("not a label: %r" % label)
    mass = int(match.group(2))
    index = np.arange(size)
    hamiltonian = np.diag(41.0 * mass ** (-1 / 3) * (index + 1.5))
    coupling = STRENGTH[match.group(3)] * np.exp(-np.abs(index[:, None] - index[None, :]) / 3.0)
    levels = np.linalg.eigvalsh(hamiltonian - coupling)
    results = Path("results")
    results.mkdir(exist_ok=True)
    target = results / (label + ".json")
    target.write_text(json.dumps({"label": label, "lowest_mev": [round(float(v), 4) for v in levels[:8]]}, indent=1) + "\n")
    print("wrote", target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
