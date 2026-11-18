---
name: nuclear-reaction-kinematics
description: "Two-body nuclear reaction kinematics and yields - lab and centre-of-mass frames, inverse kinematics, thresholds, Coulomb barrier, Rutherford scattering, beam current and target thickness to counts."
disable-model-invocation: true
---

# Nuclear reaction kinematics and yields

The mistakes: lab and centre-of-mass (CM) angles, energies or cross sections
mixed, with no Jacobian between them; non-relativistic formulas used where
they are a few per cent out; the second kinematic solution in inverse
kinematics forgotten; and a yield with the beam in electrical rather than
particle current, or the target in mg/cm² where atoms/cm² was needed.

## Set-up

- A(a,b)B: target A, projectile a, ejectile b, residue B. Inverse kinematics:
  the heavy partner is the beam. Q from `nuclear-masses-and-q-values`; to a
  level at E_x use Q - E_x.
- Target at rest, projectile kinetic energy T_a, masses in energy units:
  s = (m_a + m_A)² + 2 m_A T_a; the energy available above the entrance
  masses is E_cm = √s - m_a - m_A, which is T_a m_A/(m_a + m_A)
  non-relativistically.
- Compute with four-vectors and invariants as the reference (a few lines of
  numpy). Non-relativistic formulas are a check, good to about T/(mc²) of
  the fastest particle; never use them for electrons or photons.

## Two-body final state

- In the CM each product has momentum p* with
  p*² = [s - (m_b + m_B)²] [s - (m_b - m_B)²] / (4s); boost to the lab with
  β = p_a/(T_a + m_a + m_A).
- Non-relativistic ejectile energy at lab angle θ:
  √T_b = { √(m_a m_b T_a) cos θ ± √[ m_a m_b T_a cos²θ
  + (m_B + m_b)(m_B Q + (m_B - m_a) T_a) ] } / (m_b + m_B).
- When the CM moves faster than the ejectile does in the CM (inverse
  kinematics; just above an endothermic threshold) both signs are physical,
  and there is a maximum lab angle. Elastic scattering of a heavy m₁ on a
  lighter m₂: sin θ_max = m₂/m₁. Report both solutions.
- Elastic recoil at lab angle φ: T = T_a · 4 m_a m_A/(m_a + m_A)² · cos²φ.

## Cross sections

- dσ/dΩ changes frame with the solid-angle Jacobian. Non-relativistic, with
  ρ = (CM speed)/(ejectile speed in the CM): tan θ_lab = sin θ_cm/(cos θ_cm + ρ)
  and dΩ_cm/dΩ_lab = (1 + ρ² + 2ρ cos θ_cm)^(3/2) / |1 + ρ cos θ_cm|.
  Integrated cross sections are the same in both frames.
- Rutherford, CM: dσ/dΩ = (Z1 Z2 e² / (4 E_cm))² / sin⁴(θ_cm/2), with
  e² = 1.44 MeV fm; the result is in fm²/sr, and 1 fm² = 10 mb.
- Head-on distance of closest approach: 1.44 Z1 Z2 / E_cm fm (E_cm in MeV).
- Coulomb barrier estimate: Vc = 1.44 Z1 Z2 / [r0 (A1^(1/3) + A2^(1/3))] MeV
  with r0 between 1.2 and 1.5 fm. State the r0 used; it is good to about 10%,
  and it is a CM energy: the lab energy is Vc (m_a + m_A)/m_A.

## Yields

- Thin target: counts = N_beam × n_t × σ × efficiency, or with
  dσ/dΩ × ΔΩ for a detector, σ in cm² (1 b = 1e-24 cm²).
- N_beam = I t / (q e) for electrical current I and charge state q. One
  particle nA is 6.24e9 particles per second.
- n_t (atoms/cm²) = areal density (g/cm²) × N_A / M × atoms of the isotope
  per formula unit × enrichment.
- Thick target: Y = N_beam ∫ σ(E) / S(E) dE from the threshold to the beam
  energy, S the stopping power per target atom per cm². The energy at the
  reaction is the beam energy less the loss in windows and in the target up
  to that depth: `stopping-power-and-range`.

## Tools

LISE++ and CatKin compute relativistic two-body kinematics and are a good
cross-check of your own calculation; neither replaces writing it out.

## Check before reporting

- Energy and momentum are conserved numerically for the reported solution.
- Every angle, energy and dσ/dΩ is labelled lab or CM.
- Relativistic and non-relativistic answers compared; the difference stated.
- Inverse kinematics: maximum angle and both solutions given.
- Units: mb/sr, atoms/cm², particles (not charges) on target.
- A known case reproduced: Rutherford at a forward angle, or one point
  against LISE++ or CatKin.

## Related

- Skills here: `nuclear-masses-and-q-values`, `stopping-power-and-range`,
  `scattering-theory-and-partial-waves`, `nuclear-reaction-codes`,
  `hep-kinematics`, `uncertainty-propagation`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `uncertainty-and-units`, `matplotlib`.
