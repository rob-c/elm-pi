---
skill: nuclear-data-lookup
also: gamma-spectroscopy, uncertainty-propagation
category: nuclear
pitfall: relative gamma intensities taken as photons per 100 decays, without the data set's NR and BR; the ground state's half-life or data set read for the isomer's; "249.83 D 4" and "1.28 +5-3" misread
timeout_sec: 900
---
ag110_ensdf.txt is the excerpt of the ENSDF evaluation I pulled for our Ag-110m source. From it I need the isomer's half-life in seconds, the number of 884.68 keV photons and of 1562.29 keV photons per decay of the isomer, each of the three with its uncertainty as the evaluation gives it (upper and lower for the 1562 keV line), and the photon energy emitted per decay of the isomer, in keV, summed over the lines listed for its beta decay. Write result.json with half_life_s, half_life_unc_s, p_885, p_885_unc, p_1562, p_1562_unc_plus, p_1562_unc_minus and gamma_energy_per_decay_kev.
