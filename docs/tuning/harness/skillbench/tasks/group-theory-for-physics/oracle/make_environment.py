"""Writes environment/ for this task. The truth is here and in the verifier, nowhere a session can read it.

    python make_environment.py <environment dir>

Nothing is random. The representations are chosen so that the answer cannot be
read off a short table: SU(3) has two irreps of dimension 15, (2,1) and (4,0),
and both are asked for and both appear in the product (2,1) x (1,1); the SU(5)
45 is neither a two-index tensor nor the adjoint; and the SU(5) product
10 x 24 contains the 15 and the 40, whose conjugates have the same dimensions.
"""
import sys
from pathlib import Path

out = Path(sys.argv[1])

REPRESENTATIONS = [
    ("su3_a", "SU(3)", "(2,1)"),
    ("su3_b", "SU(3)", "(4,0)"),
    ("su3_c", "SU(3)", "(2,2)"),
    ("su5_a", "SU(5)", "(0,1,0,0)"),
    ("su5_b", "SU(5)", "(1,0,0,1)"),
    ("su5_c", "SU(5)", "(0,1,0,1)"),
]
PRODUCTS = [
    ("product_su3", "SU(3)", "(2,1)", "(1,1)"),
    ("product_su5", "SU(5)", "(0,1,0,0)", "(1,0,0,1)"),
]

(out / "reps.md").write_text("""# Representations in the coloured-exotics and SU(5) sectors

Irreducible representations are named by their Dynkin labels (the highest
weight in the basis of fundamental weights). For SU(3), (1,0) is the triplet
and (0,1) the antitriplet; for SU(5), (1,0,0,0) is the 5 and (0,0,0,1) the
5bar.

Normalisation: Tr[T^a T^b] = T(R) delta^ab with T(fundamental) = 1/2, and the
quadratic Casimir is defined by sum_a T^a T^a = C2(R) 1 with the same
generators.

## Representations

| name | group | Dynkin labels |
|---|---|---|
""" + "".join("| %s | %s | %s |\n" % row for row in REPRESENTATIONS) + """
## Tensor products to decompose into irreducible representations

| name | group | product |
|---|---|---|
""" + "".join("| %s | %s | %s x %s |\n" % row for row in PRODUCTS))
print("wrote reps.md")
