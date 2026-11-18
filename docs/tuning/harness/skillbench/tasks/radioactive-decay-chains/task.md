---
skill: radioactive-decay-chains
also: nuclear-data-lookup, numerical-methods
category: nuclear
pitfall: Mo-99 taken to feed Tc-99m in every decay (the 87.6% branch ignored), so the Tc-99m activity is 14% high and the Tc-99 count 6% low; atoms made as rate times time, with no decay during the irradiation
timeout_sec: 900
---
notes.md has the irradiation log and the decay data for this week's Mo-99 batch. I need the Mo-99 activity at the end of irradiation and when the generator column was loaded, how long after loading the Tc-99m activity on the column peaks and what it is then, and how many Tc-99 ground-state atoms are on the column at that moment. Put them in result.json as a_mo99_eob_bq, a_mo99_load_bq, t_max_h, a_tc99m_max_bq and n_tc99_atoms.
