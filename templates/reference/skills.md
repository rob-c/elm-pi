# Every skill here, and how one reaches a session

A skill is a checked procedure: `@AGENT_DIR@/skills/<name>/SKILL.md`. A request
gets the ones it matches as a "Skills for this request" message after it - up
to two general skills and one topic skill in full, others by name and path.
That match is by keyword, and it misses: when the work is covered by a skill
below that was not sent, read it first. One read per session is enough.

## General

pi lists these in every session's system prompt.

- `changing-code` - Fixing a bug, making failing tests pass, adding a function or writing code from a written spec - find the cause, then try to break your own change before reporting it.
- `containers` - Run software the machine lacks (TeX Live, pandoc, toolchains) in Docker or Podman, offline, with --network=none. Use when a tool is missing and pip cannot supply it.
- `data-fitting` - Fitting a model to measured data and reporting it properly - least squares or likelihood, weights and Poisson counts, chi2/ndf, residuals, parameter uncertainties.
- `derivation-checks` - Checking an analytic derivation before trusting it - dimensions, natural units, limiting cases, symmetries, numerical spot checks, sympy.
- `developing-elm-pi` - Add a plugin (extension) to elm-pi, or change elm-pi itself: work in a clone, set it up with scripts/dev-setup.sh, scaffold with scripts/new-extension, prove it with scripts/check-extension.
- `elm-delegation` - Delegating to sub-agents here - when to fan out, qwen or llama, writing a child's prompt, budgets, checking its work. Read before the first subagent call.
- `elm-dynamic-workflows` - The `workflow` tool (offered unless pi --no-workflows) - when to use it, checking a script with workflow-check, getting results back. Read before any workflow call.
- `elm-subagent-workflows` - Fanning out several qwen/llama children - the built-in parallel workflow, or a validated runs.all script when steps depend on each other - and collecting the results.
- `histogram-analysis` - Histograms and event selections - binning, per-bin Poisson errors, normalisation, weighted events, background subtraction, cut flows.
- `installing-software` - When something the task needs is not installed - search the package indexes, install the isolated way (pip, pixi, containers), Homebrew with approval, apt/dnf for the user, and report what went where.
- `numerical-methods` - Numerically trustworthy results - floating point, ODE/PDE integration and stiffness, quadrature, root finding, conditioning, convergence checks.
- `package-admin` - Setting up a service or a cluster there is no recipe for here - a scheduler, a database, several that talk to each other: research each step in its documentation, do it, check it, search the exact error when it fails.
- `physical-constants` - Getting a physical constant, particle mass, lifetime, branching ratio or coupling right, with its source. Use whenever a reference value enters a result.
- `physics-documents` - Slides, notes, reports and papers in LaTeX/Beamer or Markdown - outline and notation first, consistent symbols, siunitx, figures, honest references, compiling to check.
- `scientific-cpp` - C++ for numerical physics - compiler flags and warnings, sanitizers, floating-point pitfalls, reproducible builds, testing.
- `scientific-python` - Scientific Python - which environment, numpy/scipy/pandas idioms, plots, notebooks and the python tool, reproducible scripts, reading ROOT/HDF5/CSV.
- `statistics-and-significance` - Statistical inference for physics results - p-values and significance, confidence intervals and upper limits, efficiencies, the look-elsewhere effect.
- `uncertainty-propagation` - Propagating and quoting uncertainties - linear propagation with covariance, correlated inputs, Monte Carlo propagation, combining measurements, significant figures.

## Experimental particle physics

Not listed by pi: sent when a request matches, or read from here.

