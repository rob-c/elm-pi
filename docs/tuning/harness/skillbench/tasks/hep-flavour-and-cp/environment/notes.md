# B0 -> D+ D-: flavour-tagged decay-time sample

## counts.csv

Signal candidates that have a flavour tag, background subtracted, in bins of
reconstructed decay time and in the three tagging categories.

| column | |
|---|---|
| category | tagging category |
| t_low_ps, t_high_ps | edges of the decay-time bin, ps |
| n_b0_tag | candidates tagged as B0 at production |
| n_b0bar_tag | candidates tagged as anti-B0 at production |

## Flavour tagging

Of the 80000 signal candidates in this decay-time range, tagged or not:

| category | tagging efficiency | mistag fraction |
|---|---|---|
| A | 0.0439 | 0.08 |
| B | 0.1098 | 0.24 |
| C | 0.2154 | 0.40 |

The mistag fractions were calibrated on the flavour-specific B0 -> Ds+ D-
sample and are the same for B0 and anti-B0. Production and detection
asymmetries are below 1% and are neglected here.

## Decay time

- Mixing frequency: dm_d = 0.5065 ps^-1 (PDG), to be kept fixed. B0 lifetime 1.517 ps.
- Decay-time resolution: 55 fs.
- The trigger's acceptance falls at short decay times; it is the same for both
  tags.

## Convention

    A(t) = [Gamma(anti-B0(t) -> D+ D-) - Gamma(B0(t) -> D+ D-)] / [sum] = S sin(dm_d t) - C cos(dm_d t)

where B0(t) is a meson that was a B0 at production.
