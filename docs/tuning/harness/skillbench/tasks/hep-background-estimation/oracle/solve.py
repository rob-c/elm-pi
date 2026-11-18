"""The reference solution: run in the project folder, writes result.json.

Prompt simulation subtracted from every region; the method tested in the validation set, where the
observed-over-predicted ratio is far from 1 and becomes a correction with its uncertainty; data
statistics, the subtraction and the correction propagated to the estimate.
"""
import csv
import json
import math

regions = {}
for row in csv.DictReader(open("regions.csv")):
    data = float(row["data"]) if row["data"] else None
    regions[row["region"]] = (data, float(row["prompt_mc"]), float(row["prompt_mc_unc"]))


def multijet(name):
    """(data minus prompt, its relative variance): Poisson on the count, the simulation's own error."""
    data, prompt, error = regions[name]
    value = data - prompt
    return value, (data + error**2) / value**2


b, c, d = multijet("B"), multijet("C"), multijet("D")
va, vb, vc, vd = multijet("VA"), multijet("VB"), multijet("VC"), multijet("VD")

predicted_va = vb[0] * vc[0] / vd[0]
kappa = va[0] / predicted_va
kappa_var = va[1] + vb[1] + vc[1] + vd[1]
uncorrected = b[0] * c[0] / d[0]
estimate = kappa * uncorrected
relative = math.sqrt(kappa_var + b[1] + c[1] + d[1])
json.dump({"multijet_a": estimate, "multijet_a_unc": estimate * relative}, open("result.json", "w"), indent=1)
print("validation: predicted %.1f, observed %.1f, ratio %.3f +- %.3f" % (predicted_va, va[0], kappa, kappa * math.sqrt(kappa_var)))
print("uncorrected %.1f; estimate %.1f +- %.1f (%.1f%%)" % (uncorrected, estimate, estimate * relative, 100 * relative))
