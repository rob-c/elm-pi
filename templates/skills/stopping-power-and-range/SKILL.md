---
name: stopping-power-and-range
description: "Energy loss of charged particles in matter - Bethe formula and its scaling, units, ranges and the Bragg peak, straggling and Landau tails, electrons, SRIM and NIST tables, loss in targets and windows."
disable-model-invocation: true
---

# Stopping power and range

The mistakes: the mean energy loss used where the most probable is what a
thin detector sees; units mixed (MeV cm²/g, MeV/cm, keV/µm, a thickness in
mg/cm²); ΔE taken as S × thickness in a layer thick enough for S to change;
and a formula or table used below its range of validity.

## The Bethe formula

-dE/dx = K z² (Z/A) (1/β²) [ ½ ln(2 mₑc² β²γ² Tmax / I²) - β² - δ/2 ],
K = 0.307 MeV cm²/mol, giving MeV cm²/g with A in g/mol; z is the projectile
charge, I the mean excitation energy (tabulated), δ the density correction.

- It depends on the projectile only through z and β: at the same velocity
  dE/dx scales as z². Falls as 1/β² at low speed, has a broad minimum near
  βγ = 3-4, then a slow relativistic rise.
- Minimum-ionising values: between about 1.1 (lead) and 2 MeV cm²/g (water,
  plastics), about 4 in hydrogen.
- Valid to a few per cent for βγ from about 0.1 to 1000. Below, shell and
  charge-exchange effects and nuclear stopping take over: use tables. Far
  above, radiative losses do.
- Range scaling at equal velocity: R scales as M/z². So
  R_b(T) = (M_b/M_a)(z_a/z_b)² R_a(T M_a/M_b), less a small correction for
  electron pick-up at low energy.

## Units

- Linear stopping power = ρ × mass stopping power: MeV cm²/g × g/cm³ gives
  MeV/cm, and 1 MeV/cm = 0.1 keV/µm.
- Thickness as areal density: mg/cm² = ρ × length. SRIM also prints
  eV per 1e15 atoms/cm²: convert with N_A/M.
- Compounds: Bragg additivity, mass stopping powers weighted by mass
  fraction. Off by several per cent at low energy (chemical binding, phase).

## Energy loss and range

- Thin layer (ΔE much less than E): ΔE = S(E) t. Otherwise integrate
  dE/dx = -S(E), or use range tables: R(E_out) = R(E_in) - t, which is exact
  in the continuous-slowing-down approximation (CSDA) and the simplest.
- CSDA range R(E) = ∫ dE/S from 0 to E. The projected range is shorter:
  slightly for ions, greatly for electrons.
- Bragg peak: the loss rises as the particle slows, so most energy goes in
  near the end; range straggling (about 1% of the range for protons) smears
  it.
- Thin absorbers: the loss distribution is Landau-Vavilov, with a long
  high-loss tail. The mean is pulled up by rare events; a detector's peak is
  the most probable value, well below the Bethe mean. The width is about 4ξ,
  ξ = (K/2) z² (Z/A) x/β² with x in g/cm². Thick absorbers: Gaussian.
- Add the layers in the order the beam meets them: window, dead layer,
  target (reaction depth), detector entrance.

## Electrons

Collisional plus radiative loss. They are equal at the critical energy,
about 610 MeV/(Z + 1.24) in solids and liquids and 710 MeV/(Z + 0.92) in
gases; above it E(x) = E0 exp(-x/X0), X0 the radiation length (tabulated,
g/cm²). An electron's path is tortuous: the depth reached is far less than
the CSDA range.

## Tables and codes

- NIST PSTAR, ASTAR, ESTAR: protons, alphas, electrons in many materials.
- SRIM: any ion in any target, tables and Monte Carlo; a few per cent for
  light ions, 5-10% for heavy ions in compounds.
- ATIMA and LISE++ for fast heavy ions and stacks of layers; Geant4 for a
  full geometry (`radiation-transport-monte-carlo`).
- Tables differ by a few per cent: name the one used and its version.

## Check before reporting

- Units followed through every step; table or code named; energy inside its
  validity.
- Thick or thin treated accordingly; mean or most probable loss said.
- A known value reproduced: a 5.5 MeV α goes about 4 cm in air; a 100 MeV
  proton about 7.7 cm in water; a minimum-ionising particle leaves about
  2 MeV per cm of plastic scintillator.
- Where a range matters at the per cent level: straggling, and the
  uncertainty of I.

## Related

- Skills here: `nuclear-data-lookup`, `radiation-transport-monte-carlo`,
  `nuclear-reaction-kinematics`, `dosimetry-and-shielding`,
  `hep-particle-identification`, `hep-detector-performance`, `numerical-methods`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `uncertainty-and-units`, `matplotlib`.
