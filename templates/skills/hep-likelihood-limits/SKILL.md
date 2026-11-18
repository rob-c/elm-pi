---
name: hep-likelihood-limits
description: "Binned likelihood models for searches and measurements (HistFactory, pyhf, Combine) - nuisance parameters, profile-likelihood tests, CLs limits, expected bands, Asimov data, pulls and impacts."
disable-model-invocation: true
---

# Likelihood models, limits and significances

What goes wrong: an observed limit quoted with no expected band beside it;
asymptotic formulae used with a handful of events; nuisance parameters pulled
or constrained by the fit without anyone looking; and a workspace that does
not reproduce the yields it was built from.

## The model

L(μ, θ) = Π over bins Pois(n | μ s(θ) + b(θ)) × Π constraint(θ). μ is the
signal strength (parameter of interest); each nuisance parameter θ has a
constraint term standing for an auxiliary measurement.

In HistFactory terms a channel (region) holds samples, and samples carry
modifiers: a free normalisation (μ, or a background fixed by a control
region); a constrained normalisation (log-normal); a shape from ±1σ templates;
per-bin terms for limited simulation statistics; luminosity. A nuisance
parameter with one name is one parameter everywhere it appears: the name is
the correlation model.

Tools: `pyhf` (Python, JSON workspaces, reads likelihoods published on
HEPData), with `cabinetry` to build workspaces from histograms; ROOT
HistFactory and RooStats; CMS Combine with datacards. None installed:
the formulae below, by hand.

## Test statistics (Cowan, Cranmer, Gross, Vitells, 2011)

- Profile likelihood ratio: λ(μ) = L(μ, θ fitted at that μ) / L(μ̂, θ̂).
- Discovery: q0 = -2 ln λ(0) if μ̂ ≥ 0, else 0. Asymptotically Z = √q0.
- Upper limits: q̃μ = -2 ln λ̃(μ) if μ̂ ≤ μ, else 0, with μ̂ kept non-negative.
- CLs = CLs+b / CLb, both the same tail: CLs+b = P(q ≥ q_obs | μ) and
  CLb = P(q ≥ q_obs | 0) - never 1 minus that tail. μ is excluded at 95% CL
  when CLs < 0.05; the limit is where a scan in μ crosses it.
- By hand, asymptotically: q_A is q̃μ on background-only Asimov data (data
  set equal to the expectation). CLs+b = 1 - Φ(√q), CLb = 1 - Φ(√q - √q_A).
  Expected at Nσ: CLs = [1 - Φ(√q_A - N)] / Φ(N), N = 0 the median; -1σ is
  the lower limit, so minus < median < plus. Not counts of b ± σ_b. Or toys.
- The asymptotic formulae need enough events. With a few expected events or
  fewer in the sensitive bins, or a parameter at a boundary, throw toys
  (pyhf `calctype="toybased"`, RooStats FrequentistCalculator, Combine
  HybridNew) and say how many.

## Procedure

1. Build the workspace and check it: pre-fit yields per sample and region
   equal the input histograms. `pyhf.Workspace(spec)` validates the schema.
2. Fit background only (control regions, or Asimov) first. Look at the pulls
   (θ̂ - θ0)/Δθ, the post-fit constraints (well below 1 means the data
   constrain that parameter - believable?), the correlations, and the ranking
   of impacts on μ̂.
3. Post-fit data against model in every region, with a goodness of fit.
4. While blinded: expected limit or significance only.
5. Then observed: limit, best-fit μ̂ with its interval (-2Δ ln L = 1),
   observed and expected significance. An observed limit far outside the band
   sends you back to the pulls.
6. In pyhf:
   `pyhf.infer.hypotest(1.0, data, model, test_stat="qtilde", return_expected_set=True)`
   gives observed CLs and the five expected values at μ = 1.

## Pitfalls

- A limit stronger than the expected band is a fluctuation, not a result;
  CLs guards against excluding what the search cannot see, CLs+b does not.
- A bin with no background prediction gives unbounded significance.
- A theory uncertainty on the signal cross-section belongs in a limit on μ,
  and beside the theory curve (not in the fit) for a limit on the cross-section.
  Say which was done and which cross-section defines μ = 1.
- A scan over mass has a look-elsewhere effect: local and global significance
  are different numbers - `statistics-and-significance`.

## Check before reporting

- The workspace reproduces its inputs; the fit converged
  (`hep-roofit-models` for status and covariance quality).
- Pulls and constraints shown; any pull beyond 1σ or strong constraint explained.
- Observed with expected median and bands; the confidence level; CLs; the
  test statistic; asymptotic or toys.
- Asymptotics confirmed with toys at one point when counts are low.
- A published likelihood reproduces its published numbers first
  (`hep-reinterpretation`).

## Related

- Skills here: `statistics-and-significance`, `data-fitting`, `hep-systematics`,
  `hep-roofit-models`, `hep-background-estimation`, `hep-reinterpretation`,
  `rare-event-searches`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `statistical-analysis`, `pymc`, `matplotlib`.
