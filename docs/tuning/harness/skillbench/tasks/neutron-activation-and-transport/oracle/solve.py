"""The reference solution: run in the project folder, writes result.json.

Every number below is read off notes.md. The flux there is the true Maxwellian flux
(integral of n(v) v at 293.6 K) and the cross section is the 2200 m/s value of a 1/v
absorber, so the rate per atom is (sqrt(pi)/2) sigma0 phi. Everything in seconds.
"""
import json
import math

# The foil and the plan.
MASS_G, MN_FRACTION, MOLAR_MASS, ABUNDANCE, N_A = 38.40e-3, 0.880, 54.938, 1.0, 6.02214e23
SIGMA0_CM2 = 13.36e-24
FLUX_MAXWELLIAN = 6.0e7                      # cm^-2 s^-1
HALF_LIFE_S = 2.5789 * 3600
T_IRRADIATION, T_WAIT, T_COUNT = (3 * 60 + 20) * 60.0, 47 * 60.0, 5400.0
EMISSION, EFFICIENCY = 0.9885, 8.62e-4
# The time-of-flight check.
PATH_M, T_GAMMA_NS, T_NEUTRON_NS, MN_C2, C_M_NS = 20.00, 118.4, 437.1, 939.565, 0.299792

atoms = MASS_G * MN_FRACTION * ABUNDANCE * N_A / MOLAR_MASS
sigma = math.sqrt(math.pi) / 2 * SIGMA0_CM2                  # the cross section that goes with this flux
lam = math.log(2) / HALF_LIFE_S
rate = atoms * sigma * FLUX_MAXWELLIAN                       # captures per second = saturation activity
activity_eoi = rate * (1 - math.exp(-lam * T_IRRADIATION))
# Decays during the count: the integral of the activity, not activity x time.
decays = activity_eoi * math.exp(-lam * T_WAIT) * (1 - math.exp(-lam * T_COUNT)) / lam
counts = decays * EMISSION * EFFICIENCY

# The gamma flash left the target with the neutrons and took L/c to arrive.
flight_ns = T_NEUTRON_NS - T_GAMMA_NS + PATH_M / C_M_NS
beta = PATH_M / (C_M_NS * flight_ns)
energy = MN_C2 * (1 / math.sqrt(1 - beta**2) - 1)

json.dump({"activity_eoi_bq": activity_eoi, "expected_peak_counts": counts, "tof_energy_mev": energy},
          open("result.json", "w"), indent=1)
print("atoms %.4g, saturation activity %.4g Bq, at end of irradiation %.4g Bq, counts %.4g"
      % (atoms, rate, activity_eoi, counts))
print("flight time %.2f ns, beta %.5f, energy %.3f MeV (non-relativistic %.3f)"
      % (flight_ns, beta, energy, 0.5 * MN_C2 * beta**2))
