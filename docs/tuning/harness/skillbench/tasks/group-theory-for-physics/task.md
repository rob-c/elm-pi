---
skill: group-theory-for-physics
also: derivation-checks
category: particle-theory
pitfall: Casimirs and indices in the normalisation with index 1 for the fundamental (twice the stated one); a product whose dimensions do not add up, or with a conjugate or the wrong one of two same-dimension irreps
timeout_sec: 900
---
reps.md lists the SU(3) and SU(5) representations we need, by Dynkin labels, and the normalisation we use. For each one I want the dimension, the quadratic Casimir and the Dynkin index, and for the two tensor products at the end their decomposition into irreps. Put them in result.json: for every name in the first table <name>_dim, <name>_c2 and <name>_index, and for each product a list of Dynkin labels under its name, like [[1,0],[0,2]], with an irrep that occurs twice listed twice.
