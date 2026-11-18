---
skill: hep-jets
also: hep-kinematics
category: particle
pitfall: pseudorapidity used where rapidity belongs, in the clustering distance and for the massive jet; the kT measure for anti-kT; neutrinos left among the inputs
timeout_sec: 1200
---
event.csv has the stable particles of one simulated pp event (PDG code and px, py, pz, E in GeV), and notes.md has our particle-level jet definition, anti-kT with R = 0.4. FastJet is not installed on this machine, so cluster them directly, and tell me how many jets pass the pT cut and the pT, rapidity and mass of the leading jet. Write result.json with n_jets, lead_pt_gev, lead_rapidity and lead_mass_gev.
