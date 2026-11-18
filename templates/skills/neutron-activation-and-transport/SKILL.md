---
name: neutron-activation-and-transport
description: "Neutron work by hand - thermal and resonance cross sections, the activation equation, self-shielding, moderation, mean free path, time of flight, neutron detection and shielding; the flux conventions."
disable-model-invocation: true
---

# Neutrons: activation, moderation, time of flight

The mistakes: a 2200 m/s cross section multiplied by a flux defined some
other way; the saturation or decay factor left out, or its exponent in mixed
time units; self-shielding ignored in a thick or strongly absorbing sample;
and a time-of-flight energy from the wrong flight path or time zero.

## Cross sections and flux conventions

- The "thermal" cross section σ0 is at 0.0253 eV, that is 2200 m/s, 293.6 K.
  A 1/v absorber has σ(E) = σ0 √(0.0253 eV / E), and its reaction rate per
  atom is σ0 × n × 2200 m/s whatever the spectrum: that product n v0 is the
  conventional "2200 m/s flux". If the flux is instead the true ∫ n(v) v dv
  of a Maxwellian at 293.6 K, the matching cross section is (√π/2) σ0 =
  0.886 σ0. Find out which flux you were given.
- Not 1/v (resonance near thermal): multiply by the Westcott g-factor,
  looked up for the temperature.
- Epithermal: the flux is roughly 1/E, and the rate is the resonance
  integral I0 = ∫ σ(E) dE/E above the cadmium cut-off (about 0.5 eV) times
  the epithermal flux per unit lethargy. Per atom:
  R = σ0 φ(thermal) + I0 φ(epithermal). A cadmium-covered foil separates them.
- Fast: spectrum-averaged cross sections; IRDFF for dosimetry reactions.
- σ0, I0 and σ(E) from ENDF/B, JEFF or TENDL via `nuclear-data-lookup`.

## Activation

- Rate R = N σ φ, with N = m N_A θ / M target atoms (θ the isotopic
  abundance), σ in cm² (1 b = 1e-24 cm²), φ in cm⁻² s⁻¹.
- Activity after irradiating for t_irr and cooling for t_c:
  A = N σ φ (1 - exp(-λ t_irr)) exp(-λ t_c). Counting corrections are in
  `radioactive-decay-chains` and `gamma-spectroscopy`.
- In a high flux check target burn-up and capture on the product.
- Self-shielding: when Σ t is not small the inside of the sample sees less
  flux, thermal and (more sharply) at resonances. Use thin foils or dilute
  samples, or compute the factor.
- k0 method: concentrations relative to a gold comparator, from tabulated
  k0 factors and two measured channel parameters (flux ratio f, shape α).

## Moderation and transport by hand

- Macroscopic cross section Σ = N σ, N = ρ N_A / M atoms/cm³; mean free
  path 1/Σ; uncollided (narrow-beam) transmission exp(-Σ x).
- Elastic scattering on mass number A: the neutron keeps at least
  α = ((A-1)/(A+1))² of its energy. Mean lethargy gain per collision
  ξ = 1 + α ln α / (1 - α): 1 for hydrogen, 0.158 for carbon, about
  2/(A + 2/3) for heavy nuclei. Collisions from E0 to E: ln(E0/E)/ξ - from
  2 MeV to thermal, 18 in hydrogen and 115 in graphite.
- Anything with real geometry or spectra: `radiation-transport-monte-carlo`.

## Time of flight

- Non-relativistic: E[eV] = (72.3 L[m] / t[µs])². Above about 1 MeV use
  E = m_n c² (γ - 1) with β = L/(c t); the non-relativistic value is already
  0.16% low at 1 MeV.
- Time zero is not the gamma flash: the flash left with the neutrons and
  arrives L/c = 3.336 ns per metre later. t = t(n) - t(γ) + L/c.
  Resolution: ΔE/E = 2 √((Δt/t)² + (ΔL/L)²).

## Detection and shielding

- Detectors convert: He-3(n,p), B-10(n,α), Li-6(n,t) for slow neutrons, all
  1/v; proton recoil in organic scintillators with n/γ pulse-shape
  discrimination, moderated counters (Bonner spheres), fission chambers and
  threshold activation foils for fast ones. Efficiency varies strongly with
  energy: state the calibration (Cf-252, AmBe).
- Shielding in layers: slow fast neutrons with hydrogen (polyethylene,
  water, concrete); absorb the thermals (boron, lithium, cadmium); then stop
  the capture gammas (2.2 MeV from hydrogen) with lead or steel. Above
  about 10 MeV put iron first.
- A hand estimate of shielding or dose is for planning, not a safety
  assessment: the local radiation protection officer and regulations decide.

## Check before reporting

- Which flux convention, which spectrum, cross section source and
  temperature.
- Units: b to cm², seconds throughout, abundance and enrichment included.
- Saturation and decay factors present; self-shielding considered.
- Time of flight: path length, time zero, relativistic or not.
- One number checked against a published worked case (a gold foil).

## Related

- Skills here: `nuclear-data-lookup`, `radioactive-decay-chains`,
  `gamma-spectroscopy`, `radiation-transport-monte-carlo`,
  `dosimetry-and-shielding`, `radiation-detectors-and-daq`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `uncertainty-and-units`, `matplotlib`, `sympy`.
