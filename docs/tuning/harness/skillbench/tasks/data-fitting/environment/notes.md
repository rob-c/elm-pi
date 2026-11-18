# Run 14 - short-lived activity in the irradiated foil

- Foil out of the neutron source at 14:02:10, on counter 3 (end-window GM tube)
  at 14:02:40. Counting started then: that is t = 0 in the file.
- Multichannel scaler, 400 channels, dwell time 2.0 s a channel, no gap between
  channels. `decay.csv`: `t_s` is the start of each channel, `counts` what the
  scaler recorded in it.
- Tube dead time is 100 us: nothing to correct at these rates.
- The tube counts the room background as well. It was not measured separately
  for this run; it does not change over a run.
- One activity only: the foil is a single element, and its other activation
  product has a half-life of days.
