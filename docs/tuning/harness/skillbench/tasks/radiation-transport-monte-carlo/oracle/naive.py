"""What the task is built to catch: a plain average of the six lines of runs.csv (the 2e6-history
run counting as much as the 4e8 one, and the repeated seed counted twice), and the tally times
the activity, as if it were per decay, with no emission probability."""
import csv
import json
import math

runs = list(csv.DictReader(open("runs.csv")))
tally = [float(r["tally_per_cm2"]) for r in runs]
error = [float(r["rel_err"]) for r in runs]
mean = sum(tally) / len(tally)
rel_err = math.sqrt(sum((t * e) ** 2 for t, e in zip(tally, error))) / len(tally) / mean
flux = mean * 1.85e9
analytic = 1.85e9 * 0.851 * math.exp(-0.1101 * 11.35 * 4.00) / (4 * math.pi * 100.0**2)
json.dump({"combined_tally_per_cm2": mean, "combined_rel_err": rel_err,
           "flux_per_cm2_s": flux, "flux_unc_per_cm2_s": flux * rel_err, "analytic_flux_per_cm2_s": analytic,
           "unreliable_runs": [int(r["run"]) for r in runs if float(r["rel_err"]) > 0.10]},
          open("result.json", "w"), indent=1)
