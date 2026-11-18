---
name: group-theory-for-physics
description: "Lie groups and representations for model building - dimensions, Casimirs and Dynkin indices, tensor products, branching rules, anomaly coefficients, hypercharge conventions, Clebsch-Gordan and Wigner symbols."
disable-model-invocation: true
---

# Group theory for particle physics

Most errors here are normalisations and names: an index quoted with
T(fundamental) = 1 beside one with 1/2, hypercharge as Y in one line and Y/2
in the next, a representation named by a dimension that two representations
share, or a conjugate dropped in a product. State the normalisation, then
check by counting.

## Normalisation used below

Tr[T^a T^b] = T(R) δ^{ab} with T(fundamental) = 1/2; T^a T^a = C2(R) on R.
They are tied by T(R) dim(G) = C2(R) dim(R).

| SU(N) representation | dimension | T(R) | C2(R) |
|---|---|---|---|
| fundamental | N | 1/2 | (N² - 1)/(2N) |
| adjoint | N² - 1 | N | N |
| symmetric, two indices | N(N+1)/2 | (N+2)/2 | (N-1)(N+2)/N |
| antisymmetric, two indices | N(N-1)/2 | (N-2)/2 | (N+1)(N-2)/N |

- SU(2), spin j: dimension 2j+1, C2 = j(j+1), T = j(j+1)(2j+1)/3.
- SU(3), Dynkin labels (p, q): dimension (p+1)(q+1)(p+q+2)/2 and
  C2 = (p² + q² + pq + 3p + 3q)/3. The conjugate swaps p and q.
- Name a representation by its Dynkin labels when the dimension is ambiguous
  (SU(3) has two of dimension 15), and always mark conjugates.

## Products and branching

- SU(3): 3 ⊗ 3bar = 1 ⊕ 8; 3 ⊗ 3 = 6 ⊕ 3bar; 3 ⊗ 8 = 3 ⊕ 6bar ⊕ 15;
  3 ⊗ 3 ⊗ 3 = 1 ⊕ 8 ⊕ 8 ⊕ 10; 8 ⊗ 8 = 1 ⊕ 8 ⊕ 8 ⊕ 10 ⊕ 10bar ⊕ 27.
- SU(2): j1 ⊗ j2 = |j1 - j2| ⊕ ... ⊕ (j1 + j2).
- SU(5) to SU(3) × SU(2) × U(1), with Q = T3 + Y:
  5bar = (3bar, 1, 1/3) ⊕ (1, 2, -1/2);
  10 = (3, 2, 1/6) ⊕ (3bar, 1, -2/3) ⊕ (1, 1, 1);
  24 = (8, 1, 0) ⊕ (1, 3, 0) ⊕ (1, 1, 0) ⊕ (3, 2, -5/6) ⊕ (3bar, 2, 5/6).
  SO(10): 16 = 10 ⊕ 5bar ⊕ 1 of SU(5).
- Compute the product (Littlewood-Richardson, or weights); never pick
  irreps to make sums come out. Checks: dimensions add up; indices add up,
  T(R1) dim(R2) + dim(R1) T(R2) = Σ T(R_i); and N-ality, Σ k a_k mod N, is
  the factors' sum for every irrep. Only the last tells R from Rbar: SU(4)
  4 ⊗ 15 has the 20 (0,1,1), not (1,1,0).

## Hypercharge

Q = T3 + Y (left-handed quark doublet Y = 1/6) or Q = T3 + Y/2 (then 1/3):
say which, once. In a unified normalisation the U(1) coupling is
g1 = √(5/3) g', which gives sin²θ_W = 3/8 at the unification scale.

## Anomalies

- Cubic coefficient A(R): A(fundamental) = 1, A(conjugate) = -A(R), zero for
  real and pseudoreal representations. SU(N): antisymmetric two-index N - 4,
  symmetric N + 4. Check: in SU(5), 5bar and 10 give -1 + 1 = 0.
- SU(2) has no cubic anomaly, but the number of Weyl doublets must be even.
- With a U(1), over left-handed Weyl fermions with their multiplicities:
  Σ Y³ = 0, Σ Y = 0 (gravitational), Σ Y over colour triplets = 0 and
  Σ Y over SU(2) doublets = 0. One Standard Model generation satisfies all
  four: verify a new charge assignment the same way, in exact fractions.

## Clebsch-Gordan and Wigner symbols

- SymPy: `sympy.physics.quantum.cg.CG(j1, m1, j2, m2, j, m).doit()`, and
  `sympy.physics.wigner` for 3j, 6j, 9j symbols and Gaunt coefficients. Pass
  half-integers as `sympy.Rational(1, 2)`, not 0.5.
- Convention: Condon-Shortley phases, and
  ⟨j1 m1 j2 m2 | J M⟩ = (-1)^{j1-j2+M} √(2J+1) × the 3j symbol with (m1, m2, -M).
- Check a table by orthonormality, Σ over m1, m2 of the product of two
  coefficients = δ δ.

## Tools

LieART and GroupMath (Mathematica) for products, branching rules and
invariants; LiE (standalone); SageMath's WeylCharacterRing for characters and
branching; `sympy.liealgebras` only for roots, Cartan matrices and Weyl
groups. Slansky's tables and Yamatsu's review are the references to check
against (`hep-literature-and-data`). Tool output is reported only from a run.

## Check before reporting

- Normalisation of T(R) and of hypercharge stated.
- Dimensions and indices add up in every product and branching.
- Conjugates explicit; ambiguous dimensions given with Dynkin labels.
- Anomaly sums done in exact arithmetic.
- One line of each result compared with a published table.

## Related

- Skills here: `derivation-checks`, `qft-amplitudes`,
  `qft-renormalisation-group`, `bsm-model-tools`, `effective-field-theory`,
  `hep-literature-and-data`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `paper-lookup`.
