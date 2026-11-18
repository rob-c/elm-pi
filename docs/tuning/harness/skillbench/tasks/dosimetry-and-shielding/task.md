---
skill: dosimetry-and-shielding
also: radioactive-decay-chains
category: nuclear
pitfall: narrow-beam exp(-mu x) for a concrete wall with no build-up factor, also when solving for the thickness; certificate activity in Ci not decayed to the date; emission probability or the tissue coefficient left out
timeout_sec: 900
---
notes.md describes the Cs-137 source in the store, the concrete wall and the desk behind it, with the handbook data. For a planning estimate I need the absorbed dose rate in soft tissue at the desk as it would be with no wall, the dose rate there behind the wall as built, and how thick the wall would have to be to bring it down to 2.0 µGy/h. Write result.json with unshielded_ugy_per_h, shielded_ugy_per_h and thickness_cm.
