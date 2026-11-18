"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

A six-step derivation of the fraction of photons that leave a uniformly
emitting sphere unattenuated, towards a distant detector. Every step is right
but the fifth: the boundary term of the integration by parts has the wrong
sign. The right closed form, with tau = mu R, is

    f = 3 / (8 tau^3) * [2 tau^2 - 1 + (1 + 2 tau) exp(-2 tau)]

and the file ends with (1 - 2 tau) in the bracket. The file's own check, the
limit of large tau, holds for both. The limit of small tau does not: the right
form goes to 1 - 3 tau / 4, the file's diverges to minus infinity. At the two
spheres asked about (tau = 1.17 and 1.95) the file's formula still gives
fractions that look like fractions, 22% and 2.3% low.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])

MU_RHO, DENSITY = 0.0726, 8.96            # cm2/g at 662 keV and g/cm3: copper
DIAMETER_MM = {"A": 36.0, "B": 60.0}

(out / "derivation.md").write_text("""# Self-absorption of the 662 keV line in the spherical samples

The line is emitted uniformly through a homogeneous sphere of radius R. The
detector is far away compared with R, so the photons that count leave in one
direction, parallel to each other. mu is the linear attenuation coefficient of
the sample material at the line's energy. Wanted: the fraction f of those
photons that leave the sample without interacting. The measured count rate is
divided by f.

## Derivation

1. Put the z axis towards the detector and use cylindrical coordinates
   (rho, z). The sphere's surface is at z = +-h(rho), with

       h(rho) = sqrt(R^2 - rho^2).

   A photon emitted at (rho, z) has a path s = h - z to the surface and
   survives it with probability exp(-mu s).

2. Averaged over the volume V = (4/3) pi R^3:

       f = (1/V) * Int_0^R 2 pi rho d(rho) * Int_{-h}^{+h} exp(-mu (h - z)) dz

3. The z integral:

       Int_{-h}^{+h} exp(-mu (h - z)) dz = (1 - exp(-2 mu h)) / mu

4. Change variable from rho to h. From h^2 = R^2 - rho^2, rho d(rho) = -h dh,
   and rho from 0 to R is h from R to 0, so

       f = (2 pi / (mu V)) * Int_0^R h (1 - exp(-2 mu h)) dh
         = (2 pi / (mu V)) * (R^2 / 2 - I),      I = Int_0^R h exp(-2 mu h) dh

5. I by parts:

       I = R exp(-2 mu R) / (2 mu) + (1 - exp(-2 mu R)) / (4 mu^2)

6. Putting it together, with tau = mu R:

       f = (2 pi / (mu V)) * [R^2/2 - R exp(-2 tau)/(2 mu) - (1 - exp(-2 tau))/(4 mu^2)]

       f = 3 / (8 tau^3) * [2 tau^2 - 1 + (1 - 2 tau) exp(-2 tau)]

Check: for tau >> 1 this is f = 3 / (4 tau), which is what it should be - only
a layer about 1/mu deep on the detector's side of the sphere gets out, and
that is the fraction (pi R^2 / mu) / V = 3 / (4 mu R) of the volume.

## The two samples

Copper, mass attenuation coefficient at 662 keV mu/rho = %.4f cm^2/g (NIST
XCOM, coherent scattering included), density %.2f g/cm^3.

| sphere | diameter |
|---|---|
| A | %.0f mm |
| B | %.0f mm |
""" % (MU_RHO, DENSITY, DIAMETER_MM["A"], DIAMETER_MM["B"]))

for name, diameter in DIAMETER_MM.items():
    tau = MU_RHO * DENSITY * diameter / 20.0
    right = 3 / (8 * tau**3) * (2 * tau**2 - 1 + (1 + 2 * tau) * np.exp(-2 * tau))
    written = 3 / (8 * tau**3) * (2 * tau**2 - 1 + (1 - 2 * tau) * np.exp(-2 * tau))
    print("sphere %s: tau = %.4f, f = %.5f; as written %.5f (%+.1f%%)" % (name, tau, right, written, 100 * (written / right - 1)))
