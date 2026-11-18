---
name: qft-amplitudes
description: "Tree-level amplitudes and squared matrix elements by hand - conventions, Feynman rules, spin and polarisation sums, traces, colour factors, crossing, and the checks that catch a wrong sign."
disable-model-invocation: true
---

# Amplitudes and squared matrix elements

A wrong amplitude is nearly always a sign, a factor of 2 or i, or two
conventions mixed: one book's Feynman rules with another's metric, an average
over the wrong number of initial states, a polarisation sum used where it does
not hold. Fix the conventions first and write them at the top of the work.

## Conventions to state before the first diagram

- **Metric**: (+,-,-,-), so p² = m² (most collider literature), or (-,+,+,+),
  so p² = -m². Everything below is for (+,-,-,-).
- **γ5 and ε**: with γ5 = iγ⁰γ¹γ²γ³, Tr[γ⁰γ¹γ²γ³γ5] = -4i. So
  Tr[γ^μγ^νγ^ργ^σγ5] is -4i ε^{μνρσ} if ε^{0123} = +1 and +4i ε^{μνρσ} if
  ε^{0123} = -1. Books and programs differ: say which, and never copy a γ5
  trace from a source without checking its ε.
- **Spinors**: ū u = 2m, with Σ u ū = p̸ + m and Σ v v̄ = p̸ - m. The other
  common choice (ū u = 1) changes rates by factors of 2m.
- **Covariant derivative**: ∂ + igA or ∂ - igA flips the sign of every vertex
  odd in g. Harmless inside one set of rules, wrong when two sources are mixed.

## From Lagrangian to amplitude

1. Vertex = i × (the term in the interaction Lagrangian with the fields
   stripped) × n! for n identical fields; a derivative acting on a field with
   incoming momentum p gives -i p_μ.
2. Draw every diagram at the order wanted and count them against a reference
   or a diagram generator (`qft-computer-algebra`).
3. Signs: (-1) for each closed fermion loop, and a relative (-1) between
   diagrams that differ by exchanging two identical external fermions.
4. Square, sum over final states and average over initial ones: 1/2 for a
   fermion's spin, 1/3 for a quark's colour, 1/8 for a gluon's, 1/2 for the
   polarisations of a massless vector (1/(d-2) in d dimensions), 1/3 for a
   massive one. The 1/n! for n identical final particles belongs to the
   phase-space integral (`qft-phase-space`).

## Sums and traces

- Massive vector: Σ ε_μ ε*_ν = -g_μν + k_μ k_ν / m².
- Massless vector: Σ ε_μ ε*_ν → -g_μν only where the amplitude obeys the Ward
  identity for that leg. True for photons; with two or more external gluons it
  lets unphysical polarisations in. Then use the physical sum
  -g_μν + (k_μ n_ν + k_ν n_μ)/(k·n) with n² = 0, or add the ghost diagrams.
- Traces: Tr[1] = 4; an odd number of γ gives 0; Tr[γ^μγ^ν] = 4 g^{μν};
  Tr[γ^μγ^νγ^ργ^σ] = 4 (g^{μν}g^{ρσ} - g^{μρ}g^{νσ} + g^{μσ}g^{νρ});
  γ^μγ_μ = 4 and γ^μγ^νγ_μ = -2γ^ν in four dimensions (d and -(d-2)γ^ν in d).
- Colour, SU(3) with T^a = λ^a/2: Tr[T^a T^b] = TR δ^{ab} with TR = 1/2,
  CF = 4/3, CA = 3, and T^a_{ij} T^a_{kl} = (δ_il δ_kj - δ_ij δ_kl / 3) / 2.
- Crossing a fermion between the initial and the final state: p → -p and an
  overall (-1) in the spin-summed square.
- Massless legs: spinor-helicity variables give compact results, but the sign
  of [ij] differs between the QCD literature (⟨ij⟩[ji] = s_ij) and the twistor
  literature. State which.

## Numbers at given momenta

Compute, never recall. Build it in numpy: 4×4 γ matrices, explicit u and v,
the two transverse ε of each gluon, T^a = λ^a/2 and f^{abc}. Sum |M|² over
every index and divide by the initial states (gg: 256). Run the gauge check
(ε → k gives 0) before reporting. A remembered closed form is only a
cross-check; two that disagree prove nothing.

## Check before reporting

- Conventions listed, and every Feynman rule taken from one source.
- Gauge check: replace one external polarisation vector by its momentum. The
  amplitude must vanish when the other vector legs are physical.
- Mass dimension: an n-point amplitude in four dimensions has dimension 4 - n.
- A known case with the same rules first: for e⁺e⁻ → μ⁺μ⁻ with massless
  fermions the spin-averaged square is 2e⁴ (t² + u²)/s².
- Symmetry under exchange of identical particles; sensible massless and
  high-energy limits (no growth that violates unitarity).
- A number: the result at one phase-space point against a generator's matrix
  element (`hep-event-generators`), and a symbolic spot check per
  `derivation-checks`.

## Related

- Skills here: `derivation-checks`, `qft-computer-algebra`, `qft-phase-space`,
  `qft-loop-integrals`, `group-theory-for-physics`, `hep-event-generators`,
  `hep-literature-and-data`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `sympy`, `paper-lookup`.
