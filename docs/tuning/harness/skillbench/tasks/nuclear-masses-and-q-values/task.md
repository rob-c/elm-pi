---
skill: nuclear-masses-and-q-values
also: nuclear-data-lookup, physical-constants
category: nuclear
pitfall: the 2 m_e c^2 left out of the beta-plus endpoint; Q taken as the alpha's kinetic energy; the non-relativistic threshold, 45 keV low at 23 MeV
timeout_sec: 900
---
mass_excess.csv has the atomic mass excesses I pulled from the mass evaluation and notes.md the constants. I need, in keV: for Cu-64 the Q-value of the beta-minus decay, the endpoint energy of the beta-plus spectrum and the neutrino energy in K capture, all to the ground states; for Gd-148 the alpha-decay Q-value and the kinetic energy of the alpha; and the threshold proton energy in the lab for 4He(p,d)3He on helium at rest. Write them to result.json as q_beta_minus_kev, beta_plus_endpoint_kev, k_capture_neutrino_kev, q_alpha_kev, alpha_energy_kev and threshold_kev.
