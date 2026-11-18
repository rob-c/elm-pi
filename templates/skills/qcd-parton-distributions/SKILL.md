---
name: qcd-parton-distributions
description: "Parton distributions in a hadron-collider prediction - LHAPDF, matching the set's order and alpha_s to the calculation, Hessian and replica uncertainties, scales, flavour schemes, luminosities, sum-rule checks."
disable-model-invocation: true
---

# Parton distributions

Common mistakes: forgetting that LHAPDF returns x f(x), not f(x); a coupling
that is not the set's own; a PDF of one order with a matrix element of
another; an uncertainty formula that belongs to a different kind of set; and
evaluating a grid outside its range in x or Q.

## The formula

σ = Σ over partons a, b of ∫ dx1 dx2 f_a(x1, μF) f_b(x2, μF) σ̂_ab(x1 x2 s; μR, μF),
up to power corrections in Λ²/Q². The partonic cross section, the PDFs and αs
must share one order, one scheme and one value of αs(mZ).

## LHAPDF 6

1. `lhapdf.mkPDF("SetName", 0)` is the central member; `lhapdf.getPDFSet(name)`
   gives the set and `.mkPDFs()` all its members. Sets are data files: see
   where LHAPDF looks with `lhapdf-config --datadir`; a missing one has to be
   fetched in a session that has web access.
2. `pdf.xfxQ(pid, x, Q)` and `pdf.xfxQ2(pid, x, Q2)` return x f(x). Divide by
   x. Parton codes are PDG ids: 21 for the gluon, 1 to 5 for d, u, s, c, b,
   negative for antiquarks.
3. Take the coupling from the same member: `pdf.alphasQ(Q)`.
4. Stay inside the grid (`pdf.xMin`, `pdf.xMax`, `pdf.q2Min`, `pdf.q2Max`):
   outside it the values are extrapolated or frozen. Near x = 1 and at low Q
   the uncertainties are large, and beyond leading order a PDF may be
   negative there without being a bug.

## Uncertainties: by the kind of set

Compute the observable X once per member, with that member's PDFs and αs
throughout; then combine. Never propagate PDF errors point by point in x:
the members carry the correlations.

- Hessian, eigenvector pairs (X⁺, X⁻): symmetric
  δX = ½ √(Σ (X⁺ - X⁻)²); asymmetric
  δX⁺ = √(Σ max(X⁺ - X0, X⁻ - X0, 0)²), δX⁻ the same with X0 - X. One term
  per pair, the larger shift of its two members: in NumPy
  `np.maximum.reduce([Xp - X0, Xm - X0, 0 * Xp])`;
  `np.maximum([Xp - X0, Xm - X0], 0)` keeps both members of a pair that
  moves one way.
- Symmetric Hessian (one member per eigenvector): δX = √(Σ (X_k - X0)²).
- Monte Carlo replicas: mean and standard deviation over the replicas
  (member 0 is their average), or the central 68% interval.
- Confidence level: CT eigenvector sets are 90%; divide by 1.645 for 68%.
  Read the set's `.info` file rather than assume.
- αs: repeat with the sets fitted at αs(mZ) shifted up and down, and add that
  in quadrature to the PDF part.
- `set.uncertainty(values)` applies the set's own prescription: use it, and
  check it once against the formula.

## Choices to state

- Scales: μF and μR at the hard scale, varied as in
  `qft-renormalisation-group`. The PDF's μF and the logarithms in σ̂ move
  together.
- Flavour scheme: four-flavour (massive b in the matrix element, an nf = 4
  set and coupling) or five-flavour (b in the proton, massless). Mixing a
  five-flavour set with a four-flavour matrix element is wrong.
- Parton luminosity: dL/dτ = ∫ dx/x f_a(x) f_b(τ/x) from τ to 1, with
  τ = ŝ/s; say whether a ↔ b is included.
- Showered samples: the generator's tune is tied to its PDF
  (`hep-event-generators`); reweight with stored weights, do not swap sets.

## Tools

LHAPDF for values; APFEL, HOPPET or EKO for DGLAP evolution; PineAPPL,
APPLgrid or fastNLO grids to redo a convolution for many sets quickly.

## Check before reporting

- Momentum sum: Σ over partons of ∫ x f(x) dx = 1. Valence counts:
  ∫ (u - ū) dx = 2, ∫ (d - d̄) dx = 1, ∫ (s - s̄) dx = 0. Integrate in ln x.
- Set name with version, member convention, order, αs(mZ), confidence level.
- The coupling in the hard cross section is the set's.
- A benchmark reproduced (a published cross section or luminosity) before
  the new number.
- PDF, αs and scale uncertainties quoted separately.

## Related

- Skills here: `qft-renormalisation-group`, `qft-phase-space`,
  `uncertainty-propagation`, `numerical-methods`, `hep-event-generators`,
  `hep-cross-section-measurement`, `hep-literature-and-data`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `matplotlib`, `scientific-visualization`.
