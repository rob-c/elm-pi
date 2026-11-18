"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Nothing is random: the task is two charge assignments of a U(1)_X extension.

Assignment B is 3Y + 3(B-L) on the Standard Model fields (Y with Q = T3 + Y/2),
so it is anomaly-free when the lepton doublet has z = -6, and the Higgs doublet
then has x_H = 3. Assignment A is not in the two-parameter anomaly-free family:
all six coefficients are non-zero. The top partner T is vector-like under the
whole gauge group in both, so it drops out of every trace.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

# field, SU(3), SU(2), Y, copies, X in assignment A, X in assignment B
FIELDS = [
    ("Q_L", "3", "2", "1/3", 3, "1/3", "2"),
    ("u_R", "3", "1", "4/3", 3, "1", "5"),
    ("d_R", "3", "1", "-2/3", 3, "-2/3", "-1"),
    ("L_L", "1", "2", "-1", 3, "-2", "z"),
    ("e_R", "1", "1", "-2", 3, "-3", "-9"),
    ("N_R", "1", "1", "0", 3, "-1", "-3"),
    ("T_L", "3", "1", "4/3", 1, "1", "5"),
    ("T_R", "3", "1", "4/3", 1, "1", "5"),
]

table = "".join("| %s | %s | %s | %s | %d | %s | %s |\n" % row for row in FIELDS)
(out / "model.md").write_text("""# U(1)_X model: fermion content and the two charge assignments

Gauge group SU(3)_c x SU(2)_L x U(1)_Y x U(1)_X. Hypercharge is normalised so
that Q = T3 + Y/2. Every field is listed under its own name, with the chirality
in the name and the charges of that field itself (u_R is the right-handed
up-type quark, electric charge +2/3).

| field | SU(3)_c | SU(2)_L | Y | copies | X, assignment A | X, assignment B |
|---|---|---|---|---|---|---|
""" + table + """
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
""")
print("wrote model.md")
