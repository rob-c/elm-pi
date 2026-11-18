---
skill: hep-kinematics
also: physical-constants
category: particle
pitfall: track momenta in MeV added to cluster energies in GeV; pseudorapidity given for a massive system; sqrt(s) of a fixed-target collision from a collider formula or from the kinetic energy
timeout_sec: 900
---
notes.md describes one exclusive pp -> pp pi+ pi- pi0 candidate from our fixed-target run; tracks.csv has its charged tracks and clusters.csv the two photons from the pi0. I need the invariant mass of the pi+ pi- gamma gamma system, that system's rapidity in the laboratory frame, and the centre-of-mass energy of the collision. Write result.json with mass_gev, rapidity and sqrt_s_gev.
