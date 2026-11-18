"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Scores of one classifier on three sets of simulated events. Validation and test
are drawn from the same distributions; on the training set the classifier is
visibly better (it is overtrained). The significance is nearly flat over three
working points, so which one is best in a given set is decided by that set's
own fluctuation of the heavy-weight background: the working point that is best
on validation is not the one that is best on test, and what validation says of
its own best point is too good by about a tenth.

The seed was picked from 60 tried (20261117 on) as one where the three sets
each prefer a different working point and validation's preference is clear
(2.5% over its second best). About half of all seeds give test a different
optimum from validation; this one gives the verifier margins it can hold.
"""
import sys
from pathlib import Path

import numpy as np

out = Path(sys.argv[1])
rng = np.random.default_rng(20261165)

LUMI_FB = 140
TOTAL = {"signal": 45.0, "multijet": 2400.0, "irreducible": 110.0}      # expected events after preselection
LABEL = {"signal": 1, "multijet": 0, "irreducible": 0}
# Beta(a, b) score shapes. The irreducible background looks like signal, so tight cuts stop paying.
SHAPE = {
    "valid": {"signal": (5.0, 1.6), "multijet": (1.0, 4.0), "irreducible": (4.0, 2.0)},
    "test": {"signal": (5.0, 1.6), "multijet": (1.0, 4.0), "irreducible": (4.0, 2.0)},
    "train": {"signal": (5.8, 1.5), "multijet": (1.0, 4.8), "irreducible": (3.7, 2.15)},
}
ROWS = {"train": (1600, 2600, 1000), "valid": (800, 1300, 500), "test": (800, 1300, 500)}
WORKING_POINTS = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]

sets = {}
for name in ("train", "valid", "test"):
    labels, scores, weights = [], [], []
    for process, n in zip(TOTAL, ROWS[name]):
        score = np.round(rng.beta(*SHAPE[name][process], n), 4)
        weight = rng.lognormal(0.0, 0.15, n)                 # pile-up and scale-factor weights
        weight *= TOTAL[process] / weight.sum()              # each set sums to the full expected yield
        labels.append(np.full(n, LABEL[process]))
        scores.append(score)
        weights.append(np.round(weight, 4))
    label, score, weight = (np.concatenate(x) for x in (labels, scores, weights))
    score[np.isin(score, WORKING_POINTS)] += 0.0001          # no score exactly on a working point
    sets[name] = (label, score, weight)

# One file, in event-number order: the split is by event number modulo 4.
rows = []
event = {"train": iter(n for n in range(1, 10**6) if n % 4 in (0, 1)),
         "valid": iter(n for n in range(1, 10**6) if n % 4 == 2),
         "test": iter(n for n in range(1, 10**6) if n % 4 == 3)}
for name, (label, score, weight) in sets.items():
    for i in rng.permutation(len(label)):
        rows.append((next(event[name]), name, label[i], score[i], weight[i]))
rows.sort()
(out / "scores.csv").write_text("event,set,label,score,weight\n" + "".join("%d,%s,%d,%.4f,%.4f\n" % row for row in rows))

(out / "notes.md").write_text("""# Scores of the VBF BDT (version 7) on the simulated samples

scores.csv has one row for each simulated event that passes the preselection.

| column | |
|---|---|
| event | event number |
| set | which part of the split the event is in: train, valid or test. The split is by event number modulo 4 (0 and 1 train, 2 valid, 3 test) and was fixed before the BDT was trained |
| label | 1 for signal, 0 for background (multijet and the irreducible Z + jets) |
| score | the BDT output, from 0 (background-like) to 1 (signal-like) |
| weight | event weight. In each set the weights are scaled so that the set on its own sums to the yields expected in %d fb^-1: a set can be used without rescaling it by its share of the events |

## Working points

The cut is score > x. The scale factors for the BDT exist for
x = %s only, so the choice is among those.

## Figure of merit

A counting experiment after the cut, with s signal and b background events
expected and the background taken as known:

    Z = sqrt(2 ((s + b) ln(1 + s/b) - s))

The signal efficiency of a working point is relative to the preselection.
""" % (LUMI_FB, ", ".join("%.2f" % x for x in WORKING_POINTS)))


def significance(s, b):
    return np.sqrt(2 * ((s + b) * np.log1p(s / b) - s))


def table(label, score, weight):
    out = []
    for cut in WORKING_POINTS:
        s, b = weight[(label == 1) & (score > cut)].sum(), weight[(label == 0) & (score > cut)].sum()
        out.append((cut, s, b, significance(s, b), s / weight[label == 1].sum()))
    return np.array(out)


everything = tuple(np.concatenate([sets[name][i] for name in sets]) for i in range(3))
tables = {name: table(*sets[name]) for name in sets}
tables["all rows"] = table(*everything)
best = {}
for name, rows_ in tables.items():
    best[name] = int(np.argmax(rows_[:, 3]))
    print(name)
    for i, row in enumerate(rows_):
        print("  score > %.2f  s %7.3f  b %8.3f  Z %.4f  efficiency %.4f%s" % (*row, "   <- best" if i == best[name] else ""))
chosen = best["valid"]
by_z = np.sort(tables["valid"][:, 3])[::-1]
assert by_z[0] / by_z[1] > 1.02, "validation's choice is not clear"
assert chosen == int(np.argmax(tables["valid"][:, 1] / np.sqrt(tables["valid"][:, 2]))), "s/sqrt(b) chooses differently"
assert best["test"] != chosen and best["train"] != chosen and best["all rows"] != chosen
assert abs(tables["valid"][chosen, 3] / tables["test"][chosen, 3] - 1) > 0.05
print("truth: cut %.2f, on test s %.3f b %.3f Z %.4f efficiency %.4f" % tuple(tables["test"][chosen]))
