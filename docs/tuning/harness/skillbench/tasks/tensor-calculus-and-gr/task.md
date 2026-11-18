---
skill: tensor-calculus-and-gr
also: derivation-checks
category: particle-theory
pitfall: curvature computed with the textbook (or the library's) Riemann sign instead of the one the notes define, so the Ricci tensor and scalar come out with the wrong sign; orthonormal-frame components given for coordinate ones
timeout_sec: 900
---
notes.md has the metric of the charged dilaton black hole we are using, our curvature conventions, and the parameter values and point I care about. I need the coordinate components R_tt, R_rr, R_theta,theta and R_phi,phi of the Ricci tensor, the Ricci scalar and the Kretschmann scalar there, as numbers. Put them in result.json as ricci_tt, ricci_rr, ricci_thth, ricci_phph, ricci_scalar and kretschmann.
