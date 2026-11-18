"""Writes environment/ for this task: one file of notes with the handbook data in it.

    python make_environment.py <environment dir>

The build-up factors are a Berger form, B = 1 + a mu x exp(b mu x) with a = 1.45 and
b = 0.055, rounded to three figures on the usual grid of mean free paths: close to the
published point-source values for concrete near 0.66 MeV, but not a copy of them. The
coefficients are rounded handbook values. A session must take all of them from the file.
"""
import math
import sys
from pathlib import Path

out = Path(sys.argv[1])
MEAN_FREE_PATHS = (0.5, 1, 2, 3, 4, 5, 6, 7, 8, 10, 15, 20)
rows = "\n".join("| %g | %.3g |" % (x, 1 + 1.45 * x * math.exp(0.055 * x)) for x in MEAN_FREE_PATHS)
(out / "notes.md").write_text("""# Source store: the Cs-137 source and the desk behind the wall

- Source: Cs-137 sealed source, active part 8 mm long, so a point source at
  these distances. Certificate: 2.00 Ci on 17 November 2016.
- The estimate is wanted for 17 November 2026.
- Point of interest: the desk on the other side of the store wall, 2.50 m
  from the source. The line from the source to the desk crosses the wall at
  right angles.
- Wall as built: ordinary concrete, 30.0 cm thick, density 2.30 g/cm3. Apart
  from the wall there is only air in between.
- If the wall has to be made thicker the source and the desk stay where they
  are.

## Decay data

- Cs-137: half-life 30.05 y.
- 661.7 keV gamma ray (from Ba-137m, in equilibrium): 0.851 per Cs-137 decay.
- The barium K x rays do not get out of the capsule.

## Handbook data at 661.7 keV

| quantity | value |
|---|---|
| mass attenuation coefficient, ordinary concrete | 0.0775 cm2/g |
| mass energy-absorption coefficient, air | 0.0293 cm2/g |
| mass energy-absorption coefficient, water | 0.0326 cm2/g |
| mass energy-absorption coefficient, soft tissue (ICRU four-component) | 0.0323 cm2/g |

Build-up factors for a point isotropic source in ordinary concrete at
661.7 keV, against the thickness in mean free paths:

| mean free paths | build-up factor |
|---|---|
| 0 | 1 |
%s

1 Ci = 3.7e10 Bq. 1 MeV = 1.602177e-13 J.
""" % rows)
print("notes.md written")
