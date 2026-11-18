---
name: gamma-spectroscopy
description: "Gamma-ray spectra from HPGe, NaI or LaBr detectors - energy and efficiency calibration, net peak areas, dead time, summing, activities and detection limits."
disable-model-invocation: true
---

# Gamma-ray spectroscopy

Three results go wrong most often: a peak's height or gross counts reported as
its area; an efficiency taken at the wrong energy or for a different geometry;
and dead time or coincidence summing left out of an activity.

## From a spectrum to an activity

1. **Energy calibration.** Fit centroid against energy for known lines across
   the range used (linear, quadratic only if the residuals ask for it) and show
   the residuals. Familiar lines: 511.0 (annihilation), 661.7 (Cs-137), 1173.2
   and 1332.5 (Co-60), 1460.8 (K-40), 2614.5 keV (Tl-208). Energies to more
   digits, and every emission probability Iγ, come from `nuclear-data-lookup`,
   not from memory.
2. **Net peak area.** Fit a Gaussian (HPGe: plus a low-energy tail and a step
   if the fit needs them) on a local background with a Poisson likelihood - see
   `data-fitting`. The area is the integral of the peak function, in counts. By
   regions instead: N = G - B with B = (n/m) C, where G is the gross count in
   the n peak channels and C the count in m background channels either side;
   σ(N)² = G + (n/m)² C.
3. **Resolution as a check.** FWHM = 2.355 σ. HPGe is about 2 keV at 1332 keV,
   NaI about 7% at 662 keV; a peak much wider is a doublet, a gain drift or the
   wrong detector model.
4. **Full-energy-peak efficiency.** ε(E) = N / (A Iγ t_live) from a calibrated
   source in the same geometry and matrix as the sample. Fit ln ε as a
   polynomial in ln E, interpolate only, and carry the source certificate's
   uncertainty. A point-source curve does not apply to a volume sample
   (solid angle, self-absorption).
5. **Activity.** A = N / (ε Iγ t_live), then:
   - decay during the count: multiply by λ t_real / (1 - exp(-λ t_real));
   - decay since the reference date: multiply by exp(λ Δt);
   - dead time: use live time, and say how it was measured (MCA clock, pulser);
     above roughly 10% dead time also check for pile-up losses;
   - true-coincidence summing for cascade emitters (Co-60, Eu-152, Y-88) close
     to the detector: correct it, or count at a distance where it is negligible.
6. **Background.** Subtract a background spectrum scaled by live time, peak by
   peak. Room lines: 1460.8 (K-40), 609.3 and 1764.5 (Bi-214), 2614.5 (Tl-208).

## Reading a spectrum

- Compton edge at 2E² / (mₑc² + 2E); backscatter peak at E / (1 + 2E/mₑc²),
  with mₑc² = 511.0 keV. Single and double escape peaks at E - 511 and
  E - 1022 keV for E above 1022 keV; sum peaks at E₁ + E₂; lead X-rays at
  72-88 keV from the shield.
- Identify a nuclide by all its strong lines in the right ratios (after
  efficiency), not by one energy match within the resolution.

## Detection limits

For a peak that is absent or marginal, give a limit rather than a small
activity with a large error. Currie, 5% false-positive and false-negative
rates, background B counts in the peak region: critical level
L_c = 2.33 √B, detection limit L_d = 2.71 + 4.65 √B counts, and the minimum
detectable activity is L_d / (ε Iγ t_live). Say which convention was used.

## Check before reporting

- Area, not height; net, not gross; live time, not real time.
- Efficiency curve: source, date, geometry, fit residuals, energy range.
- Each Iγ and half-life with the evaluation it was read from.
- Uncertainty budget: counting, efficiency, Iγ, half-life, summing, geometry -
  combined per `uncertainty-propagation`.
- A known line (K-40, or the calibration source re-measured) comes out right.

## Related

- Skills here: `data-fitting`, `uncertainty-propagation`, `histogram-analysis`,
  `nuclear-data-lookup`, `radioactive-decay-chains`, `radiation-detectors-and-daq`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `uncertainty-and-units`, `matplotlib`.
