"""What the task is built to catch.

The 2200 m/s cross section multiplied by a flux that is not the 2200 m/s flux; the
counts taken as (activity at the start of the count) x time, with no decay during a
count that lasts 0.6 half-lives; and the flight time read as neutron peak minus gamma
flash, with the classical kinetic energy.
"""
import json
import math

atoms = 38.40e-3 * 0.880 * 6.02214e23 / 54.938
lam = math.log(2) / (2.5789 * 3600)
activity_eoi = atoms * 13.36e-24 * 6.0e7 * (1 - math.exp(-lam * 200 * 60))
counts = activity_eoi * math.exp(-lam * 47 * 60) * 5400 * 0.9885 * 8.62e-4

beta = 20.00 / (0.299792 * (437.1 - 118.4))
energy = 0.5 * 939.565 * beta**2
json.dump({"activity_eoi_bq": activity_eoi, "expected_peak_counts": counts, "tof_energy_mev": energy},
          open("result.json", "w"))
