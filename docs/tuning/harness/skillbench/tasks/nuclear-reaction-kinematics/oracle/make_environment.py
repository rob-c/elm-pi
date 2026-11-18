"""Writes environment/ for this task: the run plan. Nothing is random.

    python make_environment.py <environment dir>

p(7Li,n)7Be in inverse kinematics, 1.9 MeV per nucleon above a 13.09 MeV
threshold: the neutrons are confined to a 20.9 degree cone, so a detector at
10 degrees sees two energies, and the lab cross section is 15 and 4 times the
centre-of-mass one for the two groups.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

(out / "notes.md").write_text("""# Run plan: neutrons from p(7Li,n)7Be

## Beam

- 7Li, charge state 3+, kinetic energy 15.00 MeV at the middle of the target
  (the energy loss in the foil is already taken off; treat the target as thin).
- 60.0 nA electrical on target, from the Faraday cup.

## Target

- Polyethylene foil, (CH2)n, 50.0 ug/cm2, perpendicular to the beam.
- Molar mass of CH2: 14.027 g/mol. Hydrogen is the target; ignore the carbon.

## Detector

- Neutron detector on a collimator at 10.0 degrees to the beam (lab),
  subtending 0.500 msr at the target.

## Reaction data

- Rest masses of the nuclei, MeV/c2:

  | particle | mass |
  |---|---|
  | p | 938.272 |
  | n | 939.565 |
  | 7Li | 6533.833 |
  | 7Be | 6534.184 |

- 7Be is left in its ground state.
- Cross section at this energy: isotropic in the centre-of-mass frame,
  d(sigma)/d(Omega) = 24.0 mb/sr (centre of mass).

## Constants

- e = 1.602177e-19 C
- N_A = 6.02214e23 /mol
""")
print("wrote notes.md")
