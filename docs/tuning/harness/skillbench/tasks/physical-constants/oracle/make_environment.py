"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Five reference numbers for an ultracold-neutron storage trap. Two of the
constants they need are the project's own and are in its constants.py: the
neutron lifetime the collaboration adopted (877.75 s, not any PDG average) and
the acceleration of gravity measured in the hall (9.80297 m/s2, not 9.80665).
The rest - the neutron's mass and magnetic moment, e, h - are CODATA constants,
which scipy.constants has to all their digits. The numbers are asked for to six
significant figures, which values rounded from memory (m_n = 1.675e-27 kg,
60.3 neV/T, e = 1.602e-19 C, g = 9.81) miss by 1e-5 to 1e-3.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

WALL_NEV = 213.0          # Fermi potential of the wall coating
STORAGE_S = 300.0
TAU_N = 877.75            # s
G_LOCAL = 9.80297         # m/s2

(out / "constants.py").write_text('''"""Constants for the Bottle 2 storage analysis. Every analysis script imports them.

Change a value here only together with the analysis note (section 2.1): the
2026 result is quoted for these.
"""

# Neutron lifetime adopted for the 2026 analysis: the magneto-gravitational
# trap result, as agreed at the collaboration meeting of 2026-03-12. [s]
TAU_N = %.2f

# Acceleration of gravity at the trap floor, from the gravimetric survey of the
# hall in 2023 (the hall is 1040 m above sea level). [m/s^2]
G_LOCAL = %.5f

# Loss probability per wall bounce, fitted to the 2025 runs.
WALL_LOSS_PER_BOUNCE = 2.7e-4

# Dead time of the neutron counter. [s]
DEAD_TIME = 1.2e-6
''' % (TAU_N, G_LOCAL))

(out / "trap.md").write_text("""# Bottle 2: reference numbers for the analysis note (section 3)

Material storage bottle for ultracold neutrons on the West-2 port.

## The trap

- Walls and lid: electroless nickel-phosphorus on aluminium. Fermi potential of
  the coating, measured on witness samples by cold-neutron reflectometry:
  %.0f neV. Take it as exact for the table.
- A neutron whose kinetic energy at the trap floor is below the wall potential
  is stored; one exactly at it has the "critical" energy.
- Holding time in the standard cycle: %.0f s.

## What the table lists

For a neutron at the critical energy:

- the critical velocity: its speed;
- its de Broglie wavelength;
- the height it can rise to in the hall before gravity stops it;
- the magnetic flux density B at which |mu_n| B equals the wall potential (the
  field that holds one spin state as well as the wall does).

And for the standard cycle: the fraction of the stored neutrons that have not
beta-decayed at the end of the holding time (no other losses counted).

## Files

- `trap.md` - this note
- `constants.py` - the constants the analysis scripts import
""" % (WALL_NEV, STORAGE_S))
print("wrote trap.md and constants.py")
