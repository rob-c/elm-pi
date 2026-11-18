---
name: effective-field-theory
description: "Effective field theories and SMEFT - power counting, operator bases and redundancies, matching and running of Wilson coefficients, input schemes, linear versus quadratic terms, validity, and the tools."
disable-model-invocation: true
---

# Effective field theory

Results fail to compare because two papers or tools use different operator
bases or normalisations for the "same" Wilson coefficient; because the
expansion is used where E is not well below Λ; because terms of one order in
1/Λ are kept selectively; or because running between the matching scale and
the measurement is left out.

## Power counting

L = L4 + Σ C_i O_i / Λ^{d-4}. Field dimensions in four dimensions: scalar and
vector 1, fermion 3/2, derivative 1, field strength 2. An operator of
dimension d corrects an observable by powers of (E/Λ)^{d-4} or (v/Λ)^{d-4}.
State the order kept and keep all of it.

## Bases and redundancy

- Operators related by integration by parts, by field redefinitions
  (equations of motion), by Fierz or by Bianchi identities are not
  independent. A basis is a choice of which to remove.
- SMEFT at dimension 6: the Warsaw basis has 59 baryon-number-conserving
  operators for one generation, 2499 real parameters for three. At dimension
  5 there is only the Weinberg operator.
- A coefficient means nothing without its basis, its normalisation (is Λ
  set to 1 TeV? are couplings or loop factors pulled out?), the sign
  convention of the covariant derivative, and the scale μ. Observables are
  basis independent; single coefficients are not.
- Flavour assumptions decide how many of the 2499 are in play.

## Matching and running

1. Match at μ near the heavy mass M, so that no large logarithm appears:
   equate full-theory and EFT amplitudes order by order in 1/M. At tree level
   expand the heavy propagator, 1/(p² - M²) = -1/M² (1 + p²/M² + ...).
   **A heavy vector with L = M²V²/2 + V·J leaves -J·J/(2M²): the sign is
   minus.** For J = Σ gᵢ Jᵢ the mixed operator Jᵢ·Jⱼ has -gᵢ gⱼ/M², and one
   with two identical currents -gᵢ²/(2M²) - half, as its vertex attaches 2!
   ways. Same-sign couplings give negative C.
2. Worked check: W exchange gives the Fermi theory with
   GF/√2 = g²/(8 mW²), and v = (√2 GF)^{-1/2} is about 246 GeV.
3. Run to the scale of the measurement: dC_i/d ln μ = γ_ij C_j / (16π²).
   Whether γ or its transpose appears, and where the 16π² sits, differ
   between papers. Mixing switches on operators that were zero at Λ.
4. Below the electroweak scale match again (no W, Z, Higgs, top).

Tools: Matchete and matchmakereft for matching; DsixTools and the `wilson`
package for running and for SMEFT to low-energy matching. Move numbers
between codes in the WCxf format, which names the theory, the basis and each
coefficient, rather than by hand.

## Predictions and fits

- Input scheme: {α, mZ, GF} or {mW, mZ, GF}. Operators shift the relation
  between inputs and Lagrangian parameters; predictions from different
  schemes do not combine.
- σ = σ(SM) + Σ C_i σ_i / Λ² + Σ C_i C_j σ_ij / Λ⁴. The quadratic
  dimension-6 term is of the order of the missing dimension-8 interference.
  Give results with and without it; a large difference means the fit sits
  where the expansion is in doubt.
- Sign of the linear term: write both amplitudes with one rule, never from
  factors of i. A vector coupled as c V·J gives c c′/(q² - m²): the photon
  e²QQ′/s, the contact term C/Λ² = -g g′/M². So x = C s/(e²QQ′Λ²),
  σ/σ(SM) = (1 + x)², and the linear term 2x is negative (destructive) for
  same-sign couplings below the pole.
- Validity: the energies probed (the tails that drive the limit) must be
  below Λ for couplings that stay perturbative. Say what Λ the limit implies,
  or cut the data at an energy and say so.
- Prediction tools: SMEFTsim (leading order, several flavour and input
  schemes), SMEFT@NLO, flavio and smelli for flavour and electroweak
  observables. Model files have their own conventions: `bsm-model-tools`.
- Other EFTs (HQET, SCET, chiral, NRQCD): name the expansion parameter.

## Check before reporting

- Basis, normalisation, covariant-derivative sign, scale μ, flavour
  assumption and input scheme stated for every coefficient.
- Linear and quadratic results both given; EFT validity discussed.
- Running and mixing included, or shown to be negligible.
- A known result reproduced by the same chain: the Fermi relation above, or
  a published limit.
- Coefficients carried between tools as WCxf, not retyped.

## Related

- Skills here: `qft-renormalisation-group`, `qft-amplitudes`,
  `bsm-model-tools`, `hep-reinterpretation`, `hep-likelihood-limits`,
  `hep-flavour-and-cp`, `derivation-checks`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `pymc`, `matplotlib`.
