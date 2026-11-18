# Sm-154: lifetime of the first 2+ state

Sm-154: Z = 62, A = 154.

## Ground-state band (ENSDF adopted levels)

| J pi | E [keV] |
|---|---|
| 0+ | 0.0 |
| 2+ | 81.976 |
| 4+ | 266.79 |
| 6+ | 543.9 |

The 2+ state decays only by the 81.976 keV E2 transition to the ground state.

## Our measurement

- LaBr3 fast timing, centroid-shift analysis of the 185 keV - 82 keV cascade.
- Half-life of the 2+ state: T1/2 = 3.10(5) ns.
- Total conversion coefficient of the 81.976 keV E2 transition (BrIcc):
  alpha = 4.94.

## Formulas we use

- E2 gamma-ray transition rate:
  T_gamma(E2; Ji -> Jf) [1/s] = 1.223e9 x (E_gamma [MeV])^5 x B(E2; Ji -> Jf) [e2 fm4].
  The level's total decay rate is T_gamma x (1 + alpha).
- Weisskopf unit for E2: 0.0594 x A^(4/3) e2 fm4.
- beta2 = (4 pi / (3 Z R0^2)) x sqrt(B(E2)up / e2), R0 = 1.2 A^(1/3) fm.
- Rigid rotor: E(J) = hbar^2 J (J + 1) / (2 I), I the moment of inertia.
