"""What the task is built to catch: the B(E2) that the lifetime gives (2+ -> 0+) reported as
B(E2; 0+ -> 2+), with no factor 5, and beta2 computed from it."""
import json
import math

e_2, e_4 = 0.081976, 0.26679
mean_life = 3.10e-9 / math.log(2)
be2 = 1 / (mean_life * (1 + 4.94)) / (1.223e9 * e_2**5)              # e2 fm4
r0 = 1.2 * 154 ** (1 / 3)
json.dump({
    "be2_up_e2b2": be2 / 1e4,
    "be2_down_wu": be2 / (0.0594 * 154 ** (4 / 3)),
    "beta2": 4 * math.pi / (3 * 62 * r0**2) * math.sqrt(be2),
    "r42": e_4 / e_2,
    "moment_of_inertia_hbar2_per_mev": 3 / e_2,
}, open("result.json", "w"), indent=1)
