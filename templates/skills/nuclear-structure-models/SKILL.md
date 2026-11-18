---
name: nuclear-structure-models
description: "Nuclear structure calculations - shell model (model space, interaction, truncation; KSHELL, NuShellX, BIGSTICK), B(E2) and Weisskopf units, collective signatures, mean field and DFT, ab initio convergence."
disable-model-invocation: true
---

# Nuclear structure models

The mistakes: a shell-model result quoted without its interaction, model
space and truncation, so nobody can reproduce it; a B(E2) in the wrong units
or direction, with effective charges unstated; calculated levels matched to
experiment by energy alone rather than by Jπ and order; and ab initio or
mean-field numbers quoted before they have converged.

## Shell model (configuration interaction)

- Closed shells at 2, 8, 20, 28, 50, 82, 126. A calculation is three choices:
  an inert core and valence **space**, an effective **interaction** fitted for
  that space, and a **truncation**. Common pairs: p shell with Cohen-Kurath;
  sd shell (above O-16) with USDB; pf shell (above Ca-40) with KB3G or
  GXPF1A; f5pg9 (above Ni-56) with JUN45. An interaction is not valid outside
  its space; islands of inversion need cross-shell interactions.
- Orbit labels count the radial quantum number from 0 or from 1 (0d5/2 or
  1d5/2): say which convention the code and the paper use.
- Codes: KSHELL, BIGSTICK (m-scheme, Lanczos), NuShellX, ANTOINE. Use what
  is installed (`installing-software`). Estimate the m-scheme dimension
  before a run: it grows combinatorially towards mid-shell. With a
  truncation (particle-hole rank), show the result against the truncation.
- Spaces spanning several oscillator shells have spurious centre-of-mass
  states: push them up (Lawson term) and say so.

## Observables

- Electromagnetic rates need **effective charges** (1.5 e and 0.5 e for
  protons and neutrons is a common sd-shell choice, not a constant) and
  effective g-factors; Gamow-Teller strengths need a quenching factor. State
  the values and the oscillator length or ħω used.
- B(E2) has a direction: B(E2; Jᵢ → J_f) × (2Jᵢ + 1) is the same both ways,
  so B(E2; 0+ → 2+) is five times B(E2; 2+ → 0+). Units e² fm⁴;
  1 e² b² = 10⁴ e² fm⁴.
- Weisskopf units: for E2, 0.0594 A^(4/3) e² fm⁴; for E1,
  0.0645 A^(2/3) e² fm²; for M1, 1.79 nuclear magnetons squared. Tens of
  W.u. for an E2 means collective; near 1, single-particle.
- Spectroscopic factors and occupations depend on the space: compare
  relative values.

## Collective signatures

- R(4/2) = E(4+)/E(2+): about 2.0 for a harmonic vibrator, 2.5 for a γ-soft
  nucleus, 3.33 for a rigid rotor, where E(J) = ħ² J(J+1) / (2ℐ); below 2
  near closed shells.
- Deformation from the transition rate: β₂ = (4π / (3 Z R0²)) √(B(E2; 0+ → 2+)/e²)
  with R0 = 1.2 A^(1/3) fm.

## Mean field and density functionals

Skyrme (SLy4, UNEDF1), Gogny (D1S) or relativistic functionals, with HFB for
pairing; HFBTHO (axial) and HFODD. Converge in the basis (number of
oscillator shells, box size); odd nuclei need blocking. The functional is a
model choice: name it, and compare two or three to show the spread. A
calculated mass is a prediction with an error of an MeV or so, not data.

## Ab initio

No-core shell model, coupled cluster, IMSRG and quantum Monte Carlo results
depend on the interaction (name it, with its cutoff and three-nucleon force)
and must be converged in model-space size (Nmax or emax) and oscillator
frequency. Show both dependences, give the extrapolation formula, and quote
the extrapolation uncertainty.

## Check before reporting

- Interaction, model space, truncation, code and version named.
- Levels compared with ENSDF (`nuclear-data-lookup`) state by state: Jπ,
  order, then energy. A good empirical interaction is right to a few hundred
  keV; a larger miss, or a wrong order, is said.
- Transitions: direction, units, effective charges.
- Convergence shown (truncation, basis size, ħω).
- A trivial case reproduces its input: one valence nucleon returns the
  single-particle energies.

## Related

- Skills here: `nuclear-data-lookup`, `nuclear-reaction-codes`,
  `group-theory-for-physics`, `numerical-methods`, `installing-software`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `matplotlib`, `get-available-resources`.
