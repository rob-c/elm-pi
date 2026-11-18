# HLT_Mu50 efficiency from the MET-triggered reference sample

The reference sample is 2025 data recorded by the missing-momentum triggers,
which do not use the muon system, so it is unbiased for a muon trigger.

`probes.csv` has one row per probe: an offline muon passing the tight
identification and isolation, |eta| < 2.4, in an event with exactly one such
muon.

| column | meaning |
|---|---|
| probe | running number |
| pt | offline muon pT [GeV] |
| hlt_mu50 | 1 if HLT_Mu50 fired and its trigger object matches the probe (deltaR < 0.1), else 0 |

## Binning

The efficiency is quoted in these offline pT bins [GeV], the ones the
scale-factor file uses:

30, 40, 45, 48, 50, 52, 55, 60, 70, 90, 120, 200, 500

Twelve bins. Probes below 30 GeV or above 500 GeV are not used.
