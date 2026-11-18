---
name: hep-ml-classifiers
description: "Signal-versus-background classifiers in particle physics - splitting by event, BDT or network, weights, overtraining, working points, k-fold, systematics through the classifier, mass sculpting."
disable-model-invocation: true
---

# Signal and background classifiers

Three mistakes make a classifier look better than it is: applying it to the
events it was trained on, so the simulated background in the signal region is
too low; choosing the working point on the test sample; and feeding it inputs
the simulation models badly, so its performance in data is not the one quoted.

**Scores with a train/valid/test column: two steps, two sets.**

1. `valid` rows only: compute Z for every candidate cut; the cut is the one
   with the largest Z there. The test rows are not looked at yet.
2. `test` rows only: s, b, Z and efficiency of that one cut. No scan here.

"Test set only" is step 2, not the whole job: a maximum taken over the test
rows is the mistake. Nor sum all rows (the yields multiply).

## Procedure

1. **Figure of merit.** What counts is the expected significance or limit
   after the full selection with systematics (`hep-likelihood-limits`), not
   the AUC. For a single count with known background,
   Z = √(2[(s+b) ln(1+s/b) - s]); s/√b only when s is much smaller than b.
2. **Split by event, once.** A fixed rule (event number modulo k) into train,
   validation and test. Never split rows after flattening per-object arrays,
   and keep correlated entries together (one generated event with its
   systematic variations or re-simulations). Record the rule.
3. **Inputs.** Only variables whose data and simulation agree in a control
   region. Few, well-modelled inputs beat many. Drop anything that encodes
   the sample itself (run number, generator weight, dataset id).
4. **Weights.** Train with the physical event weights, each class normalised
   to the same sum. Negative weights (NLO generators) break many libraries:
   train on absolute values or without the negative events, but evaluate,
   always, with the full signed weights.
5. **Model.** Start with a BDT (XGBoost, LightGBM, TMVA) on high-level
   inputs: robust, fast, little preprocessing. A neural network when
   low-level or structured inputs (constituents, sets, graphs) carry the
   information; standardise inputs with training-sample statistics only.
6. **Overtraining.** Compare the response and the ROC curve on train and
   test, per class, and the loss curves. Stop early on the validation sample.
   A Kolmogorov-Smirnov p-value alone depends on binning and sample size.
7. **Working point.** Choose the cut, or the score binning to be fitted, on
   validation; quote performance on test. A test sample used for any choice
   has become a validation sample.
8. **k-fold, to use all the simulation.** Train k models; apply each only to
   the fold it did not see, assigned by event number; assign data the same
   way. No event is ever scored by a model that trained on it.
9. **Systematics.** Pass each systematic variation through the frozen
   classifier to get varied score templates; do not retrain per variation.
   Input mismodelling is covered by the same scale factors and control
   regions as the rest of the analysis (`hep-systematics`).
10. **Mass sculpting.** A classifier that learns the mass shapes the
    surviving background into a peak. Plot the background mass before and
    after the cut. Remedies: drop mass-correlated inputs, reweight the
    training sample flat in mass, a decorrelation penalty or adversary, a
    mass-parametrised network - or fit the score, not the mass.

## Small simulated samples

A cut that leaves a handful of simulated background events gives an
unreliable b: the effective number is (Σw)²/Σw², and an optimisation will
chase downward fluctuations. Require a minimum effective count per bin, and
carry the simulation's statistical error into the fit.

## Check before reporting

- The split rule, and that no scored event was in its model's training set.
- Train-versus-test curves; the working point's origin (validation).
- Data against simulation for every input and for the score in a control
  region.
- Background mass shape after the cut.
- Seeds, library versions, input list and preprocessing saved with the model.

## Related

- Skills here: `hep-event-selection`, `hep-systematics`,
  `hep-likelihood-limits`, `hep-background-estimation`,
  `statistics-and-significance`, `scientific-python`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `scikit-learn`, `pytorch-lightning`, `torch-geometric`, `shap`.
