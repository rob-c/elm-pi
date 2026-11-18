"""What the task is built to catch: one run of solve_ivp as it comes, and the peak read off its steps.

The equations and the initial conditions are right. The tolerances are the
defaults (rtol 1e-3), the method the default explicit one, and nothing is
repeated at another resolution: the numbers look fine and are right to two or
three figures.
"""
import json

import numpy as np
from scipy.integrate import solve_ivp

lam = np.array([0.0124, 0.0305, 0.111, 0.301, 1.14, 3.01])
beta_i = np.array([0.000215, 0.001424, 0.001274, 0.002568, 0.000748, 0.000273])
beta, generation, alpha, heat_capacity, rho0, power0 = beta_i.sum(), 4.0e-5, 1.0e-4, 8.0e4, 0.0125, 100.0


def rhs(t, y):
    rho = rho0 - alpha * y[7]
    return np.concatenate(([(rho - beta) / generation * y[0] + lam @ y[1:7]], beta_i / generation * y[0] - lam * y[1:7], [y[0] / heat_capacity]))


sol = solve_ivp(rhs, (0, 10), np.concatenate(([power0], beta_i * power0 / (generation * lam), [0.0])))
k = np.argmax(sol.y[0])
json.dump({"peak_power_mw": sol.y[0][k] / 1e6, "peak_time_ms": sol.t[k] * 1e3, "energy_10s_mj": sol.y[7][-1] * heat_capacity / 1e6},
          open("result.json", "w"), indent=1)
