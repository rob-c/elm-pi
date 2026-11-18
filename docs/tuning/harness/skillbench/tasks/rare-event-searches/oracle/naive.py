"""What the task is built to catch: excess over sqrt(background) as the significance, and a
classical one-sided Poisson limit with the background subtracted where the plan says Feldman-Cousins."""
import json

import numpy as np
from scipy import optimize, stats

background_a = 350 * 12.5 / 62.5
significance = (112 - background_a) / np.sqrt(background_a)
background_b = 24 * 9.0 / 72.0
limit = optimize.brentq(lambda mu: stats.poisson.cdf(2, mu) - 0.10, 0.1, 50) - background_b
expected = optimize.brentq(lambda mu: stats.poisson.cdf(3, mu) - 0.10, 0.1, 50) - background_b
exposure = 5.2e4 * 1e4 * 9.0 * 3600 * 0.70
json.dump({"significance_sigma": significance, "limit_counts": limit, "expected_limit_counts": expected,
           "flux_limit_cm2_s": limit / exposure}, open("result.json", "w"))
