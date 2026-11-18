"""The reference solution: run in the project folder, writes result.json.

The cut's response depends on momentum and the two samples have different
spectra, so the pass fraction is measured in momentum bins on the calibration
sample and averaged with the analysis sample's population of those bins.
"""
import json

import numpy as np
import pandas as pd

calibration = pd.read_csv("calibration.csv")
analysis = pd.read_csv("analysis_tracks.csv")
# Narrow where the calibration sample is rich and the response changes, wide where it is thin.
edges = np.array([3, 6, 9, 12, 15, 18, 22, 26, 30, 35, 40, 46, 52, 60, 70, 80, 100.0])


def for_analysis_sample(species):
    tracks = calibration[calibration["species"] == species]
    total, _ = np.histogram(tracks["p_gev"], edges)
    passed, _ = np.histogram(tracks.loc[tracks["passed"] == 1, "p_gev"], edges)
    wanted, _ = np.histogram(analysis.loc[analysis["species"] == species, "p_gev"], edges)
    assert wanted.sum() == (analysis["species"] == species).sum() and np.all(total[wanted > 0] > 0)
    rate = passed / total
    share = wanted / wanted.sum()
    error = np.sqrt(np.sum(share**2 * rate * (1 - rate) / total))
    print("%-2s  calibration sample as a whole %.4f; weighted to the analysis sample %.4f +- %.4f"
          % (species, passed.sum() / total.sum(), np.sum(share * rate), error))
    return float(np.sum(share * rate))


json.dump({"kaon_efficiency": for_analysis_sample("K"), "pion_misid_rate": for_analysis_sample("pi")},
          open("result.json", "w"), indent=1)
