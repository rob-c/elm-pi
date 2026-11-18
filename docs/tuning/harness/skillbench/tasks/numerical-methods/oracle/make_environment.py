"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A reactivity pulse in a research reactor: point kinetics with six groups of
delayed neutrons and an adiabatic temperature feedback (the Fuchs-Nordheim
model with the delayed neutrons kept). Eight coupled equations, rates from
0.012 /s (the slowest precursors) to 150 /s (the prompt neutrons), and a pulse
23 ms wide that rises through six decades in the first 0.1 s.

There is no noise: the answer is the solution of the equations in model.md.
Radau, BDF, LSODA and DOP853 at rtol 1e-12 agree on it to ten figures
(2026-11-17):

    peak power 362.6496734 MW at 104.8193726 ms; 16.69159858 MJ released by 10 s

What less care gives is in verifier/test_outputs.py.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

GROUPS = [  # decay constant [1/s], delayed fraction: thermal fission of U-235 (Keepin)
    (0.0124, 0.000215), (0.0305, 0.001424), (0.111, 0.001274), (0.301, 0.002568), (1.14, 0.000748), (3.01, 0.000273)]
GENERATION_TIME = 4.0e-5       # s
FEEDBACK = 1.0e-4              # reactivity lost per kelvin of fuel temperature
HEAT_CAPACITY = 8.0e4          # J/K
INSERTED = 0.0125              # reactivity step at t = 0
INITIAL_POWER = 100.0          # W



def plain(x):
    """4.0e-5, not 4.0e-05."""
    mantissa, exponent = ("%.1e" % x).split("e")
    return "%se%d" % (mantissa, int(exponent))


rows = "\n".join("| %d | %.4g | %.6f |" % (i + 1, lam, beta) for i, (lam, beta) in enumerate(GROUPS))
(out / "model.md").write_text("""# Pulse test P-07: the model for the prediction

Point kinetics with six groups of delayed neutrons and prompt temperature
feedback, as in the safety report (section 4.3). The fuel heats adiabatically:
nothing is removed on the time scale of the pulse.

    dP/dt   = (rho - beta) / Lambda * P + sum_i lambda_i * C_i
    dC_i/dt = beta_i / Lambda * P - lambda_i * C_i            i = 1 .. 6
    dT/dt   = P / C_fuel
    rho     = rho_0 - alpha * (T - T_0)

P is the power in W, C_i the precursor groups (in the same units as P), T the
fuel temperature, beta the sum of the beta_i.

| group | lambda_i [1/s] | beta_i |
|---|---|---|
%s

| quantity | value |
|---|---|
| prompt generation time Lambda | %s s |
| temperature coefficient alpha | %s per K |
| heat capacity of the fuel C_fuel | %s J/K |
| reactivity inserted rho_0 | %.4f |
| power before the pulse | %.0f W |

Before the pulse the reactor is critical and steady at that power, with the
precursors in equilibrium with it and the fuel at T_0. At t = 0 the transient
rod is fired: the reactivity steps to rho_0 and then follows the fuel
temperature.

The energy released is the integral of P from t = 0.
""" % (rows, plain(GENERATION_TIME), plain(FEEDBACK), plain(HEAT_CAPACITY), INSERTED, INITIAL_POWER))
beta = sum(b for _, b in GROUPS)
print("beta = %.6f, rho_0 = %.2f dollars; Fuchs-Nordheim peak %.0f MW, period %.2f ms" % (
    beta, INSERTED / beta, HEAT_CAPACITY * (INSERTED - beta) ** 2 / (2 * FEEDBACK * GENERATION_TIME) / 1e6, 1e3 * GENERATION_TIME / (INSERTED - beta)))
