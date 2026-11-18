---
name: qft-renormalisation-group
description: "Running couplings and masses - beta-function conventions, flavour thresholds and matching, pole versus MS-bar masses, scale variation, RGEs for general models, and checks against looked-up values."
disable-model-invocation: true
---

# Running couplings and masses

The usual errors: two normalisations of the beta function mixed (a factor of 2
or 4π), a coupling run across a quark threshold without changing the number of
flavours, a pole mass used where a running mass is meant, and a
scale-variation band read as a 68% interval.

## State the convention

For QCD three forms are in use, and they describe the same running:

- a = αs/(4π): μ² da/dμ² = -β0 a² - β1 a³ - ..., with β0 = 11 - 2nf/3 and
  β1 = 102 - 38nf/3.
- αs itself: μ² dαs/dμ² = -b0 αs² - ..., with b0 = (33 - 2nf)/(12π).
- A derivative in ln μ instead of ln μ² doubles every coefficient.

One loop: αs(μ) = αs(μ0) / [1 + (β0/4π) αs(μ0) ln(μ²/μ0²)]
= 4π / [β0 ln(μ²/Λ²)]. Asymptotic freedom needs β0 > 0, so nf ≤ 16.

General gauge coupling: μ dg/dμ = b g³/(16π²), with
b = -(11/3) C2(G) + (2/3) Σ T(Weyl fermions) + (1/3) Σ T(complex scalars).
The Standard Model has b = (41/10, -19/6, -7) for U(1) in GUT normalisation,
SU(2) and SU(3). Group factors: `group-theory-for-physics`.

## Thresholds, masses and Λ

- nf is the number of quarks lighter than μ: 3 below m_c, 4 to m_b, 5 to
  m_t, 6 above it, so 1 TeV is across the top threshold. Switch nf there and
  match the couplings: continuous with one-loop matching at μ equal to the
  quark mass, a small step from two-loop matching on. n-loop running goes
  with (n-1)-loop matching.
- Λ depends on nf, on the loop order and on the scheme. Quote αs(mZ) instead,
  or Λ with all three labels.
- The pole mass and the MS-bar mass differ at order αs:
  m_pole = m(m) [1 + 4αs(m)/(3π) + ...], roughly 10 GeV for the top quark.
  One-loop running, from μ dm/dμ = -(2αs/π) m:
  m(μ) = m(μ0) [αs(μ)/αs(μ0)]^{4/β0}, 4/β0 = 12/(33-2nf), interval by
  interval with each nf. The mass falls as μ rises: m_b(mZ) is near 3 GeV.
- Light-quark masses are quoted in MS-bar at 2 GeV, charm and bottom usually
  as m(m). Say which mass every number is.

## Scale variation

- Put the central μR (and μF) at the hard scale and vary by factors of 2.
  Seven-point: every (μR, μF) pair from {1/2, 1, 2} times the central value
  except the two where they move in opposite directions.
- Beyond leading order the coefficients contain ln μR terms that change with
  the scale; changing only the coupling overstates the band.
- The envelope is a convention for missing higher orders, not a confidence
  interval. Call it "scale variation" and give the central scale.

## Beyond QCD

- Coupled gauge, Yukawa and quartic RGEs: generate them (PyR@TE, SARAH) rather
  than by hand, integrate in t = ln μ with `scipy.integrate.solve_ivp`
  (`numerical-methods`), and state the loop order of each.
- One-loop QED: μ² dα/dμ² = (α²/3π) Σ N_c Q², summed over active charged
  Dirac fermions.
- A Landau pole at one loop marks where perturbation theory has already
  failed. QCD running is not to be trusted below about 1 GeV.
- Fixed points: β(g*) = 0, stable or not by the sign of dβ/dg there.
- Anomalous dimensions, μ dO/dμ = -γ O up to a sign convention: operators
  mix, so γ is a matrix (`effective-field-theory`).

## Tools

RunDec and CRunDec (αs and quark masses to five loops, with decoupling),
REvolver, PyR@TE and SARAH for general models. With parton distributions the
coupling must be the set's own (`qcd-parton-distributions`).

## Check before reporting

- The β convention, the loop order of the running and of the matching, nf in
  each interval, the threshold values and whether they are pole or MS-bar.
- The one-loop formula against the numerical integration.
- αs run from mZ to a second scale (the τ or b mass) against a looked-up
  value: `physical-constants`, not memory.
- Running back up returns the starting value.
- Scheme and scale given for every mass and coupling quoted.

## Related

- Skills here: `physical-constants`, `numerical-methods`, `derivation-checks`,
  `qft-loop-integrals`, `qcd-parton-distributions`, `effective-field-theory`,
  `group-theory-for-physics`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `matplotlib`.
