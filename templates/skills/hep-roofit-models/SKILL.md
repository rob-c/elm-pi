---
name: hep-roofit-models
description: "RooFit and RooStats models - workspaces, normalisation ranges, extended and weighted likelihood fits, fit status and covariance quality, sPlot, toy studies, zfit in Python."
disable-model-invocation: true
---

# RooFit models and fits

What goes wrong: a fit reported although the minimiser failed or the
covariance matrix is only an approximation; a pdf normalised over one range
and fitted over another; yields quoted from a fit that was not extended; and
sWeights used for a variable correlated with the fitted one.

## Building the model

- `RooRealVar x("x", "m [GeV]", lo, hi)`: the observable's range is the
  normalisation range, and data outside it are dropped silently on import. Set
  the range first and compare `data.sumEntries()` with what you expect.
- Every parameter gets a start value and limits wide enough that the minimum
  is not at one. A parameter that ends at a limit has no valid error.
- The factory keeps a model readable and saveable:
  `w.factory("Gaussian::sig(x, mean[91,86,96], sigma[2.5,0.5,10])")`,
  `w.factory("SUM::model(nsig[100,0,1e5]*sig, nbkg[1000,0,1e6]*bkg)")` - with
  yields as coefficients the sum is extended; with one fraction `f*sig, bkg` it
  is not. `w.writeToFile("ws.root")` saves model and data together.
- Fitting a sub-range with fractions: say which range the fractions refer to
  (`SumCoefRange`), or use yields.

## Fitting

1. Unbinned `RooDataSet` (weights through `WeightVar`) or binned
   `RooDataHist`. Above about a million events bin finely instead. Prefer the
   likelihood to a chi-square: see `data-fitting`.
2. `r = model.fitTo(data, Save(), Extended(true), Range("fit"), PrintLevel(-1))`.
   Pass `Extended(true)` explicitly whenever yields are parameters.
3. Read the `RooFitResult` every time: `r->status()` is 0, `r->covQual()` is 3
   (3 full and accurate, 2 forced positive-definite, 1 approximate, 0 not
   computed), `r->edm()` is small, no parameter is at a limit. `r->Print("v")`
   and `r->correlationMatrix()`.
4. Refit from other start values: the same minimum must come back.
5. Asymmetric or non-parabolic errors: `Minos(true)`, or scan the profile
   likelihood (`createNLL`, then `createProfile`).
6. Weighted data: the plain likelihood gives wrong parameter errors.
   `SumW2Error(true)` corrects them approximately; recent ROOT also has
   `AsymptoticError(true)`. Confirm the errors with toys.
7. Several categories: `RooSimultaneous` over a `RooCategory`; parameters with
   the same name in the workspace are shared. External knowledge enters as a
   constraint pdf (`ExternalConstraints`), not as a fixed value.

## Plot and goodness of fit

`frame = x.frame()`, `data.plotOn(frame)`, `model.plotOn(frame)` in that
order: the curve is normalised to the last dataset plotted. Components with
`Components("bkg")`. `frame.chiSquare(nFloated)` is the reduced chi-square of
the last curve against the last histogram; `frame.pullHist()` gives the
pulls, which must show no structure. With few events per bin judge the fit
with toys instead.

## sPlot

`RooStats::SPlot("sData", "", data, &model, RooArgList(nsig, nbkg))` needs:
an extended fit; every parameter except the yields fixed for the final fit;
and the variable to be plotted statistically independent of the fitted one
within each species - test that in simulation or sidebands. The sWeights of a
species sum to its yield. Histograms of sWeighted events need Σw² errors; a
fit to them needs the weighted-fit treatment above.

## Toys

`RooMCStudy mc(model, x, Extended(true), FitOptions(Save(true), PrintLevel(-1)))`,
`mc.generateAndFit(1000)`, then `mc.plotPull(par, ...)`. Pulls with mean 0 and
width 1 within their errors mean an unbiased estimate with correct errors.
Report the fraction of failed fits; a bias is corrected or quoted.

## Without ROOT

`zfit` (with `hepstats` for limits and sWeights) and `iminuit` give the same
fits in Python; the same checks apply (`result.valid` and `result.converged`
in zfit, `m.valid` and `m.accurate` in iminuit). Missing: `installing-software`.

## Check before reporting

- Status 0, covariance quality 3, small EDM, nothing at a limit, same minimum
  from other start values.
- Events in range equal events fitted; extended yields sum to that number.
- Pulls without structure; a chi-square per degree of freedom or a toy p-value.
- For sWeights: independence tested, weights sum to the yield.
- Toy pulls shown, or the bias quoted. ROOT version and saved workspace named.

## Related

- Skills here: `data-fitting`, `statistics-and-significance`, `hep-root`,
  `uncertainty-propagation`, `hep-likelihood-limits`, `hep-systematics`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `statistical-analysis`, `matplotlib`.
