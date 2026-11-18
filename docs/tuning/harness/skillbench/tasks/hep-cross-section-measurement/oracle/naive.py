"""What the task is built to catch: the recorded luminosity used although the trigger was
prescaled, the efficiency taken from the events that stay in the fiducial region, and
sqrt(N - B) as the statistical error."""
import json
import math

n_obs, background, background_err = 27113, 7250.0, 290.0
lumi_pb = 0.800 * 1000.0
acceptance = 1008000.0 / 4000000.0
efficiency = 586300.0 / 1008000.0
br = 0.0248
signal = n_obs - background
fid = signal / (lumi_pb * efficiency)
stat = math.sqrt(signal) / signal
syst = math.hypot(background_err / signal, 0.024)
total = fid / (acceptance * br)
json.dump({
    "fid_pb": fid, "fid_stat_pb": fid * stat, "fid_syst_pb": fid * syst, "fid_lumi_pb": fid * 0.023,
    "tot_pb": total, "tot_stat_pb": total * stat, "tot_syst_pb": total * syst, "tot_lumi_pb": total * 0.023,
    "tot_extrap_pb": total * math.hypot(0.065, 0.0005 / 0.0248),
}, open("result.json", "w"))
