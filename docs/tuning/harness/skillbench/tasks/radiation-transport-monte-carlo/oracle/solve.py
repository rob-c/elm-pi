"""The reference solution: run in the project folder, writes result.json.

Runs that share a seed are one run, counted once. The independent runs are
pooled as one long run - weighted by their histories - and the pooled error
comes from their quoted errors; an inverse-variance mean checks it. The tally
is per source photon, so the flux is tally x activity x emission probability.
"""
import csv
import json
import math
import re

notes = open("notes.md").read()


def number(pattern):
    return float(re.search(pattern, notes).group(1))


thickness = number(r"slab, ([\d.]+) cm thick")
density = number(r"density ([\d.]+) g/cm3")
distance = number(r"centred ([\d.]+) cm")
activity = number(r"Cs-137, ([\d.]+) GBq") * 1e9
emission = number(r"photon: ([\d.]+) per decay")
mu_over_rho = number(r"mu/rho = ([\d.]+) cm2/g")
limit = number(r"relative error above ([\d.]+) is not reliable")

runs = [{"run": int(r["run"]), "seed": r["seed"], "histories": float(r["histories"]),
         "tally": float(r["tally_per_cm2"]), "rel_err": float(r["rel_err"])} for r in csv.DictReader(open("runs.csv"))]
unreliable = [r["run"] for r in runs if r["rel_err"] > limit]

independent = {}
for r in runs:                                   # a seed used twice gives the same histories twice
    kept = independent.get(r["seed"])
    if kept is None or r["histories"] > kept["histories"]:
        independent[r["seed"]] = r
independent = list(independent.values())

weight = sum(r["histories"] for r in independent)
combined = sum(r["histories"] * r["tally"] for r in independent) / weight
sigma = math.sqrt(sum((r["histories"] * r["tally"] * r["rel_err"]) ** 2 for r in independent)) / weight
rel_err = sigma / combined

inverse = [1 / (r["tally"] * r["rel_err"]) ** 2 for r in independent]
by_variance = sum(w * r["tally"] for w, r in zip(inverse, independent)) / sum(inverse)
assert abs(by_variance / combined - 1) < 0.005, (by_variance, combined)
chi2 = sum(((r["tally"] - combined) / (r["tally"] * r["rel_err"])) ** 2 for r in independent)

source_rate = activity * emission                # photons of this line per second
flux = combined * source_rate
analytic = source_rate * math.exp(-mu_over_rho * density * thickness) / (4 * math.pi * distance**2)

json.dump({"combined_tally_per_cm2": combined, "combined_rel_err": rel_err,
           "flux_per_cm2_s": flux, "flux_unc_per_cm2_s": flux * rel_err,
           "analytic_flux_per_cm2_s": analytic, "unreliable_runs": unreliable}, open("result.json", "w"), indent=1)
print("%d runs, %d independent (%.3g histories); chi2 %.1f for %d" % (len(runs), len(independent), weight, chi2, len(independent) - 1))
print("combined %.4e /cm2 per photon +- %.2f%% (inverse-variance mean %.4e)" % (combined, 100 * rel_err, by_variance))
print("flux %.2f +- %.2f /cm2/s; narrow-beam %.2f /cm2/s; ratio %.3f; unreliable runs %s"
      % (flux, flux * rel_err, analytic, flux / analytic, unreliable))
