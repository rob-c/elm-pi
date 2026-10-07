---
name: physical-constants
description: "Getting the value of a physical constant, particle mass, lifetime, branching ratio, coupling or other reference number right, with its source. Use whenever a numerical result depends on a measured constant or reference value, and before quoting any such value."
---

# Physical constants and reference values

Values recalled from training are often an older edition and are never
verified: a recalled number with a specific source attached ("PDG 2024") is a
fabricated citation, even when the number is close. In a test on this install
the model gave the W mass as "80.379 ± 0.012 GeV (PDG 2024)"; PDG 2024 says
80.3692 ± 0.0133 GeV.

## Exact values (SI since 2019) - safe to use as given

| Quantity | Value |
|---|---|
| speed of light c | 299 792 458 m s⁻¹ |
| Planck constant h | 6.626 070 15 × 10⁻³⁴ J s |
| elementary charge e | 1.602 176 634 × 10⁻¹⁹ C |
| Boltzmann constant k_B | 1.380 649 × 10⁻²³ J K⁻¹ |
| Avogadro constant N_A | 6.022 140 76 × 10²³ mol⁻¹ |
| caesium hyperfine frequency Δν_Cs | 9 192 631 770 Hz |
| luminous efficacy K_cd | 683 lm W⁻¹ |

Derived and also exact: ħ = h/2π; 1 eV = 1.602 176 634 × 10⁻¹⁹ J;
ħc = 197.326 980 4… MeV fm.

## Everything else, in order of preference

1. **A value in the user's files** (their analysis constants, a paper they
   gave you): use it, cite the file.
2. **scipy.constants** for CODATA constants (G, α, m_e, m_p, μ₀, ε₀, …):
   `scipy.constants.physical_constants["fine-structure constant"]` gives value,
   unit and uncertainty; the CODATA release is the one bundled with the
   installed scipy - say which (`scipy.__version__`).
3. **The source itself**, in a session with web access (`pi --remote`): PDG
   (pdg.lbl.gov) for particle properties, NIST (physics.nist.gov/cuu) for
   constants. Quote the value with the edition and table you actually read.
4. **Memory, as a last resort**: write "(from memory, unverified)" after the
   value, no source or year, and say how to check it. If the result depends on
   it at the precision quoted, stop and ask instead.

## Quoting

Value, uncertainty, units, and source with edition - only a source you read
in this session. Keep enough digits that the constant's uncertainty is
negligible against the result's, or propagate it.
