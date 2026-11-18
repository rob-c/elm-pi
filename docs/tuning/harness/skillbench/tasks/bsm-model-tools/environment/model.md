# U(1)_X model: fermion content and the two charge assignments

Gauge group SU(3)_c x SU(2)_L x U(1)_Y x U(1)_X. Hypercharge is normalised so
that Q = T3 + Y/2. Every field is listed under its own name, with the chirality
in the name and the charges of that field itself (u_R is the right-handed
up-type quark, electric charge +2/3).

| field | SU(3)_c | SU(2)_L | Y | copies | X, assignment A | X, assignment B |
|---|---|---|---|---|---|---|
| Q_L | 3 | 2 | 1/3 | 3 | 1/3 | 2 |
| u_R | 3 | 1 | 4/3 | 3 | 1 | 5 |
| d_R | 3 | 1 | -2/3 | 3 | -2/3 | -1 |
| L_L | 1 | 2 | -1 | 3 | -2 | z |
| e_R | 1 | 1 | -2 | 3 | -3 | -9 |
| N_R | 1 | 1 | 0 | 3 | -1 | -3 |
| T_L | 3 | 1 | 4/3 | 1 | 1 | 5 |
| T_R | 3 | 1 | 4/3 | 1 | 1 | 5 |

"copies" is the number of generations: three for the Standard Model fields and
the right-handed neutrinos N_R, one for the top partner T.

Assignment A is the one in the first draft. In assignment B the quark and
singlet charges are fixed by the flavour sector, and the charge z of the lepton
doublet is still open.

## Scalars and Yukawa couplings

One Higgs doublet H: (1, 2), Y = +1, U(1)_X charge x_H. The Yukawa terms we
need are

    -L = y_u Qbar_L H~ u_R + y_d Qbar_L H d_R + y_e Lbar_L H e_R + y_nu Lbar_L H~ N_R + h.c.

with H~ = i sigma_2 H*.

## Anomaly coefficients

All traces run over all the left-handed Weyl fermions of the model. Non-abelian
generators are normalised to Tr[T^a T^b] = (1/2) delta^ab in the fundamental
representation.

| key | definition |
|---|---|
| a_ccx | Tr[T^a T^b X] = a_ccx delta^ab, T^a the SU(3)_c generators |
| a_wwx | Tr[T^a T^b X] = a_wwx delta^ab, T^a the SU(2)_L generators |
| a_yyx | Tr[Y^2 X] |
| a_yxx | Tr[Y X^2] |
| a_xxx | Tr[X^3] |
| a_ggx | Tr[X] (mixed gravitational) |
