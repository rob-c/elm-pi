"""Writes environment/ for this task: one file of notes, no generated data.

    python make_environment.py <environment dir>

What the task turns on, none of it pointed out in the notes: the beam energy is a
laboratory energy and the masses are given, so k needs the reduced mass and the
centre-of-mass energy; at k R = 2.3 the d wave is 8% of the cross section; and the
scattering length is wanted in the convention k cot(delta) = +1/a, in which this well,
which binds one s state, has a negative a.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])
(out / "notes.md").write_text("""# Square-well model for n + 4He

The toy model for the comparison with the lattice group: a neutron on 4He,
both treated as spinless, one central potential for every partial wave,
non-relativistic.

- V(r) = -24.0 MeV for r < 2.60 fm, zero outside; r is the distance between
  the neutron and the 4He.
- Masses: neutron 939.565 MeV/c^2, 4He nucleus 3727.379 MeV/c^2.
- hbar c = 197.327 MeV fm.
- Beam: neutrons of 25.0 MeV kinetic energy in the laboratory, helium target
  at rest.
- Low-energy parameters go into the lattice group's table, which is in their
  convention: k cot(delta_0) = 1/a + (1/2) r k^2 + ...
- Phase shifts in degrees, cross sections in barn.
""")
print("notes.md written")
