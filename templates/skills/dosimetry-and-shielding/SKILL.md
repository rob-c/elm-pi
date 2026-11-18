---
name: dosimetry-and-shielding
description: "Radiation dose and shielding estimates - absorbed, equivalent and effective dose, Gy and Sv, point-source dose rates, attenuation with build-up, half-value layers, betas and neutrons; estimates, not assessments."
disable-model-invocation: true
---

# Dosimetry and shielding estimates

**A calculation here is an estimate for planning, not a safety assessment.**
Limits, classification of areas and whether something is acceptable are for
the local radiation protection officer and the regulations; never write that
a set-up "is safe". Say this in the report.

The mistakes: Gy and Sv, or equivalent and effective dose, used as one thing;
an activity turned into a dose rate without emission probabilities; narrow-beam
attenuation applied to a broad-beam shield with no build-up; old and SI
units mixed.

## Quantities

- Fluence Φ (particles/cm²); energy fluence Ψ = ΦE.
- Kerma (uncharged particles): energy transferred per mass. Absorbed dose D:
  energy imparted per mass, Gy = J/kg. With charged-particle equilibrium,
  for photons D = Ψ μ_en/ρ.
- Equivalent dose to a tissue: Σ w_R D, in Sv. w_R = 1 for photons,
  electrons and muons; 2 for protons and charged pions; 20 for alphas,
  fission fragments and heavy ions; for neutrons a function of energy from
  2.5 up to about 20 near 1 MeV (ICRP 103; look the curve up).
- Effective dose: Σ w_T × equivalent dose over tissues, Sv. It cannot be
  measured; instruments read operational quantities such as the ambient dose
  equivalent H*(10). Name the quantity you computed.
- 1 rad = 0.01 Gy; 1 rem = 0.01 Sv; 1 R = 2.58e-4 C/kg of air;
  1 Ci = 3.7e10 Bq; 1 MeV/g = 1.602e-10 Gy.

## Photon dose rate from a point source

1. Activity at the date in question (`radioactive-decay-chains`).
2. For each line, photons per second = A × emission probability
   (`nuclear-data-lookup`).
3. Fluence rate at distance r, nothing in between: φ = A Iγ / (4π r²).
4. Dose rate = Σ over lines of φ E (μ_en/ρ), with the mass
   energy-absorption coefficient of the medium (air, water, tissue) at that
   energy from the NIST tables; MeV/g/s × 1.602e-10 gives Gy/s.
5. Or use a tabulated gamma dose-rate constant, saying which quantity it
   gives (air kerma, ambient dose equivalent) and where it is from.

Magnitude check: about 0.14 µGy/h in tissue at 1 m per MBq per MeV of
photons emitted per decay, for photon energies of 0.5-2 MeV.

Inverse square holds for a source small against the distance, with no
scatter. Close to an extended source use the line or disc formula, or a
transport code.

## Attenuation

- Narrow beam: I = I0 exp(-μx), μ = (μ/ρ) ρ from NIST XCOM. Half-value layer
  0.693/μ; tenth-value layer 2.303/μ = 3.32 half-value layers.
- A real shield is broad-beam: multiply by the build-up factor
  B(μx, E, material), which is at least 1 and reaches 10 or more over several
  mean free paths in low-Z shields (tabulated; ANSI/ANS-6.4.3). Leaving it
  out underestimates the dose. If you do leave it out, say "narrow-beam: a
  lower bound".
- Several lines: attenuate each separately. The spectrum hardens, so a
  half-value layer measured for the first layer does not hold for the next.

## Other radiations

- Betas: range from ESTAR (`stopping-power-and-range`). Shield with low-Z
  material (plastic, aluminium) first: the fraction of beta energy turned to
  bremsstrahlung is roughly 3.5e-4 Z E_max[MeV]. Then lead for those photons
  if needed.
- Neutrons: fluence to dose with energy-dependent conversion coefficients
  (ICRP 74 operational, ICRP 116 effective), looked up; shielding in
  `neutron-activation-and-transport`.
- Alphas do not penetrate skin; the hazard is intake, through ICRP dose
  coefficients (Sv/Bq).
- Scatter around a shield, skyshine, streaming through gaps and activation
  are beyond hand estimates: `radiation-transport-monte-carlo`.

## Check before reporting

- The quantity named (absorbed, equivalent, effective, ambient) and Gy or Sv.
- Activity and date; emission probabilities and coefficients with sources,
  energy and medium.
- Build-up included, or the result labelled a lower bound.
- Agreement with the magnitude check or a gamma-constant estimate.
- Assumptions listed, with which way each errs.
- The statement that this is an estimate, not a safety assessment.

## Related

- Skills here: `nuclear-data-lookup`, `radioactive-decay-chains`,
  `stopping-power-and-range`, `neutron-activation-and-transport`,
  `radiation-transport-monte-carlo`, `uncertainty-propagation`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `uncertainty-and-units`, `pydicom`, `matplotlib`.
