---
name: nuclear-masses-and-q-values
description: "Nuclear binding energies, separation energies, Q-values and reaction thresholds from atomic masses - mass excess, beta-plus and electron capture, alpha decay, keeping the electrons counted."
disable-model-invocation: true
---

# Nuclear masses and Q-values

The mistakes: atomic and nuclear masses mixed, so the answer is off by
electron masses; the 2 mₑc² left out of β+ decay (or put into electron
capture); and a Q-value taken as the small difference of masses in u rounded
to six figures.

## What the tables give

- AME2020 lists **atomic** masses (neutral atoms) as the mass excess
  Δ = (M - A u) c², in keV. 1 u = 931.494 MeV/c², so
  M c² = A × 931.494 MeV + Δ. Take every Δ from `nuclear-data-lookup`.
- Work in mass excesses: when nucleon number is conserved the A u terms
  cancel and Q = Σ Δ(initial) - Σ Δ(final), with no loss of digits.
- Nuclear mass = atomic mass - Z mₑ + electron binding. The binding is up to
  several hundred keV in heavy atoms but nearly cancels in differences; use
  atomic masses throughout and count electrons instead.
- AME values marked "#" are extrapolated from systematics, not measured: say so.
- Read a mass table with code and look each Δ up by nuclide name: retyped by
  hand, a neighbouring row (same A, other Z) gets copied instead.

## Binding and separation energies (atomic masses)

- B(Z, N) = [Z M(¹H) + N m_n - M(Z, N)] c²: the hydrogen atom, not the bare
  proton, so the electrons balance. Δ(¹H) = 7.289 MeV, Δ(n) = 8.071 MeV.
- S_n = [M(Z, N-1) + m_n - M(Z, N)] c²; S_p uses M(Z-1, N) + M(¹H); the
  two-neutron S(2n) uses M(Z, N-2) + 2 m_n.
- Sanity: B/A is 7.5 to 8.8 MeV for A above 12, largest near A = 56-62.

## Q-values

- **Reaction** a + A → b + B: Q = [M(a) + M(A) - M(b) - M(B)] c², atoms for
  all (¹H for a proton, ⁴He for an α, nothing for a γ). Q > 0 releases energy.
  To an excited state at E_x: Q = Q(ground) - E_x.
- **β-**: Q = [M(Z) - M(Z+1)] c². The emitted electron is the daughter atom's
  extra electron.
- **β+**: Q = [M(Z) - M(Z-1)] c² - 2 mₑc², with 2 mₑc² = 1.022 MeV. Allowed
  only if the atomic mass difference exceeds 1.022 MeV.
- **Electron capture**: Q = [M(Z) - M(Z-1)] c² minus the binding energy of
  the captured electron's shell. No 1.022 MeV.
- **α decay**: Q = [M(parent) - M(daughter) - M(⁴He)] c². The α carries
  Q × M(daughter)/(M(daughter) + M(α)), about Q (A-4)/A; the rest is recoil,
  so Q is larger than the α line energy.
- A β endpoint is Q for the ground-state branch, and Q - E_x for a branch to
  a level at E_x.

## Thresholds

- **One formula, with all four masses.** For Q < 0 and the target at rest:
  T_th = -Q (m_a + m_A + m_b + m_B) / (2 m_A), masses in energy units
  (M c² = A u + Δ, not mass numbers). Do not use the textbook two-mass
  shortcut with only projectile and target: it is non-relativistic and low
  by Q²/(2 m_A c²) - 45 keV for Q = -18 MeV on ⁴He.
- For charged particles the Coulomb barrier, not the threshold, usually
  decides where the cross section is measurable: `nuclear-reaction-kinematics`.

## The semi-empirical mass formula

Volume, surface, Coulomb, asymmetry and pairing terms reproduce B to about 1%,
which is 10 MeV or more in a heavy nucleus, and textbooks disagree on the
coefficients and on the form of the asymmetry term. Use it to catch a sign or
a factor, and to explain a trend; never for a Q-value when tabulated masses
exist. If you do quote it, give the coefficient set.

## Check before reporting

- Atomic masses on both sides, and the same number of electrons, or the
  difference accounted for.
- A and Z balance; the sign of Q matches "releases" or "needs" in the text.
- β+ has the 1.022 MeV and electron capture does not.
- A threshold has all four masses in it (the formula above).
- Each mass excess with its table (AME2020 or which), and uncertainties
  propagated per `uncertainty-propagation`.
- One number checked independently: the same Q from a tabulated Q-value, or
  B/A against the range above.

## Related

- Skills here: `nuclear-data-lookup`, `nuclear-reaction-kinematics`,
  `radioactive-decay-chains`, `nuclear-astrophysics`, `physical-constants`,
  `uncertainty-propagation`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `uncertainty-and-units`, `sympy`.
