"""The reference solution: run in the project folder, writes result.json.

sigma(fid) = (N - B) / (L C), with L the luminosity the prescaled trigger saw and
C = selected / fiducial from the simulation (events migrating in included).
sigma(total) = sigma(fid) / (A BR). Statistical error from sqrt(N); background and
scale factors are the systematic one; luminosity and extrapolation stay apart.
"""
import csv
import json
import math
import re

notes = open("notes.md").read()


def number(pattern, group=1):
    return float(re.search(pattern, notes).group(group))


prescale = number(r"prescale of (\d+)")
lumi_fb = number(r"good-run list: ([0-9.]+) fb\^-1")
lumi_rel = number(r"relative uncertainty ([0-9.]+)%") / 100
n_obs = number(r"after the full selection: (\d+)")
background = number(r"sideband fit: ([0-9.]+) \+- ([0-9.]+)")
background_err = number(r"sideband fit: ([0-9.]+) \+- ([0-9.]+)", 2)
c_rel = number(r"uncertainty on the selected yield is ([0-9.]+)%") / 100
a_rel = number(r"Acceptance: ([0-9.]+)% relative") / 100
br = number(r"= \(([0-9.]+) \+- ([0-9.]+)\)%") / 100
br_err = number(r"= \(([0-9.]+) \+- ([0-9.]+)\)%", 2) / 100
mc = {row["stage"]: float(row["sum_of_weights"]) for row in csv.DictReader(open("mc_counts.csv"))}

lumi_pb = lumi_fb * 1000.0 / prescale                 # 1 fb^-1 = 1000 pb^-1; the trigger kept one event in `prescale`
acceptance = mc["fiducial"] / mc["generated"]
correction = mc["selected"] / mc["fiducial"]          # not selected_and_fiducial: the data contain the migrations too
signal = n_obs - background

fid = signal / (lumi_pb * correction)
stat = math.sqrt(n_obs) / signal                      # the count that fluctuates is N
syst = math.hypot(background_err / signal, c_rel)
total = fid / (acceptance * br)
extrap = math.hypot(a_rel, br_err / br)

result = {
    "fid_pb": fid, "fid_stat_pb": fid * stat, "fid_syst_pb": fid * syst, "fid_lumi_pb": fid * lumi_rel,
    "tot_pb": total, "tot_stat_pb": total * stat, "tot_syst_pb": total * syst, "tot_lumi_pb": total * lumi_rel,
    "tot_extrap_pb": total * extrap,
}
json.dump(result, open("result.json", "w"), indent=1)
print("L = %.3f pb^-1, A = %.4f, C = %.4f" % (lumi_pb, acceptance, correction))
print("fiducial: %.0f +- %.0f (stat) +- %.0f (syst) +- %.0f (lumi) pb" % (fid, fid * stat, fid * syst, fid * lumi_rel))
print("total: %.4g +- %.2g (stat) +- %.2g (syst) +- %.2g (lumi) +- %.2g (extrapolation) pb"
      % (total, total * stat, total * syst, total * lumi_rel, total * extrap))
