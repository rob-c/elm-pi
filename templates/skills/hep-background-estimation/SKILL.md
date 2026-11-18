---
name: hep-background-estimation
description: "Estimating backgrounds in a collider analysis - simulation normalised in control regions, transfer factors, ABCD, fake-factor and matrix methods, sideband and template fits, closure and validation."
disable-model-invocation: true
---

# Background estimation

What goes wrong: ABCD used without testing that its two variables are
independent; signal leaking into a control region and being subtracted as
background; a transfer factor quoted without its extrapolation uncertainty;
and a method validated on the very events it was derived from.

## Choosing a method

- Shape well modelled, rate uncertain: simulation normalised in a control
  region.
- Instrumental or badly modelled (misidentified and non-prompt leptons,
  multijet, charge flips): from data - fake factors, the matrix method, ABCD.
- Smooth under a narrow peak: sideband or functional fit.
- Small and well known: simulation with its cross-section uncertainty.

## Control region and transfer factor

N(SR) = (data(CR) - other backgrounds(CR)) × TF, TF = MC(SR) / MC(CR).

- Evaluate every systematic variation on the ratio TF, not on its numerator
  and denominator separately: what cancels, cancels; what is left is the
  extrapolation uncertainty.
- The control region is close to the signal region in kinematics, pure, well
  populated and poor in signal. Its data statistics propagate to the estimate.
- A free normalisation shared by both regions in one fit does the same thing
  (`hep-likelihood-limits`).

## ABCD

Two variables, each with a pass and a fail side. A is pass-pass (signal
region), B and C fail one each, D fails both: N(A) = N(B) N(C) / N(D).

- It holds only if the two variables are independent for this background:
  test it, never assume it. If the data have a signal-free copy of the four
  regions (a validation set), run the method there first, other backgrounds
  subtracted, and compare predicted with observed.
- If observed/predicted there (or R = N(A) N(D) / (N(B) N(C)) in simulation)
  is not 1 within its error, multiply the estimate by it with its
  uncertainty, or take its departure from 1 as a systematic.
- Subtract other backgrounds from B, C and D first, with their uncertainties.
- Signal in B, C or D inflates the prediction. Quantify it for a benchmark
  signal, or fit the four regions together with a signal term.
- Statistical error for large counts: relative variance 1/N(B) + 1/N(C) +
  1/N(D). For small counts use the Poisson likelihood.

## Fake factor and matrix method

- Fake factor F = tight / (loose and not tight), measured in a region rich in
  misidentified objects, in bins of what it depends on (p_T, η, ...), with the
  prompt contribution subtracted using simulation. Apply it to events that
  pass the analysis selection with a loose-not-tight object, again minus the
  prompt simulation.
- With two such objects (T tight, L loose-not-tight):
  N(TT, fake) = F2 N(TL) + F1 N(LT) - F1 F2 N(LL). The last term stops events
  with two fakes being counted twice.
- Matrix method, with real efficiency r and fake efficiency f for
  loose-to-tight: fakes among tight = f (r N(all loose) - N(tight)) / (r - f),
  all loose including the tight. Unstable where r and f are close.
- Uncertainties: statistics of F; the prompt subtraction; and the make-up of
  the fakes (flavour, origin) differing between where F is measured and where
  it is applied - measure F in regions of different make-up, and close the
  method in simulation.
- Adding a data-driven fake estimate to simulation: remove simulated events
  with a fake object (truth matching), or they are counted twice.

## Sidebands and templates

- Sideband: fit the background shape outside the signal window, or signal
  plus background everywhere. The choice of function is a systematic: try
  alternatives, and fit signal plus background to a large background-only
  sample - the fitted signal there is the bias (spurious signal). See
  `data-fitting`.
- Template fit: the data in a discriminating variable as a sum of shapes from
  simulation or control data, with floating fractions and the templates' own
  statistical errors (`hep-systematics`).

## Check before reporting

- Per background: method, regions, and the predicted yield with statistical
  and systematic errors.
- Closure in simulation and agreement in a validation region, as numbers:
  predicted, observed, and how many sigma apart.
- Signal contamination of each control region for a benchmark signal.
- No event counted twice between data-driven and simulated estimates.

## Related

- Skills here: `hep-event-selection`, `hep-systematics`,
  `hep-likelihood-limits`, `hep-efficiency-measurement`, `data-fitting`,
  `histogram-analysis`, `uncertainty-propagation`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `statistical-analysis`, `uncertainty-and-units`, `matplotlib`.
