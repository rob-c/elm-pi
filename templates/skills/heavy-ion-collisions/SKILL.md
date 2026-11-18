---
name: heavy-ion-collisions
description: "Relativistic heavy-ion collision analysis - collision energy per nucleon pair, centrality and Glauber, rapidity, nuclear modification factor, anisotropic flow, statistical hadronisation, hydro and transport codes."
disable-model-invocation: true
---

# Heavy-ion collisions

The mistakes: pseudorapidity and rapidity swapped for massive particles; a
nuclear modification factor built from mismatched pieces (binary-collision
number, pp reference at another energy or acceptance); v2 from an event plane
with no resolution correction, or with non-flow left in; and centrality
classes defined differently from the data being compared with.

## Energies and kinematics

- √s_NN is the centre-of-mass energy per nucleon pair. Collider, equal
  beams: twice the beam energy per nucleon. At fixed magnetic rigidity,
  symmetric nuclei reach (Z/A) × the pp value; p-A reaches √(Z/A) × the pp
  value, with the centre of mass shifted by ½ ln(Z1 A2 / (Z2 A1)) in
  rapidity (0.465 for p-Pb).
- Fixed target: √s_NN = √(2 m_N² + 2 m_N E_lab), E_lab the total beam energy
  per nucleon; state the nucleon mass used.
- Rapidity y = ½ ln((E + p_z)/(E - p_z)); pseudorapidity η = -ln tan(θ/2).
  They agree only for p_T far above the mass: dN/dη is below dN/dy at
  mid-rapidity, by the factor p_T/m_T there. m_T = √(m² + p_T²); invariant
  yield (1/(2π p_T)) d²N/(dp_T dy).

## Centrality and the Glauber model

- Centrality is a percentile of the hadronic cross section, cut on
  multiplicity or forward energy: 0-5% is the most central.
- Glauber (Monte Carlo, or optical): inputs are the nuclear density
  (Woods-Saxon radius and diffuseness, deformation where there is any), the
  inelastic nucleon-nucleon cross section at that energy (looked up), and a
  minimum nucleon separation. Outputs per class: participants N_part, binary
  collisions N_coll, the overlap function T(AA) = N_coll / σ(NN, inelastic),
  eccentricities. Tools: TGlauberMC, TRENTo.
- Comparing with an experiment, use its published Glauber values and carry
  their uncertainties. Soft yields go roughly with N_part, hard processes
  with N_coll.

## Observables

- **Nuclear modification factor**: R(AA) = (dN/dp_T in A-A) /
  (⟨T(AA)⟩ × dσ/dp_T in pp) = (yield in A-A) / (⟨N_coll⟩ × yield in pp), at
  the same √s_NN, rapidity window and particle. Say if the pp reference is
  interpolated. The T(AA) and luminosity uncertainties move all p_T points
  together: show them apart from the point-to-point errors.
- **Anisotropic flow**: dN/dφ ∝ 1 + 2 Σ v_n cos n(φ - Ψ_n).
  Event plane: v_n = ⟨cos n(φ - Ψ_n)⟩ / R_n, the resolution R_n from
  sub-event correlations (two equal sub-events: √⟨cos n(Ψa - Ψb)⟩ is the
  sub-event resolution). Take the particle out of its own plane's Q-vector,
  and flatten the plane distribution. The scalar-product method is better
  defined than the event plane.
  Cumulants: v_n{2} includes non-flow (jets, decays) and adds fluctuations;
  v_n{4} = (2⟨⟨2⟩⟩² - ⟨⟨4⟩⟩)^(1/4) suppresses non-flow and subtracts
  fluctuations, so v_n{2} > v_n{4}. A pseudorapidity gap reduces non-flow in
  two-particle methods. Name the method with every v_n.
- Femtoscopy: two-particle correlations at small relative momentum give the
  source radii.
- **Statistical hadronisation**: yields fitted with a temperature, a
  baryochemical potential and a volume (Thermal-FIST, THERMUS). Feed-down
  from resonance and weak decays must match the data's definition; small
  systems need canonical strangeness.

## Models

Initial state (Glauber, TRENTo, IP-Glasma), viscous hydrodynamics (MUSIC,
VISHNU) with an equation of state from lattice QCD, particlisation, then a
hadronic afterburner (UrQMD, SMASH). Event generators and transport: AMPT,
HIJING, EPOS, PHSD; jets in a medium: JEWEL, JETSCAPE. A model is compared
with data only under the data's centrality definition, cuts and feed-down.
Bayesian parameter estimation uses a Gaussian-process emulator and MCMC with
the experimental covariance: report closure tests and emulator validation.

## Check before reporting

- Energy per nucleon pair, system, centrality definition and its source.
- y or η stated; p_T range; particle species; feed-down treatment.
- R(AA): reference, normalisation uncertainty shown separately.
- Flow: method, resolution, gap, and a non-flow estimate.
- Statistical and systematic errors separate (`uncertainty-propagation`).

## Related

- Skills here: `hep-kinematics`, `hep-event-generators`,
  `hep-columnar-analysis`, `histogram-analysis`, `lattice-qcd-analysis`,
  `statistics-and-significance`, `uncertainty-propagation`.
- K-Dense library (read `@AGENT_DIR@/skills/kdense/<name>/SKILL.md` when you use
  the tool; absent if the library was left out of this install):
  `pymc`, `scikit-learn`, `matplotlib`.
