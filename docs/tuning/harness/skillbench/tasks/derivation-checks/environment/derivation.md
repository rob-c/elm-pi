# Self-absorption of the 662 keV line in the spherical samples

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

Copper, mass attenuation coefficient at 662 keV mu/rho = 0.0726 cm^2/g (NIST
XCOM, coherent scattering included), density 8.96 g/cm^3.

| sphere | diameter |
|---|---|
| A | 36 mm |
| B | 60 mm |
