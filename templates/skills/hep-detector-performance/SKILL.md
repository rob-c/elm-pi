---
name: hep-detector-performance
description: "Tracking and calorimeter performance - momentum from curvature, sagitta, multiple scattering, impact parameter, alignment; energy-resolution terms, shower scales, calibration; fitted resolutions."
disable-model-invocation: true
---

# Tracking and calorimeter performance

Common errors: resolution terms added linearly instead of in quadrature; an
RMS or one full-range Gaussian width quoted for a distribution with tails; scale (where the peak
is) confused with resolution (how wide it is); and a calibration that exists
only in simulation. Below, ⊕ means a sum in quadrature.

## Tracking

- **Curvature.** p_T [GeV] = 0.3 B [T] R [m] for unit charge, and
  p = p_T / sin θ with θ the polar angle. Over a lever arm L the sagitta is
  s = L²/(8R) = 0.3 B L² / (8 p_T).
- A tracker measures curvature, so errors are Gaussian in q/p_T, not in p_T.
  At high momentum, plot and fit residuals in 1/p_T.
- **Measurement term** (N equally spaced points of resolution σx, in metres):
  σ(p_T)/p_T = σx p_T / (0.3 B L²) × √(720/(N+4)). It grows with p_T.
- **Multiple scattering** (Highland): the plane-projected angle is
  θ0 = (13.6 MeV / βcp) z √(x/X0) [1 + 0.038 ln(x z² / (X0 β²))]
  for thickness x in radiation lengths X0. It gives a term roughly constant
  in p_T, so σ(p_T)/p_T = a p_T ⊕ b.
- **Impact parameter.** σ(d0) = a ⊕ b / (p_T √(sin θ)): a from point
  resolution and geometry, b from scattering in the innermost material.
- **Vertices.** Decay length L = βγcτ; cut on its significance L/σ, and
  remember that a displacement cut biases a lifetime.
- **Alignment.** Unbiased residuals (the hit left out of the fit) centred on
  zero are necessary, not sufficient: weak modes (twist, radial expansion,
  sagitta bias) keep residuals fine and shift momenta. Check the Z or J/ψ
  mass against φ, η and charge, E/p for electrons against positrons, and
  cosmic-ray tracks.

## Calorimetry

- σ(E)/E = a/√E ⊕ b/E ⊕ c, E in GeV: stochastic term a (sampling,
  photostatistics), noise b (electronics, pile-up), constant c
  (non-uniformity, miscalibration, leakage), which dominates at high energy.
- **Scales.** Electromagnetic showers: depth in radiation lengths X0, maximum
  near ln(E/Ec) X0 with Ec the critical energy; about 90% of the energy
  within one Molière radius. Hadronic showers: the nuclear interaction
  length, and of order ten of them for containment at collider energies.
- Unequal response to electrons and hadrons (e/h ≠ 1) makes the hadron
  response non-linear and adds to the constant term.
- **Calibration chain.** Electronics (pulser, ADC to charge); cell
  equalisation with minimum-ionising muons; the electromagnetic scale from
  test beam and from Z → ee (peak position gives scale, width gives
  resolution); π0 → γγ and E/p at low energy; jets in `hep-jets`. In situ,
  scale corrections go on data and extra smearing on simulation.

## Measuring a resolution

- In simulation: (reconstructed - true)/true. In data: a mass peak; for two
  equal, uncorrelated legs σ(m)/m = (1/√2) σ(p)/p.
- A resonance's natural width is not resolution: fit the Z as a Breit-Wigner
  convolved with a resolution function, never a bare Gaussian.
- Histogram the response before taking a width. With a tail (upstream
  showers, leakage, bremsstrahlung) the RMS measures the tail: a tail of a
  fixed fraction of E fakes a constant term of several per cent. For a, b
  and c use the core. In one line:
  `sigma = 1.4826 * np.median(np.abs(x - np.median(x)))`. Or a Gaussian
  fitted to the histogram (a curve fit, not moments) from about mean - 2σ to
  mean + 2.5σ, iterated until the window stops moving; or the half-width of
  the smallest 68.3% interval. Never `np.std` or `np.mean` of the events
  inside a window, iterated or not: clipping cuts the Gaussian's own tails
  and settles 14% low in every term. Name the estimator.
- Report scale and resolution separately, against energy or p_T and η, and
  fit the terms with ⊕ (`data-fitting`), giving their correlation.

## Check before reporting

- Quadrature, not linear sums; units GeV, tesla, metres.
- Tracking residuals examined in curvature at high p_T.
- The estimator of width named; tails shown on a log scale.
- A data-driven check of the scale (a known mass peak).
- Sample, selection and the material description used.

## Related

- Skills here: `data-fitting`, `hep-detector-simulation`,
  `hep-particle-identification`, `hep-jets`, `hep-kinematics`,
  `stopping-power-and-range`, `uncertainty-propagation`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `uncertainty-and-units`, `matplotlib`, `scientific-visualization`.
