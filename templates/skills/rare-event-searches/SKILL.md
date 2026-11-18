---
name: rare-event-searches
description: "Searches with few or no events - Poisson limits, Feldman-Cousins, CLs and Bayesian intervals, on/off counting, exposure, blinding, dark-matter and double-beta sensitivities, look-elsewhere."
disable-model-invocation: true
---

# Rare-event searches

With a handful of events the usual shortcuts fail: √N errors and s/√b are
wrong at small counts; choosing between a limit and an interval after seeing
the data ("flip-flopping") breaks the coverage; and a selection tuned on the
events that then give the result is biased.

## Before unblinding

1. Write down the signal region, the selection, the background model, the
   statistical method (including when a limit and when an interval is
   quoted) and what would count as evidence.
2. Predict the background and its uncertainty from sidebands, control
   regions or calibration data (`hep-background-estimation`); state the
   shape assumed in any extrapolation.
3. Signal efficiency against energy - threshold, trigger, fiducial volume,
   live time. Exposure is mass × live time (kg yr, t yr); say whether
   efficiency is folded in.
4. Expected sensitivity: the median limit with its 1σ and 2σ bands from
   background-only pseudo-experiments. It is reported beside the observed
   limit.
5. Unblind once. Anything changed afterwards is said to have been changed.

## Small-count statistics

- n observed with mean s + b: use the Poisson probability itself.
- Nothing observed, no background: s < 2.30 at 90% CL, s < 3.00 at 95%.
- With background, a classical one-sided limit can exclude s = 0 or come out
  empty when n is below b. Three remedies, three definitions - name yours:
  - **Feldman-Cousins**: unified intervals ordered by likelihood ratio; they
    turn from an upper limit into a two-sided interval on their own and
    cover correctly (n = 0, b = 0 gives 2.44 at 90%). A downward fluctuation
    still gives a tighter limit, hence item 4 above.
  - **CLs**: exclude when CL(s+b)/CL(b) falls below 1 - CL. Over-covers by
    construction and never excludes where there is no sensitivity.
  - **Bayesian**, flat prior in s ≥ 0: state the prior; for b = 0 it equals
    the classical limit.
- Uncertain background: constrain it with the auxiliary measurement in a
  profile likelihood (`hep-likelihood-limits`).
- **On/off counting**, off exposure 1/α times the on exposure: background
  α n_off, and the significance is Li and Ma's
  S = √2 {n_on ln[(1+α)/α × n_on/(n_on+n_off)]
  + n_off ln[(1+α) × n_off/(n_on+n_off)]}^½ - not excess/√background.
- Known b, expected signal s: Z = √(2[(s+b) ln(1+s/b) - s]).
- Scanning a mass or many channels: quote the global significance
  (`statistics-and-significance`). 3σ is evidence, 5σ observation
  (one-sided p of 1.35 × 10⁻³ and 2.87 × 10⁻⁷).

## Dark-matter direct detection

- Spin-independent rate per unit recoil energy Er on a nucleus of mass
  number A: ρ0 σ(n) A² F²(Er) / (2 m(χ) μ(n)²) × ∫ f(v)/v d³v over
  v > v_min = √(m(N) Er / 2μ²), where μ(n) and μ are the reduced masses with
  a nucleon and with the nucleus, and F is the nuclear form factor.
- The halo sets the answer: the local density (0.3 GeV/cm³ by convention),
  the velocity distribution's v0, the escape speed and the Earth's velocity.
  Take them from the community's recommended conventions, looked up, and
  list the values used: limits scale with them.
- State the energy scale (electron-equivalent or nuclear-recoil), the
  quenching model, threshold and efficiency curve.

## Neutrinoless double-beta decay

- From counts: t½ = ln 2 × N(atoms) × ε × t / N(signal); for a limit use the
  upper limit on signal counts.
- Sensitivity scales as ε a M t without background, and as
  ε a √(M t / (B ΔE)) when background-limited (a the isotopic abundance, M
  the mass, B the background index in counts per keV kg yr, ΔE the energy
  window).
- Converting t½ to an effective mass needs a phase-space factor and nuclear
  matrix elements: give the range over the calculations.

## Check before reporting

- Method and confidence level named; decided before unblinding.
- Expected sensitivity beside the observed result.
- Background estimate, its uncertainty and its validation.
- Exposure, efficiency and threshold; astrophysical or nuclear inputs cited.
- Local and global significance for any excess.

## Related

- Skills here: `statistics-and-significance`, `hep-likelihood-limits`,
  `hep-background-estimation`, `hep-event-selection`,
  `radiation-detectors-and-daq`, `gamma-spectroscopy`, `particle-cosmology`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `statistical-analysis`, `pymc`, `matplotlib`.
