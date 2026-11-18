"""Constants for the Bottle 2 storage analysis. Every analysis script imports them.

Change a value here only together with the analysis note (section 2.1): the
2026 result is quoted for these.
"""

# Neutron lifetime adopted for the 2026 analysis: the magneto-gravitational
# trap result, as agreed at the collaboration meeting of 2026-03-12. [s]
TAU_N = 877.75

# Acceleration of gravity at the trap floor, from the gravimetric survey of the
# hall in 2023 (the hall is 1040 m above sea level). [m/s^2]
G_LOCAL = 9.80297

# Loss probability per wall bounce, fitted to the 2025 runs.
WALL_LOSS_PER_BOUNCE = 2.7e-4

# Dead time of the neutron counter. [s]
DEAD_TIME = 1.2e-6
