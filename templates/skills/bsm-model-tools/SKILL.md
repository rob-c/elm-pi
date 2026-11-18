---
name: bsm-model-tools
description: "New-physics models through the tool chain - FeynRules or SARAH to UFO, spectrum generators and SLHA files, MadGraph, micrOMEGAs, HiggsTools, SModelS; model consistency checks and honest parameter scans."
disable-model-invocation: true
---

# Models beyond the Standard Model, through the tool chain

A model file that loads is not a model that is right. The usual faults: a
Lagrangian that is not hermitian or not gauge invariant, mixing matrices in
one convention and couplings in another, widths left over from a different
parameter point, and scan points kept although the spectrum generator had
failed on them.

## The chain

1. **Lagrangian to model files.** FeynRules or SARAH (both need a Mathematica
   kernel). Run their own checks before exporting: FeynRules tests
   hermiticity, diagonal quadratic terms, kinetic normalisation and the mass
   spectrum; SARAH checks anomalies and charge conservation.
2. **Export.** UFO (a Python module: particles, parameters, couplings,
   vertices) for MadGraph5_aMC@NLO, Sherpa and Herwig; CalcHEP files for
   micrOMEGAs; SARAH also writes SPheno source for the spectrum. Loop-level
   work needs a UFO with counterterms.
3. **Spectrum.** SPheno, SoftSUSY or FlexibleSUSY turn Lagrangian inputs into
   masses, mixings and decays, written as an SLHA file (blocks of numbered
   entries: MASS, the mixing blocks, DECAY tables).
4. **Observables.** The SLHA file feeds MadGraph (as its parameter card),
   micrOMEGAs or MadDM (relic density, direct and indirect detection),
   HiggsTools (HiggsBounds and HiggsSignals), SModelS and recasting tools
   (`hep-reinterpretation`), flavio for flavour.

Report tool output only from runs that happened, with versions.

## Is the model consistent?

- Every term hermitian (or its conjugate added), Lorentz invariant, and a
  singlet: charges sum to zero, SU(2) and colour indices contracted.
- Anomalies cancel when chiral fermions or a new U(1) are added
  (`group-theory-for-physics`). Sum over left-handed Weyl fields: a
  right-handed field enters as its conjugate with every charge reversed (-Y
  and -X, so Y X² changes sign too), times colour × isospin × generations.
  A vector-like pair then cancels in every trace: if yours does not, a sign
  is wrong.
- Minimisation (tadpole) conditions solved, the point is a minimum (all
  physical scalar masses squared positive) and the potential is bounded from
  below. Count: one massless Goldstone mode per broken generator.
- Mass matrices diagonalised with the convention written down: which index is
  the mass eigenstate, and whether a real mixing matrix with signed masses or
  a complex one with positive masses is used (SLHA neutralinos: the former).
- Couplings perturbative, and tree-level 2 → 2 partial waves within
  unitarity, |Re a0| ≤ 1/2.
- Decoupling: with the new states heavy or their couplings zero, the model
  reproduces Standard Model cross sections and Higgs couplings. Compare
  against the generator's built-in Standard Model at one point.

## Parameter cards and scans

- SLHA parameters are running parameters at the scale in the block header;
  the masses are pole masses. Do not mix a card's masses with couplings
  computed from other inputs.
- Widths belong to the parameter point: recompute them (the generator's
  automatic width, or the spectrum generator's DECAY tables) at every point.
- Sign conventions (μ, trilinear terms, mixing angles) are fixed by the SLHA
  papers; a code that departs from them needs translating, not guessing.
- A scan records ranges, priors, sampler and seed. A point where the spectrum
  generator reports an error, a tachyon or no convergence (SLHA block SPINFO,
  entries 3 and 4) is not a physical point: drop it and count the drops.
- Say whether a plotted region is profiled or marginalised, and how many
  points support it.

## Check before reporting

- The tools' own model checks passed; anomaly and minimum checks done.
- Standard Model limit reproduced numerically.
- One benchmark point from the literature reproduced (spectrum, a cross
  section, the relic density) before the new points.
- Conventions for mixings and signs stated; widths recomputed.
- Failed and excluded points counted, not hidden.
- Versions of every tool, and the model files kept with the results.

## Related

- Skills here: `qft-computer-algebra`, `group-theory-for-physics`,
  `effective-field-theory`, `particle-cosmology`, `hep-event-generators`,
  `hep-reinterpretation`, `hep-literature-and-data`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `pymoo`, `matplotlib`.