- `hep-background-estimation` - Estimating backgrounds in a collider analysis - simulation normalised in control regions, transfer factors, ABCD, fake-factor and matrix methods, sideband and template fits, closure and validation.
- `hep-columnar-analysis` - Array-at-a-time HEP analysis with uproot, awkward, vector, hist and coffea - jagged arrays, event and object masks, combinatorics, flattening, None, chunks, weights.
- `hep-cross-section-measurement` - Measuring a cross section - yield, background, efficiency, acceptance and luminosity; fiducial versus total, differential bins, pile-up reweighting, units, and comparison with theory.
- `hep-data-formats` - Particle-physics data formats and open data - ROOT TTree and RNTuple, NanoAOD, PHYSLITE, HepMC, LHE, YODA, HEPData, Parquet; good-run lists, XRootD, sample metadata, MeV versus GeV.
- `hep-detector-performance` - Tracking and calorimeter performance - momentum from curvature, sagitta, multiple scattering, impact parameter, alignment; energy-resolution terms, shower scales, calibration; fitted resolutions.
- `hep-detector-simulation` - Detector simulation - Geant4 geometry, materials, physics lists, production cuts and scoring, digitisation, validation against data, and fast simulation with Delphes and where it stops being valid.
- `hep-efficiency-measurement` - Measuring efficiencies - binomial intervals (Clopper-Pearson), weighted events, tag-and-probe, trigger turn-on curves, data-to-simulation scale factors, efficiency maps, TEfficiency.
- `hep-event-generators` - Monte Carlo event generation - matrix element plus parton shower, LHE and HepMC, matching and merging, weights and negative weights, sample normalisation, scale and PDF variations, seeds, Rivet validation.
- `hep-event-selection` - Selecting collision events - data quality, trigger and its plateau, object definitions, overlap removal, cut flows, signal, control and validation regions, blinding, unbiased optimisation.
- `hep-flavour-and-cp` - Flavour physics and CP-violation measurements - CKM, neutral-meson mixing, time-dependent asymmetries, flavour tagging, decay-time resolution and acceptance, Dalitz and angular analyses, normalisation channels.
- `hep-jets` - Jets - anti-kT and sequential recombination, IRC safety, FastJet, pile-up mitigation, energy scale and resolution, b-tagging working points and scale factors, substructure, truth matching, overlaps.
- `hep-kinematics` - Relativistic kinematics for collider and fixed-target work - units, four-vectors, invariant and transverse mass, rapidity and pseudorapidity, boosts, centre-of-mass energy, thresholds, two-body decays, PDG codes.
- `hep-likelihood-limits` - Binned likelihood models for searches and measurements (HistFactory, pyhf, Combine) - nuisance parameters, profile-likelihood tests, CLs limits, expected bands, Asimov data, pulls and impacts.
- `hep-literature-and-data` - Finding and citing particle-physics sources - INSPIRE-HEP, arXiv, HEPData, the PDG and CDS: searches, APIs, BibTeX keys; never a recalled reference; record the query and the date.
- `hep-ml-classifiers` - Signal-versus-background classifiers in particle physics - splitting by event, BDT or network, weights, overtraining, working points, k-fold, systematics through the classifier, mass sculpting.
- `hep-particle-identification` - Charged-particle identification - dE/dx, time of flight, Cherenkov angle, transition radiation, E/p and muon systems; combined likelihoods; efficiency and misidentification from data control samples.
- `hep-reinterpretation` - Reinterpreting published collider results for another model - HEPData, full likelihoods, simplified models, Rivet, MadAnalysis 5, CheckMATE, SModelS, Contur; validating against the published limit.
- `hep-roofit-models` - RooFit and RooStats models - workspaces, normalisation ranges, extended and weighted likelihood fits, fit status and covariance quality, sPlot, toy studies, zfit in Python.
- `hep-root` - CERN ROOT 6 - macros under Cling and ACLiC, TFile/TTree/TChain, RDataFrame and implicit multithreading, histogram ownership and Sumw2, batch mode, PyROOT or uproot.
- `hep-systematics` - Systematic uncertainties in a collider analysis - the inventory, plus and minus one sigma templates, shape against normalisation, correlations, one-sided and two-point variations, smoothing, pruning, the breakdown.
- `hep-unfolding` - Unfolding detector-level distributions to particle level - response matrix, fakes and misses, purity and stability, regularised methods and their strength, closure and stress tests, covariance.
- `neutrino-oscillations` - Neutrino oscillation calculations and analyses - two- and three-flavour probabilities, PMNS, mass ordering, matter effects, event rates, near/far ratios, systematics, sensitivities.
- `rare-event-searches` - Searches with few or no events - Poisson limits, Feldman-Cousins, CLs and Bayesian intervals, on/off counting, exposure, blinding, dark-matter and double-beta sensitivities, look-elsewhere.

