#!/usr/bin/env python3
"""Low-lying spectrum of one isotope with one effective interaction.

    python spectra.py Ca48_gxpf1a

The argument is a label, <isotope>_<interaction>, as listed one to a line in
inputs.txt. Builds the Hamiltonian matrix in the valence space, finds its
lowest states and writes results/<label>.json (the folder is made if it is
not there). Paths are taken relative to the directory the program is started
in.

The matrix work is numpy's and is multithreaded: it runs on as many threads
as OMP_NUM_THREADS says, and on every core of the machine if that is not set.
At production dimension an isotope takes about four hours on 8 cores and
peaks near 27 GB.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

SCALE = {"gxpf1a": 1.00, "kb3g": 0.96, "jun45": 1.07}


def main(label, size=80):
    match = re.fullmatch(r"([A-Z][a-z]?)(\d+)_(\w+)", label)
    if not match or match.group(3) not in SCALE:
        sys.exit("not a label: %r" % label)
    mass = int(match.group(2))
    index = np.arange(size)
    matrix = np.diag(0.35 * index * (mass / 48.0) ** -0.3)
    matrix = matrix - SCALE[match.group(3)] * np.cos(0.4 * (index[:, None] - index[None, :])) / (1.0 + np.abs(index[:, None] - index[None, :]))
    levels = np.linalg.eigvalsh(matrix)
    results = Path("results")
    results.mkdir(exist_ok=True)
    target = results / (label + ".json")
    target.write_text(json.dumps({"label": label, "excitation_mev": [round(float(v - levels[0]), 4) for v in levels[:6]]}, indent=1) + "\n")
    print("wrote", target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
