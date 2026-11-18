---
name: qft-computer-algebra
description: "Feynman-diagram calculations by program - FORM, FeynCalc, FeynArts and FormCalc, FeynRules, QGRAF, LoopTools, SymPy: which tool, the conventions each uses, and reporting only what a run produced."
disable-model-invocation: true
---

# Computer algebra for Feynman diagrams

Three failures recur. An expression is reported that no program produced:
FORM and FeynCalc syntax is easy to get almost right. Two tools with different
conventions are combined and an interference term changes sign. And
four-dimensional identities are applied to D-dimensional objects.

## Rules of use

1. Find out what is installed before choosing:
   `command -v form tform wolframscript`. FORM and QGRAF are free; FeynCalc,
   FeynArts, FormCalc, FeynRules and Package-X need a Mathematica kernel.
   Without one, say so - never write out what FeynCalc "would" return.
   Anything missing: `installing-software`.
2. Report only output that a run printed. Keep each script and its log beside
   the result, and give the tool's version.
3. Reproduce a textbook result with the same setup before the new calculation:
   e⁺e⁻ → μ⁺μ⁻ (spin-averaged 2e⁴(t² + u²)/s² for massless fermions), then a
   known process with the features of the real one (a γ5, a loop, colour).

## The chain, and a tool for each link

| Step | Tools | Check |
|---|---|---|
| diagrams | QGRAF, FeynArts | their number, against the literature |
| Feynman rules | FeynRules (to UFO or FeynArts model files), built-in models | a model file is input: read its conventions |
| Dirac and colour algebra | FORM (large expressions), FeynCalc (interactive) | one trace by hand |
| loop reduction | FeynCalc, FormCalc, then `qft-loop-integrals` | the UV poles |
| numbers | LoopTools, FormCalc's generated code | one point against a generator |

SymPy does small four-dimensional traces and contractions
(`sympy.physics.hep.gamma_matrices`), the algebra around a calculation and the
numerical spot checks. It does not replace FORM or FeynCalc for loop
reductions, D-dimensional algebra or expressions with thousands of terms.

## Conventions that differ between tools

- **Metric**: these tools work in (+,-,-,-). A hand calculation in (-,+,+,+)
  has to be translated before comparing.
- **Levi-Civita tensor and γ5 traces**: the sign, and even the factor of i, of
  Tr[γ^μγ^νγ^ργ^σγ5] is a setting, not a fact. FeynCalc exposes it as
  `$LeviCivitaSign`; FORM's trace returns its ε tensor without the i that most
  books carry. Compute this one trace in each tool used and compare with the
  hand value (`qft-amplitudes`) before combining their outputs.
- **γ5 in D dimensions**: an anticommuting γ5 is inconsistent for traces with
  an odd number of γ5; the 't Hooft-Veltman (Breitenlohner-Maison) scheme is
  consistent but breaks chiral symmetry and needs extra counterterms. Say
  which scheme the tool was set to.
- **4 versus D**: FeynCalc keeps four-dimensional objects (`GA`, `SP`, `FV`)
  apart from D-dimensional ones (`GAD`, `SPD`, `FVD`); mixing them in a loop
  gives a wrong finite part. In FORM the dimension is declared with the
  indices, and `tracen` replaces `trace4`.
- **Couplings**: the signs in the covariant derivative come from the model
  file, not from the textbook open beside it.
- **Loop integrals**: A0, B0 and the rest are normalised differently by
  FeynCalc, LoopTools and Package-X (`qft-loop-integrals`).

## FORM in practice

- A program is declarations, expressions (`Local F = ...;`), statements and
  module ends (`.sort`, `.end`). Gamma matrices `g_(1,mu)` and `g5_(1)` belong
  to spin line 1; `d_(mu,nu)` is the metric, `e_(mu,nu,ro,si)` the ε tensor,
  `i_` the imaginary unit.
- Run `form file.frm` (`tform` for threads). A syntax error stops the run:
  fix it and run again. Do not guess what the output would have been.
- Substitutions with `id` match patterns literally; a replacement that did not
  match leaves the expression unchanged without an error. Look at the output.

## Check before reporting

- What ran: tool, version, script, log - and that the result is pasted from it.
- The textbook process reproduced by the same setup.
- Conventions: metric, ε sign, γ5 scheme, D or 4, integral normalisation.
- Diagram count; UV poles cancel after renormalisation; independence of the
  gauge parameter where a general gauge was available.
- One number against an independent code: a second algebra tool, or a
  generator's matrix element at a phase-space point (`hep-event-generators`).

## Related

- Skills here: `qft-amplitudes`, `qft-loop-integrals`, `derivation-checks`,
  `bsm-model-tools`, `installing-software`, `hep-event-generators`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `get-available-resources`.
