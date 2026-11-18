#!/usr/bin/env python3
"""Track reconstruction for one event file.

    python reco.py --threads 4 data/evt_2417.dat

Fits a straight track to the hits of the file (plane, x, y on each line) and
writes results/<name>.json (the folder is made if it is not there). Paths are
taken relative to the directory the program is started in.

--threads is required: the number of worker threads the fit may use. Give it
the number of cores the job has, no more. A full-size file takes about an
hour on 4 cores and peaks near 9 GB.
"""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Track reconstruction for one event file.")
    parser.add_argument("--threads", type=int, required=True, help="worker threads: the cores the job has")
    parser.add_argument("file")
    options = parser.parse_args()
    if options.threads < 1:
        parser.error("--threads must be at least 1")
    os.environ["OMP_NUM_THREADS"] = str(options.threads)
    import numpy as np

    hits = np.loadtxt(options.file)
    slope_x, offset_x = np.polyfit(hits[:, 0], hits[:, 1], 1)
    slope_y, offset_y = np.polyfit(hits[:, 0], hits[:, 2], 1)
    results = Path("results")
    results.mkdir(exist_ok=True)
    target = results / (Path(options.file).stem + ".json")
    target.write_text(json.dumps({"file": options.file, "hits": int(len(hits)), "threads": options.threads,
                                  "x": [float(slope_x), float(offset_x)], "y": [float(slope_y), float(offset_y)]},
                                 indent=1) + "\n")
    print("wrote", target)


if __name__ == "__main__":
    main()
