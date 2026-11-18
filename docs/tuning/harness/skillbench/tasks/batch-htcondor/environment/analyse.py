#!/usr/bin/env python3
"""Calibrated spectrum of one run.

    python3 analyse.py run_4100.dat

Reads the run file named on the command line and the calibration, calib.json,
which it looks for in the directory it is started in. Writes
<run>.result.json into that same directory.

Needs Python 3 with numpy. At full size a run takes about 80 minutes on 4
cores and peaks near 6 GB.
"""
import json
import sys
from pathlib import Path

import numpy as np


def main(path):
    calibration = json.loads(Path("calib.json").read_text())
    table = np.loadtxt(path)
    energy = calibration["offset_kev"] + calibration["gain_kev_per_channel"] * table[:, 0]
    counts = table[:, 1]
    mean = float((energy * counts).sum() / counts.sum())
    target = Path(Path(path).stem + ".result.json")
    target.write_text(json.dumps({"run": Path(path).stem, "counts": int(counts.sum()), "mean_energy_kev": mean}, indent=1) + "\n")
    print("wrote", target)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
