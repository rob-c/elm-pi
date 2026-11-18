"""Writes environment/ for this task. The truth is in the verifier, computed from this table.

    python make_environment.py <environment dir>

The table is not PSTAR itself: it is the Andersen-Ziegler proton fit for aluminium below
1 MeV joined to the Bethe formula (I = 166 eV) above 3 MeV, on PSTAR's energy grid, which
lands within about 2% of PSTAR. A session must take the numbers from the file.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])

Z, A, I_EV = 13, 26.9815, 166.0
ME, MP, K = 0.510999, 938.272, 0.307075          # MeV, MeV, MeV cm2/mol
N_A = 6.02214e23


def bethe(energy):
    gamma = 1 + energy / MP
    beta2 = 1 - 1 / gamma**2
    bg2 = beta2 * gamma**2
    t_max = 2 * ME * bg2 / (1 + 2 * gamma * ME / MP + (ME / MP) ** 2)
    return K * Z / A / beta2 * (0.5 * np.log(2 * ME * bg2 * t_max / (I_EV * 1e-6) ** 2) - beta2)


def andersen_ziegler(energy):
    """Protons in Al, eV per 1e15 atoms/cm2 with E in keV, turned into MeV cm2/g."""
    kev = energy * 1000.0
    low = 4.739 * kev**0.45
    high = 2766.0 / kev * np.log(1 + 164.5 / kev + 0.02023 * kev)
    return low * high / (low + high) * 1e-21 * N_A / A


def stopping(energy):
    x = np.clip((np.log(energy) - np.log(1.0)) / (np.log(3.0) - np.log(1.0)), 0, 1)
    weight = x * x * (3 - 2 * x)
    return (1 - weight) * andersen_ziegler(energy) + weight * bethe(energy)


grid = np.concatenate([
    np.arange(10, 30, 2.5), np.arange(30, 100, 5), np.arange(100, 300, 25), np.arange(300, 1000, 50),
    np.arange(1000, 3000, 250), np.arange(3000, 10000, 500), np.arange(10000, 20000, 2500), [20000, 25000, 30000],
]) / 1000.0
rows = ["energy_mev,stopping_power_mev_cm2_g"] + ["%.4g,%.4g" % (e, stopping(e)) for e in grid]
(out / "stopping_power.csv").write_text("\n".join(rows) + "\n")
(out / "notes.md").write_text("""# Degrader for the proton irradiations, beam line 2

- Beam: protons, 17.0 MeV kinetic energy behind the vacuum window (the window
  is already taken off).
- Degrader now in the holder: one aluminium plate straight behind the window,
  270.0 mg/cm2 by weighing. The beam crosses it at normal incidence.
- Aluminium: density 2.699 g/cm3.
- For the next run we want 5.0 MeV behind the degrader, and have to order a
  plate for that in place of this one.

## stopping_power.csv

Mass stopping power (electronic plus nuclear) of protons in aluminium, from
the tables the group uses: kinetic energy in MeV, stopping power in MeV cm2/g,
10 keV to 30 MeV. Below 10 keV the stopping power goes as the square root of
the energy.
""")
print("%d rows; S(17 MeV) = %.2f MeV cm2/g" % (len(grid), stopping(17.0)))
