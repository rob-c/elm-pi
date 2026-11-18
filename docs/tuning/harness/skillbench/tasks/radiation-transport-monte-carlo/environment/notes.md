# Cs-137 behind lead: Monte Carlo validation runs

## Model

- Point isotropic source; the source card emits 661.657 keV photons only.
- Lead slab, 4.00 cm thick, density 11.35 g/cm3, across the line from the
  source to the detector. Everything else is void.
- Detector: a small cell centred 100.0 cm from the source.
- Tally: track-length photon flux in the detector cell, energy bin 0.6610 to
  0.6620 MeV only (photons that have not scattered), in 1/cm2 per source
  particle.
- runs.csv: one line per job as the code printed it - the seed, the number of
  histories, the tally mean and its relative error (one standard deviation).

## Source

- Cs-137, 1.85 GBq on the day of the measurement we compare with.
- Emission probability of the 661.657 keV photon: 0.851 per decay (ENSDF).

## Attenuation data

- Lead at 661.7 keV: mu/rho = 0.1101 cm2/g (NIST XCOM, total attenuation with
  coherent scattering).

## Group rule

- A tally with a relative error above 0.10 is not reliable and is never
  quoted on its own (MCNP manual).
