---
name: radioactive-decay-chains
description: "Radioactive decay and decay chains - activity and specific activity, Bateman equations done stably, secular and transient equilibrium, branching, production by irradiation, radiocarbon conventions."
disable-model-invocation: true
---

# Radioactive decay and decay chains

The mistakes: mean life taken for half-life (a factor ln 2); the Bateman
formula evaluated in double precision where decay constants are close or
many orders apart, giving noise or negative activities; equilibrium assumed
where it does not hold; and an activity quoted with no reference time.

## One nuclide

- N(t) = N0 exp(-λt), λ = ln 2 / t½, mean life τ = 1/λ = 1.4427 t½,
  activity A = λN. Half-lives and branching fractions from
  `nuclear-data-lookup`; convert to seconds before forming λ.
- 1 Bq = 1 decay per second; 1 Ci = 3.7e10 Bq exactly. Decays are not
  emitted particles: emission rate = A × emission probability.
- Atoms from mass: N = m N_A / M. Specific activity λ N_A / M, in Bq/g with M
  in g/mol.
- Branches: partial decay constants add, λ = Σ λᵢ; branching fraction
  bᵢ = λᵢ/λ; the partial half-life is t½/bᵢ.

## Chains

- dN₁/dt = -λ₁N₁, dN₂/dt = b λ₁N₁ - λ₂N₂, and so on down the chain.
- Parent and daughter: N₂(t) = N₁(0) b λ₁/(λ₂ - λ₁) [exp(-λ₁t) - exp(-λ₂t)]
  + N₂(0) exp(-λ₂t). From a pure parent the daughter's activity peaks at
  t = ln(λ₂/λ₁)/(λ₂ - λ₁).
- General Bateman solution, distinct λ, only the first member present at
  t = 0: the n-th member has N₁(0) (λ₁ ... λₙ₋₁) Σᵢ exp(-λᵢt) / Πⱼ≠ᵢ (λⱼ - λᵢ).
  With branching, multiply by the branching fractions along each path and
  sum the paths.
- **Numerics.** That sum has large terms of alternating sign. Do not code it
  in floats for a real chain. Use the radioactivedecay package (its
  high-precision inventory, `radioactivedecay.InventoryHP`, where half-lives
  span many orders), or `scipy.linalg.expm` of the decay matrix, or a stiff
  ODE solver per `numerical-methods`. Equal decay constants need the limit
  form (a factor t), not the formula.

## Equilibrium

- **Secular** (λ₁ much smaller than λ₂): A₂ tends to b A₁, within 1% after
  about seven daughter half-lives.
- **Transient** (λ₁ < λ₂, comparable): A₂/A₁ tends to b λ₂/(λ₂ - λ₁), which
  is greater than b.
- **None** if the daughter outlives the parent (λ₁ > λ₂).
- Chemistry or an escaping gas (radon) breaks a chain: state the assumption
  that it is closed, and since when.

## Production and counting

- Irradiation at a constant rate R = N σ φ atoms per second gives
  A = R (1 - exp(-λ t_irr)) at the end: half of saturation after one
  half-life, three quarters after two. After cooling for t_c multiply by
  exp(-λ t_c). Target burn-up is neglected in this form.
- Decays during a count from t₁ lasting t_m: (A(t₁)/λ)(1 - exp(-λ t_m)).
  The corrections for a measured spectrum are in `gamma-spectroscopy`.
- Every activity carries its reference date and time.

## Radiocarbon

Conventional radiocarbon ages use the Libby half-life, 5568 y (mean life
8033 y), are counted back from AD 1950 ("BP") and are then calibrated to
calendar years with a calibration curve. The physical half-life is not used
for a conventional age: say which convention a number follows.

## Check before reporting

- Half-life or mean life, and time units consistent with λ.
- t = 0 returns the initial inventory; the total number of atoms (with the
  stable end member) is conserved; no activity is negative.
- One time point agrees with an independent method (the package against the
  two-member formula, or the matrix exponential).
- Decay data: source and evaluation named.
- Reference time, and any equilibrium assumed, stated.

## Related

- Skills here: `nuclear-data-lookup`, `gamma-spectroscopy`,
  `neutron-activation-and-transport`, `numerical-methods`, `data-fitting`,
  `uncertainty-propagation`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `uncertainty-and-units`, `matplotlib`.
