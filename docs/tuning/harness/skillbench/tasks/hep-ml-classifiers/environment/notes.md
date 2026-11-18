# Scores of the VBF BDT (version 7) on the simulated samples

scores.csv has one row for each simulated event that passes the preselection.

| column | |
|---|---|
| event | event number |
| set | which part of the split the event is in: train, valid or test. The split is by event number modulo 4 (0 and 1 train, 2 valid, 3 test) and was fixed before the BDT was trained |
| label | 1 for signal, 0 for background (multijet and the irreducible Z + jets) |
| score | the BDT output, from 0 (background-like) to 1 (signal-like) |
| weight | event weight. In each set the weights are scaled so that the set on its own sums to the yields expected in 140 fb^-1: a set can be used without rescaling it by its share of the events |

## Working points

The cut is score > x. The scale factors for the BDT exist for
x = 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85 only, so the choice is among those.

## Figure of merit

A counting experiment after the cut, with s signal and b background events
expected and the background taken as known:

    Z = sqrt(2 ((s + b) ln(1 + s/b) - s))

The signal efficiency of a working point is relative to the preselection.
