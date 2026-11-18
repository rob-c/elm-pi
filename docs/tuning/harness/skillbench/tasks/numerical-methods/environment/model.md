# Pulse test P-07: the model for the prediction

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
| 1 | 0.0124 | 0.000215 |
| 2 | 0.0305 | 0.001424 |
| 3 | 0.111 | 0.001274 |
| 4 | 0.301 | 0.002568 |
| 5 | 1.14 | 0.000748 |
| 6 | 3.01 | 0.000273 |

| quantity | value |
|---|---|
| prompt generation time Lambda | 4.0e-5 s |
| temperature coefficient alpha | 1.0e-4 per K |
| heat capacity of the fuel C_fuel | 8.0e4 J/K |
| reactivity inserted rho_0 | 0.0125 |
| power before the pulse | 100 W |

Before the pulse the reactor is critical and steady at that power, with the
precursors in equilibrium with it and the fuel at T_0. At t = 0 the transient
rod is fired: the reactivity steps to rho_0 and then follows the fuel
temperature.

The energy released is the integral of P from t = 0.
