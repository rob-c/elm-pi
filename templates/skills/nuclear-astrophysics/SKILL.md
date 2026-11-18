---
name: nuclear-astrophysics
description: "Thermonuclear reaction rates - S-factor and Gamow peak, non-resonant and narrow-resonance rates, units, reverse rates, REACLIB and STARLIB, reaction networks, the s, r and p processes."
disable-model-invocation: true
---

# Nuclear astrophysics: reaction rates and networks

The mistakes: a cross section extrapolated to stellar energies as σ instead
of as the S-factor; lab energies in formulas that need centre-of-mass (CM)
ones; reduced mass, T or resonance strength in the wrong units (u or MeV, K
or T9, eV or MeV); and a rate quoted without saying whether it carries N_A.

## Charged-particle reactions

All energies CM; μ = M1 M2/(M1 + M2) in u; T9 = T/10⁹ K; kT = 0.08617 T9 MeV.

- σ(E) = S(E) exp(-2πη) / E, with 2πη = 31.29 Z1 Z2 √(μ / E[keV]). Away from
  resonances S(E) varies slowly: fit and extrapolate S, never σ.
- Gamow peak: E0 = 0.122 (Z1² Z2² μ T9²)^(1/3) MeV, with 1/e width
  Δ = 0.2368 (Z1² Z2² μ T9⁵)^(1/6) MeV. E0 ± Δ/2 is where a non-resonant
  reaction burns, and what a measurement should reach or be extrapolated to.
  For a reaction dominated by narrow resonances it is only a guide.
- Non-resonant rate: N_A⟨σv⟩ = N_A √(8/(πμ)) (kT)^(-3/2)
  ∫ S(E) exp(-E/kT - 2πη) dE. Integrate numerically with the grid
  concentrated around E0 (the integrand spans many decades) and check
  convergence; the leading behaviour is τ² exp(-τ) with τ = 3 E0/kT.
  In numbers: 3.7318e10 μ^(-1/2) T9^(-3/2) ∫ S exp(-E/kT - 2πη) dE
  cm³ mol⁻¹ s⁻¹, S in MeV b, E and kT in MeV (S dE is MeV² b: convert both).
  Check against 4.339e8/(Z1 Z2 μ) S(E0)[MeV b] τ² exp(-τ). Below the data, S
  comes from a fitted line or constant, not from the lowest two points.
- Narrow resonances, summed: N_A⟨σv⟩ = 1.5399e11 (μ T9)^(-3/2) ωγ
  exp(-11.605 Er/T9) cm³ mol⁻¹ s⁻¹, with ωγ and Er (centre of mass) in MeV.
  Strengths are quoted in eV, meV or μeV, and meV is milli: 1 meV = 10⁻⁹ MeV,
  not 10⁻³. Here
  ωγ = (2J+1)/((2j1+1)(2j2+1)) × Γa Γb/Γ. Er sits in the exponent: a keV
  matters at low temperature. Broad resonances: integrate the Breit-Wigner
  shape with energy-dependent widths.
- Laboratory electron screening raises measured cross sections at the lowest
  energies by exp(πη Ue/E); stellar plasma screening is a separate
  correction. Rates need the bare S-factor.

## Neutron capture

No barrier, so the quantity is the Maxwellian-averaged cross section,
conventionally at kT = 30 keV:
⟨σ⟩ = (2/√π) (kT)⁻² ∫ σ(E) E exp(-E/kT) dE, and the rate is N_A ⟨σ⟩ v_T with
v_T = √(2kT/μ).

## Reverse and stellar rates

- Reverse rates follow from detailed balance (spin factors, reduced-mass
  ratio, exp(-Q/kT)); take them from the library, or derive them, but never
  fit them separately. Q from `nuclear-masses-and-q-values`.
- In a star, excited states of the target are populated: stellar rates carry
  partition functions and differ from ground-state laboratory rates at high
  temperature. Say which you have.

## Libraries and codes

- **JINA REACLIB**: each rate is a sum of sets, each
  exp[a0 + Σ aᵢ T9^((2i-5)/3) + a6 ln T9] with i = 1..5, valid for T9 from
  0.01 to 10. Each has a label of origin: experiment or Hauser-Feshbach
  theory - look.
- **STARLIB**: tabulated rates with factor uncertainties (lognormal), made
  for Monte Carlo sensitivity studies. **NACRE II**: charged-particle
  reactions on light nuclei.
- Networks: pynucastro (builds a network from REACLIB and writes the
  right-hand side), SkyNet, WinNet. The equations are stiff: an implicit
  solver per `numerical-methods`; abundances Y = X/A, with Σ X = 1 conserved.
- Unmeasured rates come from statistical-model codes
  (`nuclear-reaction-codes`) and are uncertain by factors of 2 to 10.

## The processes, briefly

s process: neutron capture slower than β decay, along stability. r process:
capture far faster than β decay, far from stability, with abundance peaks
from the closed shells N = 50, 82, 126. p (γ) process: photodisintegration
of heavy seeds. rp process: proton capture along the proton drip line.

## Check before reporting

- CM energies, μ in u, T9, and the units of the rate.
- Numerical integral converged; rate compared with REACLIB or STARLIB at
  several temperatures, as a ratio.
- Resonance energies and strengths: source and uncertainty.
- Rate uncertainty quoted as a factor; laboratory or stellar; screening.
- Network: mass fractions sum to 1; result stable against the tolerance.

## Related

- Skills here: `nuclear-data-lookup`, `nuclear-masses-and-q-values`,
  `nuclear-reaction-codes`, `scattering-theory-and-partial-waves`,
  `numerical-methods`, `uncertainty-propagation`, `particle-cosmology`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `astropy`, `matplotlib`, `sympy`.
