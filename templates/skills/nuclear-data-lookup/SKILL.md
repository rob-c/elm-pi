---
name: nuclear-data-lookup
description: "Getting a half-life, level, gamma line, mass, cross section or attenuation coefficient from an evaluated nuclear database, with its source - NNDC, IAEA LiveChart, AME, ENDF, EXFOR, NIST."
disable-model-invocation: true
---

# Nuclear data, looked up

A nuclide's half-life, line energies, emission probabilities, masses and cross
sections recalled from training are unverified and often from a superseded
evaluation; a recalled number with a library's name attached is a fabricated
citation. The other two mistakes: evaluated and single-measurement values
mixed without saying so, and the uncertainty notation misread.

## Which source for what

| Need | Source |
|---|---|
| half-lives, decay modes, levels, gamma energies and intensities | ENSDF, read through NNDC NuDat; XUNDL for recent unevaluated papers |
| the same at a glance, scriptable | IAEA LiveChart of Nuclides and its data API |
| atomic masses, mass excesses, Q-values | AME2020; NUBASE2020 for ground and isomeric states |
| evaluated cross sections | ENDF/B, JEFF, JENDL; TENDL (model-based, covers everything) |
| measured cross sections | EXFOR |
| reaction-model inputs | RIPL-3 |
| photon attenuation; stopping powers and ranges | NIST XCOM; PSTAR, ASTAR, ESTAR |

## In order of preference

1. **A value in the user's files** (their decay-data table, a paper they gave
   you): use it, cite the file.
2. **An installed package that bundles data**: radioactivedecay (ICRP-107 decay
   data), periodictable and mendeleev (isotope masses and abundances). Say
   which data set and package version the number came from.
3. **The source itself**, in a session with web access (pi started with
   `--remote`). The LiveChart API returns CSV from
   nds.iaea.org/relnsd/v1/data, for example
   `fields=ground_states&nuclides=60co` or
   `fields=decay_rads&nuclides=60co&rad_types=g`; its guide lists the fields.
   Quote the value with the library, its version or cut-off date, and the date
   you read it.
4. **Memory, as a last resort**: write "(from memory, unverified)" after the
   value, no library or year, and say how to check it. If the result depends on
   it at the precision quoted, stop and ask instead.

## Evaluated or measured

- Evaluated (ENSDF, AME, ENDF, JEFF): one recommended value from all the
  measurements up to a cut-off date. Cite the evaluation and its version.
- Measured (EXFOR, XUNDL): single experiments, which scatter. Cite the entry
  and the paper, and say it is one measurement.
- TENDL is a TALYS calculation adjusted to data: a model prediction.
- Take a decay scheme (half-life, energies, intensities) from one evaluation;
  mixing libraries breaks the normalisation.

## Reading the notation

- ENSDF writes the uncertainty in the last digits: "12.3 4" is 12.3 ± 0.4 and
  "0.0563 12" is 0.0563 ± 0.0012; "+5-3" is asymmetric.
- Isomers (Tc-99m, m1, m2) have their own half-life and decay data; check the
  entry is the state you mean. Jπ in parentheses is a tentative assignment.
- Gamma intensities are either relative (strongest line = 100) or per 100
  decays of the parent; the first needs the evaluation's normalisation factor.
  Photon intensity is not transition intensity: they differ by (1 + α), the
  internal conversion coefficient.
- Converting a half-life in years to seconds: use the year the source uses
  (tropical or Julian) when the precision needs it.
- ENDF reaction numbers: MT=1 total, 2 elastic, 18 fission, 102 radiative
  capture. EXFOR energies may be lab or centre-of-mass: read the heading.
- Elemental (natural) and isotopic cross sections are different entries.

## Check before reporting

- Every value: library, version or year, date read, the query used.
- Uncertainty as the source gives it; ground state or isomer; the right branch.
- Units (keV or MeV, b or mb, s or y).
- Two sources compared where the result rests on the value; a difference
  beyond the uncertainties is stated, not averaged away.
- Anything from memory is flagged as such.

## Related

- Skills here: `physical-constants`, `nuclear-masses-and-q-values`,
  `radioactive-decay-chains`, `gamma-spectroscopy`, `uncertainty-propagation`,
  `hep-literature-and-data`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `database-lookup`, `citation-management`, `uncertainty-and-units`.
