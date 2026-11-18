---
name: hep-efficiency-measurement
description: "Measuring efficiencies - binomial intervals (Clopper-Pearson), weighted events, tag-and-probe, trigger turn-on curves, data-to-simulation scale factors, efficiency maps, TEfficiency."
disable-model-invocation: true
---

# Efficiency measurements

What goes wrong: √(ε(1-ε)/n) quoted near 0 or 1, where it gives ±0; pass and
total histograms divided as if they were independent; a map binned so coarsely
that its average is wrong for any other spectrum; and tag-and-probe with
background under the peak or a tag that biases the probe.

## k passes out of n

- The estimate is k/n. The normal-approximation error √(ε(1-ε)/n) is zero at
  k = 0 and k = n and too small near them: use it only when both nε and
  n(1-ε) are well above 5.
- Default: Clopper-Pearson (exact, never under-covers). Central interval at
  68.3%, α = 0.317: lower = Beta⁻¹(α/2; k, n-k+1), upper =
  Beta⁻¹(1-α/2; k+1, n-k), with lower = 0 at k = 0 and upper = 1 at k = n.
  100 of 100 is ε = 1 with a lower bound (α/2)^(1/n) = 0.982, not 1 ± 0.
- In code: `scipy.stats.beta.ppf`;
  `scipy.stats.binomtest(k, n).proportion_ci(0.683, method="exact")`;
  ROOT `TEfficiency` (Clopper-Pearson by default);
  `hist.intervals.clopper_pearson_interval(k, n)`.
- Wilson, or Bayesian with a uniform or Jeffreys prior, are alternatives:
  name the method and the level.
- The numerator must be a subset of the denominator, event by event.
- Histograms: `TEfficiency(passed, total)`, or
  `h->Divide(passed, total, 1, 1, "B")`. Never a plain `Divide`.
- Weighted events are not binomial. Variance of ε = Σw(pass)/Σw(total):
  [(1 - 2ε) Σw²(pass) + ε² Σw²(total)] / (Σw(total))². Negative weights can
  push a bin outside 0 to 1: merge bins.

## Tag-and-probe, in data

1. A resonance (Z, J/ψ, Υ to two leptons). The tag passes a tight selection
   and the trigger, so the event is recorded whatever the probe does; the
   probe is the other leg, loosely selected, with the pair mass in the window.
2. ε = passing probes / all probes. If both legs qualify as tags, each is
   probed in turn.
3. Subtract background under the peak: fit the pair mass of passing and
   failing probes together (signal shape plus background) and take ε from the
   yields, with the fit's uncertainty - `hep-roofit-models`.
4. Bin in what ε depends on (p_T, η, pile-up, ...).
5. Factorise in a fixed order - reconstruction, identification given
   reconstruction, isolation given identification, trigger given all of them:
   each step's denominator is the previous numerator.
6. Systematics: tag definition, mass window, signal and background shapes.
   In simulation, tag-and-probe must reproduce the efficiency from truth.

## Trigger turn-on

Measure against an unbiased reference: an orthogonal trigger, a lower-
threshold prescaled one, or tag-and-probe. Bin finely through the rise and
fit ε(x) = (p/2)(1 + erf((x - μ)/(√2 σ))) - plateau p, midpoint μ, width σ -
with a binomial likelihood, not a chi-square on symmetric errors. Cut offline
where ε is at least 99% of the plateau and say so, or weight by the curve.

## Scale factors

- SF = ε(data) / ε(simulation) per bin, both measured the same way, applied
  as a weight per object in simulation. An object required to fail (a veto)
  takes (1 - SF ε(sim)) / (1 - ε(sim)).
- Statistical parts are independent between bins, systematic parts usually
  correlated: propagate both as variations (`hep-systematics`).
- Outside the measured range use the edge bin with a larger uncertainty, and
  say so.
- A map's average over a bin depends on the spectrum inside it. Bin finely
  where ε changes fast, and in every variable that matters, before applying
  the map to a sample with other kinematics.

## Check before reporting

- k and n given with ε; numerator inside denominator.
- Interval method and level named; no ±0 at 0 or 1.
- Binning, variables and events per bin.
- Tag-and-probe: fits shown for a few bins; closure in simulation.
- Scale factors far from 1 explained.
- Efficiency kept apart from acceptance (`hep-cross-section-measurement`).

## Related

- Skills here: `statistics-and-significance`, `histogram-analysis`,
  `data-fitting`, `hep-root`, `hep-roofit-models`, `hep-systematics`,
  `hep-event-selection`, `hep-particle-identification`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `statsmodels`, `statistical-analysis`, `matplotlib`.
