---
skill: nuclear-structure-models
also: nuclear-data-lookup, physical-constants
category: nuclear
pitfall: the B(E2) from the lifetime is the 2+ to 0+ value, reported as B(E2; 0+ to 2+) without the factor 5 (and beta2 then low by root 5); e2b2 and e2fm4 mixed; half-life used as mean life; internal conversion left out
timeout_sec: 900
---
notes.md has our fast-timing result for the first 2+ state of Sm-154 with the level energies and the formulas we use. From it I need B(E2; 0+ -> 2+) in e2b2, the 2+ -> 0+ strength in Weisskopf units, the deformation beta2, R(4/2), and the moment of inertia from the 2+ energy read as a rigid rotor, in hbar^2/MeV. Write result.json with be2_up_e2b2, be2_down_wu, beta2, r42 and moment_of_inertia_hbar2_per_mev.
