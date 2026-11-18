---
skill: physical-constants
also: scientific-python
category: reference-data
pitfall: constants typed in from memory to three or four figures (m_n, e, h, 60.3 neV/T) where six are asked for; standard g and a PDG lifetime used although the project's constants.py holds the hall's g and the lifetime the analysis adopted
timeout_sec: 900
---
trap.md describes our UCN storage bottle and the reference numbers the analysis note needs for it: the critical velocity, the de Broglie wavelength at that velocity, the height such a neutron can rise to, the magnetic field that matches the wall potential, and the fraction surviving beta decay over the holding time. I need them to six significant figures, because the simulation is checked against this table. Put them in result.json as v_crit_m_s, wavelength_nm, h_max_m, b_reflect_t and survival_fraction, with a sources entry that says where each constant you used came from.
