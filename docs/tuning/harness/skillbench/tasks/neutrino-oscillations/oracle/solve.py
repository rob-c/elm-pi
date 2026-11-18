"""The reference solution: run in the project folder, writes result.json.

Two-flavour survival, P = 1 - sin^2(2 theta) sin^2(1.267 dm2 L / E) with dm2 in
eV^2, L in km and E in GeV, applied to the spectrum in its own 10 MeV bins and
only then summed into the analysis bins: below 800 MeV the phase turns by more
than a radian across an analysis bin.
"""
import json
import re

import numpy as np
import pandas as pd

notes = open("notes.md").read()
baseline_km = float(re.search(r"baseline of ([0-9.]+) km", notes).group(1))
sin2_theta = float(re.search(r"sin\^2\(theta23\) = ([0-9.]+)", notes).group(1))
dm2 = float(re.search(r"dm2_32 = ([0-9.e+-]+) eV\^2", notes).group(1))
edges = [int(x) for x in re.findall(r"\d+", re.search(r"Analysis bins[^:]*: (.*)\.", notes).group(1))]
bins = list(zip(edges[0::2], edges[1::2]))

spectrum = pd.read_csv("unoscillated.csv")
sin2_2theta = 4 * sin2_theta * (1 - sin2_theta)
# The phase changes by up to 0.23 rad across a 10 MeV bin: average the probability over twenty points in it.
points = (np.arange(20) + 0.5) / 20
low, width = spectrum["e_low_mev"].to_numpy(float), (spectrum["e_high_mev"] - spectrum["e_low_mev"]).to_numpy(float)
energy_gev = (low[:, None] + width[:, None] * points[None, :]) / 1000.0
survival = np.mean(1 - sin2_2theta * np.sin(1.267 * dm2 * baseline_km / energy_gev) ** 2, axis=1)
oscillated = spectrum["events"].to_numpy() * survival

result = {}
for number, (first, last) in enumerate(bins, 1):
    inside = (spectrum["e_low_mev"] >= first) & (spectrum["e_high_mev"] <= last)
    result["n_osc_%d" % number] = float(oscillated[inside].sum())
    print("%4d-%4d MeV: %7.2f of %7.2f, average survival %.3f"
          % (first, last, oscillated[inside].sum(), spectrum.loc[inside, "events"].sum(),
             oscillated[inside].sum() / spectrum.loc[inside, "events"].sum()))
result["n_osc_total"] = float(sum(result.values()))
json.dump(result, open("result.json", "w"), indent=1)
print("sin^2(2 theta) = %.4f; total %.2f of %.2f" % (sin2_2theta, result["n_osc_total"], spectrum["events"].sum()))
