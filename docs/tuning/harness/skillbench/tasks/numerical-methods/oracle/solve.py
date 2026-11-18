"""The reference solution: run in the project folder, writes result.json.

The system is stiff once the pulse is over (the prompt term relaxes at about
150 /s while the precursors decay at 0.01 to 3 /s), so it is integrated with
Radau and the analytic Jacobian. The peak is not read off the solver's steps or
off a grid: it is the root of dP/dt, found on the dense output. Convergence is
shown by tightening the tolerance a hundredfold twice, and the result is
checked with a different kind of method (DOP853, explicit, order 8).
"""
import json
import re

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

text = open("model.md").read()
groups = np.array([[float(a), float(b)] for a, b in re.findall(r"^\| \d \| ([\d.e-]+) \| ([\d.e-]+) \|$", text, re.M)])
assert len(groups) == 6
lam, beta_i = groups[:, 0], groups[:, 1]
beta = beta_i.sum()


def quantity(name):
    return float(re.search(r"\| %s[^|]*\| ([\d.e+-]+)" % name, text).group(1))


generation, alpha, heat_capacity = quantity("prompt generation time"), quantity("temperature coefficient"), quantity("heat capacity")
rho0, power0 = quantity("reactivity inserted"), quantity("power before the pulse")
T_END = 10.0


def rhs(t, y):                      # y = P, C_1..C_6, T - T_0
    power, precursors, heating = y[0], y[1:7], y[7]
    rho = rho0 - alpha * heating
    return np.concatenate(([(rho - beta) / generation * power + lam @ precursors],
                           beta_i / generation * power - lam * precursors, [power / heat_capacity]))


def jacobian(t, y):
    J = np.zeros((8, 8))
    J[0, 0] = (rho0 - alpha * y[7] - beta) / generation
    J[0, 1:7] = lam
    J[0, 7] = -alpha * y[0] / generation
    J[1:7, 0] = beta_i / generation
    J[1:7, 1:7] = -np.diag(lam)
    J[7, 0] = 1 / heat_capacity
    return J


start = np.concatenate(([power0], beta_i * power0 / (generation * lam), [0.0]))


def solve(method, rtol):
    extra = {"jac": jacobian} if method == "Radau" else {}
    # atol far below every component: the power starts at 100 W, the smallest precursor group at 2e7.
    sol = solve_ivp(rhs, (0.0, T_END), start, method=method, rtol=rtol, atol=rtol * 1e-3, dense_output=True, **extra)
    assert sol.success, sol.message
    slope = lambda t: rhs(t, sol.sol(t))[0]
    grid = np.linspace(0.0, 1.0, 4001)
    k = int(np.argmax(sol.sol(grid)[0]))
    t_peak = brentq(slope, grid[k - 1], grid[k + 1], xtol=1e-14, rtol=1e-14)
    return sol.sol(t_peak)[0] / 1e6, t_peak * 1e3, sol.sol(T_END)[7] * heat_capacity / 1e6, len(sol.t)


print("method   rtol     peak [MW]        at [ms]          energy by 10 s [MJ]   steps")
runs = {}
for method, rtol in (("Radau", 1e-7), ("Radau", 1e-9), ("Radau", 1e-11), ("DOP853", 1e-11)):
    runs[method, rtol] = solve(method, rtol)
    print("%-7s  %.0e  %.9f  %.9f  %.9f  %6d" % ((method, rtol) + runs[method, rtol]))
best, coarser, other = runs["Radau", 1e-11], runs["Radau", 1e-9], runs["DOP853", 1e-11]
for i in range(3):
    assert abs(coarser[i] / best[i] - 1) < 1e-7 and abs(other[i] / best[i] - 1) < 1e-8, "not converged"
json.dump({"peak_power_mw": best[0], "peak_time_ms": best[1], "energy_10s_mj": best[2]}, open("result.json", "w"), indent=1)
