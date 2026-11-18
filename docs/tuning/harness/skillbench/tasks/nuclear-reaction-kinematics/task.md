---
skill: nuclear-reaction-kinematics
also: nuclear-masses-and-q-values, hep-kinematics
category: nuclear
pitfall: one neutron energy given where inverse kinematics has two; the centre-of-mass cross section used in the lab with no Jacobian (a factor 15 and a factor 4 here); beam particles from the electrical current without the 3+ charge state; hydrogen atoms per cm2 not worked out from the foil's ug/cm2 of CH2 (two per formula unit)
timeout_sec: 900
---
notes.md describes tomorrow's run: a 7Li beam on a polyethylene foil with the neutron detector at 10 degrees in the lab. For p(7Li,n)7Be give me the centre-of-mass kinetic energy in the entrance channel, the lab kinetic energy of the neutrons that reach the detector, and the rate of neutrons from this reaction entering the detector. Write result.json with e_cm_mev, neutron_energies_mev (a list, in MeV) and rate_per_s.
