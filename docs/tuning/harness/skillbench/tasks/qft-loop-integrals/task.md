---
skill: qft-loop-integrals
category: particle-theory
pitfall: imaginary part above threshold with the wrong sign (the default branch of the logarithm instead of the i0 one); ln 4 pi - gamma_E left in the MS-bar finite part
timeout_sec: 900
---
notes.md defines our one-loop scalar integral B0 in dimensional regularisation and the scheme, and points.csv lists four kinematic points. I need the MS-bar subtracted B0 at each of them, real and imaginary part, to compare with what the self-energy code uses. Write result.json with re_1, im_1, re_2, im_2, re_3, im_3, re_4 and im_4 (dimensionless).
