---
name: radiation-detectors-and-daq
description: "Radiation detectors and their data acquisition - what limits energy and time resolution, pulse-shape discrimination, dead time, pile-up, accidental coincidences, list-mode data, digitisers, efficiencies."
disable-model-invocation: true
---

# Radiation detectors and data acquisition

The mistakes: count rates left uncorrected for dead time, or corrected with
the wrong model; accidental coincidences not subtracted; a resolution
compared with the statistical limit without the Fano factor or the noise; and
an efficiency quoted without saying intrinsic or absolute.

## Energy resolution

- FWHM = 2.355 σ. Contributions add in quadrature: carrier statistics,
  electronic noise, incomplete collection or light-yield non-uniformity.
- Semiconductors: FWHM(statistics) = 2.355 √(F w E), with w the energy per
  electron-hole pair (3.6 eV in Si, 2.96 eV in Ge) and F the Fano factor,
  about 0.1 (look the value up). That is about 1.5 keV at 1.33 MeV in Ge
  before noise.
- Scintillators: Poisson in the number of photoelectrons, FWHM/E about
  2.355/√N_pe, so it improves as 1/√E, plus non-proportionality.
- Fit FWHM² = a + bE (+ cE²) over calibration lines; check linearity too.

## Timing

- A leading-edge discriminator walks with amplitude. A constant-fraction
  discriminator removes the walk for a fixed pulse shape; on digitised
  pulses, interpolate between samples. Jitter is σ_t = σ_noise/(dV/dt) at
  the crossing.
- Measure the resolution from a prompt coincidence peak; for two identical
  detectors each is the pair's width divided by √2.

## Pulse-shape discrimination

Charge comparison (tail over total integral) or zero-crossing. Figure of
merit = separation of the two peaks / (FWHM₁ + FWHM₂); above 1.27 the
Gaussians are apart by 3(σ₁ + σ₂). It depends on energy: quote the threshold
(in keV electron-equivalent) with it.

## Rates

- Dead time τ, with m the measured rate and n the true one. Non-paralysable:
  n = m/(1 - mτ). Paralysable (extending): m = n exp(-nτ), which has two
  solutions for n and a maximum m = 1/(eτ): a saturated detector reads low.
  Solve for both roots (nτ below and above 1) and choose with a second
  reading at a known different rate (source moved back, absorber): a reading
  that rises when the true rate falls means the upper root.
  Decide which model the chain is; better, use the system's live-time clock,
  a pulser, or the ratio of accepted to presented triggers.
- Pile-up within a resolving time τ_p affects a fraction 1 - exp(-nτ_p) of
  pulses; rejection circuits change the live time.
- Accidental coincidences between uncorrelated singles rates R1 and R2 with
  logic pulses of width τ: 2τ R1 R2. Measure them in a delayed window and
  subtract; the true-to-accidental ratio falls as the rate rises.
- Intervals between random events are exponential: a histogram of them is a
  quick health check of a DAQ.

## Digitisers and list mode

- Sample faster than twice the highest signal frequency after the
  anti-aliasing filter, with several samples on the leading edge for timing.
  Take the baseline from pre-trigger samples pulse by pulse; watch it shift
  at high rate.
- List mode is (channel, timestamp, energy, maybe shape or waveform). Build
  events with a coincidence window on time-sorted data, the window chosen
  from the time-difference spectrum. Look for timestamp roll-over, unsynchronised
  clocks between boards, out-of-order buffers and duplicated events before
  any physics.
- Thresholds are stated in calibrated energy, and the efficiency just above
  one is a curve, not a step (`hep-efficiency-measurement`).

## Efficiency

- Absolute = detected / emitted by the source; intrinsic = detected /
  incident on the detector; absolute = intrinsic × Ω/4π × transmission.
  Say also whether it is full-energy-peak or total.
- A disc of radius a seen on axis from distance d subtends
  Ω = 2π (1 - d/√(d² + a²)), about πa²/d² far away.

## Check before reporting

- Dead-time model and how τ or the live time was measured; correction size.
- Accidentals measured and subtracted; window stated.
- Resolution: FWHM or σ, at what energy, with what fit.
- Thresholds, calibration and which efficiency.
- Counting uncertainties per `statistics-and-significance`; rates as counts
  over live time.

## Related

- Skills here: `gamma-spectroscopy`, `stopping-power-and-range`,
  `radiation-transport-monte-carlo`, `hep-detector-performance`,
  `hep-efficiency-measurement`, `histogram-analysis`, `data-fitting`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `uncertainty-and-units`, `matplotlib`, `polars`.
