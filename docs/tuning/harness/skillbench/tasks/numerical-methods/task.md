---
skill: numerical-methods
also: scientific-python
category: computation
pitfall: solve_ivp at its default tolerances, with the peak read off the solver's steps or a coarse output grid - one run, no convergence check, right to two or three figures where five are asked for
timeout_sec: 900
---
model.md has the kinetics model and the parameters for the pulse test. For the prediction I need the peak power, the time at which it is reached, and the energy released in the first 10 s, each good to five significant figures. Put them in result.json as peak_power_mw, peak_time_ms and energy_10s_mj.