## Theoretical particle physics

- `bsm-model-tools` - New-physics models through the tool chain - FeynRules or SARAH to UFO, spectrum generators and SLHA files, MadGraph, micrOMEGAs, HiggsTools, SModelS; model consistency checks and honest parameter scans.
- `effective-field-theory` - Effective field theories and SMEFT - power counting, operator bases and redundancies, matching and running of Wilson coefficients, input schemes, linear versus quadratic terms, validity, and the tools.
- `group-theory-for-physics` - Lie groups and representations for model building - dimensions, Casimirs and Dynkin indices, tensor products, branching rules, anomaly coefficients, hypercharge conventions, Clebsch-Gordan and Wigner symbols.
- `lattice-qcd-analysis` - Analysing lattice QCD data - correlators and effective masses, correlated fits with a sampled covariance, jackknife and bootstrap, autocorrelation, scale setting, continuum, chiral and finite-volume extrapolations.
- `particle-cosmology` - Early-universe particle physics - natural-unit conversions, expansion rate and entropy, g*, freeze-out and the Boltzmann equation, relic abundance, N_eff and BBN, baryogenesis conditions, and the standard tools.
- `qcd-parton-distributions` - Parton distributions in a hadron-collider prediction - LHAPDF, matching the set's order and alpha_s to the calculation, Hessian and replica uncertainties, scales, flavour schemes, luminosities, sum-rule checks.
- `qft-amplitudes` - Tree-level amplitudes and squared matrix elements by hand - conventions, Feynman rules, spin and polarisation sums, traces, colour factors, crossing, and the checks that catch a wrong sign.
- `qft-computer-algebra` - Feynman-diagram calculations by program - FORM, FeynCalc, FeynArts and FormCalc, FeynRules, QGRAF, LoopTools, SymPy: which tool, the conventions each uses, and reporting only what a run produced.
- `qft-loop-integrals` - Loop integrals in dimensional regularisation - conventions and MS-bar, Feynman parameters, Passarino-Veltman and IBP reduction, UV versus infrared poles, thresholds, numerical libraries, and the checks.
- `qft-phase-space` - From a squared matrix element to a decay rate or cross section - Lorentz-invariant phase space, two- and three-body formulae, flux and symmetry factors, Monte Carlo integration, GeV to barn conversion.
- `qft-renormalisation-group` - Running couplings and masses - beta-function conventions, flavour thresholds and matching, pole versus MS-bar masses, scale variation, RGEs for general models, and checks against looked-up values.
- `tensor-calculus-and-gr` - Tensor calculus and general relativity - sign conventions, Christoffel symbols, curvature, geodesics, Einstein's equations, standard metrics, gauge choices in perturbation theory, symbolic tools and their checks.

## Nuclear physics

