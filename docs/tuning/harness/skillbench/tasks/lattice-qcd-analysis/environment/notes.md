# Ensemble S16: strange-strange pseudoscalar two-point function

- N_f = 2+1 clover fermions, 16^3 x 32 (L/a = 16, T/a = 32), periodic in space;
  the meson correlator is periodic in time.
- Lattice spacing a = 0.0847(12) fm, from the gradient-flow scale.
- hbar c = 197.3269804 MeV fm.

## corr.h5

- `c2pt`, shape (1000, 32): the zero-momentum two-point function C(t) of the
  connected strange-strange pseudoscalar, one row per gauge configuration,
  columns t/a = 0 .. 31 (source at t = 0, point source and point sink).
- `trajectory`, shape (1000,): the molecular-dynamics trajectory each
  configuration was saved at. One Markov chain, every 4th trajectory, in the
  order they were generated; the thermalisation (trajectories below 2000) is
  already cut.
