---
name: nuclear-reaction-codes
description: "Nuclear reaction model codes - TALYS and EMPIRE (Hauser-Feshbach, pre-equilibrium), FRESCO and DWBA, optical potentials, fusion-evaporation; which model choices are the uncertainty, and comparing with EXFOR."
disable-model-invocation: true
---

# Nuclear reaction model codes

The mistakes: a default-parameter run reported as "the" cross section with no
model uncertainty; an input written from memory with keywords the installed
version does not accept, and output described that the code never produced;
an optical potential used outside its range of energy or mass; and a
comparison with data in the wrong frame, units or isotopic mix.

## Which code

- **TALYS**: n, p, d, t, ³He, α and γ on targets from A = 12, about 1 keV to
  200 MeV: optical model, direct, pre-equilibrium (exciton), compound
  (Hauser-Feshbach with width fluctuations), fission. Excitation functions,
  residual production, spectra. TENDL is built with it.
- **EMPIRE**: the same scope, built for evaluations.
- **FRESCO**: coupled channels, DWBA, transfer, inelastic, breakup: angular
  distributions of direct reactions. DWUCK and TWOFNR for plain DWBA.
- **CCFULL**: coupled-channels fusion near and below the barrier.
- **PACE4** (in LISE++): fusion-evaporation residues. **GEF**: fission yields.
- **NJOY** processes evaluated files (Doppler broadening, group structures);
  it is not a reaction model.

Use what is installed; for anything missing see `installing-software`.

## Procedure

1. Run a sample case shipped with the code and reproduce its reference output
   before changing anything. Record the code version.
2. Write the input from the installed version's manual. TALYS needs four
   lines - `projectile n`, `element nb`, `mass 93`, `energy 14.` - and every
   other keyword has a default: check each one you add (`ldmodel`,
   `strength`, the optical-potential switches) against that manual. Read the
   output's warnings. Report only numbers the code printed.
3. Name the ingredients, because they are the result:
   - optical potential: Koning-Delaroche (global, neutrons and protons, 1 keV
     to 200 MeV, 24 ≤ A ≤ 209, near-spherical nuclei); α-particle potentials
     are the least certain and move (α,γ) and (α,n) by large factors;
   - level density model; γ-ray strength function; pre-equilibrium model;
   - the mass model wherever a mass is not measured.
4. **Model uncertainty.** Vary level density, γ strength and the optical
   potentials over the code's alternatives and quote the spread as a model
   uncertainty, not a statistical error. Near stability it may be tens of per
   cent; far from it, or near a threshold, a factor of 2 to 10.
5. Compare with EXFOR for the same reaction, or for neighbours when there is
   none (`nuclear-data-lookup`): the same quantity (ground state or isomer,
   independent or cumulative, enriched or natural target), in mb, at lab
   energies.

## Direct reactions (FRESCO, DWBA)

- Fix the entrance-channel optical potential on elastic scattering at the
  same energy before computing transfer or inelastic cross sections.
- The bound-state well's radius and diffuseness (1.25 and 0.65 fm are
  conventional) are choices: a spectroscopic factor, the ratio of measured to
  calculated cross section, moves by 20-30% with them. Quote them, and prefer
  relative spectroscopic factors.
- Show convergence in radial step, matching radius and number of partial
  waves.

## Limits of the statistical model

Hauser-Feshbach averages over many overlapping levels. It fails for light
nuclei, near closed shells and at low energy, where resonances are resolved:
use an R-matrix description (`scattering-theory-and-partial-waves`).

## Check before reporting

- Code, version and the whole input in the report; sample case reproduced.
- Every model choice named; the spread across alternatives quoted.
- Energy grid fine enough near thresholds; lab or centre-of-mass stated.
- The channels sum to the reaction (non-elastic) cross section.
- Compared with measurements; a disagreement is stated, not tuned away
  silently.

## Related

- Skills here: `nuclear-data-lookup`, `nuclear-reaction-kinematics`,
  `scattering-theory-and-partial-waves`, `nuclear-structure-models`,
  `nuclear-astrophysics`, `installing-software`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `matplotlib`, `uncertainty-and-units`, `get-available-resources`.
