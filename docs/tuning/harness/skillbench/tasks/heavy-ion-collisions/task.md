---
skill: heavy-ion-collisions
also: uncertainty-propagation, hep-kinematics
category: nuclear
pitfall: v2 from an event plane with no resolution correction, or with each track left in its own plane's Q-vector; sqrt(s_NN) of a fixed-target run from the kinetic energy taken as the total beam energy
timeout_sec: 900
---
events.txt has the azimuths of the selected tracks, one event per line, from the fixed-target Au+Au run described in notes.md. I need the elliptic flow v2 of these tracks with its statistical uncertainty, and √s_NN for this beam. Write result.json with v2, v2_stat and sqrt_snn_gev.
