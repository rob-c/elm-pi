---
name: lattice-qcd-analysis
description: "Analysing lattice QCD data - correlators and effective masses, correlated fits with a sampled covariance, jackknife and bootstrap, autocorrelation, scale setting, continuum, chiral and finite-volume extrapolations."
disable-model-invocation: true
---

# Lattice QCD data analysis

What goes wrong: errors too small because the configurations are
autocorrelated; a correlated fit whose covariance matrix is too noisy to
invert, or an uncorrelated fit whose χ² is then quoted as goodness of fit; a
fit window chosen where excited states still contribute; and a number at one
lattice spacing reported as a continuum result.

## Procedure

1. **Look at the Monte Carlo history** of each observable. Discard the
   thermalisation. Estimate the integrated autocorrelation time τ_int: the
   error of a mean is √(2 τ_int / N) times the naive standard deviation.
   Either bin the data in blocks much longer than τ_int (grow the bin until
   the error stops rising) or use the Γ-method.
2. **Correlators.** C(t) = Σ A_n exp(-E_n t); with (anti)periodic time
   extent T a meson correlator is A [exp(-E t) + exp(-E (T - t))]. Plot the
   effective mass ln[C(t)/C(t+1)] (the cosh form near T/2) and find where it
   is flat within errors. The relative noise grows with t for everything but
   the pion, so the usable window is short.
3. **Fits.** Minimise the correlated χ² with the covariance of the mean
   estimated from the N (binned) samples. That matrix is singular if N does
   not exceed the number of points and noisy unless N is much larger: use
   fewer points, an SVD cut, or shrinkage, and say which. An uncorrelated fit
   can give a usable central value with resampled errors, but its χ² is not a
   test.
4. **Fit window and excited states.** Show the result against t_min; quote a
   value from the stable region and take the variation as a systematic. More
   exponentials need priors or a variational (GEVP) basis: state the priors
   and check that the posterior is not just the prior.
5. **Resampling.** Jackknife: θ_i with bin i removed,
   σ² = (N-1)/N Σ (θ_i - θ̄)². Bootstrap: resample bins with replacement.
   Run the whole chain (fits, ratios, extrapolations) inside each sample, and
   use the same samples for every quantity on an ensemble so correlations
   survive.
6. **Scale setting.** Results are in lattice units. Fix a from a reference
   quantity (gradient-flow scales, a hadron mass, a decay constant) and
   convert with ħc = 197.327 MeV fm: m [MeV] = (a m) × 197.327 / a [fm].
   Carry the scale's uncertainty; reference values come from the FLAG review
   via `hep-literature-and-data`, not from memory.
7. **Extrapolations.** Continuum: at least three lattice spacings, in a² for
   an O(a)-improved action. Chiral: to the physical pion mass unless the
   ensembles are already there. Finite volume: m_π L of 4 or more, with
   corrections that fall as exp(-m_π L). Say which sea flavours are included
   and how the operators were renormalised.
8. **Error budget**: statistical, fit window and model, scale, continuum,
   chiral, finite volume, renormalisation - listed separately.

## Tools

- `gvar` (correlated Gaussian variables), `lsqfit` (least squares with priors
  and `svdcut`) and `corrfitter` for multi-exponential fits.
- `pyerrors` for the Γ-method and autocorrelation-aware propagation.
- Data are usually HDF5 (`h5py`): record ensemble names, configuration ranges
  and source positions with every number.
- Generating configurations (Grid, Chroma, openQCD) is cluster work and not
  covered here.

## Check before reporting

- Binning or Γ-method shown to have converged; N effective stated.
- Correlated χ² per degree of freedom and p-value, with how the covariance
  was regularised; t_min stability plot.
- Synthetic data with a known energy and the same covariance go through the
  same code and return that energy within errors.
- Jackknife and bootstrap agree; errors fall as 1/√N when the sample is cut.
- Lattice spacing, volume, pion mass and sea content given for each
  ensemble; continuum and chiral extrapolations done or their absence stated.
- Comparison with the FLAG average or experiment, with the source read in
  this session.

## Related

- Skills here: `data-fitting`, `uncertainty-propagation`,
  `statistics-and-significance`, `numerical-methods`, `scientific-python`,
  `physical-constants`, `hep-literature-and-data`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `matplotlib`, `pymc`, `scientific-visualization`.
