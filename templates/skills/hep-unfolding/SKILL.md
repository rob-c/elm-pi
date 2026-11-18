---
name: hep-unfolding
description: "Unfolding detector-level distributions to particle level - response matrix, fakes and misses, purity and stability, regularised methods and their strength, closure and stress tests, covariance."
disable-model-invocation: true
---

# Unfolding

What goes wrong: bin-by-bin correction factors presented as unfolding; an
unregularised inversion whose oscillations are read as physics, or shown with
error bars and no covariance; and a regularisation strength chosen by eye on
the data, with no test of the bias it brings.

## First: is unfolding needed?

To test one model, fold the prediction through the response and compare at
detector level: always valid. Unfold to publish a spectrum others can reuse.
Then define the particle level exactly - fiducial cuts on stable particles,
lepton dressing, jets - close to the detector-level selection.

## Ingredients, from simulation

**Three steps, none skipped: data × (1 - f); unfold; divide by the
efficiency.** A matrix whose columns are normalised to sum to 1 has no
efficiency in it: divide each true bin by ε afterwards, or normalise the
columns by the generated count instead. The unfolded total is larger than
the data's, never equal to it.

- Response matrix R(i,j): probability that an event generated in true bin j
  is reconstructed in bin i, from events passing both selections.
- Efficiency ε per true bin: reconstructed and selected over generated (the
  rest are misses). Fake fraction f per reconstructed bin: the simulated
  share with no particle-level counterpart in the fiducial region. Never
  subtract simulated fake counts, raw or scaled by total data/MC.
- Purity (of events reconstructed in a bin, the fraction generated there) and
  stability (the converse). Bins no narrower than the resolution; both
  above about one half is a common target.

## Why the simple ways fail

- Bin-by-bin factors (true over reconstructed, from simulation) ignore
  migrations: the answer is pulled towards the simulated spectrum and its
  errors are too small. Usable only when purity is near 1.
- Plain matrix inversion is unbiased, but amplifies fluctuations: oscillating
  values, large negative correlations. Acceptable with wide bins and the
  full covariance.

## Regularised methods

- Iterative Bayesian (D'Agostini): starts from the simulated truth; the
  number of iterations is the regularisation. Few stay near the prior; many
  approach plain inversion. Four is a habit, not a criterion: where the
  simulated shape differs from the data's, iterate until the stress-test
  bias is below the statistical error - often 10 or more.
- SVD (Höcker-Kartvelishvili): keeps k significant singular components.
- TUnfold: least squares with a Tikhonov term of strength τ (L-curve scan);
  wants more reconstructed bins than true bins.
- Likelihood unfolding: true-bin normalisations as parameters of a
  profile-likelihood fit (`hep-likelihood-limits`).

Fix the strength by a stated criterion on simulation or pseudo-data (smallest
bias² + variance; coverage) before unfolding the data.

## Tests, in this order

1. Technical closure: simulated detector-level input, same simulation's
   response - the truth comes back exactly.
2. Independent closure: response from one half of the simulation, unfold the
   other half - agreement within statistics.
3. Stress test: reweight the truth to another shape (the data-to-simulation
   trend), fold it, unfold with the nominal response. Unfolded minus
   reweighted truth is the bias: a systematic, or too strong a regularisation.
4. Toys: fluctuate the input, unfold; pulls have mean 0 and width 1.

## Uncertainties

- Statistical: data and the response's simulation statistics, by toys or
  analytically, as a covariance matrix.
- Each systematic: vary the response, unfold again (`hep-systematics`).
- Publish values, full covariance, and the method with its strength. A
  normalised spectrum has a singular covariance: drop one bin for a
  chi-square. Any chi-square against theory uses the full covariance, Δᵀ C⁻¹ Δ.

## Tools

RooUnfold (ROOT, Python bindings: Bayes, SVD, TUnfold, inversion),
`pyunfold` (iterative, pure Python), pyhf or Combine for likelihood
unfolding.

## Check before reporting

- Particle-level definition written out; binning with purity and stability.
- Method, strength, and the criterion that fixed it.
- Closure and stress-test results as numbers; the bias in the uncertainty.
- Covariance or correlation matrix shown; chi-squares use it.
- Compared with the simulated truth and with plain inversion; the total
  agrees with background-subtracted data over the average efficiency.

## Related

- Skills here: `hep-cross-section-measurement`, `hep-systematics`, `hep-root`,
  `histogram-analysis`, `uncertainty-propagation`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `statistical-analysis`, `matplotlib`.