- `dosimetry-and-shielding` - Radiation dose and shielding estimates - absorbed, equivalent and effective dose, Gy and Sv, point-source dose rates, attenuation with build-up, half-value layers, betas and neutrons; estimates, not assessments.
- `gamma-spectroscopy` - Gamma-ray spectra from HPGe, NaI or LaBr detectors - energy and efficiency calibration, net peak areas, dead time, summing, activities and detection limits.
- `heavy-ion-collisions` - Relativistic heavy-ion collision analysis - collision energy per nucleon pair, centrality and Glauber, rapidity, nuclear modification factor, anisotropic flow, statistical hadronisation, hydro and transport codes.
- `neutron-activation-and-transport` - Neutron work by hand - thermal and resonance cross sections, the activation equation, self-shielding, moderation, mean free path, time of flight, neutron detection and shielding; the flux conventions.
- `nuclear-astrophysics` - Thermonuclear reaction rates - S-factor and Gamow peak, non-resonant and narrow-resonance rates, units, reverse rates, REACLIB and STARLIB, reaction networks, the s, r and p processes.
- `nuclear-data-lookup` - Getting a half-life, level, gamma line, mass, cross section or attenuation coefficient from an evaluated nuclear database, with its source - NNDC, IAEA LiveChart, AME, ENDF, EXFOR, NIST.
- `nuclear-masses-and-q-values` - Nuclear binding energies, separation energies, Q-values and reaction thresholds from atomic masses - mass excess, beta-plus and electron capture, alpha decay, keeping the electrons counted.
- `nuclear-reaction-codes` - Nuclear reaction model codes - TALYS and EMPIRE (Hauser-Feshbach, pre-equilibrium), FRESCO and DWBA, optical potentials, fusion-evaporation; which model choices are the uncertainty, and comparing with EXFOR.
- `nuclear-reaction-kinematics` - Two-body nuclear reaction kinematics and yields - lab and centre-of-mass frames, inverse kinematics, thresholds, Coulomb barrier, Rutherford scattering, beam current and target thickness to counts.
- `nuclear-structure-models` - Nuclear structure calculations - shell model (model space, interaction, truncation; KSHELL, NuShellX, BIGSTICK), B(E2) and Weisskopf units, collective signatures, mean field and DFT, ab initio convergence.
- `radiation-detectors-and-daq` - Radiation detectors and their data acquisition - what limits energy and time resolution, pulse-shape discrimination, dead time, pile-up, accidental coincidences, list-mode data, digitisers, efficiencies.
- `radiation-transport-monte-carlo` - Monte Carlo radiation transport with Geant4, FLUKA, MCNP, PHITS or OpenMC - geometry, materials, source, physics and data libraries, cuts, tallies and their normalisation, statistics, variance reduction.
- `radioactive-decay-chains` - Radioactive decay and decay chains - activity and specific activity, Bateman equations done stably, secular and transient equilibrium, branching, production by irradiation, radiocarbon conventions.
- `scattering-theory-and-partial-waves` - Quantum scattering calculations - partial waves and phase shifts, cross sections, optical theorem, effective range and scattering length conventions, Breit-Wigner resonances, solving the radial equation, R-matrix.
- `stopping-power-and-range` - Energy loss of charged particles in matter - Bethe formula and its scaling, units, ranges and the Bragg peak, straggling and Landau tails, electrons, SRIM and NIST tables, loss in targets and windows.

## Batch systems on a cluster

- `batch-grid-engine` - Grid Engine jobs (SGE, Son of Grid Engine, Univa and Altair Grid Engine) - qsub scripts, parallel environments, per-slot memory, array jobs, and qstat and qacct to see what happened.
- `batch-htcondor` - HTCondor jobs - submit description files, queue statements for many jobs, file transfer and the scratch directory, resource requests, held jobs, and condor_q and condor_history to see what happened.
- `batch-jobs` - Running work on a university cluster's batch system - which scheduler it is, a job script, resource requests, job arrays, scratch, checkpoints, and reading what a finished job used.
- `batch-lsf` - IBM Spectrum LSF jobs - bsub scripts read from standard input, slots and span, memory reservation versus limit, job arrays, and bjobs, bhist and bacct to see what happened.
- `batch-pbs` - PBS jobs (PBS Professional, OpenPBS, Torque with or without Moab) - qsub scripts, select and ncpus versus nodes and ppn, walltime, array jobs, and qstat and tracejob to see what happened.
- `batch-slurm` - Slurm jobs - sbatch scripts, tasks versus cpus-per-task, memory per node or per CPU, GPUs, job arrays with a throttle, dependencies, and squeue, sacct and seff to see what happened.

## The K-Dense library

`@AGENT_DIR@/skills/kdense/<name>/SKILL.md` holds 167 community skills for
scientific Python packages (astropy, sympy, scikit-learn, pymc, polars, ...),
databases and research methods; `@AGENT_DIR@/skills/kdense/INDEX.md` lists
them. The folder is not there when the install left the library out. Each
topic skill above ends with the library skills that go with it, and a request
that names a package gets its skill's path. Read one when you are about to use
a tool you do not know well - they are long, so read the one you need.

They were written for other agents. Where a library skill says to install
software, to set an API key or to call another AI service, this install's
rules decide, not the skill: installs go the `installing-software` way, and
the only model service here is ELM.
