---
skill: nuclear-astrophysics
also: numerical-methods, data-fitting
category: nuclear
pitfall: laboratory beam energies used where centre-of-mass energies are needed (S-factor and resonance energy); the cross section, not the S-factor, carried below the lowest data point; resonance strength in meV, rate with or without N_A
timeout_sec: 900
---
cross_sections.csv has our 14N(p,γ)15O capture cross sections against proton beam energy, and notes.md the resonance parameters, masses and constants. For T9 = 0.12 I need the Gamow peak energy and its 1/e width, the non-resonant rate from our data, and the rate from the 278 keV resonance, both rates as N_A<σv> in cm^3 mol^-1 s^-1. Write result.json with gamow_peak_kev, gamow_width_kev, rate_nonresonant_cm3_mol_s and rate_resonance_cm3_mol_s.
